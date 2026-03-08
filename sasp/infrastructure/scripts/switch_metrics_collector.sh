#!/usr/bin/env bash
# switch_metrics_collector.sh — Collects N9K RoCE port metrics and sends to Splunk HEC
#
# Usage: HEC_TOKEN=xxx ./switch_metrics_collector.sh
# Requires SSH key auth to the N9K (Host "n9k" in ~/.ssh/config)

set -uo pipefail

: "${HEC_TOKEN:?Set HEC_TOKEN}"
: "${SPLUNK_HEC:=http://<SPLUNK_IP>:8088}"
: "${INTERVAL:=30}"
: "${INDEX:=sasp_metrics}"
: "${SOURCETYPE:=sasp:switch_metrics}"
: "${N9K_HOST:=n9k}"

HEC_URL="${SPLUNK_HEC}/services/collector/event"

echo "Switch metrics collector starting (interval: ${INTERVAL}s)"
echo "  N9K: ${N9K_HOST}  Ports: Eth1/32 (VM) Eth1/38 (S2) Eth1/44 (S1)"
echo "  HEC: ${HEC_URL}  Index: ${INDEX}"

# Previous counters for rate calculation
prev_32_in=0; prev_32_out=0
prev_38_in=0; prev_38_out=0
prev_44_in=0; prev_44_out=0
first_run=true

parse_counters() {
    local raw="$1" short="$2"
    in_oct=$(echo "$raw" | awk -v p="$short" '/InOctets/{getline; getline; if($1==p) print $2}')
    in_pkt=$(echo "$raw" | awk -v p="$short" '/InOctets/{getline; getline; if($1==p) print $3}')
    out_oct=$(echo "$raw" | awk -v p="$short" '/OutOctets/{getline; getline; if($1==p) print $2}')
    out_pkt=$(echo "$raw" | awk -v p="$short" '/OutOctets/{getline; getline; if($1==p) print $3}')
    in_mcast=$(echo "$raw" | awk -v p="$short" '/InMcastPkts/{getline; getline; if($1==p) print $2}')
    in_err=$(echo "$raw" | awk -v p="$short" '/Rcv-Err/{getline; getline; if($1==p) print $5}')
    out_disc=$(echo "$raw" | awk -v p="$short" '/Rcv-Err/{getline; getline; if($1==p) print $7}')
    echo "${in_oct:-0} ${out_oct:-0} ${in_pkt:-0} ${out_pkt:-0} ${in_mcast:-0} ${in_err:-0} ${out_disc:-0}"
}

parse_pfc() {
    local raw="$1" short="$2"
    local ether_short pfc_mode pfc_rx pfc_tx pfc_wd
    ether_short=$(echo "$short" | sed 's/Eth/Ethernet/')
    local pfc_line
    pfc_line=$(echo "$raw" | grep "^${ether_short}" | head -1)
    if [ -n "$pfc_line" ]; then
        pfc_mode=$(echo "$pfc_line" | awk '{print $2}')
        pfc_rx=$(echo "$pfc_line" | awk '{print $(NF-1)}')
        pfc_tx=$(echo "$pfc_line" | awk '{print $NF}')
    fi
    pfc_wd=$(echo "$raw" | awk '/Global watch-dog interval/{gsub(/[\[\]]/,"",$NF); print $NF; exit}')
    echo "${pfc_mode:-Off} ${pfc_rx:-0} ${pfc_tx:-0} ${pfc_wd:-unknown}"
}

post_port() {
    local ts="$1" port="$2" label="$3"
    local in_oct out_oct in_pkt out_pkt in_mcast in_err out_disc
    local pfc_mode pfc_rx pfc_tx pfc_wd
    local rate_in rate_out

    read -r in_oct out_oct in_pkt out_pkt in_mcast in_err out_disc <<< "$(parse_counters "$raw" "$port")"
    read -r pfc_mode pfc_rx pfc_tx pfc_wd <<< "$(parse_pfc "$raw" "$port")"

    echo "${in_oct} ${out_oct} ${pfc_mode} ${pfc_rx} ${pfc_tx} ${pfc_wd} ${in_pkt} ${out_pkt} ${in_mcast} ${in_err} ${out_disc}"
}

