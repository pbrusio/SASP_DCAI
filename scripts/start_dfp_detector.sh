#!/usr/bin/env bash
# Start SASP ISE DFP Detector on S1 (Docker)
# Usage: bash scripts/start_dfp_detector.sh

set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-sasp-dfp-detector}"
IMAGE="${IMAGE:-sasp-detectors:latest}"

# Stop existing container if running
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Starting ISE DFP Detector..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --network host \
    --restart unless-stopped \
    -e TRITON_URL="${TRITON_URL:-localhost:8000}" \
    -e KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-<S2_IP>:9092}" \
    -e KAFKA_INPUT_TOPIC="${KAFKA_INPUT_TOPIC:-ise-sanitized}" \
    -e KAFKA_OUTPUT_TOPIC="${KAFKA_OUTPUT_TOPIC:-ise-dfp-detections}" \
    -e SCALER_PATH=/models/ise-dfp/scaler.json \
    -e THRESHOLD_PATH=/models/ise-dfp/threshold.json \
    -e HEALTH_PORT="${HEALTH_PORT:-9097}" \
    -v /mnt/storage1/triton-models:/models:ro \
    "$IMAGE" python3 ise_dfp_detector.py

echo "Container $CONTAINER_NAME started."
echo "  Health: http://localhost:${HEALTH_PORT:-9097}/health"
