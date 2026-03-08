"""SASP Detection Scenario Integration Tests

Pytest wrappers for T01-T11 scenarios that:
1. Import scenario definitions from sasp.scripts.testing.scenarios
2. Produce to netflow-sanitized topic
3. Consume from morpheus-detections with a 30-second timeout
4. Assert: anomaly scenarios -> at least 1 detection; baselines -> 0 detections

Requires live Kafka and Triton infrastructure:
    KAFKA_BOOTSTRAP_SERVERS=<S2_IP>:9092 pytest -m "requires_kafka and requires_triton" -v
"""

import json
import os
import time
import uuid

import pytest

from sasp.scripts.testing.scenarios import (
    SCENARIOS,
    generate_sanitized_record,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kafka_bootstrap():
    """Kafka bootstrap servers from env or default."""
    return os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092")


@pytest.fixture
def test_run_id():
    """Unique run ID for isolating test records."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _produce_and_consume(
    bootstrap: str,
    run_id: str,
    scenario_name: str,
    batch_size: int = 3,
    consume_timeout_ms: int = 30_000,
) -> list[dict]:
    """Produce test records to netflow-sanitized and consume from morpheus-detections.

    Morpheus filters to anomalies only (MSE >= 0.05), so benign scenarios
    should produce zero messages on the output topic.
    """
    from kafka import KafkaConsumer, KafkaProducer

    # Produce test records
    producer = KafkaProducer(
        bootstrap_servers=bootstrap.split(","),
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )

    for i in range(batch_size):
        record = generate_sanitized_record(scenario_name, i)
        record["test_scenario"] = scenario_name
        record["test_run_id"] = run_id
        producer.send("netflow-sanitized", value=record)

    producer.flush()
    producer.close()

    # Consume detections with timeout
    consumer = KafkaConsumer(
        "morpheus-detections",
        bootstrap_servers=bootstrap.split(","),
        group_id=f"sasp-test-{run_id[:8]}",
        auto_offset_reset="latest",
        consumer_timeout_ms=consume_timeout_ms,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    detections: list[dict] = []
    deadline = time.time() + (consume_timeout_ms / 1000)

    for message in consumer:
        if time.time() > deadline:
            break
        data = message.value
        if data.get("test_run_id") == run_id:
            detections.append(data)

    consumer.close()
    return detections


# ---------------------------------------------------------------------------
# Per-flow anomaly scenarios (T01-T06)
# ---------------------------------------------------------------------------

@pytest.mark.requires_kafka
@pytest.mark.requires_triton
class TestPerFlowAnomalyScenarios:
    """Verify that per-flow attack scenarios trigger detections."""

    @pytest.mark.parametrize("scenario_name", [
        "large_exfil",
        "udp_flood",
        "icmp_tunnel",
        "long_c2",
        "syn_burst",
        "proto_other",
    ])
    def test_anomaly_scenario_triggers_detection(
        self, kafka_bootstrap, test_run_id, scenario_name,
    ):
        """Attack scenario should produce at least one anomaly detection."""
        detections = _produce_and_consume(
            kafka_bootstrap, test_run_id, scenario_name,
        )
        assert len(detections) >= 1, (
            f"Scenario {scenario_name} should have produced at least 1 detection, "
            f"but got {len(detections)}"
        )
        for d in detections:
            assert d.get("anomaly_label") == "anomaly"
            assert float(d.get("anomaly_score", 0)) >= 0.05


# ---------------------------------------------------------------------------
# Negative controls (T07-T08)
# ---------------------------------------------------------------------------

@pytest.mark.requires_kafka
@pytest.mark.requires_triton
class TestNegativeControlScenarios:
    """Verify that benign scenarios do NOT trigger detections."""

    @pytest.mark.parametrize("scenario_name", [
        "baseline",
        "near_threshold",
    ])
    def test_benign_scenario_no_detection(
        self, kafka_bootstrap, test_run_id, scenario_name,
    ):
        """Benign traffic should produce zero detections."""
        detections = _produce_and_consume(
            kafka_bootstrap, test_run_id, scenario_name,
        )
        assert len(detections) == 0, (
            f"Scenario {scenario_name} should NOT produce detections, "
            f"but got {len(detections)}"
        )


# ---------------------------------------------------------------------------
# Aggregate-feature scenarios (T09-T11, requires sanitizer fix)
# ---------------------------------------------------------------------------

@pytest.mark.requires_kafka
@pytest.mark.requires_triton
class TestAggregateFeatureScenarios:
    """Verify aggregate-feature scenarios after sanitizer fix.

    These scenarios inject feat_* overrides directly (Layer 1), so they
    work regardless of whether the sanitizer aggregate fix is deployed.
    """

    @pytest.mark.parametrize("scenario_name", [
        "port_scan",
        "c2_fanout",
        "data_exfil_ratio",
    ])
    def test_aggregate_scenario_triggers_detection(
        self, kafka_bootstrap, test_run_id, scenario_name,
    ):
        """Aggregate attack pattern should produce at least one detection."""
        detections = _produce_and_consume(
            kafka_bootstrap, test_run_id, scenario_name,
            batch_size=5,  # More records for aggregate patterns
        )
        assert len(detections) >= 1, (
            f"Scenario {scenario_name} should have produced at least 1 detection, "
            f"but got {len(detections)}"
        )
