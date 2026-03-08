"""Threat intelligence lookup — queries external APIs for IP/domain reputation."""

import json
import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

VIRUSTOTAL_API_KEY = os.environ.get("VIRUSTOTAL_API_KEY", "")
ABUSEIPDB_API_KEY = os.environ.get("ABUSEIPDB_API_KEY", "")
LOCAL_THREAT_FEED_PATH = os.environ.get("THREAT_FEED_PATH", "")
DEFAULT_TIMEOUT = int(os.environ.get("TOOL_TIMEOUT", "30"))


def _check_local_feed(query: str) -> dict | None:
    if not LOCAL_THREAT_FEED_PATH:
        return None
    try:
        with open(LOCAL_THREAT_FEED_PATH, "r") as f:
            feed = json.load(f)
        return feed.get(query)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _check_abuseipdb(ip: str, timeout: int) -> dict | None:
    if not ABUSEIPDB_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.abuseipdb.com/api/v2/check",
            headers={"Key": ABUSEIPDB_API_KEY, "Accept": "application/json"},
            params={"ipAddress": ip, "maxAgeInDays": "90"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {
            "source": "abuseipdb",
            "risk_score": data.get("abuseConfidenceScore", 0),
            "categories": data.get("usageType", "unknown"),
            "total_reports": data.get("totalReports", 0),
            "country": data.get("countryCode", ""),
        }
    except requests.RequestException as e:
        logger.warning("AbuseIPDB lookup failed: %s", e)
        return None


def _check_virustotal(query: str, query_type: str, timeout: int) -> dict | None:
    if not VIRUSTOTAL_API_KEY:
        return None
    try:
        if query_type == "ip":
            url = f"https://www.virustotal.com/api/v3/ip_addresses/{query}"
        elif query_type == "domain":
            url = f"https://www.virustotal.com/api/v3/domains/{query}"
        else:
            return None

        resp = requests.get(url, headers={"x-apikey": VIRUSTOTAL_API_KEY}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("attributes", {})
        stats = data.get("last_analysis_stats", {})
        return {
            "source": "virustotal",
            "risk_score": stats.get("malicious", 0),
            "categories": list(data.get("categories", {}).values()) if data.get("categories") else [],
            "reputation": data.get("reputation", 0),
        }
    except requests.RequestException as e:
        logger.warning("VirusTotal lookup failed: %s", e)
        return None


def run(query: str, query_type: str = "ip", timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Look up IP or domain reputation across threat intel sources."""
    tool_name = "threat_intel"
    start = time.monotonic()

    try:
        results = []

        local = _check_local_feed(query)
        if local:
            results.append({"source": "local_feed", **local})

        if query_type == "ip":
            abuseipdb = _check_abuseipdb(query, timeout)
            if abuseipdb:
                results.append(abuseipdb)

        vt = _check_virustotal(query, query_type, timeout)
        if vt:
            results.append(vt)

        # Aggregate risk score
        max_risk = max((r.get("risk_score", 0) for r in results), default=0)

        duration = int((time.monotonic() - start) * 1000)
        return {
            "tool_name": tool_name, "success": True,
            "result": {"query": query, "type": query_type, "risk_score": max_risk,
                       "sources": results, "iocs": []},
            "error": None, "duration_ms": duration,
        }
    except Exception as e:
        duration = int((time.monotonic() - start) * 1000)
        return {"tool_name": tool_name, "success": False, "result": None,
                "error": str(e), "duration_ms": duration}
