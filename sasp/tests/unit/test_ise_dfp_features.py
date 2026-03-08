"""
Unit tests for sasp.models.training.ise_dfp_features.

Uses synthetic ISE authentication events to validate temporal features,
categorical encoding, rolling window features, known-device detection,
scaler persistence, and edge cases.
"""

import json
import math
import tempfile
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from sasp.models.training.ise_dfp_features import ISEDFPFeatureExtractor


# ---------------------------------------------------------------------------
# Helper: synthetic ISE event builder
# ---------------------------------------------------------------------------
def _make_ise_event(
    username: str = "jsmith",
    timestamp: str = "2026-03-03T10:15:30Z",
    auth_result: str = "PASS",
    auth_type: str = "802.1X",
    nas_ip: str = "10.0.1.1",
    nas_port_type: str = "Ethernet",
    calling_station_id: str = "AA:BB:CC:DD:EE:01",
    policy_set: str = "Corporate-Wired",
    anomaly_label: str | None = None,
) -> dict:
    event = {
        "username": username,
        "timestamp": timestamp,
        "auth_result": auth_result,
        "auth_type": auth_type,
        "nas_ip": nas_ip,
        "nas_port_type": nas_port_type,
        "calling_station_id": calling_station_id,
        "policy_set": policy_set,
    }
    if anomaly_label is not None:
        event["_anomaly_label"] = anomaly_label
    return event


# ---------------------------------------------------------------------------
# Timestamp / temporal features
# ---------------------------------------------------------------------------
class TestTimestampFeatures:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.ext = ISEDFPFeatureExtractor()
        self.ext.fit([_make_ise_event()])

    def test_hour_sin_cos_noon(self):
        """At noon (hour=12), sin(2*pi*12/24) = sin(pi) ~ 0, cos(pi) ~ -1."""
        self.ext.reset_windows()
        event = _make_ise_event(timestamp="2026-03-03T12:00:00Z")
        features = self.ext.transform_single(event)
        assert abs(features["hour_sin"] - math.sin(math.pi)) < 1e-6
        assert abs(features["hour_cos"] - math.cos(math.pi)) < 1e-6

    def test_hour_sin_cos_midnight(self):
        """At midnight (hour=0), sin(0)=0, cos(0)=1."""
        self.ext.reset_windows()
        event = _make_ise_event(timestamp="2026-03-03T00:00:00Z")
        features = self.ext.transform_single(event)
        assert abs(features["hour_sin"]) < 1e-6
        assert abs(features["hour_cos"] - 1.0) < 1e-6

    def test_hour_sin_cos_6am(self):
        """At 6am (hour=6), sin(2*pi*6/24) = sin(pi/2) = 1, cos = 0."""
        self.ext.reset_windows()
        event = _make_ise_event(timestamp="2026-03-03T06:00:00Z")
        features = self.ext.transform_single(event)
        assert abs(features["hour_sin"] - 1.0) < 1e-6
        assert abs(features["hour_cos"]) < 1e-6

    def test_day_of_week(self):
        """2026-03-03 is a Tuesday (weekday=1)."""
        self.ext.reset_windows()
        event = _make_ise_event(timestamp="2026-03-03T10:00:00Z")
        features = self.ext.transform_single(event)
        assert features["day_of_week"] == 1.0

    def test_is_weekend_weekday(self):
        """Tuesday is not a weekend."""
        self.ext.reset_windows()
        event = _make_ise_event(timestamp="2026-03-03T10:00:00Z")  # Tuesday
        features = self.ext.transform_single(event)
        assert features["is_weekend"] == 0.0

    def test_is_weekend_saturday(self):
        """2026-03-07 is a Saturday."""
        self.ext.reset_windows()
        event = _make_ise_event(timestamp="2026-03-07T10:00:00Z")
        features = self.ext.transform_single(event)
        assert features["is_weekend"] == 1.0

    def test_is_weekend_sunday(self):
        """2026-03-08 is a Sunday."""
        self.ext.reset_windows()
        event = _make_ise_event(timestamp="2026-03-08T14:00:00Z")
        features = self.ext.transform_single(event)
        assert features["is_weekend"] == 1.0


