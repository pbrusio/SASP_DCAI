"""SASP Investigation Agent Node — gathers evidence using available tools."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..state import InvestigationState, AGENT_CONFIGS, Evidence, ToolCall
from ..llm_client import generate

logger = logging.getLogger(__name__)


def _execute_tool(tool_name: str, arguments: dict) -> dict:
    """Execute a tool from the registry and return the result."""
    try:
        from ..tools import TOOL_REGISTRY
        tool_fn = TOOL_REGISTRY.get(tool_name)
        if tool_fn is None:
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
    """Execute investigation node: gather evidence using tools."""
    detection = state.get("detection", {})
    config = AGENT_CONFIGS["investigate"]
    now = datetime.now(timezone.utc).isoformat()

    evidence: List[Evidence] = list(state.get("evidence", []))
    tool_calls: List[ToolCall] = list(state.get("tool_calls", []))
    affected_assets: List[str] = list(state.get("affected_assets", []))
    affected_users: List[str] = list(state.get("affected_users", []))
    timeline: List[Dict[str, Any]] = list(state.get("timeline", []))

    # Determine what to investigate from detection
    src_ip = detection.get("src_ip") or detection.get("SrcAddr", "")
    dst_ip = detection.get("dst_ip") or detection.get("DstAddr", "")

    # Execute each configured tool
    for tool_name in config.tools:
        if tool_name == "splunk_query":
            args = {"query": f'index=* src_ip="{src_ip}" OR dst_ip="{dst_ip}"',
                    "earliest": "-24h", "latest": "now"}
        elif tool_name == "ise_lookup":
            args = {"ip": src_ip}
        elif tool_name == "asset_lookup":
            args = {"ip": src_ip}
        elif tool_name == "baseline_query":
            args = {"ip": src_ip, "metric": "bytes_per_hour"}
        else:
            args = {}

        tool_result = _execute_tool(tool_name, args)
        tool_calls.append(ToolCall(
            tool_name=tool_name, arguments=args,
            result=tool_result.get("result"), agent="investigate", timestamp=now
        ))

        if tool_result["success"] and tool_result["result"]:
            evidence.append(Evidence(
                source=tool_name, query=json.dumps(args, default=str),
                result=tool_result["result"], timestamp=now
            ))

    # Use LLM to synthesize findings
    evidence_summary = json.dumps([e.get("result") for e in evidence], default=str)[:4000]
    prompt = (
        "You are a security investigator. Based on the following evidence, identify:\n"
        "1. Affected assets (IPs, hostnames)\n2. Affected users\n3. Timeline of events\n\n"
        f"Detection: {json.dumps(detection, default=str)[:1000]}\n\n"
        f"Evidence: {evidence_summary}\n\n"
        "Respond with JSON: {\"affected_assets\": [...], \"affected_users\": [...], "
        "\"timeline\": [{\"time\": ..., \"event\": ...}]}"
    )

    response = generate(
        config.endpoint, config.model, prompt,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout_seconds,
    )
    try:
        parsed = json.loads(response)
        affected_assets.extend(parsed.get("affected_assets", []))
        affected_users.extend(parsed.get("affected_users", []))
        timeline.extend(parsed.get("timeline", []))
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse investigation LLM response")
        if src_ip: affected_assets.append(src_ip)
        if dst_ip: affected_assets.append(dst_ip)

    return {
        "evidence": evidence,
        "tool_calls": tool_calls,
        "affected_assets": list(set(affected_assets)),
        "affected_users": list(set(affected_users)),
        "timeline": timeline,
    }
