# IMPLEMENTATION STATUS: Stub
#
# This tool returns empty/unknown results when no asset inventory file
# is configured. A production implementation would query a CMDB or asset
# inventory system (ServiceNow, Cisco DNA Center, or a flat JSON/CSV
# asset file) to return:
#   - asset owner
#   - asset classification (critical/standard/guest)
#   - expected network location
#   - last known good state
#
# To wire up a flat file implementation, set ASSET_INVENTORY_PATH env var
# to a JSON file keyed by IP address.

"""Asset inventory lookup — queries a local JSON file for asset details by IP."""

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

ASSET_INVENTORY_PATH = os.environ.get("ASSET_INVENTORY_PATH", "assets.json")
DEFAULT_TIMEOUT = int(os.environ.get("TOOL_TIMEOUT", "30"))

_inventory_cache = None


def _load_inventory():
    global _inventory_cache
    if _inventory_cache is not None:
        return _inventory_cache
    try:
        with open(ASSET_INVENTORY_PATH, "r") as f:
            _inventory_cache = json.load(f)
        return _inventory_cache
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.debug("Failed to load asset inventory: %s", e)
        return {}


def run(ip: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Look up an asset by IP address."""
    tool_name = "asset_lookup"
    start = time.monotonic()

    try:
        inventory = _load_inventory()

        # Search by IP in inventory (supports dict keyed by IP or list with ip field)
        result = None
        if isinstance(inventory, dict):
            result = inventory.get(ip)
        elif isinstance(inventory, list):
            for asset in inventory:
                if asset.get("ip") == ip:
                    result = asset
                    break

        duration = int((time.monotonic() - start) * 1000)
        if result:
            return {"tool_name": tool_name, "success": True, "result": result,
                    "error": None, "duration_ms": duration}
        return {"tool_name": tool_name, "success": True, "result": {"ip": ip, "status": "unknown"},
                "error": None, "duration_ms": duration}
    except Exception as e:
        duration = int((time.monotonic() - start) * 1000)
        return {"tool_name": tool_name, "success": False, "result": None,
                "error": str(e), "duration_ms": duration}
