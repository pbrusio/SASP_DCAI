"""
SASP ISE DFP Detector -- Digital Fingerprinting for ISE Auth Events

Consumes sanitized ISE authentication events from Kafka, extracts
14 behavioral features with per-user rolling windows, runs autoencoder
inference via Triton, and publishes anomaly detections (high MSE) to Kafka.

Deployed on S1 (<S1_IP>) alongside Triton.

Usage:
    python ise_dfp_detector.py

Environment variables:
    TRITON_URL              -- Triton HTTP endpoint (default: localhost:8000)
    KAFKA_BOOTSTRAP_SERVERS -- Kafka broker (default: <S2_IP>:9092)
    KAFKA_INPUT_TOPIC       -- Input topic (default: ise-sanitized)
    KAFKA_OUTPUT_TOPIC      -- Output topic (default: ise-dfp-detections)
    KAFKA_CONSUMER_GROUP    -- Consumer group (default: sasp-ise-dfp-detector)
    SCALER_PATH             -- Path to scaler JSON (default: /models/ise-dfp/scaler.json)
    THRESHOLD_PATH          -- Path to threshold JSON (default: /models/ise-dfp/threshold.json)
    HEALTH_PORT             -- Health endpoint port (default: 9097)
"""

import collections
import json
import logging
import math
import os
import signal
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from uuid import uuid4

import numpy as np
import requests
from kafka import KafkaConsumer, KafkaProducer
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
KAFKA_INPUT_TOPIC = os.environ.get("KAFKA_INPUT_TOPIC", "ise-sanitized")
KAFKA_OUTPUT_TOPIC = os.environ.get("KAFKA_OUTPUT_TOPIC", "ise-dfp-detections")
KAFKA_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "sasp-ise-dfp-detector")
SCALER_PATH = os.environ.get("SCALER_PATH", "/models/ise-dfp/scaler.json")
THRESHOLD_PATH = os.environ.get("THRESHOLD_PATH", "/models/ise-dfp/threshold.json")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9097"))

NUM_FEATURES = 14

