"""
SASP SID Detector -- Sensitive Information Detection in Syslog

Consumes sanitized syslog messages from Kafka, tokenizes with BERT
tokenizer, runs SID MiniBERT inference via Triton, and publishes
PII/credential detections to Kafka.

Deployed on S1 (<S1_IP>) alongside Triton.

Usage:
    python sid_detector.py

Environment variables:
    TRITON_URL              -- Triton HTTP endpoint (default: localhost:8000)
    KAFKA_BOOTSTRAP_SERVERS -- Kafka broker (default: <S2_IP>:9092)
    KAFKA_INPUT_TOPIC       -- Input topic (default: syslog-sanitized)
    KAFKA_OUTPUT_TOPIC      -- Output topic (default: sid-detections)
    SID_THRESHOLD           -- Confidence threshold (default: 0.7)
    VOCAB_PATH              -- Path to BERT vocab file (default: /models/sid-minibert/vocab.txt)
    HEALTH_PORT             -- Health endpoint port (default: 9095)
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from uuid import uuid4

import requests
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from tokenizers import BertWordPieceTokenizer

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
KAFKA_INPUT_TOPIC = os.environ.get("KAFKA_INPUT_TOPIC", "syslog-sanitized")
KAFKA_OUTPUT_TOPIC = os.environ.get("KAFKA_OUTPUT_TOPIC", "sid-detections")
KAFKA_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "sasp-sid-detector")
SID_THRESHOLD = float(os.environ.get("SID_THRESHOLD", "0.7"))
VOCAB_PATH = os.environ.get("VOCAB_PATH", "/models/sid-minibert/vocab.txt")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9095"))
MAX_SEQ_LEN = 256

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("sid_detector")

# ---------------------------------------------------------------------------
# SID class labels
# ---------------------------------------------------------------------------

SID_LABELS = [
    "address",
    "bank_account",
    "credit_card",
    "email",
    "govt_id",
    "name",
    "password",
    "phone_number",
    "secret_keys",
    "user",
]

# ---------------------------------------------------------------------------
# Metrics (in-memory, exposed via /health)
# ---------------------------------------------------------------------------

stats = {
    "messages_consumed": 0,
    "messages_processed": 0,
    "detections_published": 0,
    "inference_errors": 0,
    "kafka_errors": 0,
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
# Tokenizer
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()

_tokenizer = None


def _get_tokenizer() -> BertWordPieceTokenizer:
    """Lazy-load the BERT tokenizer (singleton)."""
    global _tokenizer
    if _tokenizer is None:
        logger.info("Loading BERT tokenizer from %s", VOCAB_PATH)
        _tokenizer = BertWordPieceTokenizer(VOCAB_PATH)
    return _tokenizer


def tokenize(text: str) -> tuple[list[int], list[int]]:
    """Tokenize text and return (input_ids, attention_mask) padded to MAX_SEQ_LEN."""
    tokenizer = _get_tokenizer()
    encoding = tokenizer.encode(text)
    input_ids = encoding.ids[:MAX_SEQ_LEN]
    seq_len = len(input_ids)
    attention_mask = [1] * seq_len + [0] * (MAX_SEQ_LEN - seq_len)
    input_ids = input_ids + [0] * (MAX_SEQ_LEN - seq_len)
    return input_ids, attention_mask


# ---------------------------------------------------------------------------
# Triton inference
# ---------------------------------------------------------------------------


def triton_infer(input_ids: list[int], attention_mask: list[int]) -> list[float]:
    """Call Triton SID model and return 10-class scores."""
    payload = {
        "inputs": [
            {
                "name": "input_ids",
                "shape": [1, MAX_SEQ_LEN],
                "datatype": "INT32",
                "data": [input_ids],
            },
            {
                "name": "attention_mask",
                "shape": [1, MAX_SEQ_LEN],
                "datatype": "INT32",
                "data": [attention_mask],
            },
        ]
    }
    resp = requests.post(
        f"http://{TRITON_URL}/v2/models/sid-minibert/infer",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()
    return [float(v) for v in result["outputs"][0]["data"]]


# ---------------------------------------------------------------------------
# Message extraction
# ---------------------------------------------------------------------------


def extract_message_text(record: dict) -> str:
    """Extract the syslog message body from a sanitized record."""
    for key in ("message", "msg", "MESSAGE", "MSG", "log", "content"):
        if key in record:
            return str(record[key])
    # Fallback: serialize the whole record
    return json.dumps(record, default=str)


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
        "Starting SID Detector -- triton=%s kafka=%s input=%s output=%s threshold=%.2f",
        TRITON_URL, KAFKA_BOOTSTRAP, KAFKA_INPUT_TOPIC, KAFKA_OUTPUT_TOPIC, SID_THRESHOLD,
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

                text = extract_message_text(record)
                if not text.strip():
                    continue

                # Tokenize and infer
                try:
                    input_ids, attention_mask = tokenize(text)
                    scores = triton_infer(input_ids, attention_mask)
                except Exception as exc:
                    with stats_lock:
                        stats["inference_errors"] += 1
                    logger.error("SID inference failed: %s", exc)
                    continue

                with stats_lock:
                    stats["messages_processed"] += 1
                    stats["last_message_ts"] = time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    )

                # Check for detections above threshold
                detected_classes = [
                    {"label": SID_LABELS[i], "score": round(scores[i], 4)}
                    for i in range(len(SID_LABELS))
                    if scores[i] > SID_THRESHOLD
                ]

                if not detected_classes:
                    continue

                max_class = max(detected_classes, key=lambda c: c["score"])
                detection = {
                    "detection_id": str(uuid4()),
                    "detection_type": "sensitive_info",
                    "model_name": "sid-minibert",
                    "timestamp": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                    "score": max_class["score"],
                    "source_ip": record.get("host", "unknown"),
                    "detected_classes": detected_classes,
                    "message_preview": text[:200],
                    "description": (
                        f"SID detected sensitive information: "
                        f"{max_class['label']} ({max_class['score']:.2f})"
                    ),
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
                        "SID detection: %s (score=%.4f) src=%s",
                        max_class["label"], max_class["score"],
                        detection["source_ip"],
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
        logger.info("SID Detector stopped.")


if __name__ == "__main__":
    run()