# ---------------------------------------------------------------------------
# Categorical features
# ---------------------------------------------------------------------------
class TestCategoricalFeatures:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.ext = ISEDFPFeatureExtractor()
        self.ext.fit([
            _make_ise_event(auth_type="802.1X", policy_set="Corporate-Wired"),
            _make_ise_event(auth_type="TACACS+", policy_set="Service-Accounts"),
        ])

    def test_auth_result_pass(self):
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(auth_result="PASS"))
        assert features["auth_result_code"] == 0.0

    def test_auth_result_fail(self):
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(auth_result="FAIL"))
        assert features["auth_result_code"] == 1.0

    def test_auth_type_8021x(self):
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(auth_type="802.1X"))
        assert features["auth_type_code"] == 0.0

    def test_auth_type_tacacs(self):
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(auth_type="TACACS+"))
        assert features["auth_type_code"] == 1.0

    def test_auth_type_other(self):
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(auth_type="RADIUS"))
        assert features["auth_type_code"] == 2.0

    def test_nas_port_type_ethernet(self):
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(nas_port_type="Ethernet"))
        assert features["nas_port_type_code"] == 0.0

    def test_nas_port_type_wireless(self):
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(nas_port_type="Wireless"))
        assert features["nas_port_type_code"] == 1.0

    def test_nas_port_type_virtual(self):
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(nas_port_type="Virtual"))
        assert features["nas_port_type_code"] == 2.0

    def test_policy_set_code_alphabetical(self):
        """Policy sets are encoded alphabetically: Corporate-Wired=0, Service-Accounts=1."""
        self.ext.reset_windows()
        f1 = self.ext.transform_single(_make_ise_event(policy_set="Corporate-Wired"))
        self.ext.reset_windows()
        f2 = self.ext.transform_single(_make_ise_event(policy_set="Service-Accounts"))
        assert f1["policy_set_code"] == 0.0
        assert f2["policy_set_code"] == 1.0

    def test_policy_set_unknown(self):
        """Unknown policy set gets code = len(map)."""
        self.ext.reset_windows()
        features = self.ext.transform_single(_make_ise_event(policy_set="Unknown-Policy"))
        assert features["policy_set_code"] == 2.0  # 2 known policies


