# CALIBRATION STATUS: Uncalibrated
#
# The deployed netflow-anomaly Triton model was trained on synthetic
# NetFlow data and has not been retrained against real Cat9200L traffic.
# Reconstruction error thresholds are calibrated to the synthetic
# distribution. In the current state, most or all real NetFlow records
# will exceed the anomaly threshold.
#
# To retrain against real traffic:
#   python -m sasp.scripts.data.train_pipeline \
#       --from-kafka --topic netflow-sanitized \
#       --bootstrap-servers <S2_IP>:9092 \
#       --retrain \
#       --output-dir ./models/netflow-anomaly-v2

"""SASP NetFlow Autoencoder — reconstruction-based anomaly detector for network traffic."""

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

logger = logging.getLogger(__name__)

# Feature count from NetFlowFeatureExtractor.ALL_FEATURE_COLS
INPUT_DIM = 15


class AutoEncoder(nn.Module):
    """Symmetric autoencoder for NetFlow feature reconstruction.

    Architecture:
        Encoder: input_dim -> 64 -> 32 -> 16
        Decoder: 16 -> 32 -> 64 -> input_dim
    """

    def __init__(self, input_dim: int = INPUT_DIM) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.BatchNorm1d(16),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(16, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Linear(32, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Linear(64, input_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.encoder(x)
        return self.decoder(z)


# ---------------------------------------------------------------------------
# Data helpers
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


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train_autoencoder(
    df: pd.DataFrame,
    epochs: int = 100,
    batch_size: int = 256,
    learning_rate: float = 1e-3,
    patience: int = 10,
    device: Optional[str] = None,
) -> Tuple[AutoEncoder, Dict[str, float]]:
    """Train the autoencoder and return model + threshold metadata.

    Parameters
    ----------
    df : pd.DataFrame
        Scaled feature matrix (all columns used as features).
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
    model : AutoEncoder
        Trained model (eval mode).
    metadata : dict
        Contains threshold_95, threshold_99, best_val_loss, stopped_epoch.
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    input_dim = df.shape[1]
    train_df, val_df, test_df = _split_data(df)
    logger.info(
        "Split sizes — train: %d, val: %d, test: %d",
        len(train_df), len(val_df), len(test_df),
    )

    train_loader = _make_loader(train_df, batch_size)
    val_loader = _make_loader(val_df, batch_size, shuffle=False)

    model = AutoEncoder(input_dim=input_dim).to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5
    )

    best_val_loss = float("inf")
    epochs_no_improve = 0
    stopped_epoch = epochs

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
    logger.info("Thresholds — p95: %.6f, p99: %.6f", threshold_95, threshold_99)

    metadata = {
        "input_dim": input_dim,
        "threshold_95": threshold_95,
        "threshold_99": threshold_99,
        "best_val_loss": float(best_val_loss),
        "stopped_epoch": stopped_epoch,
    }
    return model, metadata


def _reconstruction_errors(
    model: AutoEncoder, df: pd.DataFrame, device: str
) -> np.ndarray:
    """Compute per-sample MSE reconstruction errors."""
    model.eval()
    tensor = torch.tensor(df.values, dtype=torch.float32).to(device)
    with torch.no_grad():
        recon = model(tensor)
    mse = ((tensor - recon) ** 2).mean(dim=1).cpu().numpy()
    return mse


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def save_model(
    model: AutoEncoder,
    metadata: Dict[str, float],
    output_dir: str,
) -> None:
    """Save model state_dict, threshold JSON, and ONNX export."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # PyTorch state dict
    pt_path = out / "netflow_autoencoder.pt"
    torch.save(model.state_dict(), pt_path)
    logger.info("Saved state dict to %s", pt_path)

    # Threshold metadata
    meta_path = out / "netflow_autoencoder_threshold.json"
    with open(meta_path, "w") as fh:
        json.dump(metadata, fh, indent=2)
    logger.info("Saved thresholds to %s", meta_path)

    # ONNX export with dynamic batch (CPU for device-agnostic export)
    input_dim = metadata["input_dim"]
    model.cpu().eval()
    dummy = torch.randn(1, input_dim)
    onnx_path = out / "netflow_autoencoder.onnx"
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
# CLI
# ---------------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train SASP NetFlow Autoencoder for anomaly detection"
    )
    parser.add_argument(
        "--data", required=True,
        help="Path to scaled feature CSV/Parquet produced by feature_engineering.py",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Directory for model artifacts (.pt, .json, .onnx)",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    data_path = Path(args.data)
    if data_path.suffix == ".parquet":
        df = pd.read_parquet(data_path)
    else:
        df = pd.read_csv(data_path)

    logger.info("Loaded %d samples with %d features", len(df), df.shape[1])

    model, metadata = train_autoencoder(
        df,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    )
    save_model(model, metadata, args.output_dir)
    logger.info("Done. Artifacts in %s", args.output_dir)


if __name__ == "__main__":
    main()
