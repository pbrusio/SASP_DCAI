"""SASP NetFlow Feature Engineering — transforms raw GoFlow2 records into ML feature vectors."""

import argparse
import json
import logging
import math
import pickle
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Port categories
# ---------------------------------------------------------------------------
_PORT_WELL_KNOWN = 1023
_PORT_REGISTERED = 49151


def port_category(port: int) -> int:
    """Classify a port number into well-known (0), registered (1), or dynamic (2)."""
    if port <= _PORT_WELL_KNOWN:
        return 0
    if port <= _PORT_REGISTERED:
        return 1
    return 2


# ---------------------------------------------------------------------------
# Protocol one-hot helpers
# ---------------------------------------------------------------------------
_PROTO_INT_MAP: Dict[int, str] = {6: "tcp", 17: "udp", 1: "icmp"}
_PROTO_STR_MAP: Dict[str, str] = {"tcp": "tcp", "udp": "udp", "icmp": "icmp"}


def protocol_onehot(proto: Any) -> Dict[str, int]:
    """Return a dict of one-hot flags for TCP, UDP, ICMP, and other.

    Handles both integer protocol numbers (6, 17, 1) and string names
    ("TCP", "UDP", "ICMP") as produced by GoFlow2 v2.
    """
    flags = {"proto_tcp": 0, "proto_udp": 0, "proto_icmp": 0, "proto_other": 0}
    if isinstance(proto, str):
        key = _PROTO_STR_MAP.get(proto.lower())
    else:
        key = _PROTO_INT_MAP.get(int(proto))
    if key:
        flags[f"proto_{key}"] = 1
    else:
        flags["proto_other"] = 1
    return flags


# ---------------------------------------------------------------------------
# Shannon entropy
# ---------------------------------------------------------------------------
def shannon_entropy(values: List[Any]) -> float:
    """Compute Shannon entropy of a list of values."""
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    return -sum(
        (c / total) * math.log2(c / total) for c in counts.values() if c > 0
    )


