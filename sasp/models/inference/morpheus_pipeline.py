#!/usr/bin/env python3
"""
SASP Morpheus Pipeline — NetFlow Anomaly Detection

Reads feature-enriched NetFlow records from Kafka (netflow-sanitized),
runs Triton autoencoder inference, computes reconstruction error,
and publishes anomaly detections to Kafka (morpheus-detections).

Usage (inside Morpheus container):
    python3 /workspace/morpheus_pipeline.py

Environment variables:
    KAFKA_BOOTSTRAP_SERVERS  — Kafka broker (default: <S2_IP>:9092)
    TRITON_URL               — Triton HTTP endpoint (default: localhost:8000)
    ANOMALY_THRESHOLD        — MSE threshold for anomaly (default: 0.05)
    SCALER_PATH              — Path to fitted StandardScaler pickle (optional)
    THRESHOLD_PATH           — Path to threshold JSON from training (optional)
"""

import json as _json
import logging
import os
import time
import uuid

import numpy as np
import pandas as pd
import requests

from morpheus.config import Config, ExecutionMode, PipelineModes
from morpheus.messages import MessageMeta
from morpheus.messages.control_message import ControlMessage
from morpheus.pipeline.linear_pipeline import LinearPipeline
from morpheus.pipeline.stage_decorator import stage
from morpheus.stages.general.monitor_stage import MonitorStage
from morpheus.stages.input.kafka_source_stage import KafkaSourceStage
from morpheus.stages.output.write_to_kafka_stage import WriteToKafkaStage
from morpheus.stages.preprocess.deserialize_stage import DeserializeStage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sasp_pipeline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092")
TRITON_URL = os.environ.get("TRITON_URL", "localhost:8000")
INPUT_TOPIC = os.environ.get("INPUT_TOPIC", "netflow-sanitized")
OUTPUT_TOPIC = os.environ.get("OUTPUT_TOPIC", "morpheus-detections")
ANOMALY_THRESHOLD = float(os.environ.get("ANOMALY_THRESHOLD", "0.05"))
SCALER_PATH = os.environ.get(
    "SCALER_PATH", "/mnt/storage1/triton-models/netflow-anomaly/scaler.json"
)
THRESHOLD_PATH = os.environ.get(
    "THRESHOLD_PATH", "/mnt/storage1/triton-models/netflow-anomaly/threshold.json"
)

FEATURE_COLUMNS = [
    "feat_bytes_per_packet",
    "feat_duration_seconds",
    "feat_src_port_category",
    "feat_dst_port_category",
    "feat_proto_tcp",
    "feat_proto_udp",
    "feat_proto_icmp",
    "feat_proto_other",
    "feat_bytes_total",
    "feat_packets_total",
    "feat_flows_per_src_ip",
    "feat_unique_dst_ips_per_src",
    "feat_unique_dst_ports_per_src",
    "feat_bytes_out_vs_in_ratio",
    "feat_dst_ip_entropy",
]

# ---------------------------------------------------------------------------
# Scaler + threshold loading (lazy singletons)
# ---------------------------------------------------------------------------
_scaler = None
_scaler_loaded = False


class _JsonScaler:
    """Minimal StandardScaler replacement that loads from JSON.

    Avoids pickle/numpy/sklearn version compatibility issues across
    environments (e.g. Morpheus container vs. training host).
    """

    def __init__(self, mean, scale):
        self._mean = np.array(mean, dtype=np.float32)
        self._scale = np.array(scale, dtype=np.float32)

    def transform(self, X):
        return (X - self._mean) / self._scale


def _load_scaler():
    """Load scaler parameters from a JSON file (once).

    Returns a _JsonScaler object, or None if the file doesn't exist.
    Without a scaler, the pipeline falls back to raw (unscaled) features.
    """
    global _scaler, _scaler_loaded
    if _scaler_loaded:
        return _scaler
    _scaler_loaded = True
    try:
        with open(SCALER_PATH) as f:
            data = _json.load(f)
        _scaler = _JsonScaler(data["mean"], data["scale"])
        logger.info("Loaded scaler from %s (%d features)", SCALER_PATH, len(data["mean"]))
    except FileNotFoundError:
        logger.warning("Scaler not found at %s — using raw features", SCALER_PATH)
    return _scaler


