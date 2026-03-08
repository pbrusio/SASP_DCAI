#!/bin/bash
# SASP Health Check Script
# Run on each server to verify infrastructure health

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "         SASP Health Check"
echo "=========================================="
echo ""

# Detect which server we're on
HOSTNAME=$(hostname)
echo "Host: $HOSTNAME"
echo ""

# GPU Status
echo "=== GPU Status ==="
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total \
        --format=csv,noheader 2>/dev/null || echo -e "${RED}GPU query failed${NC}"
else
    echo -e "${YELLOW}nvidia-smi not found${NC}"
fi
echo ""

# RDMA Status
echo "=== RDMA Status ==="
if command -v ibstat &> /dev/null; then
    ibstat 2>/dev/null | grep -E "State|Rate" || echo -e "${YELLOW}No RDMA devices${NC}"
else
    echo -e "${YELLOW}ibstat not found (RDMA not configured)${NC}"
fi
echo ""

# Docker Containers
echo "=== Docker Containers ==="
if command -v docker &> /dev/null; then
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo -e "${RED}Docker query failed${NC}"
else
    echo -e "${RED}Docker not found${NC}"
fi
echo ""

# Kafka (Server 2 only)
echo "=== Kafka Status ==="
if docker ps | grep -q kafka; then
    echo "Kafka container: running"
    
    # Topic list
    echo "Topics:"
    docker exec kafka kafka-topics --list --bootstrap-server localhost:9092 2>/dev/null | head -10 || true
    
    # NetFlow count
    FLOW_COUNT=$(docker exec kafka kafka-run-class kafka.tools.GetOffsetShell \
        --broker-list localhost:9092 --topic netflow-raw --time -1 2>/dev/null | \
        awk -F: '{sum+=$3} END {print sum}' || echo "0")
    echo "NetFlow messages: $FLOW_COUNT"
else
    echo -e "${YELLOW}Kafka not running on this server${NC}"
fi
echo ""

# Triton (Server 1 only)
echo "=== Triton Status ==="
if curl -s localhost:8000/v2/health/ready &>/dev/null; then
    echo -e "${GREEN}Triton: Ready${NC}"
    
    # Model list
    echo "Models:"
    curl -s localhost:8000/v2/models 2>/dev/null | python3 -c "import sys,json; models=json.load(sys.stdin).get('models',[]); print('\n'.join(['  - '+m['name'] for m in models]))" 2>/dev/null || true
else
    echo -e "${YELLOW}Triton not running or not ready${NC}"
fi
echo ""

# Disk Usage
echo "=== Disk Usage ==="
df -h /data /mnt/storage1 2>/dev/null | grep -v Filesystem || df -h / | grep -v Filesystem
echo ""

# Network Connectivity
echo "=== Network Connectivity ==="
SERVER1="<S1_IP>"
SERVER2="<S2_IP>"
SPLUNK="<SPLUNK_IP>"

ping -c 1 -W 1 $SERVER1 &>/dev/null && echo -e "Server 1 ($SERVER1): ${GREEN}OK${NC}" || echo -e "Server 1 ($SERVER1): ${RED}FAIL${NC}"
ping -c 1 -W 1 $SERVER2 &>/dev/null && echo -e "Server 2 ($SERVER2): ${GREEN}OK${NC}" || echo -e "Server 2 ($SERVER2): ${RED}FAIL${NC}"
ping -c 1 -W 1 $SPLUNK &>/dev/null && echo -e "Splunk ($SPLUNK): ${GREEN}OK${NC}" || echo -e "Splunk ($SPLUNK): ${YELLOW}UNREACHABLE${NC}"
echo ""

# Splunk HEC
echo "=== Splunk HEC ==="
if curl -sk "https://$SPLUNK:8088/services/collector/health" &>/dev/null; then
    echo -e "${GREEN}Splunk HEC: Available${NC}"
else
    echo -e "${YELLOW}Splunk HEC: Not available${NC}"
fi
echo ""

echo "=========================================="
echo "         Health Check Complete"
echo "=========================================="
