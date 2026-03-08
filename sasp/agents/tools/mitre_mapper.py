"""MITRE ATT&CK mapper — maps observed behaviors to technique IDs."""

import logging
import time

logger = logging.getLogger(__name__)

# Behavior keyword to ATT&CK technique mapping
TECHNIQUE_MAP = {
    # Reconnaissance
    "port scan": {"id": "T1046", "name": "Network Service Discovery", "tactic": "Discovery", "kill_chain": "reconnaissance"},
    "network scan": {"id": "T1046", "name": "Network Service Discovery", "tactic": "Discovery", "kill_chain": "reconnaissance"},
    "dns query": {"id": "T1071.004", "name": "Application Layer Protocol: DNS", "tactic": "Command and Control", "kill_chain": "reconnaissance"},

    # Initial Access
    "brute force": {"id": "T1110", "name": "Brute Force", "tactic": "Credential Access", "kill_chain": "initial_access"},
    "phishing": {"id": "T1566", "name": "Phishing", "tactic": "Initial Access", "kill_chain": "initial_access"},
    "valid accounts": {"id": "T1078", "name": "Valid Accounts", "tactic": "Initial Access", "kill_chain": "initial_access"},
    "auth failure": {"id": "T1110", "name": "Brute Force", "tactic": "Credential Access", "kill_chain": "initial_access"},

    # Lateral Movement
    "lateral movement": {"id": "T1021", "name": "Remote Services", "tactic": "Lateral Movement", "kill_chain": "lateral_movement"},
    "smb": {"id": "T1021.002", "name": "Remote Services: SMB", "tactic": "Lateral Movement", "kill_chain": "lateral_movement"},
    "rdp": {"id": "T1021.001", "name": "Remote Services: RDP", "tactic": "Lateral Movement", "kill_chain": "lateral_movement"},
    "ssh": {"id": "T1021.004", "name": "Remote Services: SSH", "tactic": "Lateral Movement", "kill_chain": "lateral_movement"},

    # Exfiltration
    "exfiltration": {"id": "T1041", "name": "Exfiltration Over C2 Channel", "tactic": "Exfiltration", "kill_chain": "exfiltration"},
    "large upload": {"id": "T1048", "name": "Exfiltration Over Alternative Protocol", "tactic": "Exfiltration", "kill_chain": "exfiltration"},
    "data transfer": {"id": "T1041", "name": "Exfiltration Over C2 Channel", "tactic": "Exfiltration", "kill_chain": "exfiltration"},

    # Command and Control
    "beacon": {"id": "T1071", "name": "Application Layer Protocol", "tactic": "Command and Control", "kill_chain": "command_and_control"},
    "c2": {"id": "T1071", "name": "Application Layer Protocol", "tactic": "Command and Control", "kill_chain": "command_and_control"},
    "tunnel": {"id": "T1572", "name": "Protocol Tunneling", "tactic": "Command and Control", "kill_chain": "command_and_control"},

    # Execution
    "command injection": {"id": "T1059", "name": "Command and Scripting Interpreter", "tactic": "Execution", "kill_chain": "execution"},
    "script execution": {"id": "T1059", "name": "Command and Scripting Interpreter", "tactic": "Execution", "kill_chain": "execution"},

    # Defense Evasion
    "obfuscation": {"id": "T1027", "name": "Obfuscated Files or Information", "tactic": "Defense Evasion", "kill_chain": "defense_evasion"},
    "encoding": {"id": "T1132", "name": "Data Encoding", "tactic": "Command and Control", "kill_chain": "defense_evasion"},
}


def run(behaviors: str, timeout: int = 30) -> dict:
    """Map observed behaviors (text description) to MITRE ATT&CK techniques."""
    tool_name = "mitre_mapper"
    start = time.monotonic()

    try:
        behaviors_lower = behaviors.lower()
        matched_techniques = {}
        kill_chain_phases = set()

        for keyword, technique in TECHNIQUE_MAP.items():
            if keyword in behaviors_lower:
                tid = technique["id"]
                if tid not in matched_techniques:
                    matched_techniques[tid] = technique
                    kill_chain_phases.add(technique["kill_chain"])

        # Determine primary kill chain phase (latest in chain)
        phase_order = ["reconnaissance", "initial_access", "execution", "lateral_movement",
                       "command_and_control", "exfiltration", "defense_evasion"]
        primary_phase = None
        for phase in reversed(phase_order):
            if phase in kill_chain_phases:
                primary_phase = phase
                break

        techniques = [{"id": tid, **info} for tid, info in matched_techniques.items()]

        duration = int((time.monotonic() - start) * 1000)
        return {
            "tool_name": tool_name, "success": True,
            "result": {"techniques": [t["id"] for t in techniques],
                       "technique_details": techniques,
                       "kill_chain_phase": primary_phase,
                       "kill_chain_phases": list(kill_chain_phases)},
            "error": None, "duration_ms": duration,
        }
    except Exception as e:
        duration = int((time.monotonic() - start) * 1000)
        return {"tool_name": tool_name, "success": False, "result": None,
                "error": str(e), "duration_ms": duration}
