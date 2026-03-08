#!/usr/bin/env bash
# Start SASP Kafka Bridge on Mac Studio
# Usage: nohup bash scripts/start_bridge.sh &

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

export KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-<S2_IP>:9092}"
export KAFKA_TOPIC_DETECTIONS="${KAFKA_TOPIC_DETECTIONS:-morpheus-detections,abp-detections,sid-detections,ise-dfp-detections}"
export HEALTH_PORT="${HEALTH_PORT:-9093}"
export SPLUNK_HEC_URL="${SPLUNK_HEC_URL:-http://<SPLUNK_IP>:8088/services/collector/event}"
# SPLUNK_HEC_TOKEN should come from .env

echo "Starting SASP Kafka Bridge..."
echo "  Kafka: $KAFKA_BOOTSTRAP_SERVERS"
echo "  Topics: $KAFKA_TOPIC_DETECTIONS"
echo "  Health: http://0.0.0.0:$HEALTH_PORT/health"

exec "${PROJECT_DIR}/.venv/bin/python3" -m sasp.agents.kafka_bridge
