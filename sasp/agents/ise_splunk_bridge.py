"""
SASP ISE-to-Splunk Bridge

Lightweight Kafka consumer that forwards sanitized ISE authentication
events to Splunk HEC for the ISE Activity dashboard.

Runs on Mac Studio (<MAC_STUDIO_IP>) alongside the sanitizer and
detection bridge.

Usage:
    python -m sasp.agents.ise_splunk_bridge

Environment variables:
    KAFKA_BOOTSTRAP_SERVERS -- Kafka broker (default: <S2_IP>:9092)
    KAFKA_INPUT_TOPIC       -- Input topic (default: ise-sanitized)
    KAFKA_CONSUMER_GROUP    -- Consumer group (default: sasp-ise-bridge)
    SPLUNK_HEC_URL          -- Splunk HEC endpoint
    SPLUNK_HEC_TOKEN        -- Splunk HEC auth token
    SPLUNK_TLS_VERIFY       -- Verify TLS (default: false)
    HEALTH_PORT             -- Health endpoint port (default: 9096)
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

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092")
KAFKA_INPUT_TOPIC = os.environ.get("KAFKA_INPUT_TOPIC", "ise-sanitized")
KAFKA_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "sasp-ise-bridge")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9096"))

SPLUNK_HEC_URL = os.environ.get(
    "SPLUNK_HEC_URL", "http://<SPLUNK_IP>:8088/services/collector/event"
)
SPLUNK_HEC_TOKEN = os.environ.get("SPLUNK_HEC_TOKEN", "")
SPLUNK_TLS_VERIFY = os.environ.get("SPLUNK_TLS_VERIFY", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ise_splunk_bridge")

# ---------------------------------------------------------------------------
# Metrics (in-memory, exposed via /health)
# ---------------------------------------------------------------------------

stats = {
    "messages_consumed": 0,
    "splunk_posts_total": 0,
    "splunk_post_errors": 0,
    "parse_errors": 0,
    "last_message_ts": None,
    "last_splunk_post_ts": None,
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
stats_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()


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
# Splunk HEC posting
# ---------------------------------------------------------------------------


def post_to_splunk_hec(event: dict) -> bool:
    """Post an ISE event to Splunk via HEC. Returns True on success."""
    if not SPLUNK_HEC_TOKEN:
        logger.warning("SPLUNK_HEC_TOKEN not set, skipping HEC post")
        return False

    payload: dict = {
        "index": "sasp_ise",
        "sourcetype": "sasp:ise_auth",
        "source": "ise_splunk_bridge",
        "event": event,
    }

    # Use the event's timestamp for Splunk _time so dashboard timelines
    # reflect simulated event times rather than ingestion time.
    ts = event.get("timestamp")
    if ts:
        try:
            from datetime import datetime, timezone
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            payload["time"] = dt.timestamp()
        except (ValueError, TypeError):
            pass
    headers = {"Authorization": f"Splunk {SPLUNK_HEC_TOKEN}"}

    try:
        resp = requests.post(
            SPLUNK_HEC_URL,
            json=payload,
            headers=headers,
            verify=SPLUNK_TLS_VERIFY,
            timeout=10,
        )
        resp.raise_for_status()
        with stats_lock:
            stats["splunk_posts_total"] += 1
            stats["last_splunk_post_ts"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
        return True
    except requests.RequestException as exc:
        with stats_lock:
            stats["splunk_post_errors"] += 1
        logger.error("Splunk HEC post failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run() -> None:
    """Module-level entry point with signal handling and health server."""

    def _handle_signal(signum: int, _frame) -> None:
        logger.info("Received signal %d, shutting down...", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    health_server = start_health_server()

    logger.info(
        "Starting ISE Splunk Bridge -- kafka=%s topic=%s group=%s",
        KAFKA_BOOTSTRAP, KAFKA_INPUT_TOPIC, KAFKA_GROUP,
    )

    consumer = KafkaConsumer(
        KAFKA_INPUT_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        group_id=KAFKA_GROUP,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        consumer_timeout_ms=2000,
    )

    logger.info("Kafka consumer initialised -- topic=%s group=%s",
                KAFKA_INPUT_TOPIC, KAFKA_GROUP)

    try:
        while not shutdown_event.is_set():
            for message in consumer:
                if shutdown_event.is_set():
                    break

                with stats_lock:
                    stats["messages_consumed"] += 1
                    stats["last_message_ts"] = time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    )

                # Deserialize Kafka message
                raw = message.value
                try:
                    event = json.loads(raw.decode("utf-8")) if isinstance(raw, bytes) else raw
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    with stats_lock:
                        stats["parse_errors"] += 1
                    logger.warning(
                        "Skipping non-JSON message partition=%s offset=%s: %s",
                        message.partition, message.offset, exc,
                    )
                    continue

                post_to_splunk_hec(event)
    finally:
        try:
            consumer.close()
        except Exception as exc:
            logger.error("Error closing consumer: %s", exc)
        health_server.shutdown()
        logger.info("ISE Splunk Bridge stopped.")


if __name__ == "__main__":
    run()
