"""SASP Output Validator — checks agent outputs for security policy compliance."""

import re
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

MAX_OUTPUT_LENGTH = 50000

# PII detection patterns
PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
}

# Dangerous content patterns
DANGEROUS_PATTERNS = {
    "script_tag": re.compile(r"<\s*script[^>]*>", re.IGNORECASE),
    "html_tag": re.compile(r"<\s*(iframe|object|embed|form|input)\b", re.IGNORECASE),
    "base64_blob": re.compile(r"[A-Za-z0-9+/=]{100,}"),
    "external_url": re.compile(
        r"https?://(?!(?:localhost|127\.0\.0\.1|10\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.))[^\s\"'>]+",
        re.IGNORECASE,
    ),
}

# Allowed external domains (threat intel sources)
ALLOWED_EXTERNAL_DOMAINS = {
    "virustotal.com", "abuseipdb.com", "mitre.org",
    "attack.mitre.org", "cve.org", "nvd.nist.gov",
}


@dataclass
class ValidationResult:
    """Result of output validation."""
    is_valid: bool
    violations: List[str] = field(default_factory=list)
    sanitized_text: str = ""
    pii_found: List[str] = field(default_factory=list)


def check_pii(text: str) -> List[str]:
    """Check text for PII patterns.

    Returns list of PII types found (e.g., ['ssn', 'email']).
    """
    found = []
    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            found.append(pii_type)
    return found


def validate_output(text: str) -> ValidationResult:
    """Validate agent output text for security policy compliance.

    Checks:
    - Maximum length
    - No script/iframe/form HTML tags
    - No base64 blobs over 100 chars
    - No URLs to non-whitelisted external domains
    - No PII (SSN, credit card)

    Returns:
        ValidationResult with is_valid flag, violations, and sanitized text
    """
    violations = []
    sanitized = text

    # Check length
    if len(text) > MAX_OUTPUT_LENGTH:
        violations.append(f"Output exceeds maximum length ({len(text)} > {MAX_OUTPUT_LENGTH})")
        sanitized = sanitized[:MAX_OUTPUT_LENGTH]

    # Check for dangerous HTML
    for pattern_name, pattern in DANGEROUS_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            if pattern_name == "external_url":
                # Filter out allowed domains
                for url in matches:
                    is_allowed = any(domain in url.lower() for domain in ALLOWED_EXTERNAL_DOMAINS)
                    if not is_allowed:
                        violations.append(f"External URL detected: {url[:100]}")
                        sanitized = sanitized.replace(url, "[URL_REDACTED]")
            elif pattern_name == "base64_blob":
                violations.append(f"Large base64 blob detected ({len(matches)} occurrences)")
                for match in matches:
                    sanitized = sanitized.replace(match, "[BASE64_REDACTED]")
            else:
                violations.append(f"Dangerous HTML pattern: {pattern_name}")
                for match in matches:
                    sanitized = sanitized.replace(match, f"[{pattern_name.upper()}_REMOVED]")

    # Check for PII
    pii_found = check_pii(text)
    if pii_found:
        violations.append(f"PII detected: {', '.join(pii_found)}")

    is_valid = len(violations) == 0

    if violations:
        logger.warning("Output validation failed: %s", "; ".join(violations))

    return ValidationResult(
        is_valid=is_valid,
        violations=violations,
        sanitized_text=sanitized,
        pii_found=pii_found,
    )
