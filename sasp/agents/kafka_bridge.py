"""
SASP Kafka Detection Bridge

Consumes detections from Morpheus via Kafka and feeds them into the
SASP investigation workflow.  Includes retry with dead-letter queue,
health endpoint, and graceful shutdown.
"""

import json
import logging
import os
import signal
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

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

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092")
KAFKA_TOPICS = os.environ.get(
    "KAFKA_TOPIC_DETECTIONS", "morpheus-detections,abp-detections,sid-detections,ise-dfp-detections"
).split(",")
KAFKA_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "sasp-detection-bridge")
DLQ_TOPIC = os.environ.get("KAFKA_DLQ_TOPIC", "detection-dlq")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9093"))
MAX_RETRIES = 3

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
logger = logging.getLogger("kafka_bridge")

# ---------------------------------------------------------------------------
# Metrics (in-memory, exposed via /health)
# ---------------------------------------------------------------------------

stats = {
    "detections_consumed_total": 0,
    "detections_processed_total": 0,
    "detections_failed_total": 0,
    "dlq_produced_total": 0,
    "investigations_started_total": 0,
    "investigations_completed_total": 0,
    "investigations_failed_total": 0,
    "splunk_posts_total": 0,
    "splunk_post_errors_total": 0,
    "last_detection_ts": None,
    "last_investigation_ts": None,
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
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        pass


def start_health_server():
    """Start the health HTTP server in a daemon thread."""
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)  # noqa: S104
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health endpoint listening on port %d", HEALTH_PORT)
    return server

# ---------------------------------------------------------------------------
# Detection consumer
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()


