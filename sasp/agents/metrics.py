"""
SASP Agent Metrics Emitter

Emits agent performance metrics to Splunk HEC as sasp:agent_metrics events.
Used by graph.py to instrument the investigation pipeline.
"""

import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

SPLUNK_HEC_URL = os.environ.get(
    "SPLUNK_HEC_URL", "http://<SPLUNK_IP>:8088/services/collector/event"
)
SPLUNK_HEC_TOKEN = os.environ.get("SPLUNK_HEC_TOKEN", "")
SPLUNK_TLS_VERIFY = os.environ.get("SPLUNK_TLS_VERIFY", "false").lower() == "true"
LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:1234")


def emit_agent_metric(event: dict) -> None:
    """Post a single agent metric event to Splunk HEC. Fire-and-forget."""
    if not SPLUNK_HEC_TOKEN:
        return

    payload = {
        "index": "sasp_metrics",
        "sourcetype": "sasp:agent_metrics",
        "source": "sasp_agents",
        "event": event,
    }
    try:
        requests.post(
            SPLUNK_HEC_URL,
            json=payload,
            headers={"Authorization": f"Splunk {SPLUNK_HEC_TOKEN}"},
            verify=SPLUNK_TLS_VERIFY,
            timeout=5,
        )
    except requests.RequestException:
        pass  # fire-and-forget — don't break the pipeline


def emit_node_metric(
    agent_name: str,
    investigation_id: str,
    response_time_ms: float,
    status: str = "success",
    error: str | None = None,
) -> None:
    """Emit a per-node execution metric."""
    event = {
        "agent_name": agent_name,
        "investigation_id": investigation_id,
        "response_time_ms": round(response_time_ms, 1),
        "status": status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if error:
        event["error"] = error
    emit_agent_metric(event)


def emit_guardian_metric(
    investigation_id: str,
    validation_result: str,
    concerns: list[str] | None = None,
) -> None:
    """Emit a guardian validation metric."""
    emit_agent_metric({
        "agent_name": "guardian",
        "investigation_id": investigation_id,
        "validation_result": validation_result,
        "concerns": concerns or [],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


def emit_tool_call_metric(
    tool_name: str,
    agent_name: str,
    status: str = "success",
    duration_ms: float = 0,
) -> None:
    """Emit a tool call metric."""
    emit_agent_metric({
        "event_type": "tool_call",
        "tool_name": tool_name,
        "agent_name": agent_name,
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


def emit_llm_health_metric() -> None:
    """Probe the LLM endpoint and emit a health metric."""
    start = time.monotonic()
    try:
        resp = requests.get(f"{LLM_ENDPOINT}/v1/models", timeout=5)
        elapsed_ms = (time.monotonic() - start) * 1000
        emit_agent_metric({
            "event_type": "ollama_health",
            "endpoint": LLM_ENDPOINT,
            "response_time_ms": round(elapsed_ms, 1),
            "status": "healthy" if resp.status_code == 200 else "unhealthy",
            "http_status": resp.status_code,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except requests.RequestException as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        emit_agent_metric({
            "event_type": "ollama_health",
            "endpoint": LLM_ENDPOINT,
            "response_time_ms": round(elapsed_ms, 1),
            "status": "unreachable",
            "error": str(exc),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
