"""SASP Threat Intelligence Agent Node — enriches with IOCs and MITRE mapping."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..state import InvestigationState, AGENT_CONFIGS, ToolCall
from ..llm_client import generate

logger = logging.getLogger(__name__)


def _execute_tool(tool_name: str, arguments: dict) -> dict:
    """Execute a tool from the registry and return the result."""
    try:
        from ..tools import TOOL_REGISTRY
        tool_fn = TOOL_REGISTRY.get(tool_name)
        if not tool_fn:
            return {"tool_name": tool_name, "success": False, "result": None,
                    "error": f"Unknown tool: {tool_name}", "duration_ms": 0}
        start = time.monotonic()
        result = tool_fn(**arguments)
        duration = int((time.monotonic() - start) * 1000)
        return {"tool_name": tool_name, "success": True, "result": result,
                "error": None, "duration_ms": duration}
    except Exception as e:
        return {"tool_name": tool_name, "success": False, "result": None,
                "error": str(e), "duration_ms": 0}


def run(state: InvestigationState) -> dict:
    """Execute threat intel node: enrich with IOCs and MITRE mapping."""
    detection = state.get("detection", {})
    evidence = state.get("evidence", [])
    config = AGENT_CONFIGS["threat_intel"]
    now = datetime.now(timezone.utc).isoformat()

    tool_calls = list(state.get("tool_calls", []))
    iocs: List[Dict[str, Any]] = list(state.get("iocs", []))

    # Extract IPs to look up
    ips_to_check = set()
    for field in ("src_ip", "SrcAddr", "dst_ip", "DstAddr"):
        ip = detection.get(field)
        if ip:
            ips_to_check.add(ip)

    # Look up each IP in threat intel
    for ip in ips_to_check:
        result = _execute_tool("threat_intel", {"query": ip, "query_type": "ip"})
        tool_calls.append(ToolCall(
            tool_name="threat_intel", arguments={"query": ip, "query_type": "ip"},
            result=result.get("result"), agent="threat_intel", timestamp=now
        ))
        if result["success"] and result["result"]:
            iocs.append({"type": "ip", "value": ip, "intel": result["result"]})

    # Map to MITRE ATT&CK
    evidence_text = json.dumps(evidence, default=str)[:2000]
    mitre_result = _execute_tool("mitre_mapper", {"behaviors": evidence_text})
    tool_calls.append(ToolCall(
        tool_name="mitre_mapper", arguments={"behaviors": evidence_text},
        result=mitre_result.get("result"), agent="threat_intel", timestamp=now
    ))

    mitre_techniques = []
    kill_chain_phase = None
    if mitre_result["success"] and mitre_result["result"]:
        mitre_data = mitre_result["result"]
        if isinstance(mitre_data, dict):
            mitre_techniques = mitre_data.get("techniques", [])
            kill_chain_phase = mitre_data.get("kill_chain_phase")

    # Use LLM to identify threat actor and campaigns
    prompt = (
        "You are a threat intelligence analyst. Based on the following IOCs and evidence, "
        "identify any known threat actors or campaigns.\n\n"
        f"IOCs: {json.dumps(iocs, default=str)[:2000]}\n"
        f"Evidence: {evidence_text}\n"
        f"MITRE Techniques: {mitre_techniques}\n\n"
        "Respond with JSON: {\"threat_actor\": \"name or null\", "
        "\"campaigns\": [\"list\"], \"cves\": [\"list\"]}"
    )

    response = generate(
        config.endpoint, config.model, prompt,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout_seconds,
    )
    threat_actor = None
    campaigns = []
    cves = []
    try:
        parsed = json.loads(response)
        threat_actor = parsed.get("threat_actor")
        campaigns = parsed.get("campaigns", [])
        cves = parsed.get("cves", [])
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse threat intel LLM response")

    return {
        "tool_calls": tool_calls,
        "iocs": iocs,
        "mitre_techniques": mitre_techniques,
        "kill_chain_phase": kill_chain_phase,
        "threat_actor": threat_actor,
        "campaigns": campaigns,
        "cves": cves,
    }
