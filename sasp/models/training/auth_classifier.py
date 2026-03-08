"""SASP Auth Risk Classifier — classifies ISE authentication events as normal, suspicious, or malicious."""

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature schema
# ---------------------------------------------------------------------------
FEATURE_COLS: List[str] = [
    "hour_of_day",
    "day_of_week",
    "auth_result_code",
    "consecutive_failures",
    "unique_nas_count_24h",
    "location_change_flag",
    "new_device_flag",
]

LABEL_COL = "risk_label"

NUM_FEATURES = len(FEATURE_COLS)  # 7
NUM_CLASSES = 3

LABEL_MAP: Dict[int, str] = {
    0: "normal",
    1: "suspicious",
    2: "malicious",
}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class AuthClassifier(nn.Module):
    """Feed-forward classifier for ISE auth risk scoring.

    Architecture: 7 -> 128 -> 64 -> 3 with ReLU and dropout.
    """

    def __init__(
        self,
        input_dim: int = NUM_FEATURES,
        num_classes: int = NUM_CLASSES,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ---------------------------------------------------------------------------
# Class weight computation
# ---------------------------------------------------------------------------
def _compute_class_weights(labels: np.ndarray, num_classes: int = NUM_CLASSES) -> torch.Tensor:
    """Inverse-frequency class weights for imbalanced data."""
    counts = np.bincount(labels.astype(int), minlength=num_classes).astype(float)
    counts = np.maximum(counts, 1.0)  # avoid div-by-zero
    weights = len(labels) / (num_classes * counts)
    return torch.tensor(weights, dtype=torch.float32)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train_classifier(
    df: pd.DataFrame,
    epochs: int = 60,
    batch_size: int = 128,
    learning_rate: float = 1e-3,
    patience: int = 10,
    device: Optional[str] = None,
) -> Tuple[AuthClassifier, StandardScaler, Dict]:
    """Train the auth risk classifier.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain FEATURE_COLS and LABEL_COL columns.

    Returns
    -------
    model : AuthClassifier
    scaler : StandardScaler (fitted)
    metadata : dict with classification_report, stopped_epoch, etc.
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    X = df[FEATURE_COLS].values.astype(np.float32)
    y = df[LABEL_COL].values.astype(int)

    # Stratified split: 80/10/10
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, stratify=y_temp, random_state=42
    )
    logger.info(
        "Split sizes — train: %d, val: %d, test: %d",
        len(X_train), len(X_val), len(X_test),
    )

    # Scale features
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test)

    # Data loaders
    def _loader(X: np.ndarray, y: np.ndarray, shuffle: bool) -> DataLoader:
        return DataLoader(
            TensorDataset(
                torch.tensor(X, dtype=torch.float32),
                torch.tensor(y, dtype=torch.long),
            ),
            batch_size=batch_size,
            shuffle=shuffle,
        )

    train_loader = _loader(X_train, y_train, shuffle=True)
    val_loader = _loader(X_val, y_val, shuffle=False)

    # Model, loss, optimizer
    class_weights = _compute_class_weights(y_train).to(device)
    model = AuthClassifier().to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5
    )

    best_val_loss = float("inf")
    epochs_no_improve = 0
    stopped_epoch = epochs
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(X_batch)
        train_loss /= len(X_train)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                loss = criterion(model(X_batch), y_batch)
                val_loss += loss.item() * len(X_batch)
        val_loss /= len(X_val)

        scheduler.step(val_loss)

        if epoch % 10 == 0 or epoch == 1:
            logger.info(
                "Epoch %d/%d  train_loss=%.4f  val_loss=%.4f  lr=%.2e",
                epoch, epochs, train_loss, val_loss,
                optimizer.param_groups[0]["lr"],
            )

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

    model.load_state_dict(best_state)
    model.eval()

    # --- test set evaluation ---
    X_test_t = torch.tensor(X_test, dtype=torch.float32).to(device)
    with torch.no_grad():
        preds = model(X_test_t).argmax(dim=1).cpu().numpy()
    report = classification_report(
        y_test, preds, target_names=list(LABEL_MAP.values()), output_dict=True
    )
    report_str = classification_report(
        y_test, preds, target_names=list(LABEL_MAP.values())
    )
    logger.info("Test classification report:\n%s", report_str)

    metadata = {
        "input_dim": NUM_FEATURES,
        "num_classes": NUM_CLASSES,
        "label_map": LABEL_MAP,
        "stopped_epoch": stopped_epoch,
        "best_val_loss": float(best_val_loss),
        "test_report": report,
    }
    return model, scaler, metadata


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def save_model(
    model: AuthClassifier,
    scaler: StandardScaler,
    metadata: Dict,
    output_dir: str,
) -> None:
    """Save model artifacts: state_dict, ONNX, scaler, label mapping."""
    import pickle

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # State dict
    pt_path = out / "auth_classifier.pt"
    torch.save(model.state_dict(), pt_path)
    logger.info("Saved state dict to %s", pt_path)

    # Scaler
    scaler_path = out / "auth_classifier_scaler.pkl"
    with open(scaler_path, "wb") as fh:
        pickle.dump(scaler, fh)
    logger.info("Saved scaler to %s", scaler_path)

    # Label mapping + metadata
    meta_path = out / "auth_classifier_meta.json"
    serializable = {
        k: v for k, v in metadata.items() if k != "test_report"
    }
    serializable["label_map"] = {str(k): v for k, v in LABEL_MAP.items()}
    with open(meta_path, "w") as fh:
        json.dump(serializable, fh, indent=2)
    logger.info("Saved metadata to %s", meta_path)

    # Test report
    report_path = out / "auth_classifier_test_report.json"
    with open(report_path, "w") as fh:
        json.dump(metadata.get("test_report", {}), fh, indent=2)
    logger.info("Saved test report to %s", report_path)

    # ONNX export (CPU for device-agnostic export)
    model.cpu().eval()
    dummy = torch.randn(1, NUM_FEATURES)
    onnx_path = out / "auth_classifier.onnx"
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
        description="Train SASP Auth Risk Classifier"
    )
    parser.add_argument(
        "--data", required=True,
        help="Path to CSV/Parquet with feature columns and risk_label",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Directory for model artifacts",
    )
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=128)
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

    logger.info("Loaded %d samples", len(df))

    model, scaler, metadata = train_classifier(
        df,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    )
    save_model(model, scaler, metadata, args.output_dir)
    logger.info("Done. Artifacts in %s", args.output_dir)


if __name__ == "__main__":
    main()
