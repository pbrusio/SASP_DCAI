"""SASP End-to-End Smoke Tests — verify the full pipeline with mocks and optional live services.

Test 1: Sanitizer pipeline (mock or @requires_kafka)
Test 2: Detection pipeline (@requires_triton)
Test 3: Agent pipeline (mocked Ollama)
Test 4: Audit log integrity
"""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from sasp.sanitizer import NetFlowSanitizer, SyslogSanitizer, ISESanitizer


# ---------------------------------------------------------------------------
# Test 1: Sanitizer pipeline
# ---------------------------------------------------------------------------
class TestSanitizerPipeline:
    """Verify that raw records pass through the correct sanitizer cleanly."""

    def test_netflow_sanitizer_clean_record(self, sample_netflow_record):
        sanitizer = NetFlowSanitizer()
        result = sanitizer.sanitize(sample_netflow_record)
        assert result.is_clean is True
        assert result.sanitized["src_addr"] == "192.168.1.100"

    def test_syslog_sanitizer_clean_record(self, sample_syslog_record):
        sanitizer = SyslogSanitizer()
        result = sanitizer.sanitize(sample_syslog_record)
        assert result.is_clean is True

    def test_ise_sanitizer_clean_record(self, sample_ise_record):
        sanitizer = ISESanitizer()
        result = sanitizer.sanitize(sample_ise_record)
        assert result.is_clean is True

    def test_sanitizer_rejects_injection(self, sample_netflow_record):
        sample_netflow_record["src_addr"] = "'; DROP TABLE flows; --"
        sanitizer = NetFlowSanitizer()
        result = sanitizer.sanitize(sample_netflow_record)
        assert result.is_clean is False

    @pytest.mark.requires_kafka
    def test_kafka_round_trip(self, sample_netflow_record):
        """Produce a raw netflow record to Kafka and verify it appears on sanitized topic.

        Requires: KAFKA_BOOTSTRAP_SERVERS env var pointing to a live broker.
        """
        from kafka import KafkaProducer, KafkaConsumer

        bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "<S2_IP>:9092")
        producer = KafkaProducer(
            bootstrap_servers=bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        producer.send("netflow-raw-test", sample_netflow_record)
        producer.flush()

        consumer = KafkaConsumer(
            "netflow-sanitized-test",
            bootstrap_servers=bootstrap,
            auto_offset_reset="latest",
            consumer_timeout_ms=10000,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        messages = list(consumer)
        assert len(messages) > 0, "No messages received on sanitized topic"


# ---------------------------------------------------------------------------
# Test 2: Detection pipeline (Triton inference)
# ---------------------------------------------------------------------------
class TestDetectionPipeline:

    @pytest.mark.requires_triton
    def test_triton_netflow_inference(self):
        """Submit a feature vector to Triton and verify inference response.

        Requires: TRITON_SERVER_URL env var pointing to a live Triton instance.
        """
        import numpy as np
        import tritonclient.http as httpclient

        triton_url = os.environ.get("TRITON_SERVER_URL", "<S1_IP>:8000")
        client = httpclient.InferenceServerClient(url=triton_url)

        # 15-feature input matching autoencoder
        input_data = np.random.randn(1, 15).astype(np.float32)
        inputs = [httpclient.InferInput("input", input_data.shape, "FP32")]
        inputs[0].set_data_from_numpy(input_data)

        outputs = [httpclient.InferRequestedOutput("output")]
        result = client.infer("netflow-anomaly", inputs, outputs=outputs)
        output_data = result.as_numpy("output")

        assert output_data.shape == (1, 15), f"Unexpected output shape: {output_data.shape}"

    @pytest.mark.requires_triton
    def test_triton_auth_inference(self):
        """Submit auth features to Triton and verify classification output."""
        import numpy as np
        import tritonclient.http as httpclient

        triton_url = os.environ.get("TRITON_SERVER_URL", "<S1_IP>:8000")
        client = httpclient.InferenceServerClient(url=triton_url)

        input_data = np.random.randn(1, 7).astype(np.float32)
        inputs = [httpclient.InferInput("input", input_data.shape, "FP32")]
        inputs[0].set_data_from_numpy(input_data)

        outputs = [httpclient.InferRequestedOutput("output")]
        result = client.infer("auth-risk", inputs, outputs=outputs)
        output_data = result.as_numpy("output")

        assert output_data.shape == (1, 3), f"Unexpected output shape: {output_data.shape}"


# ---------------------------------------------------------------------------
# Test 3: Agent pipeline (mocked Ollama)
# ---------------------------------------------------------------------------
class TestAgentPipeline:
    """Test the investigation workflow with fully mocked LLM calls."""

    @patch("sasp.agents.nodes.triage.generate")
    @patch("sasp.agents.nodes.investigate.generate")
    @patch("sasp.agents.nodes.threat_intel.generate")
    @patch("sasp.agents.nodes.report.generate")
    def test_full_pipeline_mocked(
        self, mock_report, mock_threat, mock_investigate, mock_triage,
        sample_detection,
    ):
        """Run the full pipeline with mocked LLM generate() and verify state transitions."""
        import json as _json

        mock_triage.return_value = _json.dumps({
            "decision": "investigate",
            "reasoning": "test reasoning",
        })
        mock_investigate.return_value = _json.dumps({
            "findings": "suspicious lateral movement",
            "affected_assets": ["server-01"],
            "timeline": "2025-01-01T00:00 - initial access",
        })
        mock_threat.return_value = _json.dumps({
            "iocs": ["10.0.0.99"],
            "mitre_techniques": ["T1071"],
            "threat_actor": "unknown",
        })
        mock_report.return_value = _json.dumps({
            "summary": "Investigation of anomalous traffic from 10.0.0.50",
            "severity": "medium",
            "recommendations": ["Block source IP", "Review firewall rules"],
        })

        # Import here to avoid module-level langgraph dependency issues.
        # Reload graph module to get a fresh compile in case a prior test
        # (e.g. test_agent_workflow) mocked langgraph and polluted the
        # module-level investigation_graph.
        try:
            import importlib
            import sasp.agents.graph as graph_mod
            importlib.reload(graph_mod)
            run_investigation = graph_mod.run_investigation
        except ImportError:
            pytest.skip("langgraph not installed — skipping graph integration test")

        result = run_investigation(sample_detection)

        assert "investigation_id" in result
        assert result.get("investigation_id", "").startswith("inv-")
        assert "triage_decision" in result

    def test_individual_triage_node(self, sample_detection):
        """Test triage node in isolation with mocked LLM generate()."""
        import json as _json

        with patch("sasp.agents.nodes.triage.generate") as mock_gen:
            mock_gen.return_value = _json.dumps({
                "decision": "investigate",
                "reasoning": "high anomaly score",
            })

            from sasp.agents.nodes.triage import run

            state = {"detection": sample_detection}
            result = run(state)

            assert result["triage_decision"] == "investigate"
            # Confidence is ML-grounded from anomaly_score (0.92), not LLM
            assert result["triage_confidence"] == 0.92

    def test_triage_skip_on_low_score(self, sample_detection):
        """Triage should skip when LLM says skip."""
        import json as _json

        with patch("sasp.agents.nodes.triage.generate") as mock_gen:
            mock_gen.return_value = _json.dumps({
                "decision": "skip",
                "reasoning": "benign traffic",
            })

            from sasp.agents.nodes.triage import run
            result = run({"detection": sample_detection})
            assert result["triage_decision"] == "skip"

    def test_triage_handles_connection_error(self, sample_detection):
        """Triage should default to skip on connection failure."""
        with patch("sasp.agents.nodes.triage.generate") as mock_gen:
            # generate() catches ConnectionError internally and returns ""
            mock_gen.return_value = ""

            from sasp.agents.nodes.triage import run
            result = run({"detection": sample_detection})
            assert result["triage_decision"] == "skip"
            # skip with anomaly_score=0.92 → 1.0 - 0.92 = 0.08
            assert result["triage_confidence"] == 0.08


# ---------------------------------------------------------------------------
# Test 4: Audit log integrity
# ---------------------------------------------------------------------------
class TestAuditIntegrity:
    """Verify audit log HMAC integrity after agent operations."""

    def test_audit_log_write_and_verify(self):
        """Write audit entries and verify HMAC integrity."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            with patch.dict(os.environ, {"AUDIT_LOG_PATH": log_path}):
                # Re-import to pick up the new path
                import importlib
                import sasp.agents.security.audit as audit_mod
                importlib.reload(audit_mod)

                audit_mod.AuditLogger.log_guardian_check(
                    {"investigation_id": "test-001", "severity": "high"},
                    {"approved": True, "needs_human_review": False,
                     "concerns": [], "validation_checks": {}},
                )
                audit_mod.AuditLogger.log_tool_call(
                    "investigate", "splunk_query",
                    {"query": "index=main | head 10"},
                    {"success": True, "result": []},
                    duration_ms=150,
                )

                result = audit_mod.verify_audit_integrity(log_path)
                assert result["total_entries"] == 2
                assert result["valid_entries"] == 2
                assert result["invalid_entries"] == 0

        finally:
            os.unlink(log_path)

    def test_tampered_log_detected(self):
        """Tampering with an audit entry should be detected by HMAC verification."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            with patch.dict(os.environ, {"AUDIT_LOG_PATH": log_path}):
                import importlib
                import sasp.agents.security.audit as audit_mod
                importlib.reload(audit_mod)

                audit_mod.AuditLogger.log_guardian_check(
                    {"investigation_id": "test-002", "severity": "low"},
                    {"approved": True, "needs_human_review": False,
                     "concerns": [], "validation_checks": {}},
                )

                # Tamper with the log
                with open(log_path, "r") as fh:
                    line = fh.read()
                tampered = line.replace('"approved": true', '"approved": false')
                with open(log_path, "w") as fh:
                    fh.write(tampered)

                result = audit_mod.verify_audit_integrity(log_path)
                assert result["invalid_entries"] >= 1

        finally:
            os.unlink(log_path)