_threshold = None
_threshold_loaded = False


def _load_threshold() -> float:
    """Load the anomaly threshold from the training metadata JSON (once).

    Falls back to the ANOMALY_THRESHOLD env var / hardcoded default.
    """
    global _threshold, _threshold_loaded
    if _threshold_loaded:
        return _threshold
    _threshold_loaded = True
    try:
        with open(THRESHOLD_PATH) as f:
            meta = _json.load(f)
        _threshold = float(meta.get("threshold_95", ANOMALY_THRESHOLD))
        logger.info("Loaded threshold %.6f from %s", _threshold, THRESHOLD_PATH)
    except FileNotFoundError:
        logger.warning(
            "Threshold file not found at %s — using default %.4f",
            THRESHOLD_PATH, ANOMALY_THRESHOLD,
        )
        _threshold = ANOMALY_THRESHOLD
    return _threshold


# ---------------------------------------------------------------------------
# CUDA context initialization — must happen before worker threads use GPU
# ---------------------------------------------------------------------------
_cuda_initialized = False


def _ensure_cuda_context():
    """Initialize CUDA context in the current thread if not yet done."""
    global _cuda_initialized
    if _cuda_initialized:
        return
    try:
        import numba.cuda
        numba.cuda.select_device(0)
        logger.info("CUDA context initialized in thread (numba)")
        _cuda_initialized = True
    except Exception as e:
        logger.warning("numba CUDA init failed: %s — trying cupy", e)
        try:
            import cupy
            cupy.cuda.Device(0).use()
            logger.info("CUDA context initialized in thread (cupy)")
            _cuda_initialized = True
        except Exception as e2:
            logger.warning("cupy CUDA init also failed: %s — will use CPU fallback", e2)


def _cudf_to_pandas(df):
    """Convert a cuDF DataFrame to pandas, working around numba CUDA issues.

    Tries multiple strategies to move GPU data to CPU.
    """
    # Strategy 1: to_arrow → to_pandas (bypasses numba entirely)
    try:
        return df.to_arrow().to_pandas()
    except Exception as e:
        logger.debug("to_arrow().to_pandas() failed: %s", e)

    # Strategy 2: column-by-column via Arrow
    try:
        data = {}
        for col in df.columns:
            data[col] = df[col].to_arrow().to_pylist()
        return pd.DataFrame(data)
    except Exception as e:
        logger.debug("column-by-column arrow failed: %s", e)

    # Strategy 3: values_host (may trigger numba but worth trying)
    try:
        return df.to_pandas()
    except Exception as e:
        logger.error("All cuDF→pandas strategies failed: %s", e)
        raise


