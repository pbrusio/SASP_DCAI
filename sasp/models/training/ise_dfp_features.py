"""SASP ISE DFP Feature Engineering -- transforms ISE auth events into ML feature vectors.

Extracts 14 features per ISE authentication event for Digital Fingerprinting
(DFP) anomaly detection. Maintains per-user rolling windows for behavioral
features (failure rate, auth rate, device/NAS diversity).
"""

import json
import logging
import math
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_WINDOW_5MIN = 300       # 5-minute rolling window for consecutive failures
_WINDOW_1H = 3600        # 1-hour window for auth rate / failure rate
_WINDOW_24H = 86400      # 24-hour window for unique devices / NAS

_AUTH_RESULT_MAP: Dict[str, float] = {"PASS": 0.0, "FAIL": 1.0}
_AUTH_TYPE_MAP: Dict[str, float] = {"802.1X": 0.0, "TACACS+": 1.0}
_NAS_PORT_TYPE_MAP: Dict[str, float] = {"Ethernet": 0.0, "Wireless": 1.0, "Virtual": 2.0}

# Default code for unmapped values
_AUTH_TYPE_OTHER = 2.0
_NAS_PORT_TYPE_OTHER = 2.0  # Virtual bucket doubles as "other"


# ---------------------------------------------------------------------------
# Per-user rolling window
# ---------------------------------------------------------------------------
class _UserWindow:
    """Rolling event window for a single user.

    Stores recent (timestamp, auth_result, calling_station_id, nas_ip) tuples
    in a deque for efficient sliding-window computation.
    """

    __slots__ = ("events",)

    def __init__(self) -> None:
        self.events: deque = deque()

    def add(self, ts: float, auth_result: str, device: str, nas_ip: str) -> None:
        """Append an event and evict entries older than 24 h."""
        self.events.append((ts, auth_result, device, nas_ip))
        cutoff = ts - _WINDOW_24H
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()

    def consecutive_failures(self, ts: float) -> float:
        """Count FAIL events in the 5-minute window ending at *ts*."""
        cutoff = ts - _WINDOW_5MIN
        return float(sum(
            1 for t, result, _, _ in self.events
            if t >= cutoff and result == "FAIL"
        ))

    def auth_rate_1h(self, ts: float) -> float:
        """Count events in the 1-hour window ending at *ts*."""
        cutoff = ts - _WINDOW_1H
        return float(sum(1 for t, _, _, _ in self.events if t >= cutoff))

    def failure_rate_1h(self, ts: float) -> float:
        """Fraction of events in the 1-hour window that are FAILs."""
        cutoff = ts - _WINDOW_1H
        total = 0
        failures = 0
        for t, result, _, _ in self.events:
            if t >= cutoff:
                total += 1
                if result == "FAIL":
                    failures += 1
        return failures / max(total, 1)

    def unique_devices_24h(self, ts: float) -> float:
        """Count distinct calling_station_id values in the 24-hour window."""
        cutoff = ts - _WINDOW_24H
        devices: Set[str] = set()
        for t, _, dev, _ in self.events:
            if t >= cutoff:
                devices.add(dev)
        return float(len(devices))

    def unique_nas_24h(self, ts: float) -> float:
        """Count distinct nas_ip values in the 24-hour window."""
        cutoff = ts - _WINDOW_24H
        nas_ips: Set[str] = set()
        for t, _, _, nip in self.events:
            if t >= cutoff:
                nas_ips.add(nip)
        return float(len(nas_ips))


