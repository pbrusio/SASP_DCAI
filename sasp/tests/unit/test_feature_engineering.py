"""
Unit tests for sasp.models.training.feature_engineering.

Uses synthetic GoFlow2-style records to validate per-flow features,
aggregate features, scaler persistence, and edge cases.
"""

import math
import pickle
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sasp.models.training.feature_engineering import (
    NetFlowFeatureExtractor,
    port_category,
    protocol_onehot,
    shannon_entropy,
)


# ---------------------------------------------------------------------------
# Helper: synthetic records
# ---------------------------------------------------------------------------
def _make_record(
    src="10.0.0.1",
    dst="192.168.1.1",
    src_port=54321,
    dst_port=443,
    proto=6,
    bytes_val=1500,
    packets=10,
    t_start=1_000_000_000_000,
    t_end=1_060_000_000_000,
    bytes_in=None,
):
    rec = {
        "src_addr": src,
        "dst_addr": dst,
        "src_port": src_port,
        "dst_port": dst_port,
        "proto": proto,
        "bytes": bytes_val,
        "packets": packets,
        "time_flow_start_ns": t_start,
        "time_flow_end_ns": t_end,
    }
    if bytes_in is not None:
        rec["BytesIn"] = bytes_in
    return rec


# ---------------------------------------------------------------------------
# port_category
# ---------------------------------------------------------------------------
class TestPortCategory:
    def test_well_known(self):
        assert port_category(80) == 0
        assert port_category(443) == 0
        assert port_category(0) == 0
        assert port_category(1023) == 0

    def test_registered(self):
        assert port_category(1024) == 1
        assert port_category(8080) == 1
        assert port_category(49151) == 1

    def test_dynamic(self):
        assert port_category(49152) == 2
        assert port_category(65535) == 2


# ---------------------------------------------------------------------------
# protocol_onehot
# ---------------------------------------------------------------------------
class TestProtocolOnehot:
    def test_tcp(self):
        result = protocol_onehot(6)
        assert result["proto_tcp"] == 1
        assert result["proto_udp"] == 0
        assert result["proto_icmp"] == 0
        assert result["proto_other"] == 0

    def test_udp(self):
        result = protocol_onehot(17)
        assert result["proto_udp"] == 1
        assert result["proto_tcp"] == 0

    def test_icmp(self):
        result = protocol_onehot(1)
        assert result["proto_icmp"] == 1

    def test_other(self):
        result = protocol_onehot(47)  # GRE
        assert result["proto_other"] == 1
        assert result["proto_tcp"] == 0


