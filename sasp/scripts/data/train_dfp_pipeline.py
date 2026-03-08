"""End-to-end training pipeline for the SASP ISE DFP autoencoder.

Wraps the DFP workflow (load ISE events -> features -> scaler -> train -> threshold)
into a single command.

Usage:
    # Generate synthetic training data first:
    #   python -m sasp.scripts.testing.ise_auth_generator \
    #       --dry-run --duration-days 30 --seed 42 \
    #       --output ./data/ise_synthetic.jsonl
    #
    # Then train from that file:
    #   python -m sasp.scripts.data.train_dfp_pipeline \
    #       --data ./data/ise_synthetic.jsonl --retrain \
    #       --output-dir ./models/ise-dfp-v1

    # Full retrain from Kafka
    python -m sasp.scripts.data.train_dfp_pipeline \
        --from-kafka --topic ise-sanitized \
        --bootstrap-servers <S2_IP>:9092 \
        --max-records 100000 \
        --retrain \
        --output-dir ./models/ise-dfp-v1

    # Threshold only from existing ONNX
    python -m sasp.scripts.data.train_dfp_pipeline \
        --from-kafka --topic ise-sanitized \
        --onnx-model /path/to/ise_dfp.onnx \
        --output-dir ./models/ise-dfp-v1

    # From file
    python -m sasp.scripts.data.train_dfp_pipeline \
        --data /path/to/ise_events.jsonl \
        --retrain \
        --output-dir ./models/ise-dfp-v1
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ISE DFP Autoencoder (14 -> 32 -> 16 -> 8 -> 16 -> 32 -> 14)
# ---------------------------------------------------------------------------
ISE_DFP_INPUT_DIM = 14


class ISEDFPAutoEncoder(nn.Module):
    """Symmetric autoencoder for ISE DFP feature reconstruction.

    Architecture:
        Encoder: 14 -> 32 -> 16 -> 8
        Decoder: 8 -> 16 -> 32 -> 14
    """

    def __init__(self, input_dim: int = ISE_DFP_INPUT_DIM) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.BatchNorm1d(16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.BatchNorm1d(8),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(8, 16),
            nn.BatchNorm1d(16),
            nn.ReLU(),
            nn.Linear(16, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Linear(32, input_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.encoder(x)
        return self.decoder(z)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _records_from_file(path: str) -> List[Dict[str, Any]]:
    """Load ISE events from JSONL or JSON file."""
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
# Training helpers
# ---------------------------------------------------------------------------

def _split_data(
    df: pd.DataFrame, train_frac: float = 0.8, val_frac: float = 0.1
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split DataFrame into train / val / test (80/10/10)."""
    n = len(df)
    idx = np.random.permutation(n)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return (
        df.iloc[idx[:train_end]].reset_index(drop=True),
        df.iloc[idx[train_end:val_end]].reset_index(drop=True),
        df.iloc[idx[val_end:]].reset_index(drop=True),
    )


def _make_loader(df: pd.DataFrame, batch_size: int, shuffle: bool = True) -> DataLoader:
    tensor = torch.tensor(df.values, dtype=torch.float32)
    return DataLoader(TensorDataset(tensor), batch_size=batch_size, shuffle=shuffle)


def _reconstruction_errors(
    model: ISEDFPAutoEncoder, df: pd.DataFrame, device: str
) -> np.ndarray:
    """Compute per-sample MSE reconstruction errors."""
    model.eval()
    tensor = torch.tensor(df.values, dtype=torch.float32).to(device)
    with torch.no_grad():
        recon = model(tensor)
    mse = ((tensor - recon) ** 2).mean(dim=1).cpu().numpy()
    return mse


