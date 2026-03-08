"""
SASP ABP Detector -- GPU Anomaly Detection via nvidia-smi + Triton

Periodically samples nvidia-smi metrics, runs ABP XGBoost model inference
via Triton, and publishes anomaly detections to Kafka.

Deployed on S1 (<S1_IP>) -- same host as Triton server.

Usage:
    python abp_detector.py

Environment variables:
    TRITON_URL              -- Triton HTTP endpoint (default: localhost:8000)
    KAFKA_BOOTSTRAP_SERVERS -- Kafka broker (default: <S2_IP>:9092)
    KAFKA_OUTPUT_TOPIC      -- Output topic (default: abp-detections)
    POLL_INTERVAL           -- Seconds between nvidia-smi polls (default: 30)
    ABP_THRESHOLD           -- Anomaly score threshold (default: 0.5)
    HEALTH_PORT             -- Health endpoint port (default: 9094)
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from uuid import uuid4

import requests
from kafka import KafkaProducer
from kafka.errors import KafkaError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TRITON_URL = os.environ.get("TRITON_URL", "localhost:8000")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092")
KAFKA_OUTPUT_TOPIC = os.environ.get("KAFKA_OUTPUT_TOPIC", "abp-detections")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
ABP_THRESHOLD = float(os.environ.get("ABP_THRESHOLD", "0.5"))
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9094"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("abp_detector")

# ---------------------------------------------------------------------------
# nvidia-smi fields
# ---------------------------------------------------------------------------

NVIDIA_SMI_FIELDS = [
    "timestamp",
    "gpu_uuid",
    "utilization.gpu",
    "utilization.memory",
    "memory.total",
    "memory.free",
    "memory.used",
    "temperature.gpu",
    "temperature.memory",
    "power.draw",
    "power.limit",
    "clocks.current.graphics",
    "clocks.current.sm",
    "clocks.current.memory",
    "clocks.current.video",
    "pstate",
    "fan.speed",
    "clocks_throttle_reasons.active",
    "encoder.stats.averageFps",
    "decoder.stats.averageFps",
]

# Model input features = all except timestamp and gpu_uuid (indices 2..19)
MODEL_INPUT_FIELDS = NVIDIA_SMI_FIELDS[2:]

# ---------------------------------------------------------------------------
# Metrics (in-memory, exposed via /health)
# ---------------------------------------------------------------------------

stats = {
    "polls_total": 0,
    "anomalies_detected": 0,
    "inference_errors": 0,
    "poll_errors": 0,
    "kafka_errors": 0,
    "last_poll_ts": None,
    "last_anomaly_ts": None,
    "last_score": None,
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
stats_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal health check HTTP handler."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            with stats_lock:
                body = json.dumps(stats, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args) -> None:  # noqa: A002
        pass


def start_health_server() -> HTTPServer:
    """Start the health HTTP server in a daemon thread."""
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)  # noqa: S104
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health endpoint listening on port %d", HEALTH_PORT)
    return server


# ---------------------------------------------------------------------------
# nvidia-smi polling
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()


def _parse_pstate(value: str) -> float:
    """Convert pstate string (e.g. 'P0', 'P12') to numeric float."""
    value = value.strip()
    if value.startswith("P") or value.startswith("p"):
        try:
            return float(value[1:])
        except ValueError:
            return 0.0
    return 0.0


def _parse_value(value: str, field_name: str) -> float:
    """Parse a single nvidia-smi CSV value to float."""
    value = value.strip()
    if value in ("[N/A]", "N/A", "n/a", "", "[Not Supported]"):
        return 0.0
    if field_name == "pstate":
        return _parse_pstate(value)
    if field_name == "clocks_throttle_reasons.active":
        # May be hex bitmask like 0x0000000000000000
        try:
            return float(int(value, 0))
        except (ValueError, TypeError):
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def poll_nvidia_smi() -> list[dict]:
    """Run nvidia-smi and return a list of per-GPU metric dicts.

    Each dict has keys: 'timestamp', 'gpu_uuid', 'features' (list of 18 floats),
    and 'raw' (dict of field_name → raw string value).
    """
    query = ",".join(NVIDIA_SMI_FIELDS)
    cmd = [
        "nvidia-smi",
        f"--query-gpu={query}",
        "--format=csv,nounits,noheader",
    ]
    result = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"nvidia-smi exited {result.returncode}: {result.stderr.strip()}")

    gpus: list[dict] = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(NVIDIA_SMI_FIELDS):
            logger.warning("nvidia-smi returned %d fields, expected %d", len(parts), len(NVIDIA_SMI_FIELDS))
            continue

        timestamp_str = parts[0].strip()
        gpu_uuid = parts[1].strip()
        raw: dict[str, str] = {}
        features: list[float] = []
        for i, field in enumerate(NVIDIA_SMI_FIELDS):
            raw[field] = parts[i]
            if i >= 2:  # skip timestamp and gpu_uuid
                features.append(_parse_value(parts[i], field))

        gpus.append({
            "timestamp": timestamp_str,
            "gpu_uuid": gpu_uuid,
            "features": features,
            "raw": raw,
        })
    return gpus


# ---------------------------------------------------------------------------
# Triton inference
# ---------------------------------------------------------------------------


def triton_infer(features: list[float]) -> float:
    """Call Triton ABP model and return the anomaly score."""
    payload = {
        "inputs": [{
            "name": "input",
            "shape": [1, 18],
            "datatype": "FP32",
            "data": [features],
        }]
    }
    resp = requests.post(
        f"http://{TRITON_URL}/v2/models/abp-nvsmi/infer",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()
    # XGBoost ONNX outputs: "label" (class index) and "probabilities" (per-class probs)
    # We want the anomaly probability (class 1)
    for out in result["outputs"]:
        if out["name"] == "probabilities":
            probs = [float(v) for v in out["data"]]
            # Binary classifier: [prob_normal, prob_anomaly]
            return probs[1] if len(probs) >= 2 else probs[0]
    # Fallback: use first output
    return float(result["outputs"][0]["data"][0])


# ---------------------------------------------------------------------------
# Kafka producer
# ---------------------------------------------------------------------------


def create_producer() -> KafkaProducer:
    """Create a Kafka producer for detection output."""
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )


def publish_detection(producer: KafkaProducer, detection: dict) -> None:
    """Publish a detection record to Kafka."""
    try:
        producer.send(KAFKA_OUTPUT_TOPIC, value=detection)
        producer.flush()
    except KafkaError as exc:
        with stats_lock:
            stats["kafka_errors"] += 1
        logger.error("Kafka publish failed: %s", exc)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run() -> None:
    """Main entry point with signal handling and health server."""

    def _handle_signal(signum: int, _frame) -> None:
        logger.info("Received signal %d, shutting down...", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    health_server = start_health_server()

    logger.info(
        "Starting ABP Detector -- triton=%s kafka=%s topic=%s interval=%ds threshold=%.2f",
        TRITON_URL, KAFKA_BOOTSTRAP, KAFKA_OUTPUT_TOPIC, POLL_INTERVAL, ABP_THRESHOLD,
    )

    producer = create_producer()

    try:
        while not shutdown_event.is_set():
            try:
                gpus = poll_nvidia_smi()
                with stats_lock:
                    stats["polls_total"] += 1
                    stats["last_poll_ts"] = time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    )

                for gpu in gpus:
                    try:
                        score = triton_infer(gpu["features"])
                    except Exception as exc:
                        with stats_lock:
                            stats["inference_errors"] += 1
                        logger.error("Triton inference failed for %s: %s", gpu["gpu_uuid"], exc)
                        continue

                    with stats_lock:
                        stats["last_score"] = score

                    if score > ABP_THRESHOLD:
                        detection = {
                            "detection_id": str(uuid4()),
                            "detection_type": "gpu_anomaly",
                            "model_name": "abp-nvsmi",
                            "timestamp": time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                            ),
                            "score": score,
                            "source_ip": os.environ.get("HOSTNAME", "S1"),
                            "gpu_uuid": gpu["gpu_uuid"],
                            "gpu_metrics": gpu["raw"],
                            "description": f"ABP detected anomalous GPU behavior (score={score:.2f})",
                        }
                        publish_detection(producer, detection)
                        with stats_lock:
                            stats["anomalies_detected"] += 1
                            stats["last_anomaly_ts"] = time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                            )
                        logger.info(
                            "Anomaly detected on GPU %s score=%.4f",
                            gpu["gpu_uuid"], score,
                        )
                    else:
                        logger.debug(
                            "GPU %s normal score=%.4f", gpu["gpu_uuid"], score,
                        )

            except Exception as exc:
                with stats_lock:
                    stats["poll_errors"] += 1
                logger.error("Poll cycle failed: %s", exc)

            shutdown_event.wait(timeout=POLL_INTERVAL)
    finally:
        try:
            producer.close()
        except Exception as exc:
            logger.error("Error closing Kafka producer: %s", exc)
        health_server.shutdown()
        logger.info("ABP Detector stopped.")


if __name__ == "__main__":
    run()