# ---------------------------------------------------------------------------
# Feature extractor
# ---------------------------------------------------------------------------
class NetFlowFeatureExtractor:
    """Transform raw GoFlow2 NetFlow records into ML-ready feature vectors.

    Parameters
    ----------
    window_seconds : int
        Aggregation window in seconds (default 300 = 5 min).
    """

    # Per-flow feature columns produced by _per_flow_features
    PER_FLOW_COLS: List[str] = [
        "bytes_per_packet",
        "duration_seconds",
        "src_port_category",
        "dst_port_category",
        "proto_tcp",
        "proto_udp",
        "proto_icmp",
        "proto_other",
        "bytes_total",
        "packets_total",
    ]

    # Aggregate feature columns produced by _aggregate_features
    AGG_COLS: List[str] = [
        "flows_per_src_ip",
        "unique_dst_ips_per_src",
        "unique_dst_ports_per_src",
        "bytes_out_vs_in_ratio",
        "dst_ip_entropy",
    ]

    ALL_FEATURE_COLS: List[str] = PER_FLOW_COLS + AGG_COLS

    def __init__(self, window_seconds: int = 300) -> None:
        self.window_seconds = window_seconds
        self._scaler: Optional[StandardScaler] = None

    # ----- per-flow --------------------------------------------------------
    @staticmethod
    def _per_flow_features(record: Dict[str, Any]) -> Dict[str, float]:
        """Extract per-flow features from a single GoFlow2 v2 record."""
        packets = max(int(record.get("packets", 1)), 1)
        bytes_total = max(int(record.get("bytes", 0)), 0)
        bytes_per_packet = bytes_total / packets

        # Duration — GoFlow2 v2 uses nanosecond timestamps
        t_start = record.get("time_flow_start_ns", 0)
        t_end = record.get("time_flow_end_ns", 0)
        duration = max((float(t_end) - float(t_start)) / 1e9, 0.0)

        src_port = int(record.get("src_port", 0))
        dst_port = int(record.get("dst_port", 0))
        proto = record.get("proto", 0)  # str ("TCP") or int (6)

        features: Dict[str, float] = {
            "bytes_per_packet": bytes_per_packet,
            "duration_seconds": duration,
            "src_port_category": float(port_category(src_port)),
            "dst_port_category": float(port_category(dst_port)),
            "bytes_total": float(bytes_total),
            "packets_total": float(packets),
        }
        features.update({k: float(v) for k, v in protocol_onehot(proto).items()})
        return features

    # ----- aggregate -------------------------------------------------------
    def _aggregate_features(
        self, records: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, float]]:
        """Compute per-source-IP aggregate features across the window.

        Returns a dict keyed by (src_ip, dst_ip, src_port, dst_port, proto)
        record-index -> aggregate feature dict.
        """
        # Group by source IP
        src_groups: Dict[str, List[Dict[str, Any]]] = {}
        for rec in records:
            src = str(rec.get("src_addr", "unknown"))
            src_groups.setdefault(src, []).append(rec)

        # Pre-compute per-source aggregates
        src_agg: Dict[str, Dict[str, float]] = {}
        for src_ip, group in src_groups.items():
            dst_ips = [str(r.get("dst_addr", "")) for r in group]
            dst_ports = [int(r.get("dst_port", 0)) for r in group]
            bytes_out = sum(int(r.get("bytes", 0)) for r in group)
            bytes_in = sum(
                int(r.get("bytes_in", 0)) or int(r.get("bytes", 0)) for r in group
            )
            ratio = bytes_out / max(bytes_in, 1)

            src_agg[src_ip] = {
                "flows_per_src_ip": float(len(group)),
                "unique_dst_ips_per_src": float(len(set(dst_ips))),
                "unique_dst_ports_per_src": float(len(set(dst_ports))),
                "bytes_out_vs_in_ratio": ratio,
                "dst_ip_entropy": shannon_entropy(dst_ips),
            }

        # Map back to each record by index
        per_record: Dict[str, Dict[str, float]] = {}
        for idx, rec in enumerate(records):
            src = str(rec.get("src_addr", "unknown"))
            per_record[str(idx)] = src_agg.get(src, {})
        return per_record

    # ----- main transform --------------------------------------------------
    def transform(self, records: List[Dict[str, Any]]) -> pd.DataFrame:
        """Transform a list of GoFlow2 records into a feature DataFrame.

        Parameters
        ----------
        records : list of dict
            Raw GoFlow2 JSON records.

        Returns
        -------
        pd.DataFrame
            One row per record with columns in ``ALL_FEATURE_COLS``.
        """
        if not records:
            return pd.DataFrame(columns=self.ALL_FEATURE_COLS)

        logger.info("Extracting features from %d records", len(records))

        # Per-flow
        rows: List[Dict[str, float]] = []
        for rec in records:
            rows.append(self._per_flow_features(rec))

        # Aggregate
        agg = self._aggregate_features(records)
        for idx, row in enumerate(rows):
            row.update(agg.get(str(idx), {}))

        df = pd.DataFrame(rows, columns=self.ALL_FEATURE_COLS)
        df = df.fillna(0.0)
        logger.info("Feature matrix shape: %s", df.shape)
        return df

    # ----- scaler ----------------------------------------------------------
    def fit(self, df: pd.DataFrame) -> "NetFlowFeatureExtractor":
        """Fit the StandardScaler on the given feature DataFrame."""
        self._scaler = StandardScaler()
        self._scaler.fit(df[self.ALL_FEATURE_COLS])
        logger.info("Scaler fitted on %d samples", len(df))
        return self

    def scale(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply fitted StandardScaler to the feature DataFrame."""
        if self._scaler is None:
            raise RuntimeError("Scaler not fitted. Call fit() first.")
        scaled = self._scaler.transform(df[self.ALL_FEATURE_COLS])
        return pd.DataFrame(scaled, columns=self.ALL_FEATURE_COLS, index=df.index)

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fit the scaler and transform in one step."""
        self.fit(df)
        return self.scale(df)

    def save_scaler(self, path: str) -> None:
        """Persist the fitted StandardScaler to a pickle file."""
        if self._scaler is None:
            raise RuntimeError("Scaler not fitted. Call fit() first.")
        with open(path, "wb") as fh:
            pickle.dump(self._scaler, fh)
        logger.info("Scaler saved to %s", path)

    def load_scaler(self, path: str) -> None:
        """Load a previously saved StandardScaler from a pickle file."""
        with open(path, "rb") as fh:
            self._scaler = pickle.load(fh)  # noqa: S301
        logger.info("Scaler loaded from %s", path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SASP NetFlow Feature Engineering CLI"
    )
    parser.add_argument(
        "--input", required=True, help="Path to input JSON file (list of GoFlow2 records)"
    )
    parser.add_argument(
        "--output", required=True, help="Path to output CSV/Parquet file"
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=5,
        help="Aggregation window in minutes (default: 5)",
    )
    parser.add_argument(
        "--scaler-output",
        default=None,
        help="Path to save fitted scaler pickle (optional)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point for feature engineering."""
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    input_path = Path(args.input)
    output_path = Path(args.output)

    with open(input_path) as fh:
        records: List[Dict[str, Any]] = json.load(fh)

    logger.info("Loaded %d records from %s", len(records), input_path)

    extractor = NetFlowFeatureExtractor(window_seconds=args.window_minutes * 60)
    df = extractor.transform(records)
    df_scaled = extractor.fit_transform(df)

    if output_path.suffix == ".parquet":
        df_scaled.to_parquet(output_path, index=False)
    else:
        df_scaled.to_csv(output_path, index=False)
    logger.info("Wrote %d rows to %s", len(df_scaled), output_path)

    if args.scaler_output:
        extractor.save_scaler(args.scaler_output)


if __name__ == "__main__":
    main()
