"""SASP Guardian Agent — validates all agent outputs before they reach the user.

The Guardian is the security watchdog that prevents:
- Prompt injection propagation in outputs
- Hallucinated tool calls
- Ungrounded claims
- Policy violations (PII leakage)
"""

import logging
import re
from typing import Any, Dict, List

from ...sanitizer.patterns import check_all_patterns
from ..state import InvestigationState, GuardianResult

logger = logging.getLogger(__name__)

# PII patterns for policy compliance check
PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
}


class GuardianAgent:
    """Validates investigation outputs against security policies."""

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        # Lazy import to avoid circular dependency at module load
        self._tool_registry = None

    @property
    def tool_registry(self):
        if self._tool_registry is None:
            try:
                from ..tools import TOOL_REGISTRY
                self._tool_registry = TOOL_REGISTRY
            except ImportError:
                logger.warning("Could not import TOOL_REGISTRY")
                self._tool_registry = {}
        return self._tool_registry

    def validate(self, state: InvestigationState) -> GuardianResult:
        """Run all validation checks on the investigation state.

        Returns GuardianResult with approved/needs_human_review/concerns.
        """
        concerns: List[str] = []
        checks: Dict[str, bool] = {}

        # Check 1: Output injection
        checks["output_injection"] = self._check_output_injection(state, concerns)

        # Check 2: Tool call validation
        checks["tool_calls_valid"] = self._check_tool_calls(state, concerns)

        # Check 3: Evidence grounding
        checks["evidence_grounded"] = self._check_evidence_grounding(state, concerns)

        # Check 4: Severity consistency
        checks["severity_consistent"] = self._check_severity_consistency(state, concerns)

        # Check 5: Policy compliance (PII)
        checks["policy_compliant"] = self._check_policy_compliance(state, concerns)

        # Determine final verdict
        all_passed = all(checks.values())
        injection_found = not checks.get("output_injection", True)
        severity = state.get("severity", "info")
        any_marginal = not all_passed and not injection_found

        approved = all_passed and not injection_found
        needs_human_review = (severity == "critical") or any_marginal

        if injection_found:
            approved = False
            needs_human_review = False  # Reject outright, don't send to human

        logger.info(
            "Guardian verdict: approved=%s human_review=%s checks=%s concerns=%d",
            approved, needs_human_review, checks, len(concerns),
        )

        return GuardianResult(
            approved=approved,
            needs_human_review=needs_human_review,
            concerns=concerns,
            validation_checks=checks,
        )

    # Categories relevant for output validation.  SQL and command injection
    # patterns are input sanitization concerns and produce false positives on
    # legitimate markdown/report content (e.g. ``# Heading`` matches the SQL
    # comment pattern ``#``).
    _OUTPUT_CATEGORIES = frozenset({"prompt", "exfiltration", "evasion"})

    def _check_output_injection(self, state: InvestigationState,
                                concerns: List[str]) -> bool:
        """Check report text fields for injection patterns."""
        clean = True
        for field_name in ("report_summary", "report_full"):
            text = state.get(field_name, "")
            if not text:
                continue
            hits = check_all_patterns(text)
            relevant = {
                cat: names for cat, names in hits.items()
                if cat in self._OUTPUT_CATEGORIES
            }
            if relevant:
                clean = False
                for category, patterns in relevant.items():
                    concerns.append(
                        f"Injection detected in {field_name}: "
                        f"category={category} patterns={patterns}"
                    )

        # Also check recommendations
        for i, rec in enumerate(state.get("recommendations", [])):
            hits = check_all_patterns(str(rec))
            relevant = {
                cat: names for cat, names in hits.items()
                if cat in self._OUTPUT_CATEGORIES
            }
            if relevant:
                clean = False
                concerns.append(f"Injection detected in recommendation #{i+1}")

        return clean

    def _check_tool_calls(self, state: InvestigationState,
                          concerns: List[str]) -> bool:
        """Verify all tool calls reference real tools with valid arguments."""
        tool_calls = state.get("tool_calls", [])
        if not tool_calls:
            return True

        valid = True
        registry = self.tool_registry

        for tc in tool_calls:
            tool_name = tc.get("tool_name", "")
            if tool_name not in registry:
                valid = False
                concerns.append(
                    f"Hallucinated tool call: '{tool_name}' is not in TOOL_REGISTRY"
                )

            # Check arguments are dict-like
            args = tc.get("arguments")
            if args is not None and not isinstance(args, dict):
                valid = False
                concerns.append(
                    f"Invalid arguments type for tool '{tool_name}': "
                    f"expected dict, got {type(args).__name__}"
                )

        return valid

    def _check_evidence_grounding(self, state: InvestigationState,
                                  concerns: List[str]) -> bool:
        """Verify that claims in report are backed by evidence."""
        report_summary = state.get("report_summary", "")
        evidence = state.get("evidence", [])

        if not report_summary or not evidence:
            # No report or no evidence — can't validate grounding
            if report_summary and not evidence:
                concerns.append(
                    "Report generated without any evidence to support claims"
                )
                return False
            return True

        # Extract key entities from evidence
        evidence_text = " ".join(
            str(e.get("result", "")) for e in evidence
        ).lower()

        # Extract IPs mentioned in report
        ip_pattern = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        report_ips = set(ip_pattern.findall(report_summary))

        ungrounded_ips = []
        for ip in report_ips:
            if ip not in evidence_text:
                ungrounded_ips.append(ip)

        if ungrounded_ips:
            concerns.append(
                f"IPs mentioned in report but not found in evidence: {ungrounded_ips}"
            )
            return False

        return True

    def _check_severity_consistency(self, state: InvestigationState,
                                    concerns: List[str]) -> bool:
        """Verify severity rating is consistent with evidence."""
        severity = state.get("severity", "info")
        iocs = state.get("iocs", [])
        evidence = state.get("evidence", [])
        mitre_techniques = state.get("mitre_techniques", [])

        if severity == "critical":
            # Critical should have strong evidence
            if len(iocs) < 1 and len(evidence) < 2:
                concerns.append(
                    "Severity 'critical' but insufficient evidence: "
                    f"{len(iocs)} IOCs, {len(evidence)} evidence items"
                )
                return False
        elif severity == "high":
            if len(evidence) < 1:
                concerns.append(
                    "Severity 'high' but no evidence collected"
                )
                return False

        return True

    def _check_policy_compliance(self, state: InvestigationState,
                                 concerns: List[str]) -> bool:
        """Check that no PII appears in report output."""
        clean = True
        for field_name in ("report_summary", "report_full"):
            text = state.get(field_name, "")
            if not text:
                continue
            for pii_type, pattern in PII_PATTERNS.items():
                if pattern.search(text):
                    clean = False
                    concerns.append(
                        f"PII ({pii_type}) detected in {field_name}"
                    )
        return clean
