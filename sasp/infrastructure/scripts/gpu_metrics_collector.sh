#!/usr/bin/env bash
# gpu_metrics_collector.sh — Collects nvidia-smi metrics and sends to Splunk HEC
#
# Usage: HEC_TOKEN=xxx SPLUNK_HEC=http://<SPLUNK_IP>:8088 ./gpu_metrics_collector.sh
# Runs in a loop, posting GPU stats every INTERVAL seconds.

set -euo pipefail

: "${HEC_TOKEN:?Set HEC_TOKEN}"
: "${SPLUNK_HEC:=http://<SPLUNK_IP>:8088}"
: "${INTERVAL:=30}"
: "${INDEX:=sasp_metrics}"
: "${SOURCETYPE:=sasp:gpu_metrics}"

HEC_URL="${SPLUNK_HEC}/services/collector/event"
HOST=$(hostname -s)

echo "GPU metrics collector starting on ${HOST} (interval: ${INTERVAL}s)"
echo "  HEC: ${HEC_URL}  Index: ${INDEX}"

while true; do
    # Query nvidia-smi (csv, no header, no units)
    read -r util mem_used mem_total temp power <<< \
        "$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw \
           --format=csv,noheader,nounits 2>/dev/null | tr -d ' ' | tr ',' ' ')"

    ts=$(date +%s)

    payload=$(cat <<EOF
{"time":${ts},"host":"${HOST}","index":"${INDEX}","sourcetype":"${SOURCETYPE}","event":{"gpu_utilization_pct":${util:-0},"gpu_memory_used_mb":${mem_used:-0},"gpu_memory_total_mb":${mem_total:-0},"gpu_temp_c":${temp:-0},"gpu_power_w":${power:-0}}}
EOF
)

    curl -s -k "${HEC_URL}" \
        -H "Authorization: Splunk ${HEC_TOKEN}" \
        -d "${payload}" > /dev/null 2>&1 \
        && echo "[${ts}] ${HOST}: util=${util}% mem=${mem_used}/${mem_total}MB temp=${temp}C" \
        || echo "[${ts}] HEC post failed"

    sleep "${INTERVAL}"
done