def train_dfp_autoencoder(
    df: pd.DataFrame,
    epochs: int = 100,
    batch_size: int = 256,
    learning_rate: float = 1e-3,
    patience: int = 10,
    device: str | None = None,
) -> Tuple[ISEDFPAutoEncoder, Dict[str, float]]:
    """Train the ISE DFP autoencoder and return model + threshold metadata.

    Parameters
    ----------
    df : pd.DataFrame
        Scaled feature matrix (14 columns).
    epochs : int
        Maximum training epochs.
    batch_size : int
        Mini-batch size.
    learning_rate : float
        Initial learning rate for Adam.
    patience : int
        Early stopping patience on validation loss.
    device : str or None
        Torch device string. Auto-detects if None.

    Returns
    -------
    model : ISEDFPAutoEncoder
        Trained model (eval mode).
    metadata : dict
        Contains threshold_95, threshold_99, best_val_loss, stopped_epoch.
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    input_dim = df.shape[1]
    train_df, val_df, test_df = _split_data(df)
    logger.info(
        "Split sizes -- train: %d, val: %d, test: %d",
        len(train_df), len(val_df), len(test_df),
    )

    train_loader = _make_loader(train_df, batch_size)
    val_loader = _make_loader(val_df, batch_size, shuffle=False)

    model = ISEDFPAutoEncoder(input_dim=input_dim).to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5
    )

    best_val_loss = float("inf")
    epochs_no_improve = 0
    stopped_epoch = epochs
    best_state = model.state_dict()

    for epoch in range(1, epochs + 1):
        # --- train ---
        model.train()
        train_loss = 0.0
        for (batch,) in train_loader:
            batch = batch.to(device)
            recon = model(batch)
            loss = criterion(recon, batch)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(batch)
        train_loss /= len(train_df)

        # --- validate ---
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for (batch,) in val_loader:
                batch = batch.to(device)
                recon = model(batch)
                loss = criterion(recon, batch)
                val_loss += loss.item() * len(batch)
        val_loss /= len(val_df)

        scheduler.step(val_loss)

        if epoch % 10 == 0 or epoch == 1:
            logger.info(
                "Epoch %d/%d  train_loss=%.6f  val_loss=%.6f  lr=%.2e",
                epoch, epochs, train_loss, val_loss,
                optimizer.param_groups[0]["lr"],
            )

        # --- early stopping ---
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            epochs_no_improve = 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience:
                stopped_epoch = epoch
                logger.info("Early stopping at epoch %d", epoch)
                break

    # Restore best weights
    model.load_state_dict(best_state)
    model.eval()

    # --- compute thresholds on validation set ---
    val_errors = _reconstruction_errors(model, val_df, device)
    threshold_95 = float(np.percentile(val_errors, 95))
    threshold_99 = float(np.percentile(val_errors, 99))
    logger.info("Thresholds -- p95: %.6f, p99: %.6f", threshold_95, threshold_99)

    metadata = {
        "input_dim": input_dim,
        "threshold_95": threshold_95,
        "threshold_99": threshold_99,
        "best_val_loss": float(best_val_loss),
        "stopped_epoch": stopped_epoch,
    }
    return model, metadata


def save_dfp_model(
    model: ISEDFPAutoEncoder,
    metadata: Dict[str, float],
    output_dir: str,
) -> None:
    """Save DFP model state_dict, threshold JSON, and ONNX export."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # PyTorch state dict
    pt_path = out / "ise_dfp.pt"
    torch.save(model.state_dict(), pt_path)
    logger.info("Saved state dict to %s", pt_path)

    # Threshold metadata
    meta_path = out / "ise_dfp_threshold.json"
    with open(meta_path, "w") as fh:
        json.dump(metadata, fh, indent=2)
    logger.info("Saved thresholds to %s", meta_path)

    # ONNX export with dynamic batch
    input_dim = metadata["input_dim"]
    model.cpu().eval()
    dummy = torch.randn(1, input_dim)
    onnx_path = out / "ise_dfp.onnx"
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=17,
    )
    logger.info("Exported ONNX to %s", onnx_path)


