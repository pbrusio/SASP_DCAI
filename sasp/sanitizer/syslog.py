"""
SASP Input Sanitizer - Syslog Data

Sanitizes syslog messages before they enter the ML pipeline.
Validates facility/severity codes and checks message content for injection.
"""

import copy
import logging
from typing import Any, Dict, List

from .base import BaseSanitizer, SanitizationResult
from .patterns import check_all_patterns

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ['timestamp', 'hostname', 'facility', 'severity', 'message']

MAX_MESSAGE_LENGTH = 8192


class SyslogSanitizer(BaseSanitizer):
    """Sanitizer for syslog records."""

    def validate_schema(self, data: Any) -> bool:
        """Validate that data is a dict with all required syslog fields."""
        if not isinstance(data, dict):
            return False
        return all(field in data for field in REQUIRED_FIELDS)

    def sanitize(self, data: Any) -> SanitizationResult:
        """Sanitize a syslog record."""
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

        # Check hostname for evasion patterns (zero-width, RTL, homoglyphs)
        hostname = str(sanitized.get('hostname', ''))
        hostname_hits = check_all_patterns(hostname)
        if hostname_hits:
            for category, names in hostname_hits.items():
                for name in names:
                    threats.append(f'injection_{name}')

        # Check message content for injection patterns BEFORE truncation
        # so patterns that straddle the boundary are still detected.
        msg = str(sanitized.get('message', ''))
        pattern_hits = check_all_patterns(msg)
        if pattern_hits:
            for category, names in pattern_hits.items():
                for name in names:
                    threats.append(f'injection_{name}')

        # Truncate message to MAX_MESSAGE_LENGTH
        if len(msg) > MAX_MESSAGE_LENGTH:
            sanitized['message'] = msg[:MAX_MESSAGE_LENGTH]
            modifications.append('truncated_message')

        # Encode special chars on hostname and message
        sanitized['hostname'] = self.encode_special_chars(str(sanitized['hostname']))
        sanitized['message'] = self.encode_special_chars(str(sanitized['message']))
        if sanitized['hostname'] != str(data['hostname']):
            modifications.append('encoded_hostname')
        if sanitized['message'] != str(data['message']):
            modifications.append('encoded_message')

        # Validate facility range (0-23)
        try:
            facility = int(sanitized['facility'])
            if not (0 <= facility <= 23):
                threats.append('invalid_facility')
                sanitized['facility'] = max(0, min(facility, 23))
                modifications.append('clamped_facility')
        except (ValueError, TypeError):
            threats.append('invalid_facility')

        # Validate severity range (0-7)
        try:
            severity = int(sanitized['severity'])
            if not (0 <= severity <= 7):
                threats.append('invalid_severity')
                sanitized['severity'] = max(0, min(severity, 7))
                modifications.append('clamped_severity')
        except (ValueError, TypeError):
            threats.append('invalid_severity')

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
