"""SASP Report Agent Node — generates investigation report."""

import json
import logging
from typing import Any, Dict, List

from ..state import InvestigationState, AGENT_CONFIGS
from ..llm_client import generate

logger = logging.getLogger(__name__)


def _compute_investigation_confidence(state: InvestigationState) -> float:
    """Derive confidence from evidence quality, not LLM self-assessment.

    Factors:
    - Upstream anomaly_score from Morpheus/Triton (ML-grounded)
    - Number of evidence sources that returned data
    - Presence of IOCs from threat intel
    - MITRE technique mappings found

    NOTE: When the serving layer supports logprobs (e.g. vLLM), this can
    be augmented with token-level probabilities on severity/classification tokens.
    """
    score = 0.0
    factors = 0

    # Anomaly score from upstream ML model (strongest signal)
    detection = state.get("detection", {})
    anomaly_score = detection.get("anomaly_score")
    if anomaly_score is not None:
        try:
            score += float(anomaly_score) * 2  # Double-weighted
            factors += 2
        except (ValueError, TypeError):
            pass

    # Evidence coverage — how many tools returned results
    evidence = state.get("evidence", [])
    tool_calls = state.get("tool_calls", [])
    if tool_calls:
        successful = sum(1 for tc in tool_calls if tc.get("result") is not None)
        coverage = successful / len(tool_calls)
        score += coverage
        factors += 1

    # IOC enrichment
    iocs = state.get("iocs", [])
    if iocs:
        score += min(len(iocs) / 5, 1.0)  # Cap at 5 IOCs
        factors += 1

    # MITRE technique mappings
    mitre = state.get("mitre_techniques", [])
    if mitre:
        score += min(len(mitre) / 3, 1.0)  # Cap at 3 techniques
        factors += 1

    if factors == 0:
        return 0.5

    return round(score / factors, 3)


def run(state: InvestigationState) -> dict:
    """Generate investigation report from all gathered evidence."""
    config = AGENT_CONFIGS["report"]

    # Build context
    detection = state.get("detection", {})
    evidence = state.get("evidence", [])
    iocs = state.get("iocs", [])
    mitre = state.get("mitre_techniques", [])
    affected_assets = state.get("affected_assets", [])
    affected_users = state.get("affected_users", [])
    timeline = state.get("timeline", [])
    threat_actor = state.get("threat_actor")
    triage_reasoning = state.get("triage_reasoning", "")

    prompt = (
        "You are a security report writer. Generate a comprehensive investigation report.\n\n"
        f"Detection: {json.dumps(detection, default=str)}\n"
        f"Triage Assessment: {triage_reasoning}\n"
        f"Evidence ({len(evidence)} items): {json.dumps(evidence, default=str)}\n"
        f"IOCs: {json.dumps(iocs, default=str)}\n"
        f"MITRE ATT&CK: {mitre}\n"
        f"Affected Assets: {affected_assets}\n"
        f"Affected Users: {affected_users}\n"
        f"Timeline: {json.dumps(timeline, default=str)}\n"
        f"Threat Actor: {threat_actor}\n\n"
        "Respond with JSON containing:\n"
        "1. report_summary: 2-3 sentence executive summary\n"
        "2. report_full: detailed markdown report with sections: "
        "Executive Summary, Detection Details, Timeline, Evidence Analysis, "
        "MITRE ATT&CK Mapping, Impact Assessment, Recommendations\n"
        "3. recommendations: list of actionable items\n"
        "4. severity: critical/high/medium/low/info based on evidence\n\n"
        "Respond with JSON: {\"report_summary\": \"...\", \"report_full\": \"...\", "
        "\"recommendations\": [...], \"severity\": \"...\"}"
    )

    response = generate(
        config.endpoint, config.model, prompt,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout_seconds,
    )

    try:
        parsed = json.loads(response)
        report_summary = parsed.get("report_summary", "Investigation completed.")
        report_full = parsed.get("report_full", "No detailed report generated.")
        recommendations = parsed.get("recommendations", [])
        severity = parsed.get("severity", "medium")
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse report LLM response, generating fallback")
        report_summary = f"Investigation of detection from {detection.get('src_ip', 'unknown')}. {len(evidence)} evidence items collected."
        report_full = f"# Investigation Report\n\n## Detection\n{json.dumps(detection, indent=2, default=str)}\n\n## Evidence\n{len(evidence)} items collected.\n\n## IOCs\n{len(iocs)} indicators found."
        recommendations = ["Review detection manually", "Check affected assets"]
        severity = "medium"

    if severity not in ("critical", "high", "medium", "low", "info"):
        severity = "medium"

    # Confidence from evidence quality, not LLM self-assessment
    confidence = _compute_investigation_confidence(state)

    return {
        "report_summary": report_summary,
        "report_full": report_full,
        "recommendations": recommendations,
        "severity": severity,
        "confidence": confidence,
    }