# ---------------------------------------------------------------------------
# shannon_entropy
# ---------------------------------------------------------------------------
class TestShannonEntropy:
    def test_empty(self):
        assert shannon_entropy([]) == 0.0

    def test_single_value(self):
        assert shannon_entropy(["a", "a", "a"]) == 0.0

    def test_uniform_two(self):
        # entropy of two equally likely outcomes = 1.0
        result = shannon_entropy(["a", "b"])
        assert abs(result - 1.0) < 1e-9

    def test_higher_entropy(self):
        # 4 unique values equally distributed = log2(4) = 2.0
        result = shannon_entropy(["a", "b", "c", "d"])
        assert abs(result - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# NetFlowFeatureExtractor — per-flow
# ---------------------------------------------------------------------------
class TestPerFlowFeatures:
    @pytest.fixture
    def extractor(self):
        return NetFlowFeatureExtractor()

    def test_single_record_shape(self, extractor):
        records = [_make_record()]
        df = extractor.transform(records)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert list(df.columns) == extractor.ALL_FEATURE_COLS

    def test_bytes_per_packet(self, extractor):
        records = [_make_record(bytes_val=1000, packets=10)]
        df = extractor.transform(records)
        assert df.iloc[0]["bytes_per_packet"] == 100.0

    def test_duration_seconds(self, extractor):
        # GoFlow2 uses nanosecond timestamps: 60 seconds = 60_000_000_000 ns
        records = [_make_record(t_start=1_000_000_000_000, t_end=1_060_000_000_000)]
        df = extractor.transform(records)
        assert df.iloc[0]["duration_seconds"] == 60.0

    def test_duration_no_negative(self, extractor):
        records = [_make_record(t_start=2_000_000_000_000, t_end=1_000_000_000_000)]
        df = extractor.transform(records)
        assert df.iloc[0]["duration_seconds"] == 0.0

    def test_port_categories(self, extractor):
        records = [_make_record(src_port=80, dst_port=55000)]
        df = extractor.transform(records)
        assert df.iloc[0]["src_port_category"] == 0.0  # well-known
        assert df.iloc[0]["dst_port_category"] == 2.0  # dynamic

    def test_protocol_flags_tcp(self, extractor):
        records = [_make_record(proto=6)]
        df = extractor.transform(records)
        assert df.iloc[0]["proto_tcp"] == 1.0
        assert df.iloc[0]["proto_udp"] == 0.0

    def test_protocol_flags_udp(self, extractor):
        records = [_make_record(proto=17)]
        df = extractor.transform(records)
        assert df.iloc[0]["proto_udp"] == 1.0


# ---------------------------------------------------------------------------
# NetFlowFeatureExtractor — aggregate
# ---------------------------------------------------------------------------
class TestAggregateFeatures:
    @pytest.fixture
    def extractor(self):
        return NetFlowFeatureExtractor()

    def test_flows_per_src(self, extractor):
        records = [
            _make_record(src="10.0.0.1", dst="192.168.1.1"),
            _make_record(src="10.0.0.1", dst="192.168.1.2"),
            _make_record(src="10.0.0.1", dst="192.168.1.3"),
        ]
        df = extractor.transform(records)
        assert df.iloc[0]["flows_per_src_ip"] == 3.0

    def test_unique_dst_ips(self, extractor):
        records = [
            _make_record(src="10.0.0.1", dst="1.1.1.1"),
            _make_record(src="10.0.0.1", dst="2.2.2.2"),
            _make_record(src="10.0.0.1", dst="1.1.1.1"),  # duplicate
        ]
        df = extractor.transform(records)
        assert df.iloc[0]["unique_dst_ips_per_src"] == 2.0

    def test_unique_dst_ports(self, extractor):
        records = [
            _make_record(src="10.0.0.1", dst_port=80),
            _make_record(src="10.0.0.1", dst_port=443),
            _make_record(src="10.0.0.1", dst_port=80),
        ]
        df = extractor.transform(records)
        assert df.iloc[0]["unique_dst_ports_per_src"] == 2.0

    def test_dst_ip_entropy_scan(self, extractor):
        """Many unique destinations -> high entropy (scan-like)."""
        records = [
            _make_record(src="10.0.0.1", dst=f"192.168.1.{i}")
            for i in range(1, 17)
        ]
        df = extractor.transform(records)
        # 16 unique IPs => entropy = log2(16) = 4.0
        assert abs(df.iloc[0]["dst_ip_entropy"] - 4.0) < 1e-9

    def test_dst_ip_entropy_low(self, extractor):
        """Single destination -> zero entropy."""
        records = [
            _make_record(src="10.0.0.1", dst="192.168.1.1"),
            _make_record(src="10.0.0.1", dst="192.168.1.1"),
        ]
        df = extractor.transform(records)
        assert df.iloc[0]["dst_ip_entropy"] == 0.0


# ---------------------------------------------------------------------------
# Scaler fit / transform / persistence
# ---------------------------------------------------------------------------
class TestScaler:
    @pytest.fixture
    def extractor_with_data(self):
        ext = NetFlowFeatureExtractor()
        records = [
            _make_record(bytes_val=b, packets=p, dst=f"10.0.0.{i % 256}")
            for i, (b, p) in enumerate(
                [(1000, 5), (2000, 10), (500, 2), (3000, 15), (100, 1)]
            )
        ]
        df = ext.transform(records)
        return ext, df

    def test_fit_transform(self, extractor_with_data):
        ext, df = extractor_with_data
        scaled = ext.fit_transform(df)
        assert scaled.shape == df.shape
        # Scaled columns should have ~zero mean
        means = scaled.mean()
        for col in ext.ALL_FEATURE_COLS:
            assert abs(means[col]) < 1e-6, f"{col} mean not near zero"

    def test_scale_without_fit_raises(self):
        ext = NetFlowFeatureExtractor()
        df = pd.DataFrame(np.zeros((2, len(ext.ALL_FEATURE_COLS))), columns=ext.ALL_FEATURE_COLS)
        with pytest.raises(RuntimeError, match="not fitted"):
            ext.scale(df)

    def test_save_load_scaler(self, extractor_with_data):
        ext, df = extractor_with_data
        ext.fit(df)
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
            ext.save_scaler(tmp.name)
            # Load into a new extractor
            ext2 = NetFlowFeatureExtractor()
            ext2.load_scaler(tmp.name)
            scaled1 = ext.scale(df)
            scaled2 = ext2.scale(df)
            pd.testing.assert_frame_equal(scaled1, scaled2)

    def test_save_without_fit_raises(self):
        ext = NetFlowFeatureExtractor()
        with pytest.raises(RuntimeError, match="not fitted"):
            ext.save_scaler("/tmp/no_scaler.pkl")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_records(self):
        ext = NetFlowFeatureExtractor()
        df = ext.transform([])
        assert len(df) == 0
        assert list(df.columns) == ext.ALL_FEATURE_COLS

    def test_missing_fields_default(self):
        ext = NetFlowFeatureExtractor()
        records = [{"src_addr": "10.0.0.1"}]  # minimal
        df = ext.transform(records)
        assert len(df) == 1
        # Should not crash; missing fields default to 0
        assert df.iloc[0]["bytes_per_packet"] == 0.0

    def test_multiple_source_ips(self):
        ext = NetFlowFeatureExtractor()
        records = [
            _make_record(src="10.0.0.1", dst="1.1.1.1"),
            _make_record(src="10.0.0.2", dst="2.2.2.2"),
        ]
        df = ext.transform(records)
        # Each src has 1 flow
        assert df.iloc[0]["flows_per_src_ip"] == 1.0
        assert df.iloc[1]["flows_per_src_ip"] == 1.0

    def test_feature_count(self):
        """Verify total feature count matches ALL_FEATURE_COLS."""
        ext = NetFlowFeatureExtractor()
        assert len(ext.ALL_FEATURE_COLS) == 15
