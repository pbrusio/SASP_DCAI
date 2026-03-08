"""Export NetFlow training data from Kafka to Parquet or JSONL.

Connects to a Kafka topic populated by GoFlow2, extracts and normalises
NetFlow fields, and writes the result to a Parquet or JSON-Lines file
suitable for ML training pipelines.
"""

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import pyarrow  # noqa: F401 – needed by pandas for parquet I/O
except ImportError:
    pyarrow = None

from kafka import KafkaConsumer, TopicPartition

logger = logging.getLogger(__name__)

NETFLOW_FIELDS = [
    "src_ip",
    "dst_ip",
    "src_port",
    "dst_port",
    "protocol",
    "bytes",
    "packets",
    "duration",
    "flags",
]

# GoFlow2 v2 JSON key -> normalised field name
_GOFLOW2_MAP = {
    "src_addr": "src_ip",
    "dst_addr": "dst_ip",
    "src_port": "src_port",
    "dst_port": "dst_port",
    "proto": "protocol",
    "bytes": "bytes",
    "packets": "packets",
    "tcp_flags": "flags",
}


def extract_netflow_fields(record: dict) -> dict:
    """Extract and normalise NetFlow fields from a GoFlow2 JSON record."""
    out: dict = {}
    for goflow_key, field in _GOFLOW2_MAP.items():
        out[field] = record.get(goflow_key)

    # Duration derived from nanosecond timestamps (GoFlow2 v2 uses _ns suffix)
    flow_end = record.get("time_flow_end_ns", 0)
    flow_start = record.get("time_flow_start_ns", 0)
    out["duration"] = (flow_end - flow_start) / 1e9  # ns -> seconds

    return out


def create_consumer(args: argparse.Namespace) -> KafkaConsumer:
    """Create a KafkaConsumer using manual partition assignment.

    When *--start-time* is provided the consumer seeks to the earliest
    offset whose timestamp is >= the requested time.
    """
    consumer = KafkaConsumer(
        bootstrap_servers=args.bootstrap_servers,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=5000,
    )

    # Discover partitions and assign them manually
    partitions = consumer.partitions_for_topic(args.topic)
    if not partitions:
        logger.error("No partitions found for topic %s", args.topic)
        sys.exit(1)

    tps = [TopicPartition(args.topic, p) for p in sorted(partitions)]
    consumer.assign(tps)

    if args.start_time:
        ts_ms = int(args.start_time.timestamp() * 1000)
        timestamps = {tp: ts_ms for tp in tps}
        offsets = consumer.offsets_for_times(timestamps)
        for tp, offset_and_ts in offsets.items():
            if offset_and_ts is not None:
                consumer.seek(tp, offset_and_ts.offset)
            else:
                # No messages at or after the requested timestamp
                consumer.seek_to_end(tp)
    else:
        consumer.seek_to_beginning()

    return consumer


def export_records(consumer: KafkaConsumer, args: argparse.Namespace) -> list:
    """Consume records up to *--max-records* or *--end-time*."""
    records: list[dict] = []
    end_ts_ms = int(args.end_time.timestamp() * 1000) if args.end_time else None
    max_records = args.max_records if args.max_records > 0 else float("inf")

    for message in consumer:
        if end_ts_ms is not None and message.timestamp > end_ts_ms:
            break
        if len(records) >= max_records:
            break

        try:
            row = extract_netflow_fields(message.value)
            records.append(row)
        except Exception:
            logger.warning("Skipping malformed record at offset %s", message.offset)

    return records


def write_output(records: list[dict], args: argparse.Namespace) -> None:
    """Write extracted records to disk as Parquet or JSON-Lines."""
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    basename = f"{args.topic}_{timestamp_tag}"

    if args.label:
        for rec in records:
            rec["label"] = args.label

    if args.format == "parquet":
        if pd is None or pyarrow is None:
            logger.error(
                "pandas and pyarrow are required for parquet output. "
                "Install them with: pip install 'sasp[ml]'"
            )
            sys.exit(1)
        outpath = os.path.join(args.output_dir, f"{basename}.parquet")
        df = pd.DataFrame(records)
        df.to_parquet(outpath, compression="snappy", index=False)
    else:
        outpath = os.path.join(args.output_dir, f"{basename}.jsonl")
        with open(outpath, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")

    logger.info("Wrote %d records to %s", len(records), outpath)


def print_summary(records: list[dict]) -> None:
    """Print a human-readable summary of the exported data."""
    if not records:
        print("No records exported.")
        return

    print(f"Records exported : {len(records)}")

    durations = [r.get("duration", 0) for r in records]
    print(f"Duration range   : {min(durations)}s – {max(durations)}s")

    src_ips = {r.get("src_ip") for r in records}
    print(f"Unique source IPs: {len(src_ips)}")

    proto_counts = Counter(r.get("protocol") for r in records)
    print("Top 10 protocols :")
    for proto, count in proto_counts.most_common(10):
        print(f"  {proto}: {count}")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Export NetFlow training data from Kafka.",
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="Kafka topic to consume from.",
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092"),
        help="Kafka bootstrap servers (default: $KAFKA_BOOTSTRAP_SERVERS or <S2_IP>:9092).",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for output files (default: current directory).",
    )
    parser.add_argument(
        "--start-time",
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
        default=None,
        help="Start time in ISO 8601 format (e.g. 2025-01-01T00:00:00).",
    )
    parser.add_argument(
        "--end-time",
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc),
        default=None,
        help="End time in ISO 8601 format.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=0,
        help="Maximum number of records to export (0 = unlimited).",
    )
    parser.add_argument(
        "--format",
        choices=["parquet", "jsonl"],
        default="parquet",
        help="Output format (default: parquet).",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Optional label to add to every record (e.g. 'benign', 'attack').",
    )
    return parser


def main() -> None:
    """Entry point for the training-data export utility."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    logger.info("Connecting to Kafka at %s, topic=%s", args.bootstrap_servers, args.topic)
    consumer = create_consumer(args)

    logger.info("Exporting records …")
    records = export_records(consumer, args)
    consumer.close()

    if records:
        write_output(records, args)
    print_summary(records)


if __name__ == "__main__":
    main()