# Human-readable names for the 14 DFP features (matches extract_features order)
_FEATURE_NAMES = [
    "hour_sin", "hour_cos", "day_of_week", "is_weekend",
    "auth_result", "auth_type", "nas_port_type",
    "consecutive_failures", "auth_rate_1h", "unique_devices_24h",
    "unique_nas_24h", "failure_rate_1h", "known_device", "policy_set",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ise_dfp_detector")

# ---------------------------------------------------------------------------
# Metrics (in-memory, exposed via /health)
# ---------------------------------------------------------------------------

stats = {
    "messages_consumed": 0,
    "messages_processed": 0,
    "detections_published": 0,
    "inference_errors": 0,
    "kafka_errors": 0,
    "users_tracked": 0,
    "last_mse": None,
    "last_message_ts": None,
    "last_detection_ts": None,
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
# Scaler (JSON-based, avoids pickle/numpy version issues)
# ---------------------------------------------------------------------------


class _JsonScaler:
    """Minimal StandardScaler replacement that loads from JSON."""

    def __init__(self, mean, scale):
        self._mean = np.array(mean, dtype=np.float32)
        self._scale = np.array(scale, dtype=np.float32)

    def transform(self, X):
        return (X - self._mean) / self._scale


def load_scaler(path: str) -> _JsonScaler:
    """Load scaler parameters from JSON file."""
    with open(path) as f:
        data = json.load(f)
    scaler = _JsonScaler(data["mean"], data["scale"])
    logger.info("Loaded scaler from %s (%d features)", path, len(data["mean"]))
    return scaler


def load_threshold(path: str) -> float:
    """Load the 99th-percentile threshold from JSON file."""
    with open(path) as f:
        data = json.load(f)
    threshold = float(data["threshold_99"])
    logger.info("Loaded threshold from %s: %.6f", path, threshold)
    return threshold


# ---------------------------------------------------------------------------
# Shutdown event
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()

# ---------------------------------------------------------------------------
# Inline feature extraction (standalone, mirrors ISEDFPFeatureExtractor)
# ---------------------------------------------------------------------------

# Categorical mappings — MUST match ise_dfp_features.py exactly
_AUTH_RESULT_MAP = {"PASS": 0.0, "FAIL": 1.0}
_AUTH_TYPE_MAP = {"802.1X": 0.0, "TACACS+": 1.0}
_AUTH_TYPE_OTHER = 2.0
_NAS_PORT_TYPE_MAP = {"Ethernet": 0.0, "Wireless": 1.0, "Virtual": 2.0}
_NAS_PORT_TYPE_OTHER = 2.0

# Rolling window durations (seconds)
_WINDOW_5MIN = 300
_WINDOW_1H = 3600
_WINDOW_24H = 86400


class _UserWindow:
    """Per-user rolling window for temporal feature computation.

    Stores (timestamp, auth_result, calling_station_id, nas_ip) tuples
    in a deque. Evicts entries older than 24 h on each add().
    Mirrors ise_dfp_features._UserWindow exactly.
    """

    def __init__(self):
        self.events: collections.deque = collections.deque()

    def add(self, ts: float, auth_result: str, device: str, nas_ip: str) -> None:
        self.events.append((ts, auth_result, device, nas_ip))
        cutoff = ts - _WINDOW_24H
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()

    def consecutive_failures(self, ts: float) -> float:
        cutoff = ts - _WINDOW_5MIN
        return float(sum(1 for t, r, _, _ in self.events if t >= cutoff and r == "FAIL"))

    def auth_rate_1h(self, ts: float) -> float:
        cutoff = ts - _WINDOW_1H
        return float(sum(1 for t, _, _, _ in self.events if t >= cutoff))

    def failure_rate_1h(self, ts: float) -> float:
        cutoff = ts - _WINDOW_1H
        total = 0
        failures = 0
        for t, result, _, _ in self.events:
            if t >= cutoff:
                total += 1
                if result == "FAIL":
                    failures += 1
        return failures / max(total, 1)

    def unique_devices_24h(self, ts: float) -> float:
        cutoff = ts - _WINDOW_24H
        return float(len({dev for t, _, dev, _ in self.events if t >= cutoff}))

    def unique_nas_24h(self, ts: float) -> float:
        cutoff = ts - _WINDOW_24H
        return float(len({nip for t, _, _, nip in self.events if t >= cutoff}))


# Global per-user state
_user_windows: dict[str, _UserWindow] = {}

# Known devices per user + policy_set_map — loaded from scaler.json
_known_devices: dict[str, set[str]] = {}
_policy_set_map: dict[str, int] = {}


def load_scaler_metadata(path: str) -> None:
    """Load known_devices and policy_set_map from the scaler JSON."""
    global _known_devices, _policy_set_map
    with open(path) as f:
        data = json.load(f)
    raw_devices = data.get("known_devices", {})
    _known_devices = {user: set(devs) for user, devs in raw_devices.items()}
    _policy_set_map = data.get("policy_set_map", {})
    logger.info(
        "Loaded scaler metadata: %d users, %d policy sets",
        len(_known_devices), len(_policy_set_map),
    )


def _parse_timestamp(record: dict) -> float:
    """Parse ISO-8601 timestamp string to epoch seconds (UTC)."""
    ts = record.get("timestamp", "")
    if not ts:
        return time.time()
    try:
        s = ts.replace("Z", "+00:00")
        from datetime import datetime
        dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except (ValueError, TypeError):
        return time.time()


def extract_features(record: dict) -> list[float]:
    """Extract 14 DFP features from a single ISE auth event.

    Feature order matches ISEDFPFeatureExtractor.FEATURE_COLS exactly:
        0  hour_sin              sin(2*pi*hour/24)
        1  hour_cos              cos(2*pi*hour/24)
        2  day_of_week           0-6 (Mon=0)
        3  is_weekend            1.0 if day >= 5
        4  auth_result_code      PASS=0, FAIL=1
        5  auth_type_code        802.1X=0, TACACS+=1, other=2
        6  nas_port_type_code    Ethernet=0, Wireless=1, Virtual=2
        7  consecutive_failures  FAIL count in 5-min window
        8  auth_rate_1h          event count in 1h window
        9  unique_devices_24h    unique calling_station_id in 24h
       10  unique_nas_24h        unique nas_ip in 24h
       11  failure_rate_1h       failures / events in 1h
       12  known_device_flag     0=seen in training, 1=novel
       13  policy_set_code       integer-encoded policy_set
    """
    ts = _parse_timestamp(record)
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)

    username = record.get("username", "unknown")
    auth_result = record.get("auth_result", "FAIL")
    auth_type = record.get("auth_type", "")
    nas_port_type = record.get("nas_port_type", "")
    device = record.get("calling_station_id", "")
    nas_ip = record.get("nas_ip", "")
    policy_set = record.get("policy_set", "")

    # Get or create user window
    if username not in _user_windows:
        _user_windows[username] = _UserWindow()
    window = _user_windows[username]

    # Temporal features
    hour = dt.hour + dt.minute / 60.0
    hour_sin = math.sin(2.0 * math.pi * hour / 24.0)
    hour_cos = math.cos(2.0 * math.pi * hour / 24.0)
    day_of_week = float(dt.weekday())
    is_weekend = 1.0 if dt.weekday() >= 5 else 0.0

    # Categorical features
    auth_result_code = _AUTH_RESULT_MAP.get(auth_result, 1.0)
    auth_type_code = _AUTH_TYPE_MAP.get(auth_type, _AUTH_TYPE_OTHER)
    nas_port_type_code = _NAS_PORT_TYPE_MAP.get(nas_port_type, _NAS_PORT_TYPE_OTHER)

    # Rolling window features (computed BEFORE adding current event)
    consecutive_failures = window.consecutive_failures(ts)
    auth_rate_1h = window.auth_rate_1h(ts)
    unique_devices_24h = window.unique_devices_24h(ts)
    unique_nas_24h = window.unique_nas_24h(ts)
    failure_rate_1h = window.failure_rate_1h(ts)

    # Known device flag
    user_known = _known_devices.get(username, set())
    known_device_flag = 0.0 if device in user_known else 1.0

    # Policy set code
    policy_set_code = float(_policy_set_map.get(policy_set, len(_policy_set_map)))

    # Add current event to window for future records
    window.add(ts, auth_result, device, nas_ip)

    return [
        hour_sin,              # 0
        hour_cos,              # 1
        day_of_week,           # 2
        is_weekend,            # 3
        auth_result_code,      # 4
        auth_type_code,        # 5
        nas_port_type_code,    # 6
        consecutive_failures,  # 7
        auth_rate_1h,          # 8
        unique_devices_24h,    # 9
        unique_nas_24h,        # 10
        failure_rate_1h,       # 11
        known_device_flag,     # 12
        policy_set_code,       # 13
    ]


# ---------------------------------------------------------------------------
# Triton inference
# ---------------------------------------------------------------------------


def triton_infer(features: list[float]) -> list[float]:
    """Call Triton ise-dfp autoencoder and return reconstructed features."""
    payload = {
        "inputs": [{
            "name": "input",
            "shape": [1, NUM_FEATURES],
            "datatype": "FP32",
            "data": [features],
        }]
    }
    resp = requests.post(
        f"http://{TRITON_URL}/v2/models/ise-dfp/infer",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return [float(v) for v in resp.json()["outputs"][0]["data"]]


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

    # Load scaler, threshold, and per-user metadata (known devices, policy map)
    scaler = load_scaler(SCALER_PATH)
    load_scaler_metadata(SCALER_PATH)
    threshold_99 = load_threshold(THRESHOLD_PATH)

    logger.info(
        "Starting ISE DFP Detector -- triton=%s kafka=%s input=%s output=%s threshold=%.6f",
        TRITON_URL, KAFKA_BOOTSTRAP, KAFKA_INPUT_TOPIC, KAFKA_OUTPUT_TOPIC, threshold_99,
    )

    consumer = KafkaConsumer(
        KAFKA_INPUT_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        group_id=KAFKA_GROUP,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        consumer_timeout_ms=2000,
    )

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )

    logger.info(
        "Kafka consumer initialised -- topic=%s group=%s",
        KAFKA_INPUT_TOPIC, KAFKA_GROUP,
    )

    try:
        while not shutdown_event.is_set():
            for message in consumer:
                if shutdown_event.is_set():
                    break

                with stats_lock:
                    stats["messages_consumed"] += 1

                # Deserialize Kafka message
                raw = message.value
                try:
                    record = json.loads(raw.decode("utf-8")) if isinstance(raw, bytes) else raw
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    logger.warning(
                        "Skipping non-JSON message partition=%s offset=%s: %s",
                        message.partition, message.offset, exc,
                    )
                    continue

                username = record.get("username", "unknown")
                if not username or username == "unknown":
                    continue

                # Extract features and infer
                try:
                    features = extract_features(record)
                    features_arr = np.array([features], dtype=np.float32)
                    scaled = scaler.transform(features_arr).flatten().tolist()
                    reconstructed = triton_infer(scaled)
                except Exception as exc:
                    with stats_lock:
                        stats["inference_errors"] += 1
                    logger.error("DFP inference failed: %s", exc)
                    continue

                # Compute MSE (reconstruction error) and per-feature attribution
                feature_errors = [(a - b) ** 2 for a, b in zip(scaled, reconstructed)]
                mse = sum(feature_errors) / len(feature_errors)

                total_err = sum(feature_errors)
                if total_err > 0:
                    ranked = sorted(enumerate(feature_errors), key=lambda x: x[1], reverse=True)
                    top3 = [(_FEATURE_NAMES[i], err / total_err * 100) for i, err in ranked[:3]]
                    top_features_str = ", ".join(f"{name} ({pct:.0f}%)" for name, pct in top3)
                else:
                    top_features_str = ""

                with stats_lock:
                    stats["messages_processed"] += 1
                    stats["users_tracked"] = len(_user_windows)
                    stats["last_mse"] = round(mse, 6)
                    stats["last_message_ts"] = time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    )

                if mse <= threshold_99:
                    continue

                # Build detection record
                detection = {
                    "detection_id": str(uuid4()),
                    "detection_type": "ise_dfp_anomaly",
                    "model_name": "ise-dfp",
                    "timestamp": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                    "score": mse,
                    "username": username,
                    "source_ip": record.get("nas_ip", "unknown"),
                    "calling_station_id": record.get("calling_station_id", "unknown"),
                    "description": (
                        f"ISE DFP: behavioral anomaly for {username} "
                        f"(MSE={mse:.6f}, threshold={threshold_99:.6f})"
                    ),
                    "top_features": top_features_str,
                }

                try:
                    producer.send(KAFKA_OUTPUT_TOPIC, value=detection)
                    producer.flush()
                    with stats_lock:
                        stats["detections_published"] += 1
                        stats["last_detection_ts"] = time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                        )
                    logger.info(
                        "DFP detection: user=%s MSE=%.6f threshold=%.6f src=%s",
                        username, mse, threshold_99, detection["source_ip"],
                    )
                except KafkaError as exc:
                    with stats_lock:
                        stats["kafka_errors"] += 1
                    logger.error("Kafka publish failed: %s", exc)

    finally:
        try:
            consumer.close()
        except Exception as exc:
            logger.error("Error closing consumer: %s", exc)
        try:
            producer.close()
        except Exception as exc:
            logger.error("Error closing producer: %s", exc)
        health_server.shutdown()
        logger.info("ISE DFP Detector stopped.")


if __name__ == "__main__":
    run()
