#!/usr/bin/env python3
"""
Triton Inference Server Metrics Collector

Polls Triton's Prometheus metrics endpoint and posts inference throughput,
latency, and model info to Splunk HEC.  Computes per-interval rates from
Triton's cumulative counters.

Usage:
    HEC_TOKEN=xxx python3 triton_metrics_collector.py

Env vars:
    HEC_TOKEN       (required) Splunk HEC token
    TRITON_URL      Triton metrics URL   (default: http://localhost:8002/metrics)
    SPLUNK_HEC      Splunk HEC base URL  (default: http://<SPLUNK_IP>:8088)
    INTERVAL        Collection interval  (default: 30)
    INDEX           Splunk index         (default: sasp_metrics)
"""

import os
import re
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HEC_TOKEN = os.environ.get("HEC_TOKEN")
if not HEC_TOKEN:
    print("ERROR: Set HEC_TOKEN environment variable", file=sys.stderr)
    sys.exit(1)

TRITON_URL = os.environ.get("TRITON_URL", "http://localhost:8002/metrics")
SPLUNK_HEC = os.environ.get("SPLUNK_HEC", "http://<SPLUNK_IP>:8088")
INTERVAL = int(os.environ.get("INTERVAL", "30"))
INDEX = os.environ.get("INDEX", "sasp_metrics")
SOURCETYPE = "sasp:gpu_metrics"
HOST = os.environ.get("HOSTNAME", "t4server1")

HEC_URL = f"{SPLUNK_HEC}/services/collector/event"

# ---------------------------------------------------------------------------
# Prometheus text parser (minimal — just what we need from Triton)
# ---------------------------------------------------------------------------

# Pattern: metric_name{label="value",...} value
METRIC_RE = re.compile(
    r'^(\w+)\{([^}]*)\}\s+([\d.eE+\-]+)$'
)

def parse_prometheus(text: str) -> list[dict]:
    """Parse Prometheus exposition format into list of {name, labels, value}."""
    metrics = []
    for line in text.splitlines():
        if line.startswith('#') or not line.strip():
            continue
        m = METRIC_RE.match(line)
        if m:
            name = m.group(1)
            labels = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2)))
            value = float(m.group(3))
            metrics.append({"name": name, "labels": labels, "value": value})
    return metrics


def extract_model_metrics(metrics: list[dict]) -> dict[str, dict]:
    """Group Triton metrics by model name."""
    models: dict[str, dict] = {}
    for m in metrics:
        model = m["labels"].get("model")
        if not model:
            continue
        if model not in models:
            models[model] = {}
        models[model][m["name"]] = m["value"]
    return models


# ---------------------------------------------------------------------------
# Splunk HEC
# ---------------------------------------------------------------------------

def post_to_hec(events: list[dict], ts: int) -> bool:
    """Post multiple events to Splunk HEC as newline-delimited JSON."""
    payload = "\n".join(
        f'{{"time":{ts},"host":"{HOST}","index":"{INDEX}","sourcetype":"{SOURCETYPE}","event":{__import__("json").dumps(e)}}}'
        for e in events
    )
    try:
        resp = requests.post(
            HEC_URL,
            data=payload,
            headers={
                "Authorization": f"Splunk {HEC_TOKEN}",
                "Content-Type": "application/json",
            },
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
    print(f"Triton metrics collector starting (interval: {INTERVAL}s)")
    print(f"  Triton: {TRITON_URL}")
    print(f"  HEC: {HEC_URL}  Index: {INDEX}")

    prev_counts: dict[str, dict] = {}
    first_run = True

    while True:
        ts = int(time.time())

        try:
            resp = requests.get(TRITON_URL, timeout=5)
            resp.raise_for_status()
            metrics = parse_prometheus(resp.text)
            models = extract_model_metrics(metrics)

            events = []

            for model_name, m in models.items():
                success = m.get("nv_inference_request_success", 0)
                failure_keys = [k for k in m if k == "nv_inference_request_failure"]
                infer_count = m.get("nv_inference_count", 0)
                duration_us = m.get("nv_inference_request_duration_us", 0)
                queue_us = m.get("nv_inference_queue_duration_us", 0)
                compute_us = m.get("nv_inference_compute_infer_duration_us", 0)

                # Compute per-interval rates
                if not first_run and model_name in prev_counts:
                    prev = prev_counts[model_name]
                    delta_success = success - prev.get("success", 0)
                    delta_count = infer_count - prev.get("count", 0)
                    delta_duration = duration_us - prev.get("duration_us", 0)
                    delta_queue = queue_us - prev.get("queue_us", 0)
                    delta_compute = compute_us - prev.get("compute_us", 0)

                    requests_per_sec = round(delta_count / INTERVAL, 2) if INTERVAL > 0 else 0
                    avg_latency_ms = round(delta_duration / 1000 / delta_count, 2) if delta_count > 0 else 0
                    avg_queue_ms = round(delta_queue / 1000 / delta_count, 2) if delta_count > 0 else 0
                    avg_compute_ms = round(delta_compute / 1000 / delta_count, 2) if delta_count > 0 else 0
                else:
                    requests_per_sec = 0
                    avg_latency_ms = 0
                    avg_queue_ms = 0
                    avg_compute_ms = 0
                    delta_success = 0

                prev_counts[model_name] = {
                    "success": success,
                    "count": infer_count,
                    "duration_us": duration_us,
                    "queue_us": queue_us,
                    "compute_us": compute_us,
                }

                # Inference throughput/latency event
                events.append({
                    "event_type": "triton_inference",
                    "model_name": model_name,
                    "model_version": "1",
                    "requests_per_sec": requests_per_sec,
                    "latency_ms": avg_latency_ms,
                    "queue_ms": avg_queue_ms,
                    "compute_ms": avg_compute_ms,
                    "inferences_total": int(infer_count),
                    "success_total": int(success),
                    "requests_in_interval": int(delta_success),
                    "pending_requests": int(m.get("nv_inference_pending_request_count", 0)),
                })

                # Model info event
                events.append({
                    "event_type": "model_info",
                    "model_name": model_name,
                    "model_version": "1",
                    "model_status": "READY",
                })

            if events:
                ok = post_to_hec(events, ts)
                status = "OK" if ok else "FAIL"
            else:
                status = "NO_MODELS"

            for model_name, m in models.items():
                infer_count = int(m.get("nv_inference_count", 0))
                rps = prev_counts.get(model_name, {}).get("count", 0)
                print(f"[{ts}] {model_name}: inferences={infer_count} [{status}]")

            first_run = False

        except requests.RequestException as exc:
            print(f"[{ts}] Triton metrics fetch failed: {exc}")
        except Exception as exc:
            print(f"[{ts}] Unexpected error: {exc}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
