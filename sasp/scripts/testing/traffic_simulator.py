"""SASP Traffic Simulator — inject crafted test records into Kafka

Produces controlled attack/baseline scenarios to validate the detection
pipeline end-to-end: Kafka -> Sanitizer -> Morpheus -> Triton -> Bridge -> Agents -> Splunk.

Usage:
    # Dry run — print records to stdout
    python -m sasp.scripts.testing.traffic_simulator --dry-run --scenarios all

    # Inject to sanitized topic (Layer 1: Morpheus -> Triton -> Bridge -> Agents)
    python -m sasp.scripts.testing.traffic_simulator --target sanitized --scenarios large_exfil udp_flood

    # Inject to raw topic (Layer 2: Sanitizer -> Morpheus -> ...)
    python -m sasp.scripts.testing.traffic_simulator --target raw --scenarios all

    # With verification (Layer 2 only)
    python -m sasp.scripts.testing.traffic_simulator --target raw --scenarios large_exfil --verify

Safety:
    - Max 20 records per scenario per run (hard cap)
    - Max 10 records/second
    - Source/dest IPs in 100.64.0.0/10 (IANA shared address space)
    - Refuses to send to <MGMT_SUBNET>/24 (server subnet)
"""

import argparse
import ipaddress
import json
import logging
import sys
import time
import uuid

