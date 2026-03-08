"""SASP Audit Logger — tamper-evident, append-only audit trail for all agent actions."""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = os.environ.get("AUDIT_LOG_PATH", "logs/audit.jsonl")
AUDIT_HMAC_KEY = os.environ.get("AUDIT_HMAC_KEY", "sasp-default-key-change-me")

if AUDIT_HMAC_KEY == "sasp-default-key-change-me":
    logger.warning("AUDIT_HMAC_KEY is using the default value — set a real key via env var")


def _compute_hmac(data: str) -> str:
    """Compute HMAC-SHA256 signature for a log entry."""
    return hmac.new(
        AUDIT_HMAC_KEY.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _write_log_entry(entry: dict) -> None:
    """Write a single audit log entry with HMAC signature."""
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Serialize entry without signature for HMAC computation
    entry_json = json.dumps(entry, default=str, sort_keys=True)
    entry["hmac_signature"] = _compute_hmac(entry_json)

    # Ensure log directory exists
    log_path = Path(AUDIT_LOG_PATH)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as e:
        # Fallback to logging if file write fails (e.g., in dev/test)
        logger.warning("Failed to write audit log to %s: %s", AUDIT_LOG_PATH, e)
        logger.info("AUDIT: %s", json.dumps(entry, default=str))


class AuditLogger:
    """Append-only audit logger for SASP agent actions.

    All methods are class methods so they can be called without instantiation
    (as used in graph.py).
    """

    @classmethod
    def log_guardian_check(cls, state: dict, result: dict) -> None:
        """Log a guardian validation check."""
        entry = {
            "event_type": "guardian_check",
            "investigation_id": state.get("investigation_id", "unknown"),
            "approved": result.get("approved", False),
            "needs_human_review": result.get("needs_human_review", False),
            "concerns": result.get("concerns", []),
            "validation_checks": result.get("validation_checks", {}),
            "severity": state.get("severity", "unknown"),
        }
        _write_log_entry(entry)
        logger.info(
            "Guardian check: investigation=%s approved=%s concerns=%d",
            entry["investigation_id"], entry["approved"], len(entry["concerns"]),
        )

    @classmethod
    def log_approval_request(cls, request: dict) -> None:
        """Log a human approval request."""
        entry = {
            "event_type": "approval_request",
            "investigation_id": request.get("investigation_id", "unknown"),
            "severity": request.get("severity", "unknown"),
            "status": request.get("status", "pending_approval"),
            "guardian_concerns": request.get("guardian_concerns", []),
        }
        _write_log_entry(entry)
        logger.info(
            "Approval request: investigation=%s severity=%s",
            entry["investigation_id"], entry["severity"],
        )

    @classmethod
    def log_tool_call(cls, agent: str, tool_name: str, arguments: dict,
                      result: Any, duration_ms: int = 0) -> None:
        """Log a tool invocation by an agent."""
        entry = {
            "event_type": "tool_call",
            "agent": agent,
            "tool_name": tool_name,
            "arguments": arguments,
            "success": result.get("success", False) if isinstance(result, dict) else bool(result),
            "error": result.get("error") if isinstance(result, dict) else None,
            "duration_ms": duration_ms,
        }
        _write_log_entry(entry)

    @classmethod
    def log_agent_turn(cls, agent_name: str, input_state_hash: str,
                       output_state_diff: dict) -> None:
        """Log state changes from an agent turn."""
        entry = {
            "event_type": "agent_turn",
            "agent_name": agent_name,
            "input_state_hash": input_state_hash,
            "output_keys_changed": list(output_state_diff.keys()),
        }
        _write_log_entry(entry)


def verify_audit_integrity(log_path: Optional[str] = None) -> dict:
    """Verify HMAC signatures on all entries in an audit log file.

    Returns:
        dict with total_entries, valid_entries, invalid_entries, errors
    """
    path = log_path or AUDIT_LOG_PATH
    results = {"total_entries": 0, "valid_entries": 0, "invalid_entries": 0,
               "errors": [], "invalid_lines": []}

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                results["total_entries"] += 1

                try:
                    entry = json.loads(line)
                    stored_sig = entry.pop("hmac_signature", None)
                    if stored_sig is None:
                        results["invalid_entries"] += 1
                        results["invalid_lines"].append(line_num)
                        continue

                    # Recompute HMAC
                    entry_json = json.dumps(entry, default=str, sort_keys=True)
                    expected_sig = _compute_hmac(entry_json)

                    if hmac.compare_digest(stored_sig, expected_sig):
                        results["valid_entries"] += 1
                    else:
                        results["invalid_entries"] += 1
                        results["invalid_lines"].append(line_num)
                except json.JSONDecodeError:
                    results["invalid_entries"] += 1
                    results["errors"].append(f"Line {line_num}: invalid JSON")
    except FileNotFoundError:
        results["errors"].append(f"Audit log not found: {path}")

    return results
