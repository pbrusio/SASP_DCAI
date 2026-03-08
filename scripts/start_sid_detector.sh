#!/usr/bin/env bash
# Start SASP SID Detector on S1 (Docker)
# Detects sensitive information (PII) in syslog messages via MiniBERT
# Usage: bash scripts/start_sid_detector.sh

set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-sasp-sid-detector}"
IMAGE="${IMAGE:-sasp-detectors:latest}"

# Stop existing container if running
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Starting SID Detector..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --network host \
    --restart unless-stopped \
    -e TRITON_URL="${TRITON_URL:-localhost:8000}" \
    -e KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-<S2_IP>:9092}" \
    -e KAFKA_INPUT_TOPIC="${KAFKA_INPUT_TOPIC:-syslog-sanitized}" \
    -e KAFKA_OUTPUT_TOPIC="${KAFKA_OUTPUT_TOPIC:-sid-detections}" \
    -e SID_THRESHOLD="${SID_THRESHOLD:-0.7}" \
    -e VOCAB_PATH="${VOCAB_PATH:-/models/sid-minibert/vocab.txt}" \
    -e HEALTH_PORT="${HEALTH_PORT:-9095}" \
    -v /mnt/storage1/triton-models:/models:ro \
    "$IMAGE" python3 sid_detector.py

echo "Container $CONTAINER_NAME started."
echo "  Health: http://localhost:${HEALTH_PORT:-9095}/health"