# ---------------------------------------------------------------------------
# Rolling window features
# ---------------------------------------------------------------------------
class TestRollingWindowFeatures:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.ext = ISEDFPFeatureExtractor()
        self.ext.fit([_make_ise_event()])

    def test_consecutive_failures_within_5min(self):
        """Failures within the 5-minute window should accumulate."""
        self.ext.reset_windows()
        base = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
        records = []
        # 3 failures within 5 minutes
        for i in range(3):
            ts = (base + timedelta(seconds=i * 60)).strftime("%Y-%m-%dT%H:%M:%SZ")
            records.append(_make_ise_event(timestamp=ts, auth_result="FAIL"))
        # 4th event is the one we check -- should see 3 prior failures
        ts_check = (base + timedelta(seconds=240)).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append(_make_ise_event(timestamp=ts_check, auth_result="PASS"))

        df = self.ext.transform_batch(records)
        assert df.iloc[3]["consecutive_failures"] == 3.0

    def test_consecutive_failures_expired(self):
        """Failures older than 5 minutes should not count."""
        self.ext.reset_windows()
        base = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
        records = [
            _make_ise_event(
                timestamp=base.strftime("%Y-%m-%dT%H:%M:%SZ"),
                auth_result="FAIL",
            ),
        ]
        # Check event 6 minutes later -- failure has expired
        ts_check = (base + timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append(_make_ise_event(timestamp=ts_check))
        df = self.ext.transform_batch(records)
        assert df.iloc[1]["consecutive_failures"] == 0.0

    def test_auth_rate_1h(self):
        """Events within 1 hour should be counted."""
        self.ext.reset_windows()
        base = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
        records = []
        for i in range(5):
            ts = (base + timedelta(minutes=i * 10)).strftime("%Y-%m-%dT%H:%M:%SZ")
            records.append(_make_ise_event(timestamp=ts))
        # 6th event at minute 50 -- should see 5 prior events in the window
        ts_check = (base + timedelta(minutes=50)).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append(_make_ise_event(timestamp=ts_check))
        df = self.ext.transform_batch(records)
        assert df.iloc[5]["auth_rate_1h"] == 5.0

    def test_unique_devices_24h(self):
        """Distinct devices within 24h should be counted."""
        self.ext.reset_windows()
        base = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
        records = [
            _make_ise_event(
                timestamp=(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                calling_station_id=f"AA:BB:CC:DD:EE:{i:02X}",
            )
            for i in range(3)
        ]
        # 4th event: should see 3 unique devices
        ts_check = (base + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append(_make_ise_event(timestamp=ts_check))
        df = self.ext.transform_batch(records)
        assert df.iloc[3]["unique_devices_24h"] == 3.0

    def test_unique_nas_24h(self):
        """Distinct NAS IPs within 24h should be counted."""
        self.ext.reset_windows()
        base = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
        records = [
            _make_ise_event(
                timestamp=(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                nas_ip=f"10.0.1.{i}",
            )
            for i in range(4)
        ]
        # 5th event: should see 4 unique NAS IPs
        ts_check = (base + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append(_make_ise_event(timestamp=ts_check))
        df = self.ext.transform_batch(records)
        assert df.iloc[4]["unique_nas_24h"] == 4.0

    def test_failure_rate_1h(self):
        """failure_rate_1h = failures in 1h / max(auth_rate_1h, 1)."""
        self.ext.reset_windows()
        base = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
        records = [
            _make_ise_event(
                timestamp=(base + timedelta(minutes=i * 5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                auth_result="FAIL" if i < 2 else "PASS",
            )
            for i in range(4)
        ]
        # 5th event: 2 failures / 4 total = 0.5
        ts_check = (base + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append(_make_ise_event(timestamp=ts_check))
        df = self.ext.transform_batch(records)
        assert abs(df.iloc[4]["failure_rate_1h"] - 0.5) < 1e-6


# ---------------------------------------------------------------------------
# Known device flag
# ---------------------------------------------------------------------------
class TestKnownDeviceFlag:
    def test_known_device_returns_zero(self):
        """Device seen during fit() should produce flag=0.0."""
        ext = ISEDFPFeatureExtractor()
        training = [_make_ise_event(calling_station_id="AA:BB:CC:DD:EE:01")]
        ext.fit(training)
        features = ext.transform_single(
            _make_ise_event(calling_station_id="AA:BB:CC:DD:EE:01")
        )
        assert features["known_device_flag"] == 0.0

    def test_novel_device_returns_one(self):
        """Device NOT seen during fit() should produce flag=1.0."""
        ext = ISEDFPFeatureExtractor()
        training = [_make_ise_event(calling_station_id="AA:BB:CC:DD:EE:01")]
        ext.fit(training)
        features = ext.transform_single(
            _make_ise_event(calling_station_id="FF:FF:FF:FF:FF:FF")
        )
        assert features["known_device_flag"] == 1.0

    def test_known_device_per_user(self):
        """Known-device check is per-user: user B's device is novel for user A."""
        ext = ISEDFPFeatureExtractor()
        training = [
            _make_ise_event(username="alice", calling_station_id="AA:AA:AA:AA:AA:AA"),
            _make_ise_event(username="bob", calling_station_id="BB:BB:BB:BB:BB:BB"),
        ]
        ext.fit(training)
        # Alice using Bob's device is novel for Alice
        features = ext.transform_single(
            _make_ise_event(username="alice", calling_station_id="BB:BB:BB:BB:BB:BB")
        )
        assert features["known_device_flag"] == 1.0


# ---------------------------------------------------------------------------
# Scaler: fit / transform / save / load round-trip
# ---------------------------------------------------------------------------
class TestScaler:
    @pytest.fixture
    def extractor_with_data(self):
        ext = ISEDFPFeatureExtractor()
        base = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
        records = [
            _make_ise_event(
                timestamp=(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                auth_result="FAIL" if i % 3 == 0 else "PASS",
                calling_station_id=f"AA:BB:CC:DD:EE:{i:02X}",
                nas_ip=f"10.0.1.{i}",
                policy_set="Corporate-Wired" if i % 2 == 0 else "Guest-Wireless",
            )
            for i in range(10)
        ]
        ext.fit(records)
        df = ext.transform_batch(records)
        return ext, df

    def test_fit_transform(self, extractor_with_data):
        ext, df = extractor_with_data
        ext.fit_scaler(df)
        scaled = ext.scale(df)
        assert scaled.shape == df.shape
        # Scaled columns should have ~zero mean
        means = scaled.mean()
        for col in ext.FEATURE_COLS:
            assert abs(means[col]) < 1e-6, f"{col} mean not near zero"

    def test_scale_without_fit_raises(self):
        ext = ISEDFPFeatureExtractor()
        df = pd.DataFrame(
            np.zeros((2, len(ext.FEATURE_COLS))),
            columns=ext.FEATURE_COLS,
        )
        with pytest.raises(RuntimeError, match="not fitted"):
            ext.scale(df)

    def test_save_load_roundtrip(self, extractor_with_data):
        ext, df = extractor_with_data
        ext.fit_scaler(df)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            ext.save_scaler(tmp.name)
            # Load into a new extractor
            ext2 = ISEDFPFeatureExtractor()
            ext2.load_scaler(tmp.name)
            scaled1 = ext.scale(df)
            scaled2 = ext2.scale(df)
            pd.testing.assert_frame_equal(scaled1, scaled2)

    def test_save_without_fit_raises(self):
        ext = ISEDFPFeatureExtractor()
        with pytest.raises(RuntimeError, match="not fitted"):
            ext.save_scaler("/tmp/no_scaler.json")

    def test_scaler_json_contains_policy_set_map(self, extractor_with_data):
        """Saved scaler JSON should include the policy_set_map."""
        ext, df = extractor_with_data
        ext.fit_scaler(df)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            ext.save_scaler(tmp.name)
            with open(tmp.name) as fh:
                data = json.load(fh)
        assert "policy_set_map" in data
        assert isinstance(data["policy_set_map"], dict)
        assert len(data["policy_set_map"]) > 0

    def test_scaler_json_contains_known_devices(self, extractor_with_data):
        """Saved scaler JSON should include known_devices per user."""
        ext, df = extractor_with_data
        ext.fit_scaler(df)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            ext.save_scaler(tmp.name)
            with open(tmp.name) as fh:
                data = json.load(fh)
        assert "known_devices" in data
        assert isinstance(data["known_devices"], dict)
        assert "jsmith" in data["known_devices"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_empty_records(self):
        ext = ISEDFPFeatureExtractor()
        ext.fit([])
        df = ext.transform_batch([])
        assert len(df) == 0
        assert list(df.columns) == ext.FEATURE_COLS

    def test_missing_fields(self):
        """Minimal record with only username should not crash."""
        ext = ISEDFPFeatureExtractor()
        ext.fit([{"username": "test"}])
        df = ext.transform_batch([{"username": "test"}])
        assert len(df) == 1

    def test_single_record(self):
        ext = ISEDFPFeatureExtractor()
        record = _make_ise_event()
        ext.fit([record])
        df = ext.transform_batch([record])
        assert len(df) == 1
        assert list(df.columns) == ext.FEATURE_COLS

    def test_feature_count(self):
        """Verify total feature count is 14."""
        ext = ISEDFPFeatureExtractor()
        assert len(ext.FEATURE_COLS) == 14

    def test_transform_batch_equals_transform_single(self):
        """Batch and single transforms should produce identical results for one record."""
        ext = ISEDFPFeatureExtractor()
        record = _make_ise_event()
        ext.fit([record])

        ext.reset_windows()
        single_features = ext.transform_single(record)

        ext.reset_windows()
        batch_df = ext.transform_batch([record])

        for col in ext.FEATURE_COLS:
            assert abs(single_features[col] - batch_df.iloc[0][col]) < 1e-9, (
                f"{col}: single={single_features[col]}, batch={batch_df.iloc[0][col]}"
            )
