"""
SASP Sanitizer Kafka Service

Consumes raw telemetry from Kafka, routes each message through the
appropriate sanitizer, and produces sanitized or rejected records
back to Kafka.
"""

import json
import logging
import math
import os
import signal
import sys
import threading
import time
from collections import Counter
from http.server import HTTPServer, BaseHTTPRequestHandler

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

from .base import BaseSanitizer
from .netflow import NetFlowSanitizer
from .syslog import SyslogSanitizer
from .ise import ISESanitizer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092")
INPUT_TOPICS = os.environ.get("INPUT_TOPICS", "netflow-raw,syslog-raw,ise-raw").split(",")
OUTPUT_SUFFIX = os.environ.get("OUTPUT_TOPIC_SUFFIX", "-sanitized")
REJECTED_SUFFIX = os.environ.get("REJECTED_TOPIC_SUFFIX", "-rejected")
STRICT_MODE = os.environ.get("STRICT_MODE", "true").lower() == "true"
KAFKA_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "sasp-sanitizer")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9091"))

TOPIC_SANITIZER_MAP = {
    "netflow-raw": NetFlowSanitizer,
    "syslog-raw": SyslogSanitizer,
    "ise-raw": ISESanitizer,
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("sanitizer_service")

# ---------------------------------------------------------------------------
# Metrics (in-memory, exposed via /health)
# ---------------------------------------------------------------------------

stats = {
    "events_consumed": 0,
    "events_sanitized": 0,
    "events_rejected": 0,
    "errors": 0,
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
# Sanitizer service
# ---------------------------------------------------------------------------


_PROTO_MAP = {"TCP": "tcp", "UDP": "udp", "ICMP": "icmp", "tcp": "tcp", "udp": "udp", "icmp": "icmp"}

# ---------------------------------------------------------------------------
# Rolling window state for aggregate feature computation
# ---------------------------------------------------------------------------
WINDOW_SECONDS = 60

# Per-source-IP outbound flow window: src_ip -> [{ts, dst_ip, dst_port, bytes}]
_src_window: dict[str, list[dict]] = {}
# Per-destination-IP inbound byte tracking: dst_ip -> [(ts, bytes)]
_inbound_bytes: dict[str, list[tuple[float, int]]] = {}
_window_lock = threading.Lock()


def _compute_netflow_features(record: dict) -> dict:
    """Compute the 15 ML features inline for a single GoFlow2 record.

    Uses a 60-second rolling window keyed by source IP for aggregate features.
    Memory bound: ~5MB at 10K flows/min (60s window x ~500 bytes/flow).
    """
    packets = max(int(record.get("packets", 1)), 1)
    bytes_total = max(int(record.get("bytes", 0)), 0)
    bytes_per_packet = bytes_total / packets

    t_start = record.get("time_flow_start_ns", 0)
    t_end = record.get("time_flow_end_ns", 0)
    duration = max((float(t_end) - float(t_start)) / 1e9, 0.0)

    src_port = int(record.get("src_port", 0))
    dst_port = int(record.get("dst_port", 0))

    # Port categories: 0=well-known, 1=registered, 2=dynamic
    src_cat = 0 if src_port <= 1023 else (1 if src_port <= 49151 else 2)
    dst_cat = 0 if dst_port <= 1023 else (1 if dst_port <= 49151 else 2)

    # Protocol one-hot
    proto = record.get("proto", "")
    proto_key = _PROTO_MAP.get(str(proto)) if isinstance(proto, str) else _PROTO_MAP.get({6: "tcp", 17: "udp", 1: "icmp"}.get(int(proto), ""), "")
    proto_tcp = 1.0 if proto_key == "tcp" else 0.0
    proto_udp = 1.0 if proto_key == "udp" else 0.0
    proto_icmp = 1.0 if proto_key == "icmp" else 0.0
    proto_other = 1.0 if proto_key not in ("tcp", "udp", "icmp") else 0.0

    # --- Aggregate features from rolling window ---
    src_ip = str(record.get("src_addr", "unknown"))
    dst_ip = str(record.get("dst_addr", "unknown"))
    now = time.time()
    cutoff = now - WINDOW_SECONDS

    with _window_lock:
        # Evict stale entries from source window
        if src_ip in _src_window:
            _src_window[src_ip] = [
                f for f in _src_window[src_ip] if f["ts"] > cutoff
            ]
        else:
            _src_window[src_ip] = []

        # Evict stale entries from inbound tracking
        for ip_key in (src_ip, dst_ip):
            if ip_key in _inbound_bytes:
                _inbound_bytes[ip_key] = [
                    e for e in _inbound_bytes[ip_key] if e[0] > cutoff
                ]

        # Record this flow
        _src_window[src_ip].append({
            "ts": now,
            "dst_ip": dst_ip,
            "dst_port": dst_port,
            "bytes": bytes_total,
        })
        _inbound_bytes.setdefault(dst_ip, []).append((now, bytes_total))

        # Snapshot for aggregate computation
        src_flows = list(_src_window[src_ip])
        inbound_entries = list(_inbound_bytes.get(src_ip, []))

    # Compute aggregates from snapshot
    n_flows = len(src_flows)
    dst_ips = [f["dst_ip"] for f in src_flows]
    dst_ports = [f["dst_port"] for f in src_flows]
    bytes_out = sum(f["bytes"] for f in src_flows)
    bytes_in = sum(b for _, b in inbound_entries) if inbound_entries else bytes_out

    # Shannon entropy of destination IPs
    if len(dst_ips) > 1:
        counts = Counter(dst_ips)
        total = len(dst_ips)
        entropy = -sum(
            (c / total) * math.log2(c / total)
            for c in counts.values() if c > 0
        )
    else:
        entropy = 0.0

    ratio = float(bytes_out) / max(bytes_in, 1)

    return {
        "feat_bytes_per_packet": float(bytes_per_packet),
        "feat_duration_seconds": float(duration),
        "feat_src_port_category": float(src_cat),
        "feat_dst_port_category": float(dst_cat),
        "feat_proto_tcp": proto_tcp,
        "feat_proto_udp": proto_udp,
        "feat_proto_icmp": proto_icmp,
        "feat_proto_other": proto_other,
        "feat_bytes_total": float(bytes_total),
        "feat_packets_total": float(packets),
        "feat_flows_per_src_ip": float(n_flows),
        "feat_unique_dst_ips_per_src": float(len(set(dst_ips))),
        "feat_unique_dst_ports_per_src": float(len(set(dst_ports))),
        "feat_bytes_out_vs_in_ratio": float(ratio),
        "feat_dst_ip_entropy": float(entropy),
    }


class SanitizerService:
    """Kafka-backed sanitizer that routes messages to the correct sanitizer."""

    def __init__(self):
        self.consumer = KafkaConsumer(
            *INPUT_TOPICS,
            bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
            group_id=KAFKA_GROUP,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            consumer_timeout_ms=1000,
        )

        self.producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        # Instantiate one sanitizer per topic
        self._sanitizers = {}
        for topic, cls in TOPIC_SANITIZER_MAP.items():
            self._sanitizers[topic] = cls(strict_mode=STRICT_MODE)

        self._shutdown = threading.Event()

    def get_sanitizer(self, topic: str) -> BaseSanitizer:
        """Return the sanitizer instance for the given topic."""
        return self._sanitizers.get(topic)

    def process_message(self, message):
        """Route a single Kafka message through the correct sanitizer."""
        topic = message.topic
        sanitizer = self.get_sanitizer(topic)

        if sanitizer is None:
            logger.warning("No sanitizer registered for topic %s", topic)
            with stats_lock:
                stats["errors"] += 1
            return

        try:
            result = sanitizer.sanitize(message.value)
        except Exception:
            logger.exception("Sanitization error on topic %s", topic)
            with stats_lock:
                stats["errors"] += 1
            return

        with stats_lock:
            stats["events_consumed"] += 1

        if result.is_clean or not STRICT_MODE:
            # Produce to sanitized topic (strip -raw suffix first)
            base_topic = topic.removesuffix("-raw")
            out_topic = base_topic + OUTPUT_SUFFIX
            output = result.sanitized
            # Enrich NetFlow records with pre-computed ML features
            if topic == "netflow-raw":
                output = {**output, **_compute_netflow_features(output)}
            self.producer.send(out_topic, value=output)
            with stats_lock:
                stats["events_sanitized"] += 1
        else:
            # Produce to rejected topic (strip -raw suffix first)
            base_topic = topic.removesuffix("-raw")
            rejected_topic = base_topic + REJECTED_SUFFIX
            rejected_payload = {
                "original": result.original,
                "threats": result.threats_detected,
                "modifications": result.modifications,
            }
            self.producer.send(rejected_topic, value=rejected_payload)
            with stats_lock:
                stats["events_rejected"] += 1

    def run(self):
        """Main consumer loop with graceful shutdown support."""
        logger.info(
            "Starting sanitizer service — Kafka=%s topics=%s strict=%s",
            KAFKA_BOOTSTRAP, INPUT_TOPICS, STRICT_MODE,
        )

        try:
            while not self._shutdown.is_set():
                for message in self.consumer:
                    self.process_message(message)
                    if self._shutdown.is_set():
                        break
        finally:
            self.shutdown()

    def shutdown(self):
        """Clean shutdown of consumer and producer."""
        self._shutdown.set()
        try:
            self.producer.flush(timeout=5)
            self.producer.close(timeout=5)
        except Exception:
            logger.exception("Error closing producer")
        try:
            self.consumer.close()
        except Exception:
            logger.exception("Error closing consumer")
        logger.info("Sanitizer service stopped.")


# ---------------------------------------------------------------------------
# Module-level entry point
# ---------------------------------------------------------------------------

_service = None


def handle_signal(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    logger.info("Received signal %d, shutting down...", signum)
    if _service is not None:
        _service.shutdown()


def run():
    """Main entry point: start health server and run sanitizer service."""
    global _service

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    health_server = start_health_server()

    _service = SanitizerService()
    try:
        _service.run()
    finally:
        health_server.shutdown()
