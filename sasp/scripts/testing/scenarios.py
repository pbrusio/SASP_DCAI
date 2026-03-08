"""SASP Detection Test Scenarios

Attack scenario definitions for testing the detection pipeline.
Each scenario includes both raw GoFlow2 records and expected feat_* overrides
for Layer 1 (sanitized) and Layer 2 (raw) injection points.

Source IPs: 100.64.0.x (IANA shared address space — clearly synthetic)
Dest IPs:   100.64.1.x (same)
"""

import time
from typing import Any

# Threshold from Morpheus pipeline
ANOMALY_THRESHOLD = 0.05

# Synthetic IP ranges (IANA shared address space - 100.64.0.0/10)
SRC_IP_BASE = "100.64.0"
DST_IP_BASE = "100.64.1"

# Feature columns (must match Morpheus pipeline FEATURE_COLUMNS)
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
# Record factories
# ---------------------------------------------------------------------------

def _ts_ns(offset_seconds: float = 0.0) -> int:
    """Return current timestamp in nanoseconds with optional offset."""
    return int((time.time() + offset_seconds) * 1e9)


def _make_raw_record(
    src_ip: str,
    dst_ip: str,
    src_port: int,
    dst_port: int,
    proto: int,
    bytes_val: int,
    packets: int,
    duration_seconds: float,
    **extra: Any,
) -> dict:
    """Create a GoFlow2-format raw NetFlow record."""
    t_start = _ts_ns()
    t_end = _ts_ns(duration_seconds)
    record = {
        "type": 5,
        "sampler_address": "100.64.0.254",
        "src_addr": src_ip,
        "dst_addr": dst_ip,
        "src_port": src_port,
        "dst_port": dst_port,
        "proto": proto,
        "bytes": bytes_val,
        "packets": packets,
        "time_flow_start_ns": t_start,
        "time_flow_end_ns": t_end,
    }
    record.update(extra)
    return record


