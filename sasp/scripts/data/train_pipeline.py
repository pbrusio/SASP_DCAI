"""End-to-end training pipeline for the SASP NetFlow autoencoder.

Wraps the fragmented workflow (export → features → scaler → retrain/threshold)
into a single command.

Usage:
    # Quick path: generate scaler + threshold from existing model (no retraining)
    python -m sasp.scripts.data.train_pipeline \
        --from-kafka --topic netflow-sanitized \
        --bootstrap-servers <S2_IP>:9092 \
        --max-records 100000 \
        --onnx-model /path/to/netflow_autoencoder.onnx \
        --output-dir ./models/netflow-anomaly-v2

    # Full retrain: generate scaler + train new autoencoder + threshold
    python -m sasp.scripts.data.train_pipeline \
        --from-kafka --topic netflow-sanitized \
        --bootstrap-servers <S2_IP>:9092 \
        --max-records 100000 \
        --retrain \
        --output-dir ./models/netflow-anomaly-v2

    # From file instead of Kafka
    python -m sasp.scripts.data.train_pipeline \
        --data /path/to/netflow_records.parquet \
        --onnx-model /path/to/netflow_autoencoder.onnx \
        --output-dir ./models/netflow-anomaly-v2
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading (reuses generate_scaler helpers)
# ---------------------------------------------------------------------------

def _records_from_file(path: str) -> List[Dict[str, Any]]:
    """Load raw GoFlow2 records from Parquet or JSON-Lines."""
    p = Path(path)
    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
        return df.to_dict(orient="records")
    elif p.suffix in (".jsonl", ".json"):
        records: List[Dict[str, Any]] = []
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

    logger.info(
        "Connecting to Kafka %s topic=%s (max %d records)...",
        bootstrap_servers, topic, max_records,
    )
    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=15000,
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
        if len(records) % 10000 == 0:
            logger.info("  consumed %d records...", len(records))

    consumer.close()
    logger.info("Consumed %d records from %s", len(records), topic)
    return records


# ---------------------------------------------------------------------------
# Threshold computation (from existing ONNX model)
# ---------------------------------------------------------------------------

def _compute_threshold_from_onnx(
    onnx_path: str,
    scaled_df: pd.DataFrame,
) -> Dict[str, float]:
    """Run ONNX model on scaled features and compute p95/p99 thresholds."""
    try:
        import onnxruntime as ort
    except ImportError:
        logger.error("onnxruntime is required. pip install onnxruntime")
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "SASP NetFlow training pipeline: "
            "export → features → scaler → [retrain] → threshold"
        ),
    )

    # Data source
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data", help="Path to raw GoFlow2 records (Parquet or JSONL).")
    source.add_argument("--from-kafka", action="store_true", help="Consume records from Kafka.")

    # Kafka options
    parser.add_argument("--topic", default="netflow-sanitized", help="Kafka topic (default: netflow-sanitized).")
    parser.add_argument(
        "--bootstrap-servers",
        default=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092"),
        help="Kafka bootstrap servers.",
    )
    parser.add_argument("--max-records", type=int, default=100000, help="Max records from Kafka (default: 100000).")

    # Output
    parser.add_argument("--output-dir", required=True, help="Directory for all output artifacts.")

    # Mode
    parser.add_argument(
        "--retrain", action="store_true",
        help="Retrain the autoencoder. Without this, only generates scaler + threshold.",
    )
    parser.add_argument(
        "--onnx-model", default=None,
        help="Path to existing ONNX model (required when NOT using --retrain).",
    )

    # Training hyperparameters (only used with --retrain)
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs (default: 100).")
    parser.add_argument("--batch-size", type=int, default=256, help="Batch size (default: 256).")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="Learning rate (default: 1e-3).")

    # Optional: save intermediate data
    parser.add_argument(
        "--save-features", action="store_true",
        help="Save raw and scaled feature CSVs to output-dir.",
    )

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate args
    if not args.retrain and not args.onnx_model:
        logger.error("Either --retrain or --onnx-model is required.")
        logger.error("  --onnx-model: generate scaler + threshold from existing model (quick path)")
        logger.error("  --retrain:    train a new autoencoder from scratch")
        sys.exit(1)

    # ---------------------------------------------------------------
    # Step 1: Load raw records
    # ---------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("STEP 1: Loading raw records")
    logger.info("=" * 60)

    if args.from_kafka:
        records = _records_from_kafka(args.bootstrap_servers, args.topic, args.max_records)
    else:
        records = _records_from_file(args.data)

    if not records:
        logger.error("No records loaded — cannot proceed.")
        sys.exit(1)

    logger.info("Loaded %d records", len(records))

    # ---------------------------------------------------------------
    # Step 2: Feature extraction
    # ---------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("STEP 2: Extracting 15 features")
    logger.info("=" * 60)

    from sasp.models.training.feature_engineering import NetFlowFeatureExtractor

    extractor = NetFlowFeatureExtractor()
    feature_df = extractor.transform(records)
    logger.info("Feature matrix: %s", feature_df.shape)

    if args.save_features:
        raw_path = output_dir / "features_raw.csv"
        feature_df.to_csv(raw_path, index=False)
        logger.info("Saved raw features to %s", raw_path)

    # ---------------------------------------------------------------
    # Step 3: Fit scaler and save
    # ---------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("STEP 3: Fitting StandardScaler")
    logger.info("=" * 60)

    extractor.fit(feature_df)
    scaled_df = extractor.scale(feature_df)

    # Save scaler as pickle
    scaler_pkl_path = output_dir / "scaler.pkl"
    extractor.save_scaler(str(scaler_pkl_path))

    # Save scaler as JSON (portable — no numpy/sklearn version dependency)
    scaler = extractor._scaler
    scaler_json = {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "var": scaler.var_.tolist(),
        "n_features_in": int(scaler.n_features_in_),
        "n_samples_seen": int(scaler.n_samples_seen_),
        "feature_names": NetFlowFeatureExtractor.ALL_FEATURE_COLS,
    }
    scaler_json_path = output_dir / "scaler.json"
    with open(scaler_json_path, "w") as f:
        json.dump(scaler_json, f, indent=2)
    logger.info("Saved scaler JSON to %s", scaler_json_path)

    # Print scaler statistics
    print("\nScaler statistics (mean / std) per feature:")
    for i, col in enumerate(NetFlowFeatureExtractor.ALL_FEATURE_COLS):
        print(f"  {col:30s}  mean={scaler.mean_[i]:12.4f}  std={scaler.scale_[i]:12.4f}")

    if args.save_features:
        scaled_path = output_dir / "features_scaled.csv"
        scaled_df.to_csv(scaled_path, index=False)
        logger.info("Saved scaled features to %s", scaled_path)

    # ---------------------------------------------------------------
    # Step 4/5: Either retrain or compute threshold from existing ONNX
    # ---------------------------------------------------------------
    if args.retrain:
        logger.info("=" * 60)
        logger.info("STEP 4: Training autoencoder (--retrain)")
        logger.info("=" * 60)

        from sasp.models.training.netflow_autoencoder import (
            save_model,
            train_autoencoder,
        )

        model, metadata = train_autoencoder(
            scaled_df,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
        )
        save_model(model, metadata, str(output_dir))
        threshold_95 = metadata["threshold_95"]
        threshold_99 = metadata["threshold_99"]

        # Also save threshold as standalone file (matching Morpheus expected name)
        threshold_path = output_dir / "threshold.json"
        threshold_data = {
            "threshold_95": threshold_95,
            "threshold_99": threshold_99,
            "mse_mean": metadata.get("best_val_loss", 0.0),
            "n_samples": len(scaled_df),
        }
        with open(threshold_path, "w") as f:
            json.dump(threshold_data, f, indent=2)
        logger.info("Saved threshold.json to %s", threshold_path)

    else:
        logger.info("=" * 60)
        logger.info("STEP 4: Computing threshold from existing ONNX model")
        logger.info("=" * 60)

        onnx_path = args.onnx_model
        if not Path(onnx_path).exists():
            logger.error("ONNX model not found: %s", onnx_path)
            sys.exit(1)

        threshold_data = _compute_threshold_from_onnx(onnx_path, scaled_df)
        threshold_95 = threshold_data["threshold_95"]
        threshold_99 = threshold_data["threshold_99"]

        # Save as threshold.json (standalone)
        threshold_path = output_dir / "threshold.json"
        with open(threshold_path, "w") as f:
            json.dump(threshold_data, f, indent=2)
        logger.info("Saved threshold.json to %s", threshold_path)

        # Also save in the autoencoder-style metadata format
        meta_path = output_dir / "netflow_autoencoder_threshold.json"
        with open(meta_path, "w") as f:
            json.dump(threshold_data, f, indent=2)
        logger.info("Saved threshold metadata to %s", meta_path)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Output directory:  {output_dir}")
    print(f"  Records processed: {len(records)}")
    print(f"  Features:          {feature_df.shape[1]}")
    print(f"  Scaler:            {scaler_json_path}")
    print(f"  Threshold (p95):   {threshold_95:.6f}")
    print(f"  Threshold (p99):   {threshold_99:.6f}")
    if args.retrain:
        print(f"  ONNX model:        {output_dir / 'netflow_autoencoder.onnx'}")
    print()
    print("Next steps:")
    print(f"  1. scp {scaler_json_path} <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/netflow-anomaly/")
    print(f"  2. scp {output_dir / 'threshold.json'} <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/netflow-anomaly/")
    if args.retrain:
        print(f"  3. scp {output_dir / 'netflow_autoencoder.onnx'} <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/netflow-anomaly/1/model.onnx")
    print("  Then: ssh <SERVER_USER>@<S1_IP> 'docker restart sasp-morpheus'")
    print()

    logger.info("Done.")


if __name__ == "__main__":
    main()