def _triton_infer_chunked(features_np, max_batch=64):
    """Call Triton HTTP API with chunked batches (respects max_batch_size).

    Returns reconstructed array of same shape as features_np.
    """
    n_rows = features_np.shape[0]
    all_reconstructed = []

    for start in range(0, n_rows, max_batch):
        end = min(start + max_batch, n_rows)
        chunk = features_np[start:end]
        chunk_size = chunk.shape[0]

        payload = {
            "inputs": [{
                "name": "input",
                "shape": [int(chunk_size), 15],
                "datatype": "FP32",
                "data": chunk.tolist(),
            }]
        }
        resp = requests.post(
            f"http://{TRITON_URL}/v2/models/netflow-anomaly/infer",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()

        output_data = np.array(result["outputs"][0]["data"], dtype=np.float32)
        all_reconstructed.append(output_data.reshape(chunk_size, 15))

    return np.vstack(all_reconstructed)


# ---------------------------------------------------------------------------
# Custom stage: Triton autoencoder inference + anomaly scoring
# ---------------------------------------------------------------------------
@stage(execution_modes=(ExecutionMode.GPU, ExecutionMode.CPU))
def triton_anomaly_score(message: ControlMessage) -> MessageMeta:
    """Call Triton HTTP API for autoencoder inference, compute MSE, filter anomalies.

    In CPU mode, DataFrames are pandas (no CUDA needed).
    In GPU mode, converts cuDF→pandas early to avoid numba context issues.
    """
    meta = message.payload()

    # Get DataFrame — in CPU mode this is already pandas
    with meta.mutable_dataframe() as mdf:
        if hasattr(mdf, 'to_arrow'):
            # cuDF (GPU mode) — convert to pandas
            pdf = _cudf_to_pandas(mdf)
        else:
            # pandas (CPU mode) — use directly
            pdf = mdf.copy()

    # Fill missing feature columns
    for col in FEATURE_COLUMNS:
        if col not in pdf.columns:
            pdf[col] = 0.0

    n_rows = len(pdf)
    if n_rows == 0:
        return MessageMeta(pdf)

    # Build feature matrix from pandas (already on CPU)
    features_np = pdf[FEATURE_COLUMNS].values.astype(np.float32)

    # Apply StandardScaler so inputs match training distribution
    scaler = _load_scaler()
    if scaler is not None:
        features_np = scaler.transform(features_np).astype(np.float32)

    # Call Triton HTTP API with chunked batching (max 64 per request)
    try:
        reconstructed = _triton_infer_chunked(features_np, max_batch=64)
        mse = np.mean((features_np - reconstructed) ** 2, axis=1)
    except Exception:
        logger.exception("Triton inference failed for batch of %d", n_rows)
        mse = np.zeros(n_rows, dtype=np.float32)

    # Add detection metadata
    threshold = _load_threshold()
    pdf["anomaly_score"] = mse
    pdf["anomaly_label"] = np.where(mse >= threshold, "anomaly", "normal")
    pdf["detection_type"] = "netflow_anomaly"
    pdf["model_name"] = "netflow-anomaly"
    pdf["detection_id"] = [str(uuid.uuid4()) for _ in range(n_rows)]
    pdf["detection_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if "src_addr" in pdf.columns:
        pdf["source_ip"] = pdf["src_addr"]
    if "dst_addr" in pdf.columns:
        pdf["dest_ip"] = pdf["dst_addr"]

    # Filter to anomalies only
    anomaly_df = pdf[pdf["anomaly_label"] == "anomaly"].reset_index(drop=True)
    n_anomalies = len(anomaly_df)

    if n_anomalies > 0:
        logger.info("Batch %d → %d anomalies (max MSE=%.4f)", n_rows, n_anomalies, float(mse.max()))
    else:
        anomaly_df = pdf.iloc[:0].reset_index(drop=True)

    return MessageMeta(anomaly_df)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def main():
    logger.info("SASP Morpheus Pipeline starting")
    logger.info("  Kafka=%s  Triton=%s", KAFKA_BOOTSTRAP, TRITON_URL)
    logger.info("  %s → %s  threshold=%.4f", INPUT_TOPIC, OUTPUT_TOPIC, ANOMALY_THRESHOLD)
    logger.info("  scaler=%s  threshold_file=%s", SCALER_PATH, THRESHOLD_PATH)

    # Pre-initialize CUDA context in main thread
    _ensure_cuda_context()

    config = Config()
    config.mode = PipelineModes.OTHER
    config.execution_mode = ExecutionMode.CPU  # Use pandas, not cuDF — avoids numba CUDA issues
    config.feature_length = 15
    config.pipeline_batch_size = 256
    config.model_max_batch_size = 64
    config.num_threads = 1
    config.edge_buffer_size = 128

    pipe = LinearPipeline(config)

    pipe.set_source(KafkaSourceStage(
        config,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        input_topic=[INPUT_TOPIC],
        group_id="morpheus-netflow-detection",
        auto_offset_reset="latest",
        poll_interval="100millis",
        disable_pre_filtering=True,
    ))

    pipe.add_stage(DeserializeStage(config))

    pipe.add_stage(triton_anomaly_score(config))

    pipe.add_stage(MonitorStage(config, description="Anomaly Detection", smoothing=0.1))

    pipe.add_stage(WriteToKafkaStage(
        config,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        output_topic=OUTPUT_TOPIC,
    ))

    pipe.run()
    logger.info("Pipeline finished.")


if __name__ == "__main__":
    main()