def _make_sanitized_record(
    raw: dict,
    feat_overrides: dict | None = None,
) -> dict:
    """Create a sanitized record with feat_* fields from raw + overrides.

    Computes per-flow features from the raw record, then applies overrides
    for aggregate features.
    """
    packets = max(int(raw.get("packets", 1)), 1)
    bytes_total = max(int(raw.get("bytes", 0)), 0)
    bytes_per_packet = bytes_total / packets

    t_start = raw.get("time_flow_start_ns", 0)
    t_end = raw.get("time_flow_end_ns", 0)
    duration = max((float(t_end) - float(t_start)) / 1e9, 0.0)

    src_port = int(raw.get("src_port", 0))
    dst_port = int(raw.get("dst_port", 0))
    proto = int(raw.get("proto", 0))

    src_cat = 0 if src_port <= 1023 else (1 if src_port <= 49151 else 2)
    dst_cat = 0 if dst_port <= 1023 else (1 if dst_port <= 49151 else 2)

    proto_tcp = 1.0 if proto == 6 else 0.0
    proto_udp = 1.0 if proto == 17 else 0.0
    proto_icmp = 1.0 if proto == 1 else 0.0
    proto_other = 1.0 if proto not in (6, 17, 1) else 0.0

    features = {
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
        # Aggregate features — defaults for single-flow (no window context)
        "feat_flows_per_src_ip": 1.0,
        "feat_unique_dst_ips_per_src": 1.0,
        "feat_unique_dst_ports_per_src": 1.0,
        "feat_bytes_out_vs_in_ratio": 1.0,
        "feat_dst_ip_entropy": 0.0,
    }

    if feat_overrides:
        features.update(feat_overrides)

    return {**raw, **features}


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict] = {
    # ─── Per-flow anomaly scenarios (T01-T06) ─────────────────────────────

    "large_exfil": {
        "id": "T01",
        "description": "Large data exfiltration — extreme bytes_per_packet and bytes_total",
        "expected_detection": True,
        "expected_mse": "> 0.5",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.1",
            dst_ip=f"{DST_IP_BASE}.1",
            src_port=54321,
            dst_port=443,
            proto=6,
            bytes_val=50_000_000,
            packets=1000,
            duration_seconds=10.0,
        ),
        "feat_overrides": {},
    },

    "udp_flood": {
        "id": "T02",
        "description": "UDP flood — tiny packets, high packet count",
        "expected_detection": True,
        "expected_mse": "> 0.3",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.2",
            dst_ip=f"{DST_IP_BASE}.2",
            src_port=12345,
            dst_port=53,
            proto=17,
            bytes_val=40_000,
            packets=5000,
            duration_seconds=1.0,
        ),
        "feat_overrides": {},
    },

    "icmp_tunnel": {
        "id": "T03",
        "description": "ICMP tunnel — large ICMP payloads",
        "expected_detection": True,
        "expected_mse": "> 0.2",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.3",
            dst_ip=f"{DST_IP_BASE}.3",
            src_port=0,
            dst_port=0,
            proto=1,
            bytes_val=140_000,
            packets=100,
            duration_seconds=5.0,
        ),
        "feat_overrides": {},
    },

    "long_c2": {
        "id": "T04",
        "description": "Long C2 session — 5-min duration on non-standard port",
        "expected_detection": True,
        "expected_mse": "> 0.1",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.4",
            dst_ip=f"{DST_IP_BASE}.4",
            src_port=55555,
            dst_port=4444,
            proto=6,
            bytes_val=5000,
            packets=50,
            duration_seconds=300.0,
        ),
        "feat_overrides": {},
    },

    "syn_burst": {
        "id": "T05",
        "description": "SYN burst — extreme packet rate in sub-second window",
        "expected_detection": True,
        "expected_mse": "> 0.3",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.5",
            dst_ip=f"{DST_IP_BASE}.5",
            src_port=44444,
            dst_port=80,
            proto=6,
            bytes_val=200_000,
            packets=5000,
            duration_seconds=0.1,
        ),
        "feat_overrides": {},
    },

    "proto_other": {
        "id": "T06",
        "description": "Rare protocol (GRE) — triggers proto_other anomaly",
        "expected_detection": True,
        "expected_mse": "> 0.2",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.6",
            dst_ip=f"{DST_IP_BASE}.6",
            src_port=0,
            dst_port=0,
            proto=47,  # GRE
            bytes_val=1_000_000,
            packets=100,
            duration_seconds=10.0,
        ),
        "feat_overrides": {},
    },

    # ─── Negative controls (T07-T08) ─────────────────────────────────────

    "baseline": {
        "id": "T07",
        "description": "Normal HTTPS traffic — negative control, should NOT trigger",
        "expected_detection": False,
        "expected_mse": "< 0.05",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.7",
            dst_ip=f"{DST_IP_BASE}.7",
            src_port=54321,
            dst_port=443,
            proto=6,
            bytes_val=1500,
            packets=10,
            duration_seconds=1.0,
        ),
        "feat_overrides": {},
    },

    "near_threshold": {
        "id": "T08",
        "description": "Near-threshold traffic — boundary test, should NOT trigger",
        "expected_detection": False,
        "expected_mse": "~0.048",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.8",
            dst_ip=f"{DST_IP_BASE}.8",
            src_port=49152,
            dst_port=80,
            proto=6,
            bytes_val=5000,
            packets=20,
            duration_seconds=2.0,
        ),
        "feat_overrides": {},
    },

    # ─── Aggregate-feature scenarios (T09-T11, requires sanitizer fix) ───

    "port_scan": {
        "id": "T09",
        "description": "Horizontal port scan — many unique dst_ports from one source",
        "expected_detection": True,
        "expected_mse": "> 0.2 (with aggregate fix)",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.9",
            dst_ip=f"{DST_IP_BASE}.9",
            src_port=54321,
            dst_port=22,  # Varies per batch record
            proto=6,
            bytes_val=60,
            packets=1,
            duration_seconds=0.01,
        ),
        "feat_overrides": {
            "feat_flows_per_src_ip": 100.0,
            "feat_unique_dst_ports_per_src": 50.0,
            "feat_unique_dst_ips_per_src": 1.0,
            "feat_dst_ip_entropy": 0.0,
        },
        "batch_vary_field": "dst_port",
        "batch_vary_range": (1, 1024),
    },

    "c2_fanout": {
        "id": "T10",
        "description": "C2 callback fan-out — many unique dest IPs from one source",
        "expected_detection": True,
        "expected_mse": "> 0.2 (with aggregate fix)",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.10",
            dst_ip=f"{DST_IP_BASE}.10",  # Varies per batch record
            src_port=55555,
            dst_port=443,
            proto=6,
            bytes_val=200,
            packets=2,
            duration_seconds=0.5,
        ),
        "feat_overrides": {
            "feat_flows_per_src_ip": 50.0,
            "feat_unique_dst_ips_per_src": 20.0,
            "feat_unique_dst_ports_per_src": 1.0,
            "feat_dst_ip_entropy": 4.0,
        },
        "batch_vary_field": "dst_addr",
        "batch_vary_values": [f"{DST_IP_BASE}.{i}" for i in range(1, 21)],
    },

    "data_exfil_ratio": {
        "id": "T11",
        "description": "Asymmetric byte ratio — high out/in from one source",
        "expected_detection": True,
        "expected_mse": "> 0.2 (with aggregate fix)",
        "raw_factory": lambda: _make_raw_record(
            src_ip=f"{SRC_IP_BASE}.11",
            dst_ip=f"{DST_IP_BASE}.11",
            src_port=54321,
            dst_port=443,
            proto=6,
            bytes_val=10_000_000,
            packets=1000,
            duration_seconds=5.0,
        ),
        "feat_overrides": {
            "feat_bytes_out_vs_in_ratio": 100.0,
            "feat_flows_per_src_ip": 10.0,
        },
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_scenario(name: str) -> dict:
    """Return a scenario definition by name, raising KeyError if not found."""
    return SCENARIOS[name]


def list_scenarios() -> list[str]:
    """Return sorted list of all scenario names."""
    return sorted(SCENARIOS.keys())


def generate_raw_record(name: str, batch_index: int = 0) -> dict:
    """Generate a raw GoFlow2 record for the named scenario.

    For scenarios with batch_vary_field, the record is varied
    based on batch_index (e.g. different dst_port per record).
    """
    scenario = SCENARIOS[name]
    record = scenario["raw_factory"]()

    # Apply batch variation if defined
    if "batch_vary_field" in scenario:
        field = scenario["batch_vary_field"]
        if "batch_vary_range" in scenario:
            lo, hi = scenario["batch_vary_range"]
            record[field] = lo + (batch_index % (hi - lo))
        elif "batch_vary_values" in scenario:
            values = scenario["batch_vary_values"]
            record[field] = values[batch_index % len(values)]

    return record


def generate_sanitized_record(name: str, batch_index: int = 0) -> dict:
    """Generate a sanitized record with feat_* fields for the named scenario.

    Computes per-flow features from the raw record, then applies the
    scenario's feat_overrides for aggregate features.
    """
    scenario = SCENARIOS[name]
    raw = generate_raw_record(name, batch_index)
    return _make_sanitized_record(raw, scenario.get("feat_overrides"))