# ---------------------------------------------------------------------------
# Feature extractor
# ---------------------------------------------------------------------------
class ISEDFPFeatureExtractor:
    """Transform ISE authentication events into 14-dimensional ML feature vectors.

    Call ``fit()`` on training data to learn known devices per user and the
    policy-set encoding map, then ``transform_batch()`` or ``transform_single()``
    to extract features.
    """

    FEATURE_COLS: List[str] = [
        "hour_sin",
        "hour_cos",
        "day_of_week",
        "is_weekend",
        "auth_result_code",
        "auth_type_code",
        "nas_port_type_code",
        "consecutive_failures",
        "auth_rate_1h",
        "unique_devices_24h",
        "unique_nas_24h",
        "failure_rate_1h",
        "known_device_flag",
        "policy_set_code",
    ]

    def __init__(self) -> None:
        self._scaler: Optional[StandardScaler] = None
        self._windows: Dict[str, _UserWindow] = {}
        # Populated by fit()
        self._known_devices: Dict[str, Set[str]] = {}  # user -> set of MACs
        self._policy_set_map: Dict[str, int] = {}

    # ----- helpers ---------------------------------------------------------
    @staticmethod
    def _parse_timestamp(ts_str: str) -> float:
        """Parse ISO-8601 timestamp string to epoch seconds (UTC)."""
        # Handle trailing Z
        s = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    def _get_window(self, username: str) -> _UserWindow:
        if username not in self._windows:
            self._windows[username] = _UserWindow()
        return self._windows[username]

    # ----- fit (training phase) --------------------------------------------
    def fit(self, records: List[Dict[str, Any]]) -> "ISEDFPFeatureExtractor":
        """Learn known devices per user and policy_set encoding from training records.

        Parameters
        ----------
        records : list of dict
            ISE auth events (training set -- normals only).
        """
        # Build known-device sets per user
        self._known_devices.clear()
        policy_sets: Set[str] = set()

        for rec in records:
            user = rec.get("username", "unknown")
            device = rec.get("calling_station_id", "")
            policy = rec.get("policy_set", "")

            self._known_devices.setdefault(user, set()).add(device)
            if policy:
                policy_sets.add(policy)

        # Deterministic policy_set encoding (alphabetical)
        self._policy_set_map = {
            name: idx for idx, name in enumerate(sorted(policy_sets))
        }

        logger.info(
            "fit() complete -- %d users, %d policy sets",
            len(self._known_devices),
            len(self._policy_set_map),
        )
        return self

    # ----- feature extraction for a single record --------------------------
    def _extract_features(self, record: Dict[str, Any]) -> Dict[str, float]:
        """Extract 14 features from a single ISE event.

        Assumes the per-user window has already been updated for events
        *before* this one (chronological order matters for rolling features).
        """
        ts_str = record.get("timestamp", "1970-01-01T00:00:00Z")
        ts = self._parse_timestamp(ts_str)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)

        username = record.get("username", "unknown")
        auth_result = record.get("auth_result", "FAIL")
        auth_type = record.get("auth_type", "")
        nas_port_type = record.get("nas_port_type", "")
        device = record.get("calling_station_id", "")
        nas_ip = record.get("nas_ip", "")
        policy_set = record.get("policy_set", "")

        # Get (or create) rolling window for this user
        window = self._get_window(username)

        # -- Temporal features --
        hour = dt.hour + dt.minute / 60.0
        hour_sin = math.sin(2 * math.pi * hour / 24.0)
        hour_cos = math.cos(2 * math.pi * hour / 24.0)
        day_of_week = float(dt.weekday())
        is_weekend = 1.0 if dt.weekday() >= 5 else 0.0

        # -- Categorical features --
        auth_result_code = _AUTH_RESULT_MAP.get(auth_result, 1.0)
        auth_type_code = _AUTH_TYPE_MAP.get(auth_type, _AUTH_TYPE_OTHER)
        nas_port_type_code = _NAS_PORT_TYPE_MAP.get(nas_port_type, _NAS_PORT_TYPE_OTHER)

        # -- Rolling window features (computed BEFORE adding current event) --
        consecutive_failures = window.consecutive_failures(ts)
        auth_rate_1h = window.auth_rate_1h(ts)
        unique_devices_24h = window.unique_devices_24h(ts)
        unique_nas_24h = window.unique_nas_24h(ts)
        failure_rate_1h = window.failure_rate_1h(ts)

        # -- Known device flag --
        user_known = self._known_devices.get(username, set())
        known_device_flag = 0.0 if device in user_known else 1.0

        # -- Policy set code --
        policy_set_code = float(self._policy_set_map.get(policy_set, len(self._policy_set_map)))

        # -- Add current event to the window for future records --
        window.add(ts, auth_result, device, nas_ip)

        return {
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "auth_result_code": auth_result_code,
            "auth_type_code": auth_type_code,
            "nas_port_type_code": nas_port_type_code,
            "consecutive_failures": consecutive_failures,
            "auth_rate_1h": auth_rate_1h,
            "unique_devices_24h": unique_devices_24h,
            "unique_nas_24h": unique_nas_24h,
            "failure_rate_1h": failure_rate_1h,
            "known_device_flag": known_device_flag,
            "policy_set_code": policy_set_code,
        }

    # ----- batch transform -------------------------------------------------
    def transform_batch(self, records: List[Dict[str, Any]]) -> pd.DataFrame:
        """Extract features from a list of ISE events in chronological order.

        Records MUST be sorted by (username, timestamp) so that rolling window
        features accumulate correctly.

        Parameters
        ----------
        records : list of dict
            ISE auth events sorted chronologically.

        Returns
        -------
        pd.DataFrame
            One row per event with columns in ``FEATURE_COLS``.
        """
        if not records:
            return pd.DataFrame(columns=self.FEATURE_COLS)

        logger.info("Extracting features from %d ISE events", len(records))
        rows: List[Dict[str, float]] = []
        for rec in records:
            rows.append(self._extract_features(rec))

        df = pd.DataFrame(rows, columns=self.FEATURE_COLS)
        df = df.fillna(0.0)
        logger.info("Feature matrix shape: %s", df.shape)
        return df

    # ----- single-event transform (for live inference) ---------------------
    def transform_single(self, record: Dict[str, Any]) -> Dict[str, float]:
        """Extract features for a single ISE event (live inference path).

        Updates the internal rolling window state.
        """
        return self._extract_features(record)

    # ----- window management -----------------------------------------------
    def reset_windows(self) -> None:
        """Clear all per-user rolling window state."""
        self._windows.clear()
        logger.info("Rolling windows reset")

    # ----- scaler ----------------------------------------------------------
    def fit_scaler(self, df: pd.DataFrame) -> "ISEDFPFeatureExtractor":
        """Fit the StandardScaler on the given feature DataFrame."""
        self._scaler = StandardScaler()
        self._scaler.fit(df[self.FEATURE_COLS])
        logger.info("Scaler fitted on %d samples", len(df))
        return self

    def scale(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply fitted StandardScaler to the feature DataFrame."""
        if self._scaler is None:
            raise RuntimeError("Scaler not fitted. Call fit_scaler() first.")
        scaled = self._scaler.transform(df[self.FEATURE_COLS])
        return pd.DataFrame(scaled, columns=self.FEATURE_COLS, index=df.index)

    def save_scaler(self, path: str) -> None:
        """Persist scaler, policy_set_map, and known_devices to JSON.

        JSON format avoids numpy/sklearn version mismatches across environments.
        """
        if self._scaler is None:
            raise RuntimeError("Scaler not fitted. Call fit_scaler() first.")

        # Serialize known devices: dict of user -> sorted list of MACs
        known_devices_serializable: Dict[str, List[str]] = {
            user: sorted(devices) for user, devices in self._known_devices.items()
        }

        data = {
            "mean": self._scaler.mean_.tolist(),
            "scale": self._scaler.scale_.tolist(),
            "var": self._scaler.var_.tolist(),
            "n_features_in": int(self._scaler.n_features_in_),
            "n_samples_seen": int(self._scaler.n_samples_seen_),
            "feature_names": self.FEATURE_COLS,
            "policy_set_map": self._policy_set_map,
            "known_devices": known_devices_serializable,
        }
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2)
        logger.info("Scaler saved to %s", path)

    def load_scaler(self, path: str) -> None:
        """Load scaler, policy_set_map, and known_devices from JSON."""
        with open(path) as fh:
            data = json.load(fh)

        self._scaler = StandardScaler()
        self._scaler.mean_ = np.array(data["mean"])
        self._scaler.scale_ = np.array(data["scale"])
        self._scaler.var_ = np.array(data["var"])
        self._scaler.n_features_in_ = data["n_features_in"]
        self._scaler.n_samples_seen_ = data["n_samples_seen"]

        self._policy_set_map = data.get("policy_set_map", {})
        raw_devices = data.get("known_devices", {})
        self._known_devices = {user: set(devs) for user, devs in raw_devices.items()}

        logger.info(
            "Scaler loaded from %s (%d users, %d policy sets)",
            path,
            len(self._known_devices),
            len(self._policy_set_map),
        )
