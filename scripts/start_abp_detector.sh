#!/usr/bin/env bash
# Start SASP ABP Detector on S1 (Docker)
# Monitors T4 GPU via nvidia-smi for crypto mining / GPU malware
# Usage: bash scripts/start_abp_detector.sh

set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-sasp-abp-detector}"
IMAGE="${IMAGE:-sasp-detectors:latest}"

# Stop existing container if running
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Starting ABP Detector..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --network host \
    --restart unless-stopped \
    --gpus all \
    -e TRITON_URL="${TRITON_URL:-localhost:8000}" \
    -e KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-<S2_IP>:9092}" \
    -e KAFKA_OUTPUT_TOPIC="${KAFKA_OUTPUT_TOPIC:-abp-detections}" \
    -e POLL_INTERVAL="${POLL_INTERVAL:-30}" \
    -e ABP_THRESHOLD="${ABP_THRESHOLD:-0.5}" \
    -e HEALTH_PORT="${HEALTH_PORT:-9094}" \
    "$IMAGE" python3 abp_detector.py

echo "Container $CONTAINER_NAME started."
echo "  Health: http://localhost:${HEALTH_PORT:-9094}/health"
