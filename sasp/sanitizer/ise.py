"""
SASP Input Sanitizer - Cisco ISE Data

Sanitizes Cisco ISE authentication/authorization records before
they enter the ML pipeline. Validates MAC addresses, IPs, and
checks for injection in user-controlled fields.
"""

import copy
import ipaddress
import logging
import re
from typing import Any, Dict, List

from .base import BaseSanitizer, SanitizationResult
from .patterns import check_all_patterns

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = [
    'username', 'nas_ip', 'calling_station_id',
    'called_station_id', 'auth_result', 'policy_set',
]

MAC_PATTERN = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$')

# Real ISE MESSAGE_CODE → internal auth_result
_MESSAGE_CODE_MAP: Dict[str, str] = {
    "5200": "PASS",
    "5201": "PASS",
    "5400": "FAIL",
    "5401": "FAIL",
}

# Real ISE Protocol → internal auth_type
_PROTOCOL_MAP: Dict[str, str] = {
    "Radius": "802.1X",
    "Tacacs": "TACACS+",
}

# Rich ISE fields preserved as extras for Splunk dashboards
_RICH_ISE_FIELDS = (
    "EndPointMatchedProfile", "TotalAuthenLatency",
    "NetworkDeviceName", "IdentityGroup", "Framed_IP_Address",
    "RadiusFlowType", "UserType", "AcsSessionID",
    "AuthorizationPolicyMatchedRule", "NAS_Port_Id",
)


class ISESanitizer(BaseSanitizer):
    """Sanitizer for Cisco ISE authentication records."""

    @staticmethod
    def _normalize_mac(mac: str) -> str:
        """Convert dash-separated MAC to colon-separated."""
        return mac.replace("-", ":")

    @staticmethod
    def _normalize_ise_fields(data: Dict[str, Any]) -> Dict[str, Any]:
        """Detect real ISE syslog format and map to internal field names.

        Real ISE uses PascalCase/mixed fields (UserName, NAS_IP_Address, etc.).
        Internal format uses lowercase (username, nas_ip, etc.).
        If data already has internal field names, returns it unchanged.
        """
        # Auto-detect: internal format has "username", real ISE has "UserName"
        if "username" in data and "UserName" not in data:
            return data  # already internal format

        normalized: Dict[str, Any] = {}
        normalized["username"] = data.get("UserName", data.get("User_Name", "unknown"))
        normalized["nas_ip"] = data.get(
            "NAS_IP_Address", data.get("Device_IP_Address", ""),
        )

        # MAC normalization (dash → colon)
        raw_calling = data.get("Calling_Station_ID", "")
        normalized["calling_station_id"] = ISESanitizer._normalize_mac(raw_calling)
        raw_called = data.get("Called_Station_ID", "")
        normalized["called_station_id"] = ISESanitizer._normalize_mac(raw_called)

        # MESSAGE_CODE → auth_result
        msg_code = str(data.get("MESSAGE_CODE", ""))
        normalized["auth_result"] = _MESSAGE_CODE_MAP.get(
            msg_code,
            data.get("AuthenticationStatus", "FAIL").upper(),
        )

        # Protocol → auth_type
        protocol = data.get("Protocol", "")
        normalized["auth_type"] = _PROTOCOL_MAP.get(protocol, protocol)

        # NAS_Port_Type — direct (already matches internal names)
        normalized["nas_port_type"] = data.get("NAS_Port_Type", "Ethernet")

        # Policy set
        normalized["policy_set"] = data.get(
            "ISEPolicySetName", data.get("policy_set", ""),
        )

        # Timestamp — prefer _time from Splunk, fall back to existing
        normalized["timestamp"] = data.get("_time", data.get("timestamp", ""))

        # Preserve rich ISE fields as extras (for Splunk/dashboards)
        for extra_field in _RICH_ISE_FIELDS:
            if extra_field in data:
                normalized[extra_field] = data[extra_field]

        # Preserve internal fields that may exist (e.g., _anomaly_label)
        if "_anomaly_label" in data:
            normalized["_anomaly_label"] = data["_anomaly_label"]

        return normalized

    def validate_schema(self, data: Any) -> bool:
        """Validate that data is a dict with all required ISE fields."""
        if not isinstance(data, dict):
            return False
        return all(field in data for field in REQUIRED_FIELDS)

    def _validate_mac(self, mac: str) -> bool:
        """Validate a MAC address string."""
        return bool(MAC_PATTERN.match(mac))

    def sanitize(self, data: Any) -> SanitizationResult:
        """Sanitize a Cisco ISE record."""
        threats: List[str] = []
        modifications: List[str] = []

        # Normalize real ISE syslog fields to internal format
        if isinstance(data, dict):
            data = self._normalize_ise_fields(data)

        # Schema validation
        if not self.validate_schema(data):
            return SanitizationResult(
                original=data,
                sanitized=data,
                is_clean=False,
                threats_detected=['invalid_schema'],
                modifications=[],
            )

        sanitized = copy.deepcopy(data)

        # Check username and policy_set for injection patterns
        for field in ('username', 'policy_set'):
            text = str(sanitized.get(field, ''))
            pattern_hits = check_all_patterns(text)
            if pattern_hits:
                for category, names in pattern_hits.items():
                    for name in names:
                        threats.append(f'injection_{field}_{name}')

        # Validate nas_ip as a valid IP address
        nas_ip = str(sanitized.get('nas_ip', ''))
        try:
            ipaddress.ip_address(nas_ip)
        except (ValueError, TypeError):
            threats.append('invalid_nas_ip')

        # Validate calling_station_id and called_station_id as MAC addresses
        for mac_field in ('calling_station_id', 'called_station_id'):
            mac = str(sanitized.get(mac_field, ''))
            if not self._validate_mac(mac):
                threats.append(f'invalid_mac_{mac_field}')

        # Encode special chars on username and policy_set
        for field in ('username', 'policy_set'):
            original_val = str(data[field])
            sanitized[field] = self.encode_special_chars(str(sanitized[field]))
            if sanitized[field] != original_val:
                modifications.append(f'encoded_{field}')

        # Validate auth_result is a reasonable value
        auth_result = str(sanitized.get('auth_result', ''))
        if not auth_result or not auth_result.replace('_', '').replace('-', '').isalnum():
            threats.append('invalid_auth_result')

        # Log originals if threats found
        if threats:
            self.log_original(data, threats)

        is_clean = len(threats) == 0
        return SanitizationResult(
            original=data,
            sanitized=sanitized,
            is_clean=is_clean,
            threats_detected=threats,
            modifications=modifications,
        )