# ---------------------------------------------------------------------------
# Threshold from existing ONNX
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
        "MSE stats -- mean: %.6f, std: %.6f, p95: %.6f, p99: %.6f",
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
            "SASP ISE DFP training pipeline: "
            "load ISE events -> features -> scaler -> [retrain] -> threshold"
        ),
    )

    # Data source
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data", help="Path to ISE events (Parquet or JSONL).")
    source.add_argument("--from-kafka", action="store_true", help="Consume records from Kafka.")

    # Kafka options
    parser.add_argument("--topic", default="ise-sanitized", help="Kafka topic (default: ise-sanitized).")
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

    # Training hyperparameters
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

    if not args.retrain and not args.onnx_model:
        logger.error("Either --retrain or --onnx-model is required.")
        sys.exit(1)

    # ---------------------------------------------------------------
    # Step 1: Load raw ISE events
    # ---------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("STEP 1: Loading ISE events")
    logger.info("=" * 60)

    if args.from_kafka:
        records = _records_from_kafka(args.bootstrap_servers, args.topic, args.max_records)
    else:
        records = _records_from_file(args.data)

    if not records:
        logger.error("No records loaded -- cannot proceed.")
        sys.exit(1)

    logger.info("Loaded %d records", len(records))

    # ---------------------------------------------------------------
    # Step 2: Filter anomalies (train on normals only)
    # ---------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("STEP 2: Filtering anomalies")
    logger.info("=" * 60)

    normal_records = [r for r in records if "_anomaly_label" not in r]
    logger.info(
        "Filtered %d anomalies, %d normal records remain",
        len(records) - len(normal_records),
        len(normal_records),
    )

    if not normal_records:
        logger.error("No normal records after filtering -- cannot proceed.")
        sys.exit(1)

    # ---------------------------------------------------------------
    # Step 3: Sort by (username, timestamp) and extract features
    # ---------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("STEP 3: Extracting 14 DFP features")
    logger.info("=" * 60)

    normal_records.sort(key=lambda r: (r.get("username", ""), r.get("timestamp", "")))

    from sasp.models.training.ise_dfp_features import ISEDFPFeatureExtractor

    extractor = ISEDFPFeatureExtractor()
    extractor.fit(normal_records)
    feature_df = extractor.transform_batch(normal_records)
    logger.info("Feature matrix: %s", feature_df.shape)

    if args.save_features:
        raw_path = output_dir / "features_raw.csv"
        feature_df.to_csv(raw_path, index=False)
        logger.info("Saved raw features to %s", raw_path)

    # ---------------------------------------------------------------
    # Step 4: Fit scaler and save
    # ---------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("STEP 4: Fitting StandardScaler")
    logger.info("=" * 60)

    extractor.fit_scaler(feature_df)
    scaled_df = extractor.scale(feature_df)

    scaler_path = output_dir / "scaler.json"
    extractor.save_scaler(str(scaler_path))

    # Print scaler statistics
    scaler = extractor._scaler
    print("\nScaler statistics (mean / std) per feature:")
    for i, col in enumerate(ISEDFPFeatureExtractor.FEATURE_COLS):
        print(f"  {col:30s}  mean={scaler.mean_[i]:12.4f}  std={scaler.scale_[i]:12.4f}")

    if args.save_features:
        scaled_path = output_dir / "features_scaled.csv"
        scaled_df.to_csv(scaled_path, index=False)
        logger.info("Saved scaled features to %s", scaled_path)

    # ---------------------------------------------------------------
    # Step 5: Retrain or compute threshold from existing ONNX
    # ---------------------------------------------------------------
    if args.retrain:
        logger.info("=" * 60)
        logger.info("STEP 5: Training ISE DFP autoencoder (--retrain)")
        logger.info("=" * 60)

        model, metadata = train_dfp_autoencoder(
            scaled_df,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
        )
        save_dfp_model(model, metadata, str(output_dir))
        threshold_95 = metadata["threshold_95"]
        threshold_99 = metadata["threshold_99"]

        # Standalone threshold file
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
        logger.info("STEP 5: Computing threshold from existing ONNX model")
        logger.info("=" * 60)

        onnx_path = args.onnx_model
        if not Path(onnx_path).exists():
            logger.error("ONNX model not found: %s", onnx_path)
            sys.exit(1)

        threshold_data = _compute_threshold_from_onnx(onnx_path, scaled_df)
        threshold_95 = threshold_data["threshold_95"]
        threshold_99 = threshold_data["threshold_99"]

        threshold_path = output_dir / "threshold.json"
        with open(threshold_path, "w") as f:
            json.dump(threshold_data, f, indent=2)
        logger.info("Saved threshold.json to %s", threshold_path)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("DFP PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Output directory:  {output_dir}")
    print(f"  Records loaded:    {len(records)}")
    print(f"  Normal records:    {len(normal_records)}")
    print(f"  Features:          {feature_df.shape[1]}")
    print(f"  Scaler:            {scaler_path}")
    print(f"  Threshold (p95):   {threshold_95:.6f}")
    print(f"  Threshold (p99):   {threshold_99:.6f}")
    if args.retrain:
        print(f"  ONNX model:        {output_dir / 'ise_dfp.onnx'}")
    print()
    print("Next steps:")
    print(f"  1. scp {scaler_path} <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/ise-dfp/")
    print(f"  2. scp {output_dir / 'threshold.json'} <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/ise-dfp/")
    if args.retrain:
        print(f"  3. scp {output_dir / 'ise_dfp.onnx'} <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/ise-dfp/1/model.onnx")
    print()

    logger.info("Done.")


if __name__ == "__main__":
    main()
