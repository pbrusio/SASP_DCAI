#!/usr/bin/env bash
# SASP VM Traffic Generator — Layer 3 (Full E2E)
#
# Generates real network traffic from a Linux VM that the Cat9200L captures
# as NetFlow, testing the complete detection path including GoFlow2 conversion.
#
# Run from the attacker VM on 192.168.30.x subnet.
# The target VM must be reachable on 192.168.30.x (no services needed).
#
# Requirements: hping3, ncat (from nmap package)
#
# Usage:
#   ./vm_traffic_generator.sh <target_ip> [scenario]
#
# Examples:
#   ./vm_traffic_generator.sh 192.168.30.200         # Run all scenarios
#   ./vm_traffic_generator.sh 192.168.30.200 exfil   # Run single scenario
#
# Safety:
#   - Traffic stays within 192.168.30.x subnet
#   - Never targets 192.168.0.x server subnet
#   - hping3 sends crafted packets at controlled rates

set -euo pipefail

TARGET_IP="${1:?Usage: $0 <target_ip> [scenario]}"
SCENARIO="${2:-all}"

# Safety check: refuse to target the server subnet
if [[ "$TARGET_IP" == 192.168.0.* ]]; then
    echo "ERROR: Target IP $TARGET_IP is in the server subnet (<MGMT_SUBNET>/24)."
    echo "       Test traffic must NEVER target infrastructure IPs."
    exit 1
fi

echo "============================================================"
echo "SASP VM Traffic Generator"
echo "  Target:   $TARGET_IP"
echo "  Scenario: $SCENARIO"
echo "  Time:     $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================================"
echo ""

run_exfil() {
    echo "=== T09: Large exfiltration (high bytes/packet TCP on 443) ==="
    echo "    1000 SYN packets with 1400-byte payload to port 443"
    hping3 -S -p 443 -d 1400 -c 1000 "$TARGET_IP" 2>/dev/null || true
    echo "    Done."
    echo ""
}

run_udp_flood() {
    echo "=== T10: UDP flood (tiny 8-byte packets to port 53) ==="
    echo "    5000 UDP packets with 8-byte payload"
    hping3 --udp -p 53 -d 8 -c 5000 --faster "$TARGET_IP" 2>/dev/null || true
    echo "    Done."
    echo ""
}

run_icmp_tunnel() {
    echo "=== T11: ICMP tunnel (large 1400-byte ICMP payload) ==="
    echo "    100 ICMP packets with 1400-byte data"
    hping3 -1 -d 1400 -c 100 "$TARGET_IP" 2>/dev/null || true
    echo "    Done."
    echo ""
}

run_long_c2() {
    echo "=== T12: Long C2 session on non-standard port 4444 ==="
    echo "    5-minute TCP stream to port 4444 (background, sends /dev/zero)"
    timeout 300 ncat "$TARGET_IP" 4444 < /dev/zero 2>/dev/null &
    C2_PID=$!
    echo "    PID: $C2_PID (will auto-terminate after 300s)"
    echo "    Use 'kill $C2_PID' to stop early."
    echo ""
}

run_port_scan() {
    echo "=== T13: Horizontal port scan (TCP SYN to ports 1-100) ==="
    echo "    100 SYN packets, one per port"
    hping3 -S --scan 1-100 "$TARGET_IP" 2>/dev/null || true
    echo "    Done."
    echo ""
}

case "$SCENARIO" in
    all)
        run_exfil
        sleep 2
        run_udp_flood
        sleep 2
        run_icmp_tunnel
        sleep 2
        run_long_c2
        sleep 2
        run_port_scan
        ;;
    exfil)      run_exfil ;;
    udp_flood)  run_udp_flood ;;
    icmp)       run_icmp_tunnel ;;
    c2)         run_long_c2 ;;
    portscan)   run_port_scan ;;
    *)
        echo "Unknown scenario: $SCENARIO"
        echo "Available: all, exfil, udp_flood, icmp, c2, portscan"
        exit 1
        ;;
esac

echo "============================================================"
echo "Traffic generation complete."
echo "Check Splunk: index=sasp_investigations | table source_ip, severity, score"
echo "============================================================"
