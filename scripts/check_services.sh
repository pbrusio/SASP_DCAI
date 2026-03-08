#!/usr/bin/env bash
# SASP Service Health Check — verify all services across the platform
# Usage: bash scripts/check_services.sh

set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check_http() {
    local name="$1" url="$2" timeout="${3:-5}"
    if curl -sf --max-time "$timeout" "$url" >/dev/null 2>&1; then
        printf "  ${GREEN}OK${NC}  %s (%s)\n" "$name" "$url"
        ((PASS++))
    else
        printf "  ${RED}FAIL${NC}  %s (%s)\n" "$name" "$url"
        ((FAIL++))
    fi
}

check_tcp() {
    local name="$1" host="$2" port="$3" timeout="${4:-3}"
    if nc -z -w "$timeout" "$host" "$port" 2>/dev/null; then
        printf "  ${GREEN}OK${NC}  %s (%s:%s)\n" "$name" "$host" "$port"
        ((PASS++))
    else
        printf "  ${RED}FAIL${NC}  %s (%s:%s)\n" "$name" "$host" "$port"
        ((FAIL++))
    fi
}

echo ""
echo "=============================="
echo "  SASP Service Health Check"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================="

echo ""
echo "--- Mac Studio (<MAC_STUDIO_IP>) ---"
check_http "Sanitizer"       "http://localhost:9091/health"
check_http "Kafka Bridge"    "http://localhost:9093/health"
check_http "ISE Bridge"      "http://localhost:9096/health"
check_http "LM Studio"       "http://localhost:1234/v1/models"

echo ""
echo "--- S1 — Inference (<S1_IP>) ---"
check_http "Triton Health"   "http://<S1_IP>:8000/v2/health/ready"
check_http "DFP Detector"    "http://<S1_IP>:9097/health"

echo ""
echo "--- S2 — Collection (<S2_IP>) ---"
check_tcp  "Kafka"           "<S2_IP>" 9092
# Zookeeper runs inside Docker without host port mapping; check via container
if ssh -o ConnectTimeout=3 <SERVER_USER>@<S2_IP> \
    "docker exec zookeeper bash -c 'echo srvr | nc localhost 2181'" 2>/dev/null | grep -q "Zookeeper version"; then
    printf "  ${GREEN}OK${NC}  %s (docker exec → ruok/imok)\n" "Zookeeper"
    ((PASS++))
else
    printf "  ${RED}FAIL${NC}  %s (docker exec → ruok/imok)\n" "Zookeeper"
    ((FAIL++))
fi

echo ""
echo "--- Splunk (<SPLUNK_IP>) ---"
check_tcp  "Splunk Web"      "<SPLUNK_IP>" 8000
check_tcp  "Splunk HEC"      "<SPLUNK_IP>" 8088

echo ""
echo "=============================="
printf "  Results: ${GREEN}%d OK${NC}  ${RED}%d FAIL${NC}\n" "$PASS" "$FAIL"
echo "=============================="
echo ""

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
