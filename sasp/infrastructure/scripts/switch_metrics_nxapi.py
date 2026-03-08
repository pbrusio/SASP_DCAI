#!/usr/bin/env python3
"""
N9K RoCE Switch Metrics Collector (NX-API)

Collects interface counters and PFC stats from a Nexus 9K via NX-API (HTTPS)
and posts to Splunk HEC.  Drop-in replacement for switch_metrics_collector.sh
that used SSH — this version works from any host with HTTPS access to the N9K.

Usage:
    HEC_TOKEN=xxx python3 switch_metrics_nxapi.py

Env vars:
    HEC_TOKEN       (required) Splunk HEC token
    N9K_HOST        NX-API endpoint      (default: https://<N9K_MGMT_IP>)
    N9K_USER        NX-API username       (default: admin)
    N9K_PASS        NX-API password       (default: admin)
    SPLUNK_HEC      Splunk HEC base URL   (default: http://<SPLUNK_IP>:8088)
    INTERVAL        Collection interval   (default: 30)
    INDEX           Splunk index          (default: sasp_metrics)
"""

import json
import os
import sys
import time
import urllib3

import requests

# Suppress InsecureRequestWarning for self-signed N9K cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HEC_TOKEN = os.environ.get("HEC_TOKEN")
if not HEC_TOKEN:
    print("ERROR: Set HEC_TOKEN environment variable", file=sys.stderr)
    sys.exit(1)

N9K_HOST = os.environ.get("N9K_HOST", "https://<N9K_MGMT_IP>")
N9K_USER = os.environ.get("N9K_USER", "admin")
N9K_PASS = os.environ.get("N9K_PASS", "admin")
SPLUNK_HEC = os.environ.get("SPLUNK_HEC", "http://<SPLUNK_IP>:8088")
INTERVAL = int(os.environ.get("INTERVAL", "30"))
INDEX = os.environ.get("INDEX", "sasp_metrics")
SOURCETYPE = "sasp:switch_metrics"

HEC_URL = f"{SPLUNK_HEC}/services/collector/event"

# Ports to monitor — same as the SSH-based collector
PORTS = [
    {"interface": "Ethernet1/32", "short": "Eth1/32", "label": "vm_roce"},
    {"interface": "Ethernet1/38", "short": "Eth1/38", "label": "s2_roce"},
    {"interface": "Ethernet1/44", "short": "Eth1/44", "label": "s1_roce"},
]

# ---------------------------------------------------------------------------
# NX-API helpers
# ---------------------------------------------------------------------------

