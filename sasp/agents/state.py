"""
SASP Agent State Schema

Defines the state that flows through the investigation workflow.
"""

from typing import TypedDict, List, Optional, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime


class Evidence(TypedDict):
    """A piece of evidence gathered during investigation."""
    source: str  # e.g., "splunk", "ise", "threat_intel"
    query: str
    result: Any
    timestamp: str


class ToolCall(TypedDict):
    """Record of a tool call made by an agent."""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    agent: str
    timestamp: str


class GuardianResult(TypedDict):
    """Result of guardian agent validation."""
    approved: bool
    needs_human_review: bool
    concerns: List[str]
    validation_checks: Dict[str, bool]


class InvestigationState(TypedDict, total=False):
    """
    State schema for the investigation workflow.
    
    This state is passed through all nodes in the LangGraph workflow.
    Each node can read and update the state.
    """
    
    # Identity
    investigation_id: str
    
    # Input
    detection: Dict[str, Any]  # Original detection from Morpheus
    
    # Conversation
    messages: List[Dict[str, str]]  # Agent message history
    
    # Triage
    triage_decision: Literal["investigate", "skip", "escalate"]
    triage_reasoning: str
    triage_confidence: float
    
    # Investigation
    evidence: List[Evidence]
    tool_calls: List[ToolCall]
    timeline: List[Dict[str, Any]]
    affected_assets: List[str]
    affected_users: List[str]
    
    # Threat Intelligence
    iocs: List[Dict[str, Any]]  # Indicators of compromise
    threat_actor: Optional[str]
    campaigns: List[str]
    cves: List[str]
    
    # Analysis
    mitre_techniques: List[str]  # ATT&CK technique IDs
    kill_chain_phase: Optional[str]
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float
    
    # Report
    report_summary: str
    report_full: str
    recommendations: List[str]
    
    # Security
    guardian_result: GuardianResult
    approval_request: Optional[Dict[str, Any]]
    
    # Metadata
    start_time: str
    end_time: Optional[str]
    duration_seconds: Optional[float]


@dataclass
class AgentConfig:
    """Configuration for an agent node."""
    
    name: str
    model: str  # e.g., "llama3:8b", "llama3:70b"
    endpoint: str  # e.g., "http://localhost:11434"
    temperature: float = 0.1
    max_tokens: int = 4096
    system_prompt_path: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    timeout_seconds: int = 60


# Agent configurations
# Endpoint: OpenAI-compatible API (LM Studio, vLLM, Ollama /v1/, etc.)
# Override per-agent via environment: LLM_ENDPOINT, LLM_MODEL
import os as _os

_DEFAULT_ENDPOINT = _os.environ.get("LLM_ENDPOINT", "http://localhost:1234")
_DEFAULT_MODEL = _os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano")

AGENT_CONFIGS = {
    "triage": AgentConfig(
        name="triage",
        model=_DEFAULT_MODEL,
        endpoint=_DEFAULT_ENDPOINT,
        temperature=0.0,  # Deterministic for fast Y/N
        max_tokens=2048,
        tools=[],
    ),
    "investigate": AgentConfig(
        name="investigate",
        model=_DEFAULT_MODEL,
        endpoint=_DEFAULT_ENDPOINT,
        temperature=0.2,
        max_tokens=8192,
        tools=["splunk_query", "ise_lookup", "asset_lookup", "baseline_query"],
    ),
    "threat_intel": AgentConfig(
        name="threat_intel",
        model=_DEFAULT_MODEL,
        endpoint=_DEFAULT_ENDPOINT,
        temperature=0.3,
        max_tokens=8192,
        tools=["threat_intel", "mitre_mapper"],
    ),
    "report": AgentConfig(
        name="report",
        model=_DEFAULT_MODEL,
        endpoint=_DEFAULT_ENDPOINT,
        temperature=0.5,  # Slightly creative for writing
        max_tokens=16384,
        timeout_seconds=180,
        tools=[],
    ),
}
