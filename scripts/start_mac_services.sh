#!/usr/bin/env bash
# Start all SASP services on Mac Studio after reboot
# Usage: bash scripts/start_mac_services.sh
#
# Prerequisites:
#   1. Open LM Studio manually, load Nemotron-3-Nano, start server on 0.0.0.0:1234
#   2. Then run this script
#
# Services started (in order):
#   1. Sanitizer  — port 9091
#   2. Kafka Bridge — port 9093  (depends on Kafka + LM Studio)
#   3. ISE Bridge — port 9096

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="/tmp"

cd "$PROJECT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

wait_for_health() {
    local name="$1" url="$2" max_wait="${3:-30}"
    local waited=0
    while [ "$waited" -lt "$max_wait" ]; do
        if curl -sf --max-time 2 "$url" >/dev/null 2>&1; then
            printf "  ${GREEN}OK${NC}  %s is healthy\n" "$name"
            return 0
        fi
        sleep 2
        ((waited+=2))
    done
    printf "  ${RED}FAIL${NC}  %s did not become healthy within %ds\n" "$name" "$max_wait"
    return 1
}

echo ""
echo "=============================="
echo "  SASP Mac Studio Startup"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================="

# --- Pre-flight checks ---
echo ""
echo "--- Pre-flight checks ---"

# Check LM Studio (must be started manually)
if curl -sf --max-time 3 "http://localhost:1234/v1/models" >/dev/null 2>&1; then
    printf "  ${GREEN}OK${NC}  LM Studio is running on :1234\n"
else
    printf "  ${YELLOW}WARN${NC}  LM Studio not detected on :1234\n"
    echo "         Open LM Studio, load Nemotron-3-Nano, start server on 0.0.0.0:1234"
    echo "         Bridge will start but investigations will fail until LM Studio is up."
    echo ""
fi

# Check Kafka reachability
if nc -z -w 3 <S2_IP> 9092 2>/dev/null; then
    printf "  ${GREEN}OK${NC}  Kafka is reachable (<S2_IP>:9092)\n"
else
    printf "  ${RED}FAIL${NC}  Kafka not reachable — S2 may be down\n"
    echo "         Services will start but won't process data until Kafka is back."
fi

# --- Start services ---
echo ""
echo "--- Starting services ---"

# 1. Sanitizer
echo "Starting Sanitizer (port 9091)..."
nohup bash "$SCRIPT_DIR/start_sanitizer.sh" > "$LOG_DIR/sanitizer.log" 2>&1 &
SANITIZER_PID=$!
echo "  PID: $SANITIZER_PID  Log: $LOG_DIR/sanitizer.log"
wait_for_health "Sanitizer" "http://localhost:9091/health" 15

# 2. Kafka Bridge
echo "Starting Kafka Bridge (port 9093)..."
nohup bash "$SCRIPT_DIR/start_bridge.sh" > "$LOG_DIR/bridge.log" 2>&1 &
BRIDGE_PID=$!
echo "  PID: $BRIDGE_PID  Log: $LOG_DIR/bridge.log"
wait_for_health "Kafka Bridge" "http://localhost:9093/health" 15

# 3. ISE Bridge
echo "Starting ISE Bridge (port 9096)..."
nohup bash "$SCRIPT_DIR/start_ise_bridge.sh" > "$LOG_DIR/ise_bridge.log" 2>&1 &
ISE_PID=$!
echo "  PID: $ISE_PID  Log: $LOG_DIR/ise_bridge.log"
wait_for_health "ISE Bridge" "http://localhost:9096/health" 15

# --- Summary ---
echo ""
echo "=============================="
echo "  Startup complete"
echo ""
echo "  Sanitizer:    PID $SANITIZER_PID  →  $LOG_DIR/sanitizer.log"
echo "  Kafka Bridge: PID $BRIDGE_PID  →  $LOG_DIR/bridge.log"
echo "  ISE Bridge:   PID $ISE_PID  →  $LOG_DIR/ise_bridge.log"
echo ""
echo "  Run 'bash scripts/check_services.sh' to verify all services"
echo "=============================="
echo ""