def nxapi_cli(commands: list[str]) -> list[dict]:
    """Execute one or more show commands via NX-API and return parsed JSON."""
    payload = []
    for i, cmd in enumerate(commands, 1):
        payload.append({
            "jsonrpc": "2.0",
            "method": "cli",
            "params": {"cmd": cmd, "version": 1},
            "id": i,
        })

    resp = requests.post(
        f"{N9K_HOST}/ins",
        json=payload,
        auth=(N9K_USER, N9K_PASS),
        headers={"Content-Type": "application/json-rpc"},
        verify=False,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    # Single command returns a dict, multiple returns a list
    if isinstance(data, dict):
        data = [data]
    return data


def get_interface_counters(interface: str) -> dict:
    """Get interface counters and errors for a single interface.

    NX-API returns counters split across TABLE_rx_counters / TABLE_tx_counters,
    each with a ROW list.  Errors come from a separate "counters errors" command
    using TABLE_interface with a ROW list.
    """
    results = nxapi_cli([
        f"show interface {interface} counters",
        f"show interface {interface} counters errors",
    ])
    out = {
        "in_octets": 0, "out_octets": 0,
        "in_ucast_pkts": 0, "out_ucast_pkts": 0,
        "in_mcast_pkts": 0, "in_errors": 0, "out_discards": 0,
    }
    try:
        # --- counters ---
        body = results[0]["result"]["body"]
        # RX rows: first has eth_inbytes/eth_inucast, second has eth_inmcast
        rx_rows = body.get("TABLE_rx_counters", {}).get("ROW_rx_counters", [])
        if isinstance(rx_rows, dict):
            rx_rows = [rx_rows]
        for row in rx_rows:
            if "eth_inbytes" in row:
                out["in_octets"] = int(row["eth_inbytes"])
                out["in_ucast_pkts"] = int(row.get("eth_inucast", 0))
            if "eth_inmcast" in row:
                out["in_mcast_pkts"] = int(row["eth_inmcast"])

        # TX rows: first has eth_outbytes/eth_outucast
        tx_rows = body.get("TABLE_tx_counters", {}).get("ROW_tx_counters", [])
        if isinstance(tx_rows, dict):
            tx_rows = [tx_rows]
        for row in tx_rows:
            if "eth_outbytes" in row:
                out["out_octets"] = int(row["eth_outbytes"])
                out["out_ucast_pkts"] = int(row.get("eth_outucast", 0))

        # --- errors ---
        err_body = results[1]["result"]["body"]
        err_rows = err_body.get("TABLE_interface", {}).get("ROW_interface", [])
        if isinstance(err_rows, dict):
            err_rows = [err_rows]
        for row in err_rows:
            if "eth_rcv_err" in row:
                out["in_errors"] = int(row["eth_rcv_err"])
            if "eth_outdisc" in row:
                out["out_discards"] = int(row["eth_outdisc"])

    except (KeyError, TypeError, IndexError) as exc:
        print(f"  WARN: Failed to parse counters for {interface}: {exc}")
        return {}
    return out


def get_pfc_stats(interface: str) -> dict:
    """Get PFC stats for a single interface.

    NX-API wraps PFC data under TABLE_module > ROW_module > TABLE_pfc_interface.
    Fields: admin, oper, rx-stats, tx-stats.
    """
    results = nxapi_cli([f"show interface {interface} priority-flow-control"])
    try:
        body = results[0]["result"]["body"]
        # Navigate: TABLE_module > ROW_module > TABLE_pfc_interface > ROW_pfc_interface
        module = body.get("TABLE_module", {}).get("ROW_module", {})
        row = module.get("TABLE_pfc_interface", {}).get("ROW_pfc_interface", {})
        return {
            "pfc_mode": row.get("admin", row.get("oper", "unknown")),
            "pfc_rx_pause": int(row.get("rx-stats", 0)),
            "pfc_tx_pause": int(row.get("tx-stats", 0)),
        }
    except (KeyError, TypeError, IndexError) as exc:
        print(f"  WARN: Failed to parse PFC for {interface}: {exc}")
        return {"pfc_mode": "unknown", "pfc_rx_pause": 0, "pfc_tx_pause": 0}


# ---------------------------------------------------------------------------
# Splunk HEC
# ---------------------------------------------------------------------------

def post_to_hec(event: dict, ts: int) -> bool:
    """Post a single event to Splunk HEC."""
    payload = {
        "time": ts,
        "host": "n9k",
        "index": INDEX,
        "sourcetype": SOURCETYPE,
        "event": event,
    }
    try:
        resp = requests.post(
            HEC_URL,
            json=payload,
            headers={"Authorization": f"Splunk {HEC_TOKEN}"},
            verify=False,
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException as exc:
        print(f"  HEC post failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    print(f"NX-API switch metrics collector starting (interval: {INTERVAL}s)")
    print(f"  N9K: {N9K_HOST}  User: {N9K_USER}")
    print(f"  Ports: {', '.join(p['short'] + ' (' + p['label'] + ')' for p in PORTS)}")
    print(f"  HEC: {HEC_URL}  Index: {INDEX}")

    # Previous counters for rate calculation
    prev: dict[str, dict] = {}
    first_run = True

    while True:
        ts = int(time.time())

        try:
            for port in PORTS:
                iface = port["interface"]
                short = port["short"]
                label = port["label"]

                counters = get_interface_counters(iface)
                if not counters:
                    continue

                pfc = get_pfc_stats(iface)

                # Rate calculation (bps)
                if not first_run and short in prev:
                    rate_in = (counters["in_octets"] - prev[short]["in_octets"]) * 8 // INTERVAL
                    rate_out = (counters["out_octets"] - prev[short]["out_octets"]) * 8 // INTERVAL
                else:
                    rate_in = 0
                    rate_out = 0

                prev[short] = counters

                event = {
                    "port": short,
                    "port_label": label,
                    "in_octets": counters["in_octets"],
                    "out_octets": counters["out_octets"],
                    "in_ucast_pkts": counters["in_ucast_pkts"],
                    "out_ucast_pkts": counters["out_ucast_pkts"],
                    "in_mcast_pkts": counters["in_mcast_pkts"],
                    "in_errors": counters["in_errors"],
                    "out_discards": counters["out_discards"],
                    "in_bps": rate_in,
                    "out_bps": rate_out,
                    "pfc_mode": pfc.get("pfc_mode", "unknown"),
                    "pfc_rx_pause": pfc.get("pfc_rx_pause", 0),
                    "pfc_tx_pause": pfc.get("pfc_tx_pause", 0),
                }

                ok = post_to_hec(event, ts)
                status = "OK" if ok else "FAIL"
                print(
                    f"[{ts}] {short}({label}): "
                    f"{rate_in}bps in/{rate_out}bps out  "
                    f"pfc={pfc.get('pfc_mode', '?')} "
                    f"rx={pfc.get('pfc_rx_pause', 0)} tx={pfc.get('pfc_tx_pause', 0)} "
                    f"[{status}]"
                )

            first_run = False

        except requests.RequestException as exc:
            print(f"[{ts}] NX-API request failed: {exc}")
        except Exception as exc:
            print(f"[{ts}] Unexpected error: {exc}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
