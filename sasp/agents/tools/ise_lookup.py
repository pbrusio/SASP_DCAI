"""ISE ERS API lookup tool — queries Cisco ISE for endpoint/session data."""

import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

ISE_API_URL = os.environ.get("ISE_API_URL", "https://ise.local:9060")
ISE_USERNAME = os.environ.get("ISE_USERNAME", "")
ISE_PASSWORD = os.environ.get("ISE_PASSWORD", "")
ISE_VERIFY_TLS = os.environ.get("ISE_VERIFY_TLS", "false").lower() == "true"
DEFAULT_TIMEOUT = int(os.environ.get("TOOL_TIMEOUT", "30"))


def run(ip: str = "", mac: str = "", username: str = "",
        timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Query ISE for endpoint data by IP, MAC, or username."""
    tool_name = "ise_lookup"
    start = time.monotonic()

    if not ISE_USERNAME:
        return {"tool_name": tool_name, "success": False, "result": None,
                "error": "ISE credentials not configured", "duration_ms": 0}

    try:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        auth = (ISE_USERNAME, ISE_PASSWORD)

        # Determine query type and endpoint
        if mac:
            url = f"{ISE_API_URL}/ers/config/endpoint"
            params = {"filter": f"mac.EQ.{mac}"}
        elif ip:
            url = f"{ISE_API_URL}/admin/API/mnt/Session/ActiveList"
            params = {"noOfRecords": "10"}
        elif username:
            url = f"{ISE_API_URL}/admin/API/mnt/Session/UserName/{username}"
            params = {}
        else:
            return {"tool_name": tool_name, "success": False, "result": None,
                    "error": "Must provide ip, mac, or username", "duration_ms": 0}

        resp = requests.get(url, params=params, headers=headers, auth=auth,
                            verify=ISE_VERIFY_TLS, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()

        duration = int((time.monotonic() - start) * 1000)
        return {"tool_name": tool_name, "success": True, "result": result,
                "error": None, "duration_ms": duration}
    except requests.RequestException as e:
        duration = int((time.monotonic() - start) * 1000)
        logger.warning("ISE lookup failed: %s", e)
        return {"tool_name": tool_name, "success": False, "result": None,
                "error": str(e), "duration_ms": duration}
