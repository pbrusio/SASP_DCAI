"""Splunk SPL query tool — runs searches against the Splunk REST API."""

import json
import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

SPLUNK_API_URL = os.environ.get("SPLUNK_API_URL", "https://localhost:8089")
SPLUNK_TOKEN = os.environ.get("SPLUNK_API_TOKEN", "")
SPLUNK_VERIFY_TLS = os.environ.get("SPLUNK_VERIFY_TLS", "false").lower() == "true"
DEFAULT_TIMEOUT = int(os.environ.get("TOOL_TIMEOUT", "30"))


def run(query: str, earliest: str = "-24h", latest: str = "now",
        max_results: int = 100, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run an SPL query against Splunk and return results."""
    tool_name = "splunk_query"
    start = time.monotonic()

    if not SPLUNK_TOKEN:
        return {"tool_name": tool_name, "success": False, "result": None,
                "error": "SPLUNK_API_TOKEN not configured", "duration_ms": 0}

    try:
        # Splunk oneshot search endpoint
        url = f"{SPLUNK_API_URL}/services/search/jobs/export"
        params = {
            "search": f"search {query}" if not query.strip().startswith("|") else query,
            "earliest_time": earliest,
            "latest_time": latest,
            "output_mode": "json",
            "count": max_results,
        }
        headers = {"Authorization": f"Bearer {SPLUNK_TOKEN}"}

        resp = requests.post(url, data=params, headers=headers,
                             verify=SPLUNK_VERIFY_TLS, timeout=timeout)
        resp.raise_for_status()

        # Parse newline-delimited JSON results
        results = []
        for line in resp.text.strip().split("\n"):
            if line.strip():
                try:
                    obj = json.loads(line)
                    if "result" in obj:
                        results.append(obj["result"])
                except json.JSONDecodeError:
                    continue

        duration = int((time.monotonic() - start) * 1000)
        return {"tool_name": tool_name, "success": True, "result": results,
                "error": None, "duration_ms": duration}
    except requests.RequestException as e:
        duration = int((time.monotonic() - start) * 1000)
        logger.warning("Splunk query failed: %s", e)
        return {"tool_name": tool_name, "success": False, "result": None,
                "error": str(e), "duration_ms": duration}