from .scenarios import (
    SCENARIOS,
    generate_raw_record,
    generate_sanitized_record,
    list_scenarios,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety constraints
# ---------------------------------------------------------------------------

MAX_BATCH_SIZE = 20
MAX_RATE_LIMIT = 10  # records/second
SERVER_SUBNET = ipaddress.IPv4Network("<MGMT_SUBNET>/24")


def _validate_ip(ip: str) -> bool:
    """Return True if the IP is safe (not in the server subnet)."""
    try:
        return ipaddress.IPv4Address(ip) not in SERVER_SUBNET
    except (ipaddress.AddressValueError, ValueError):
        return True  # Non-IPv4 addresses are allowed through


def _validate_record(record: dict) -> None:
    """Raise ValueError if a record targets the server subnet."""
    for field in ("src_addr", "dst_addr"):
        ip = record.get(field, "")
        if not _validate_ip(ip):
            raise ValueError(
                f"SAFETY: {field}={ip} is in server subnet {SERVER_SUBNET}. "
                "Test traffic must NOT target infrastructure IPs."
            )


# ---------------------------------------------------------------------------
# Core production logic
# ---------------------------------------------------------------------------

def produce_scenario(
    scenario_name: str,
    target: str,
    batch_size: int,
    rate_limit: float,
    run_id: str,
    bootstrap: str,
    dry_run: bool = False,
    producer: object | None = None,
) -> list[dict]:
    """Produce records for a single scenario.

    Returns the list of records sent (or printed in dry-run mode).
    """
    batch_size = min(batch_size, MAX_BATCH_SIZE)
    rate_limit = min(rate_limit, MAX_RATE_LIMIT)
    interval = 1.0 / rate_limit if rate_limit > 0 else 0.1

    scenario = SCENARIOS[scenario_name]
    topic = "netflow-sanitized" if target == "sanitized" else "netflow-raw"
    records_sent: list[dict] = []

    logger.info(
        "Scenario %s (%s): %d records -> topic=%s",
        scenario["id"], scenario_name, batch_size, topic,
    )

    for i in range(batch_size):
        if target == "sanitized":
            record = generate_sanitized_record(scenario_name, i)
        else:
            record = generate_raw_record(scenario_name, i)

        # Tag every record for Splunk traceability
        record["test_scenario"] = scenario_name
        record["test_run_id"] = run_id
        record["test_scenario_id"] = scenario["id"]

        _validate_record(record)

        if dry_run:
            print(json.dumps(record, indent=2, default=str))
        elif producer is not None:
            producer.send(topic, value=record)
            logger.debug("Sent record %d/%d to %s", i + 1, batch_size, topic)

        records_sent.append(record)

        if i < batch_size - 1:
            time.sleep(interval)

    if producer is not None and not dry_run:
        producer.flush()

    return records_sent


def verify_sanitized_output(
    run_id: str,
    bootstrap: str,
    timeout_seconds: int = 30,
) -> list[dict]:
    """Read back from netflow-sanitized and filter for our run_id.

    Only used for --target raw --verify to confirm sanitizer processed
    the records and produced feat_* fields.
    """
    from kafka import KafkaConsumer

    consumer = KafkaConsumer(
        "netflow-sanitized",
        bootstrap_servers=bootstrap.split(","),
        group_id=f"sasp-test-verify-{run_id[:8]}",
        auto_offset_reset="earliest",
        consumer_timeout_ms=timeout_seconds * 1000,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    found: list[dict] = []
    deadline = time.time() + timeout_seconds
    for message in consumer:
        if time.time() > deadline:
            break
        data = message.value
        if data.get("test_run_id") == run_id:
            found.append(data)
            has_features = "feat_bytes_per_packet" in data
            if has_features:
                logger.info(
                    "Verified: %s feat_bytes_per_packet=%.2f feat_flows_per_src_ip=%.1f",
                    data.get("test_scenario", "?"),
                    data.get("feat_bytes_per_packet", -1),
                    data.get("feat_flows_per_src_ip", -1),
                )

    consumer.close()
    return found


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SASP Traffic Simulator — inject test scenarios into Kafka",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run --scenarios all
  %(prog)s --target sanitized --scenarios large_exfil udp_flood
  %(prog)s --target raw --scenarios all --verify
  %(prog)s --list
        """,
    )
    parser.add_argument(
        "--bootstrap",
        default="<S2_IP>:9092",
        help="Kafka bootstrap servers (default: <S2_IP>:9092)",
    )
    parser.add_argument(
        "--target",
        choices=["raw", "sanitized"],
        default="sanitized",
        help="Injection point: 'raw' (Layer 2) or 'sanitized' (Layer 1)",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["all"],
        help="Scenario names to run (space-separated), or 'all'",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=3,
        help=f"Records per scenario (default: 3, max: {MAX_BATCH_SIZE})",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=5.0,
        help=f"Max records/second (default: 5, max: {MAX_RATE_LIMIT})",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="(Layer 2 only) Read back from netflow-sanitized to verify feat_* fields",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print records to stdout instead of producing to Kafka",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_scenarios",
        help="List available scenarios and exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the traffic simulator."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = parse_args(argv)

    if args.list_scenarios:
        print("Available scenarios:\n")
        for name in list_scenarios():
            s = SCENARIOS[name]
            det = "DETECT" if s["expected_detection"] else "BENIGN"
            print(f"  {s['id']:4s}  {name:22s}  [{det}]  {s['description']}")
        return

    # Resolve scenario names
    if "all" in args.scenarios:
        scenario_names = list_scenarios()
    else:
        scenario_names = args.scenarios
        for name in scenario_names:
            if name not in SCENARIOS:
                logger.error("Unknown scenario: %s", name)
                logger.info("Available: %s", ", ".join(list_scenarios()))
                sys.exit(1)

    run_id = str(uuid.uuid4())
    batch_size = min(args.batch_size, MAX_BATCH_SIZE)
    rate_limit = min(args.rate_limit, MAX_RATE_LIMIT)

    print(f"{'=' * 60}")
    print("SASP Traffic Simulator")
    print(f"  Run ID:     {run_id}")
    print(f"  Target:     {args.target}")
    print(f"  Bootstrap:  {args.bootstrap}")
    print(f"  Scenarios:  {', '.join(scenario_names)}")
    print(f"  Batch size: {batch_size}")
    print(f"  Rate limit: {rate_limit} rec/s")
    print(f"  Dry run:    {args.dry_run}")
    print(f"{'=' * 60}")

    # Create Kafka producer (unless dry-run)
    producer = None
    if not args.dry_run:
        from kafka import KafkaProducer

        producer = KafkaProducer(
            bootstrap_servers=args.bootstrap.split(","),
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )

    total_sent = 0
    for name in scenario_names:
        records = produce_scenario(
            scenario_name=name,
            target=args.target,
            batch_size=batch_size,
            rate_limit=rate_limit,
            run_id=run_id,
            bootstrap=args.bootstrap,
            dry_run=args.dry_run,
            producer=producer,
        )
        total_sent += len(records)

    if producer is not None:
        producer.close()

    action = "printed" if args.dry_run else "sent"
    print(f"\nTotal records {action}: {total_sent}")
    print(f"Run ID: {run_id}")

    # Verification (Layer 2 only)
    if args.verify and args.target == "raw" and not args.dry_run:
        print("\nVerifying sanitized output (30s timeout)...")
        found = verify_sanitized_output(run_id, args.bootstrap)
        print(f"Found {len(found)} sanitized records for this run")

    # Print Splunk queries for verification
    if not args.dry_run:
        print("\nSplunk verification queries:")
        print(f'  index=sasp_investigations test_run_id="{run_id}"')
        print("    | table investigation_id, source_ip, score, severity, test_scenario")
        print()
        print(f'  index=sasp_investigations test_scenario=baseline test_run_id="{run_id}"')
        print("    | stats count  (expect 0 for negative controls)")


if __name__ == "__main__":
    main()
