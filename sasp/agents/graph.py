"""
SASP Agent Workflow - LangGraph Implementation

Orchestrates the investigation workflow:
Detection -> Triage -> Investigate -> Threat Intel -> Report
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TypedDict, Literal, Annotated, List, Optional

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from .state import InvestigationState
from .nodes import triage, investigate, threat_intel, report
from .security.guardian import GuardianAgent
from .security.audit import AuditLogger
from .metrics import emit_node_metric, emit_guardian_metric, emit_llm_health_metric

logger = logging.getLogger(__name__)


def _safe_node(node_fn, node_name):
    """Wrap a node function with error handling and metrics."""
    def wrapper(state: InvestigationState) -> dict:
        inv_id = state.get("investigation_id", "unknown")
        start = time.monotonic()
        try:
            result = node_fn(state)
            elapsed_ms = (time.monotonic() - start) * 1000
            AuditLogger.log_agent_turn(node_name, str(hash(str(inv_id))), result)
            emit_node_metric(node_name, inv_id, elapsed_ms, status="success")
            return result
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.exception("Node '%s' failed", node_name)
            AuditLogger.log_agent_turn(node_name, "", {"error": str(e)})
            emit_node_metric(node_name, inv_id, elapsed_ms, status="error", error=str(e))
            return {"error": f"Node {node_name} failed: {str(e)}"}
    return wrapper


def error_handler(state: InvestigationState) -> dict:
    """Handle errors in the investigation pipeline."""
    error = state.get("error", "Unknown error")
    investigation_id = state.get("investigation_id", "unknown")
    logger.error("Investigation %s failed: %s", investigation_id, error)
    AuditLogger.log_agent_turn("error_handler", "", {"error": error})
    return {
        "report_summary": f"Investigation failed: {error}",
        "report_full": f"# Investigation Error\n\nInvestigation {investigation_id} encountered an error:\n\n{error}",
        "severity": "info",
        "confidence": 0.0,
        "end_time": datetime.now(timezone.utc).isoformat(),
    }


# Define the workflow graph
def create_investigation_graph() -> StateGraph:
    """
    Create the LangGraph workflow for security investigations.

    Workflow:
    1. Detection arrives from Morpheus
    2. Triage agent decides if worth investigating
    3. If yes, Investigation agent gathers evidence
    4. Threat Intel agent enriches with IOC/reputation data
    5. Report agent generates findings
    6. Guardian agent validates all outputs
    7. Human approval for high-severity actions

    Returns:
        Compiled StateGraph
    """

    # Initialize graph with state schema
    workflow = StateGraph(InvestigationState)

    # Add nodes (wrapped with error handling)
    workflow.add_node("triage", _safe_node(triage.run, "triage"))
    workflow.add_node("investigate", _safe_node(investigate.run, "investigate"))
    workflow.add_node("threat_intel", _safe_node(threat_intel.run, "threat_intel"))
    workflow.add_node("report", _safe_node(report.run, "report"))
    workflow.add_node("guardian_check", guardian_check)
    workflow.add_node("human_approval", human_approval)
    workflow.add_node("error", error_handler)

    # Define edges
    workflow.set_entry_point("triage")

    # Conditional routing after triage
    workflow.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "investigate": "investigate",
            "skip": END,
            "escalate": "human_approval",
        }
    )

    # Sequential flow for investigation
    workflow.add_edge("investigate", "threat_intel")
    workflow.add_edge("threat_intel", "report")
    workflow.add_edge("report", "guardian_check")

    # Guardian check routes to approval or end
    workflow.add_conditional_edges(
        "guardian_check",
        route_after_guardian,
        {
            "approve": END,
            "human_review": "human_approval",
            "reject": END,
        }
    )

    workflow.add_edge("human_approval", END)
    workflow.add_edge("error", END)

    return workflow.compile()


def route_after_triage(state: InvestigationState) -> Literal["investigate", "skip", "escalate"]:
    """
    Route based on triage decision.

    Args:
        state: Current investigation state

    Returns:
        Next node to execute
    """
    decision = state.get("triage_decision")
    if decision == "investigate":
        return "investigate"
    elif decision == "escalate":
        return "escalate"
    return "skip"


def route_after_guardian(state: InvestigationState) -> Literal["approve", "human_review", "reject"]:
    """
    Route based on guardian validation.

    Args:
        state: Current investigation state

    Returns:
        Next node to execute
    """
    guardian_result = state.get("guardian_result", {})

    if guardian_result.get("approved"):
        return "approve"
    elif guardian_result.get("needs_human_review"):
        return "human_review"
    else:
        return "reject"


def guardian_check(state: InvestigationState) -> InvestigationState:
    """
    Guardian agent validates the investigation output.

    Checks for:
    - Prompt injection in outputs
    - Hallucinated tool calls
    - Unauthorized actions
    - Policy violations

    Args:
        state: Current investigation state

    Returns:
        Updated state with guardian result
    """
    inv_id = state.get("investigation_id", "unknown")
    start = time.monotonic()
    guardian = GuardianAgent()
    result = guardian.validate(state)
    elapsed_ms = (time.monotonic() - start) * 1000

    # Log to audit trail
    AuditLogger.log_guardian_check(state, result)

    # Emit guardian metric
    if result.get("approved"):
        validation_result = "approved"
    elif result.get("needs_human_review"):
        validation_result = "human_review"
    else:
        validation_result = "rejected"
    emit_guardian_metric(inv_id, validation_result, result.get("concerns", []))
    emit_node_metric("guardian", inv_id, elapsed_ms, status="success")

    return {**state, "guardian_result": result}


def human_approval(state: InvestigationState) -> InvestigationState:
    """
    Queue investigation for human approval.

    Used for:
    - High severity incidents
    - Actions requiring confirmation
    - Guardian flagged issues

    Args:
        state: Current investigation state

    Returns:
        Updated state with approval request
    """
    # TODO: Implement approval queue (webhook, Slack, email, etc.)
    approval_request = {
        "investigation_id": state.get("investigation_id"),
        "severity": state.get("severity"),
        "summary": state.get("report_summary"),
        "guardian_concerns": state.get("guardian_result", {}).get("concerns", []),
        "status": "pending_approval",
    }

    AuditLogger.log_approval_request(approval_request)

    return {**state, "approval_request": approval_request}


# Main entry point - compile graph at module level with error protection
try:
    investigation_graph = create_investigation_graph()
except Exception as e:
    logger.error("Failed to compile investigation graph: %s", e)
    investigation_graph = None


def run_investigation(detection: dict) -> dict:
    """
    Run a security investigation on a detection.

    Args:
        detection: Detection event from Morpheus

    Returns:
        Investigation results
    """
    if investigation_graph is None:
        return {"error": "Investigation graph not compiled", "investigation_id": "none"}

    # Emit LLM health probe (fire-and-forget)
    try:
        emit_llm_health_metric()
    except Exception:
        pass

    start_time = datetime.now(timezone.utc)
    initial_state = {
        "detection": detection,
        "investigation_id": f"inv-{uuid.uuid4().hex[:12]}",
        "messages": [],
        "evidence": [],
        "tool_calls": [],
        "start_time": start_time.isoformat(),
    }

    result = investigation_graph.invoke(initial_state)
    end_time = datetime.now(timezone.utc)
    result["end_time"] = end_time.isoformat()
    result["duration_seconds"] = (end_time - start_time).total_seconds()
    return result
