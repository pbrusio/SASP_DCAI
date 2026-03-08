"""
SASP Splunk HEC Forwarder

Consumes events from Kafka and forwards them to Splunk via HTTP Event Collector (HEC).
Includes batch buffering, retry with exponential backoff, and a health endpoint.
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from kafka import KafkaConsumer
from kafka.errors import KafkaError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092")
KAFKA_TOPICS = os.environ.get("KAFKA_TOPICS", "morpheus-detections").split(",")
KAFKA_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "sasp-splunk-forwarder")

SPLUNK_HEC_URL = os.environ.get("SPLUNK_HEC_URL", "https://localhost:8088/services/collector/event")
SPLUNK_HEC_TOKEN = os.environ.get("SPLUNK_HEC_TOKEN", "")
SPLUNK_INDEX = os.environ.get("SPLUNK_INDEX", "sasp_detections")
SPLUNK_TLS_VERIFY = os.environ.get("SPLUNK_TLS_VERIFY", "false").lower() == "true"

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "100"))
BATCH_TIMEOUT = float(os.environ.get("BATCH_TIMEOUT", "5.0"))

HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9090"))

MAX_RETRIES = 5
BACKOFF_BASE = 2

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("splunk_forwarder")

# ---------------------------------------------------------------------------
# Metrics (in-memory, exposed via /health)
# ---------------------------------------------------------------------------

stats = {
    "events_consumed": 0,
    "events_forwarded": 0,
    "batches_sent": 0,
    "errors": 0,
    "last_forward_ts": None,
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
stats_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal health check HTTP handler."""

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            with stats_lock:
                body = json.dumps(stats, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def write(self, data: bytes):
        self.wfile.write(data)

    def log_message(self, format, *args):  # noqa: A002
        # Suppress default access log noise
        pass


def start_health_server():
    """Start the health HTTP server in a daemon thread."""
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)  # noqa: S104
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health endpoint listening on port %d", HEALTH_PORT)
    return server

# ---------------------------------------------------------------------------
# Splunk HEC sender
# ---------------------------------------------------------------------------


def send_to_splunk(batch: list[dict]) -> bool:
    """
    POST a batch of events to Splunk HEC.

    Returns True on success, False on failure after retries.
    """
    if not SPLUNK_HEC_TOKEN:
        logger.error("SPLUNK_HEC_TOKEN is not set — dropping batch of %d events", len(batch))
        return False

    headers = {
        "Authorization": f"Splunk {SPLUNK_HEC_TOKEN}",
        "Content-Type": "application/json",
    }

    # HEC accepts newline-delimited JSON events
    payload = "\n".join(
        json.dumps({"event": event, "index": SPLUNK_INDEX}) for event in batch
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                SPLUNK_HEC_URL,
                headers=headers,
                data=payload,
                verify=SPLUNK_TLS_VERIFY,
                timeout=30,
            )
            if resp.status_code == 200:
                return True
            logger.warning(
                "Splunk HEC returned %d on attempt %d: %s",
                resp.status_code, attempt, resp.text[:200],
            )
        except requests.RequestException as exc:
            logger.warning("Splunk HEC request failed on attempt %d: %s", attempt, exc)

        if attempt < MAX_RETRIES:
            backoff = BACKOFF_BASE ** attempt
            logger.info("Retrying in %ds...", backoff)
            time.sleep(backoff)

    return False

# ---------------------------------------------------------------------------
# Main consumer loop
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()


def handle_signal(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    logger.info("Received signal %d, shutting down...", signum)
    shutdown_event.set()


def run():
    """Main entry point: consume from Kafka and forward to Splunk."""
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    health_server = start_health_server()

    logger.info(
        "Starting Splunk forwarder — Kafka=%s topics=%s HEC=%s",
        KAFKA_BOOTSTRAP, KAFKA_TOPICS, SPLUNK_HEC_URL,
    )

    consumer = KafkaConsumer(
        *KAFKA_TOPICS,
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        group_id=KAFKA_GROUP,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=int(BATCH_TIMEOUT * 1000),
    )

    batch: list[dict] = []
    last_flush = time.monotonic()

    try:
        while not shutdown_event.is_set():
            # Poll returns quickly due to consumer_timeout_ms
            for message in consumer:
                batch.append(message.value)
                with stats_lock:
                    stats["events_consumed"] += 1

                if len(batch) >= BATCH_SIZE:
                    flush_batch(batch)
                    batch = []
                    last_flush = time.monotonic()

                if shutdown_event.is_set():
                    break

            # Flush on timeout even if batch isn't full
            if batch and (time.monotonic() - last_flush) >= BATCH_TIMEOUT:
                flush_batch(batch)
                batch = []
                last_flush = time.monotonic()
    finally:
        # Flush remaining events
        if batch:
            flush_batch(batch)
        consumer.close()
        health_server.shutdown()
        logger.info("Splunk forwarder stopped.")


def flush_batch(batch: list[dict]):
    """Send a batch to Splunk and update stats."""
    ok = send_to_splunk(batch)
    with stats_lock:
        if ok:
            stats["events_forwarded"] += len(batch)
            stats["batches_sent"] += 1
            stats["last_forward_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        else:
            stats["errors"] += 1
    if ok:
        logger.info("Forwarded batch of %d events to Splunk", len(batch))
    else:
        logger.error("Failed to forward batch of %d events after %d retries", len(batch), MAX_RETRIES)


if __name__ == "__main__":
    run()
