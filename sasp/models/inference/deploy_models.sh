#!/usr/bin/env bash
# SASP Model Deployment — copies ONNX models and configs to Triton model repository
#
# Usage:
#   ./deploy_models.sh [TRITON_MODEL_REPO] [MODEL_ARTIFACTS_DIR]
#
# Defaults:
#   TRITON_MODEL_REPO=/mnt/storage1/triton-models
#   MODEL_ARTIFACTS_DIR=./models
#
# Prerequisites:
#   - Trained ONNX models (netflow_autoencoder.onnx, auth_classifier.onnx)
#   - Triton server accessible on the target host
#
# NOTE: Run this on S1 (<S1_IP>) where Triton is deployed.

set -euo pipefail

TRITON_MODEL_REPO="${1:-/mnt/storage1/triton-models}"
MODEL_ARTIFACTS_DIR="${2:-./models}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/triton_configs"

echo "=== SASP Model Deployment ==="
echo "Triton model repo: ${TRITON_MODEL_REPO}"
echo "Model artifacts:   ${MODEL_ARTIFACTS_DIR}"
echo ""

# --- NetFlow Anomaly Autoencoder ---
NETFLOW_DIR="${TRITON_MODEL_REPO}/netflow-anomaly"
echo "[1/2] Deploying netflow-anomaly model..."

mkdir -p "${NETFLOW_DIR}/1"

# Copy model
if [ -f "${MODEL_ARTIFACTS_DIR}/netflow_autoencoder.onnx" ]; then
    cp "${MODEL_ARTIFACTS_DIR}/netflow_autoencoder.onnx" "${NETFLOW_DIR}/1/model.onnx"
    echo "  -> Copied ONNX model to ${NETFLOW_DIR}/1/model.onnx"
else
    echo "  [WARN] netflow_autoencoder.onnx not found in ${MODEL_ARTIFACTS_DIR}"
fi

# Copy config
cp "${CONFIG_DIR}/netflow-anomaly/config.pbtxt" "${NETFLOW_DIR}/config.pbtxt"
echo "  -> Copied config.pbtxt"

# Copy scaler (needed by Morpheus preprocessing)
if [ -f "${MODEL_ARTIFACTS_DIR}/netflow_scaler.pkl" ]; then
    cp "${MODEL_ARTIFACTS_DIR}/netflow_scaler.pkl" "${NETFLOW_DIR}/scaler.pkl"
    echo "  -> Copied scaler.pkl"
fi

# Copy threshold metadata
if [ -f "${MODEL_ARTIFACTS_DIR}/netflow_autoencoder_threshold.json" ]; then
    cp "${MODEL_ARTIFACTS_DIR}/netflow_autoencoder_threshold.json" "${NETFLOW_DIR}/threshold.json"
    echo "  -> Copied threshold.json"
fi

echo ""

# --- Auth Risk Classifier ---
AUTH_DIR="${TRITON_MODEL_REPO}/auth-risk"
echo "[2/2] Deploying auth-risk model..."

mkdir -p "${AUTH_DIR}/1"

# Copy model
if [ -f "${MODEL_ARTIFACTS_DIR}/auth_classifier.onnx" ]; then
    cp "${MODEL_ARTIFACTS_DIR}/auth_classifier.onnx" "${AUTH_DIR}/1/model.onnx"
    echo "  -> Copied ONNX model to ${AUTH_DIR}/1/model.onnx"
else
    echo "  [WARN] auth_classifier.onnx not found in ${MODEL_ARTIFACTS_DIR}"
fi

# Copy config
cp "${CONFIG_DIR}/auth-risk/config.pbtxt" "${AUTH_DIR}/config.pbtxt"
echo "  -> Copied config.pbtxt"

# Copy scaler
if [ -f "${MODEL_ARTIFACTS_DIR}/auth_classifier_scaler.pkl" ]; then
    cp "${MODEL_ARTIFACTS_DIR}/auth_classifier_scaler.pkl" "${AUTH_DIR}/auth_classifier_scaler.pkl"
    echo "  -> Copied scaler.pkl"
fi

# Copy label mapping
if [ -f "${MODEL_ARTIFACTS_DIR}/auth_classifier_meta.json" ]; then
    cp "${MODEL_ARTIFACTS_DIR}/auth_classifier_meta.json" "${AUTH_DIR}/meta.json"
    echo "  -> Copied meta.json"
fi

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Next steps:"
echo "  1. Restart Triton: docker restart triton-server"
echo "  2. Verify models loaded: curl http://localhost:8000/v2/models"
echo "  3. Start Morpheus pipelines:"
echo "     morpheus run pipeline --config netflow_detection.yaml"
echo "     morpheus run pipeline --config auth_detection.yaml"