class KafkaDetectionConsumer:
    """Consume Morpheus detections from Kafka, parse them, and (future) hand
    them off to the SASP investigation graph."""

    def __init__(self):
        self.consumer = KafkaConsumer(
            *KAFKA_TOPICS,
            bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
            group_id=KAFKA_GROUP,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            consumer_timeout_ms=2000,
        )
        self.dlq_producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        logger.info(
            "KafkaDetectionConsumer initialised — topics=%s group=%s",
            KAFKA_TOPICS, KAFKA_GROUP,
        )

    # ---- Splunk HEC ----

    def post_to_splunk_hec(self, event: dict, index: str = "sasp_investigations") -> bool:
        """Post an event to Splunk via HEC. Returns True on success."""
        if not SPLUNK_HEC_TOKEN:
            logger.warning("SPLUNK_HEC_TOKEN not set, skipping HEC post")
            return False

        payload = {
            "index": index,
            "sourcetype": "sasp:investigation",
            "source": "kafka_bridge",
            "event": event,
        }
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
            return True
        except requests.RequestException as exc:
            with stats_lock:
                stats["splunk_post_errors_total"] += 1
            logger.error("Splunk HEC post failed: %s", exc)
            return False

    # ---- detection processing ----

    def process_detection(self, detection_data: dict) -> dict:
        """Parse a raw Morpheus detection into the InvestigationState detection
        dict format, run investigation, and post results to Splunk.

        Expected upstream fields (from Morpheus):
            source_ip, dest_ip, timestamp, score, model_name, rule_id,
            description, raw_event (optional)
        """
        detection = {
            "detection_id": detection_data.get(
                "detection_id", str(uuid.uuid4())
            ),
            "source_ip": detection_data.get("source_ip", "unknown"),
            "dest_ip": detection_data.get("dest_ip", "unknown"),
            "timestamp": detection_data.get(
                "timestamp",
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ),
            "score": float(detection_data.get("score", 0.0)),
            "model_name": detection_data.get("model_name", "unknown"),
            "rule_id": detection_data.get("rule_id"),
            "description": detection_data.get("description", ""),
            "raw_event": detection_data.get("raw_event"),
            "username": detection_data.get("username"),
            "calling_station_id": detection_data.get("calling_station_id"),
            "top_features": detection_data.get("top_features"),
        }

        logger.info(
            "Parsed detection %s  src=%s dst=%s score=%.2f model=%s",
            detection["detection_id"],
            detection["source_ip"],
            detection["dest_ip"],
            detection["score"],
            detection["model_name"],
        )

        # Run investigation via LangGraph agents
        try:
            from sasp.agents.graph import run_investigation

            with stats_lock:
                stats["investigations_started_total"] += 1

            result = run_investigation(detection)
            inv_id = result.get("investigation_id", "unknown")
            severity = result.get("severity", "unknown")
            guardian = result.get("guardian_result", {})
            approved = guardian.get("approved", False) if guardian else False

            with stats_lock:
                stats["investigations_completed_total"] += 1
                stats["last_investigation_ts"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )

            logger.info(
                "Investigation %s completed: severity=%s guardian_approved=%s",
                inv_id, severity, approved,
            )

            # Post investigation results to Splunk
            splunk_event = {
                "investigation_id": inv_id,
                "detection_id": detection["detection_id"],
                "source_ip": detection["source_ip"],
                "dest_ip": detection["dest_ip"],
                "score": detection["score"],
                "model_name": detection["model_name"],
                "severity": severity,
                "confidence": result.get("confidence"),
                "triage_decision": result.get("triage_decision"),
                "triage_reasoning": result.get("triage_reasoning", ""),
                "mitre_techniques": result.get("mitre_techniques", []),
                "kill_chain_phase": result.get("kill_chain_phase"),
                "threat_actor": result.get("threat_actor"),
                "campaigns": result.get("campaigns", []),
                "cves": result.get("cves", []),
                "iocs": result.get("iocs", []),
                "report_summary": result.get("report_summary", ""),
                "report_full": result.get("report_full", ""),
                "recommendations": result.get("recommendations", []),
                "affected_assets": result.get("affected_assets", []),
                "affected_users": result.get("affected_users", []),
                "timeline": result.get("timeline", []),
                "username": detection.get("username"),
                "calling_station_id": detection.get("calling_station_id"),
                "top_features": detection.get("top_features"),
                "guardian_approved": approved,
                "guardian_concerns": guardian.get("concerns", []) if guardian else [],
                "guardian_checks": guardian.get("validation_checks", {}) if guardian else {},
                "duration_seconds": result.get("duration_seconds"),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self.post_to_splunk_hec(splunk_event)

        except ImportError:
            logger.warning("sasp.agents.graph not available, skipping investigation")
        except Exception as exc:
            with stats_lock:
                stats["investigations_failed_total"] += 1
            logger.error(
                "Investigation failed for detection %s: %s",
                detection.get("detection_id", "unknown"), exc,
            )

        return detection

    # ---- dead-letter queue ----

    def send_to_dlq(self, message: dict, error: Exception, source_topic: str = "unknown") -> None:
        """Produce a failed message to the dead-letter queue topic."""
        envelope = {
            "original_message": message,
            "error": str(error),
            "error_type": type(error).__name__,
            "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_topic": source_topic,
            "consumer_group": KAFKA_GROUP,
        }
        try:
            self.dlq_producer.send(DLQ_TOPIC, value=envelope)
            self.dlq_producer.flush()
            with stats_lock:
                stats["dlq_produced_total"] += 1
            logger.warning(
                "Sent failed detection to DLQ topic=%s error=%s",
                DLQ_TOPIC, error,
            )
        except KafkaError as ke:
            logger.error("Failed to produce to DLQ: %s", ke)

    # ---- main loop ----

    def run(self) -> None:
        """Consume detections, process with retry, DLQ after MAX_RETRIES."""
        logger.info("Starting consumer loop")
        try:
            while not shutdown_event.is_set():
                for message in self.consumer:
                    if shutdown_event.is_set():
                        break

                    with stats_lock:
                        stats["detections_consumed_total"] += 1

                    # Deserialize manually — topic may contain non-JSON messages
                    raw = message.value
                    try:
                        detection_data = json.loads(raw.decode("utf-8")) if isinstance(raw, bytes) else raw
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        logger.warning("Skipping non-JSON message on partition=%s offset=%s: %s",
                                       message.partition, message.offset, exc)
                        with stats_lock:
                            stats["detections_failed_total"] += 1
                        continue
                    processed = False

                    for attempt in range(1, MAX_RETRIES + 1):
                        try:
                            self.process_detection(detection_data)
                            processed = True
                            break
                        except Exception as exc:
                            logger.warning(
                                "Processing attempt %d/%d failed: %s",
                                attempt, MAX_RETRIES, exc,
                            )
                            if attempt < MAX_RETRIES:
                                time.sleep(0.5 * attempt)

                    if processed:
                        with stats_lock:
                            stats["detections_processed_total"] += 1
                            stats["last_detection_ts"] = time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                            )
                    else:
                        with stats_lock:
                            stats["detections_failed_total"] += 1
                        self.send_to_dlq(
                            detection_data,
                            RuntimeError(
                                f"Failed after {MAX_RETRIES} attempts"
                            ),
                            source_topic=message.topic,
                        )
        finally:
            self.shutdown()

    # ---- shutdown ----

    def shutdown(self) -> None:
        """Close Kafka consumer and producer gracefully."""
        logger.info("Shutting down KafkaDetectionConsumer")
        try:
            self.consumer.close()
        except Exception as exc:
            logger.error("Error closing consumer: %s", exc)
        try:
            self.dlq_producer.close()
        except Exception as exc:
            logger.error("Error closing DLQ producer: %s", exc)

# ---------------------------------------------------------------------------
# Entry helpers
# ---------------------------------------------------------------------------


def _handle_signal(signum, _frame):
    logger.info("Received signal %d, shutting down...", signum)
    shutdown_event.set()


def run():
    """Module-level entry point with signal handling and health server."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    health_server = start_health_server()

    logger.info(
        "Starting Kafka Detection Bridge — bootstrap=%s topics=%s group=%s",
        KAFKA_BOOTSTRAP, KAFKA_TOPICS, KAFKA_GROUP,
    )

    bridge = KafkaDetectionConsumer()
    try:
        bridge.run()
    finally:
        health_server.shutdown()
        logger.info("Kafka Detection Bridge stopped.")


if __name__ == "__main__":
    run()
