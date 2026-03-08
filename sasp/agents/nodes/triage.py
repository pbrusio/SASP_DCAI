"""SASP Triage Agent Node — decides whether a detection warrants investigation."""

import json
import logging
from typing import Any, Dict

from ..state import InvestigationState, AGENT_CONFIGS
from ..llm_client import generate

logger = logging.getLogger(__name__)


def _build_triage_prompt(detection: Dict[str, Any]) -> str:
    """Format detection data into a triage prompt."""
    return (
        "You are a security triage analyst. Analyze the following detection event "
        "and decide whether it warrants investigation.\n\n"
        f"Detection Data:\n{json.dumps(detection, indent=2, default=str)}\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"decision": "investigate|skip|escalate", '
        '"reasoning": "detailed explanation of your assessment"}\n'
    )


def _compute_confidence(detection: Dict[str, Any], decision: str) -> float:
    """Derive triage confidence from the ML model's anomaly score.

    The anomaly_score is produced by the upstream Morpheus/Triton pipeline
    and represents actual model output — not an LLM self-assessment.

    NOTE: When the serving layer supports logprobs (e.g. vLLM), this should
    be replaced with token-level probability on the decision token.
    """
    anomaly_score = detection.get("anomaly_score")
    if anomaly_score is not None:
        try:
            score = float(anomaly_score)
            # For "skip" decisions on high-anomaly detections, confidence
            # reflects how sure we are about skipping (inverse).
            if decision == "skip":
                return round(1.0 - score, 3)
            return round(score, 3)
        except (ValueError, TypeError):
            pass
    # Fallback: no anomaly score available
    return 0.5


def run(state: InvestigationState) -> dict:
    """Execute triage node: assess detection and decide next action."""
    detection = state.get("detection", {})
    config = AGENT_CONFIGS["triage"]

    prompt = _build_triage_prompt(detection)
    response_text = generate(
        config.endpoint, config.model, prompt,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout_seconds,
    )

    # Parse response
    try:
        result = json.loads(response_text)
        decision = result.get("decision", "skip")
        reasoning = result.get("reasoning", "No reasoning provided")
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse triage response, defaulting to skip")
        decision = "skip"
        reasoning = f"Failed to parse LLM response: {response_text[:200]}"

    # Validate decision
    if decision not in ("investigate", "skip", "escalate"):
        decision = "skip"

    # Confidence from upstream ML model, not LLM self-assessment
    confidence = _compute_confidence(detection, decision)

    return {
        "triage_decision": decision,
        "triage_reasoning": reasoning,
        "triage_confidence": confidence,
    }
