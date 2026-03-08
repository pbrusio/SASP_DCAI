"""Generate a fitted StandardScaler and anomaly threshold from training data.

Reads NetFlow records from a file or Kafka, runs feature engineering,
fits a StandardScaler, and optionally recomputes the anomaly threshold
by running the existing ONNX model on the scaled validation set.

Usage:
    # From a file (Parquet or JSON-Lines of raw GoFlow2 records)
    python -m sasp.scripts.data.generate_scaler \
        --data /path/to/netflow_records.parquet \
        --scaler-output ./netflow_scaler.pkl

    # From live Kafka (sample N records from netflow-sanitized)
    python -m sasp.scripts.data.generate_scaler \
        --from-kafka --max-records 50000 \
        --scaler-output ./netflow_scaler.pkl

    # Also recompute threshold from existing ONNX model
    python -m sasp.scripts.data.generate_scaler \
        --data /path/to/records.parquet \
        --scaler-output ./netflow_scaler.pkl \
        --onnx-model /path/to/netflow_autoencoder.onnx \
        --threshold-output ./netflow_autoencoder_threshold.json
"""

import argparse
import json
import logging
import os
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _records_from_file(path: str) -> List[Dict[str, Any]]:
    """Load raw GoFlow2 records from Parquet or JSON-Lines."""
    p = Path(path)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
        return df.to_dict(orient="records")
    elif p.suffix in (".jsonl", ".json"):
        records = []
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
    else:
        raise ValueError(f"Unsupported file format: {p.suffix} (use .parquet or .jsonl)")


def _records_from_kafka(
    bootstrap_servers: str,
    topic: str,
    max_records: int,
) -> List[Dict[str, Any]]:
    """Consume up to max_records from a Kafka topic."""
    try:
        from kafka import KafkaConsumer, TopicPartition
    except ImportError:
        logger.error("kafka-python is required for --from-kafka. pip install kafka-python")
        sys.exit(1)

    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=10000,
    )

    partitions = consumer.partitions_for_topic(topic)
    if not partitions:
        logger.error("No partitions found for topic %s", topic)
        sys.exit(1)

    tps = [TopicPartition(topic, p) for p in sorted(partitions)]
    consumer.assign(tps)
    consumer.seek_to_beginning()

    records: List[Dict[str, Any]] = []
    for message in consumer:
        records.append(message.value)
        if len(records) >= max_records:
            break

    consumer.close()
    logger.info("Consumed %d records from %s", len(records), topic)
    return records


def _compute_threshold(
    onnx_path: str,
    scaled_df: pd.DataFrame,
) -> Dict[str, float]:
    """Run ONNX model on scaled features and compute p95/p99 thresholds."""
    try:
        import onnxruntime as ort
    except ImportError:
        logger.error("onnxruntime is required for --onnx-model. pip install onnxruntime")
        sys.exit(1)

    session = ort.InferenceSession(onnx_path)
    input_name = session.get_inputs()[0].name

    features = scaled_df.values.astype(np.float32)
    outputs = session.run(None, {input_name: features})
    reconstructed = outputs[0]

    mse = np.mean((features - reconstructed) ** 2, axis=1)
    threshold_95 = float(np.percentile(mse, 95))
    threshold_99 = float(np.percentile(mse, 99))

    logger.info(
        "MSE stats — mean: %.6f, std: %.6f, p95: %.6f, p99: %.6f",
        mse.mean(), mse.std(), threshold_95, threshold_99,
    )

    return {
        "threshold_95": threshold_95,
        "threshold_99": threshold_99,
        "mse_mean": float(mse.mean()),
        "mse_std": float(mse.std()),
        "n_samples": len(mse),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a fitted StandardScaler (and optional threshold) for the NetFlow autoencoder."
    )
    # Data source — file or Kafka
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--data",
        help="Path to raw GoFlow2 records (Parquet or JSON-Lines).",
    )
    source.add_argument(
        "--from-kafka",
        action="store_true",
        help="Consume records from Kafka instead of a file.",
    )

    # Kafka options
    parser.add_argument(
        "--topic",
        default="netflow-sanitized",
        help="Kafka topic (default: netflow-sanitized).",
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092"),
        help="Kafka bootstrap servers.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=50000,
        help="Max records to consume from Kafka (default: 50000).",
    )

    # Outputs
    parser.add_argument(
        "--scaler-output",
        required=True,
        help="Path to save the fitted StandardScaler pickle.",
    )
    parser.add_argument(
        "--onnx-model",
        default=None,
        help="Path to existing ONNX model (to recompute threshold).",
    )
    parser.add_argument(
        "--threshold-output",
        default=None,
        help="Path to save threshold JSON (requires --onnx-model).",
    )

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = build_parser().parse_args()

    # --- Load records ---
    if args.from_kafka:
        records = _records_from_kafka(
            args.bootstrap_servers, args.topic, args.max_records,
        )
    else:
        records = _records_from_file(args.data)

    if not records:
        logger.error("No records loaded — cannot fit scaler.")
        sys.exit(1)

    logger.info("Loaded %d records", len(records))

    # --- Feature engineering ---
    from sasp.models.training.feature_engineering import NetFlowFeatureExtractor

    extractor = NetFlowFeatureExtractor()
    feature_df = extractor.transform(records)
    logger.info("Feature matrix shape: %s", feature_df.shape)

    # --- Fit scaler ---
    extractor.fit(feature_df)
    scaler_path = Path(args.scaler_output)
    scaler_path.parent.mkdir(parents=True, exist_ok=True)

    # Save as pickle (for local use / sklearn-compatible tooling)
    extractor.save_scaler(str(scaler_path))

    # Also save as JSON (portable — no numpy/sklearn version dependency)
    scaler = extractor._scaler
    json_path = scaler_path.with_suffix(".json")
    scaler_json = {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "var": scaler.var_.tolist(),
        "n_features_in": int(scaler.n_features_in_),
        "n_samples_seen": int(scaler.n_samples_seen_),
        "feature_names": NetFlowFeatureExtractor.ALL_FEATURE_COLS,
    }
    with open(json_path, "w") as f:
        json.dump(scaler_json, f, indent=2)
    logger.info("Saved scaler JSON to %s", json_path)

    # Print scaler statistics for sanity checking
    print("\nScaler statistics (mean / std) per feature:")
    for i, col in enumerate(NetFlowFeatureExtractor.ALL_FEATURE_COLS):
        print(f"  {col:30s}  mean={scaler.mean_[i]:12.4f}  std={scaler.scale_[i]:12.4f}")

    # --- Optional: recompute threshold ---
    if args.onnx_model:
        scaled_df = extractor.scale(feature_df)
        meta = _compute_threshold(args.onnx_model, scaled_df)

        out_path = args.threshold_output
        if out_path is None:
            out_path = str(scaler_path.parent / "netflow_autoencoder_threshold.json")

        with open(out_path, "w") as f:
            json.dump(meta, f, indent=2)
        logger.info("Saved threshold metadata to %s", out_path)

        print(f"\nThreshold (p95): {meta['threshold_95']:.6f}")
        print(f"Threshold (p99): {meta['threshold_99']:.6f}")

    logger.info("Done.")


if __name__ == "__main__":
    main()
