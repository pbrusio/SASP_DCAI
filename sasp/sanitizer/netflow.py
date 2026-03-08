"""
SASP Input Sanitizer - NetFlow Data

Sanitizes NetFlow/IPFIX records before they enter the ML pipeline.
Validates IP addresses, port ranges, and protocol numbers.
"""

import copy
import ipaddress
import logging
from typing import Any, Dict, List

from .base import BaseSanitizer, SanitizationResult
from .patterns import check_all_patterns

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = [
    'type', 'sampler_address', 'src_addr', 'dst_addr',
    'src_port', 'dst_port', 'proto', 'bytes', 'packets',
]

NUMERIC_RANGES = {
    'src_port': (0, 65535),
    'dst_port': (0, 65535),
    'bytes': (0, 2**40),
    'packets': (0, 2**32),
}


class NetFlowSanitizer(BaseSanitizer):
    """Sanitizer for NetFlow/IPFIX flow records."""

    def validate_schema(self, data: Any) -> bool:
        """Validate that data is a dict with all required NetFlow fields."""
        if not isinstance(data, dict):
            return False
        return all(field in data for field in REQUIRED_FIELDS)

    def _validate_ip(self, addr: str) -> bool:
        """Validate an IP address string."""
        try:
            ipaddress.ip_address(addr)
            return True
        except (ValueError, TypeError):
            return False

    def _clamp_numeric(self, value: Any, field: str) -> int:
        """Clamp a numeric value to the valid range for its field."""
        if field not in NUMERIC_RANGES:
            return int(value)
        low, high = NUMERIC_RANGES[field]
        try:
            val = int(value)
        except (ValueError, TypeError):
            return low
        return max(low, min(val, high))

    def sanitize(self, data: Any) -> SanitizationResult:
        """Sanitize a NetFlow record."""
        threats: List[str] = []
        modifications: List[str] = []

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

        # Validate IP address fields
        for ip_field in ('src_addr', 'dst_addr', 'sampler_address'):
            addr = str(sanitized.get(ip_field, ''))
            if not self._validate_ip(addr):
                threats.append(f'invalid_ip_{ip_field}')
            # Check string representation for injection patterns
            pattern_hits = check_all_patterns(addr)
            if pattern_hits:
                threats.append(f'injection_{ip_field}')

        # Clamp numeric fields
        for field in NUMERIC_RANGES:
            if field in sanitized:
                original_val = sanitized[field]
                sanitized[field] = self._clamp_numeric(original_val, field)
                if sanitized[field] != original_val:
                    modifications.append(f'clamped_{field}')

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