while true; do
    ts=$(date +%s)

    # Single SSH call for all 3 ports — counters, errors, PFC status, PFC watchdog
    raw=$(ssh -o ConnectTimeout=5 "$N9K_HOST" "show interface ethernet 1/32 counters ; show interface ethernet 1/38 counters ; show interface ethernet 1/44 counters ; show interface ethernet 1/32 counters errors ; show interface ethernet 1/38 counters errors ; show interface ethernet 1/44 counters errors ; show interface ethernet 1/32 priority-flow-control ; show interface ethernet 1/38 priority-flow-control ; show interface ethernet 1/44 priority-flow-control ; show queuing pfc-queue interface ethernet 1/44" 2>/dev/null) || { echo "[$ts] SSH failed"; sleep "$INTERVAL"; continue; }

    # Parse all ports
    read -r in32 out32 ipkt32 opkt32 mcast32 err32 disc32 <<< "$(parse_counters "$raw" "Eth1/32")"
    read -r in38 out38 ipkt38 opkt38 mcast38 err38 disc38 <<< "$(parse_counters "$raw" "Eth1/38")"
    read -r in44 out44 ipkt44 opkt44 mcast44 err44 disc44 <<< "$(parse_counters "$raw" "Eth1/44")"

    read -r pfc_mode32 pfc_rx32 pfc_tx32 pfc_wd32 <<< "$(parse_pfc "$raw" "Eth1/32")"
    read -r pfc_mode38 pfc_rx38 pfc_tx38 pfc_wd38 <<< "$(parse_pfc "$raw" "Eth1/38")"
    read -r pfc_mode44 pfc_rx44 pfc_tx44 pfc_wd44 <<< "$(parse_pfc "$raw" "Eth1/44")"

    # Rate calculation
    if [ "$first_run" = false ]; then
        rate_32_in=$(( (in32 - prev_32_in) * 8 / INTERVAL )); rate_32_out=$(( (out32 - prev_32_out) * 8 / INTERVAL ))
        rate_38_in=$(( (in38 - prev_38_in) * 8 / INTERVAL )); rate_38_out=$(( (out38 - prev_38_out) * 8 / INTERVAL ))
        rate_44_in=$(( (in44 - prev_44_in) * 8 / INTERVAL )); rate_44_out=$(( (out44 - prev_44_out) * 8 / INTERVAL ))
    else
        rate_32_in=0; rate_32_out=0; rate_38_in=0; rate_38_out=0; rate_44_in=0; rate_44_out=0
    fi
    prev_32_in=$in32; prev_32_out=$out32
    prev_38_in=$in38; prev_38_out=$out38
    prev_44_in=$in44; prev_44_out=$out44
    first_run=false

    # Post Eth1/32 (VM RoCE)
    curl -s -k "$HEC_URL" -H "Authorization: Splunk $HEC_TOKEN" -d \
        "{\"time\":${ts},\"host\":\"n9k\",\"index\":\"${INDEX}\",\"sourcetype\":\"${SOURCETYPE}\",\"event\":{\"port\":\"Eth1/32\",\"port_label\":\"vm_roce\",\"in_octets\":${in32},\"out_octets\":${out32},\"in_ucast_pkts\":${ipkt32},\"out_ucast_pkts\":${opkt32},\"in_mcast_pkts\":${mcast32},\"in_errors\":${err32},\"out_discards\":${disc32},\"in_bps\":${rate_32_in},\"out_bps\":${rate_32_out},\"pfc_mode\":\"${pfc_mode32}\",\"pfc_rx_pause\":${pfc_rx32},\"pfc_tx_pause\":${pfc_tx32},\"pfc_watchdog\":\"${pfc_wd32}\"}}" > /dev/null 2>&1

    # Post Eth1/38 (S2 RoCE)
    curl -s -k "$HEC_URL" -H "Authorization: Splunk $HEC_TOKEN" -d \
        "{\"time\":${ts},\"host\":\"n9k\",\"index\":\"${INDEX}\",\"sourcetype\":\"${SOURCETYPE}\",\"event\":{\"port\":\"Eth1/38\",\"port_label\":\"s2_roce\",\"in_octets\":${in38},\"out_octets\":${out38},\"in_ucast_pkts\":${ipkt38},\"out_ucast_pkts\":${opkt38},\"in_mcast_pkts\":${mcast38},\"in_errors\":${err38},\"out_discards\":${disc38},\"in_bps\":${rate_38_in},\"out_bps\":${rate_38_out},\"pfc_mode\":\"${pfc_mode38}\",\"pfc_rx_pause\":${pfc_rx38},\"pfc_tx_pause\":${pfc_tx38},\"pfc_watchdog\":\"${pfc_wd38}\"}}" > /dev/null 2>&1

    # Post Eth1/44 (S1 RoCE)
    curl -s -k "$HEC_URL" -H "Authorization: Splunk $HEC_TOKEN" -d \
        "{\"time\":${ts},\"host\":\"n9k\",\"index\":\"${INDEX}\",\"sourcetype\":\"${SOURCETYPE}\",\"event\":{\"port\":\"Eth1/44\",\"port_label\":\"s1_roce\",\"in_octets\":${in44},\"out_octets\":${out44},\"in_ucast_pkts\":${ipkt44},\"out_ucast_pkts\":${opkt44},\"in_mcast_pkts\":${mcast44},\"in_errors\":${err44},\"out_discards\":${disc44},\"in_bps\":${rate_44_in},\"out_bps\":${rate_44_out},\"pfc_mode\":\"${pfc_mode44}\",\"pfc_rx_pause\":${pfc_rx44},\"pfc_tx_pause\":${pfc_tx44},\"pfc_watchdog\":\"${pfc_wd44}\"}}" > /dev/null 2>&1

    echo "[$ts] Eth1/32(VM): ${rate_32_in}bps in/${rate_32_out}bps out  pfc=${pfc_mode32} rx=${pfc_rx32} tx=${pfc_tx32}"
    echo "[$ts] Eth1/38(S2): ${rate_38_in}bps in/${rate_38_out}bps out  pfc=${pfc_mode38} rx=${pfc_rx38} tx=${pfc_tx38}"
    echo "[$ts] Eth1/44(S1): ${rate_44_in}bps in/${rate_44_out}bps out  pfc=${pfc_mode44} rx=${pfc_rx44} tx=${pfc_tx44}"

    sleep "$INTERVAL"
done
