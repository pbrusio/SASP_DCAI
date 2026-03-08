#!/usr/bin/env bash
# Start SASP ISE-to-Splunk Bridge on Mac Studio
# Usage: nohup bash scripts/start_ise_bridge.sh &

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
export KAFKA_INPUT_TOPIC="${KAFKA_INPUT_TOPIC:-ise-sanitized}"
export HEALTH_PORT="${HEALTH_PORT:-9096}"
export SPLUNK_HEC_URL="${SPLUNK_HEC_URL:-http://<SPLUNK_IP>:8088/services/collector/event}"
# SPLUNK_HEC_TOKEN should come from .env

echo "Starting SASP ISE Splunk Bridge..."
echo "  Kafka: $KAFKA_BOOTSTRAP_SERVERS"
echo "  Topic: $KAFKA_INPUT_TOPIC"
echo "  Health: http://0.0.0.0:$HEALTH_PORT/health"

exec "${PROJECT_DIR}/.venv/bin/python3" -m sasp.agents.ise_splunk_bridge
