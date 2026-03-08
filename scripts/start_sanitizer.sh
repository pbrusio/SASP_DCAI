#!/usr/bin/env bash
# Start SASP Sanitizer on Mac Studio
# Usage: nohup bash scripts/start_sanitizer.sh &

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
export HEALTH_PORT="${HEALTH_PORT:-9091}"

echo "Starting SASP Sanitizer..."
echo "  Kafka: $KAFKA_BOOTSTRAP_SERVERS"
echo "  Health: http://0.0.0.0:$HEALTH_PORT/health"

exec "${PROJECT_DIR}/.venv/bin/python3" -m sasp.sanitizer.cli
