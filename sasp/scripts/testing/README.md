# SASP Detection Pipeline Testing

Tools for generating controlled "bad" traffic to validate the full detection pipeline.

## Architecture

```
Layer 3 (VM):     hping3 → Cat9200L → GoFlow2 → Kafka(netflow-raw)
Layer 2 (Raw):    traffic_simulator.py → Kafka(netflow-raw) → Sanitizer → ...
Layer 1 (Sanitized): traffic_simulator.py → Kafka(netflow-sanitized) → Morpheus → Triton → Bridge → Agents → Splunk
```

## Quick Start

```bash
# List available scenarios
python -m sasp.scripts.testing.traffic_simulator --list

# Dry run — print JSON to stdout, no Kafka
python -m sasp.scripts.testing.traffic_simulator --dry-run --scenarios all

# Inject attack scenario to sanitized topic (bypasses sanitizer)
python -m sasp.scripts.testing.traffic_simulator --target sanitized --scenarios large_exfil

# Inject to raw topic (tests sanitizer + everything downstream)
python -m sasp.scripts.testing.traffic_simulator --target raw --scenarios large_exfil --verify

# Run all scenarios
python -m sasp.scripts.testing.traffic_simulator --target sanitized --scenarios all
```

## Scenarios

| ID  | Name              | Type   | Description                          |
|-----|-------------------|--------|--------------------------------------|
| T01 | large_exfil       | DETECT | 50MB transfer, 50K bytes/packet      |
| T02 | udp_flood         | DETECT | 5K tiny UDP packets to port 53       |
| T03 | icmp_tunnel       | DETECT | 1400-byte ICMP payloads              |
| T04 | long_c2           | DETECT | 5-min session on port 4444           |
| T05 | syn_burst         | DETECT | 5K packets in 0.1 seconds            |
| T06 | proto_other       | DETECT | GRE protocol, 1MB transfer           |
| T07 | baseline          | BENIGN | Normal HTTPS (negative control)      |
| T08 | near_threshold    | BENIGN | Near MSE=0.05 boundary               |
| T09 | port_scan         | DETECT | 50+ unique dst ports (aggregate fix) |
| T10 | c2_fanout         | DETECT | 20 unique dst IPs (aggregate fix)    |
| T11 | data_exfil_ratio  | DETECT | 100:1 out/in byte ratio (agg fix)    |

T09-T11 require the sanitizer aggregate feature fix to work via Layer 2. They
work via Layer 1 injection because feat_* overrides are applied directly.

## Safety

All safety constraints are enforced in code:

- **IP range**: Source/dest IPs use `100.64.0.x` / `100.64.1.x` (IANA shared address space, RFC 6598). Not routable, clearly synthetic.
- **Batch cap**: Max 20 records per scenario per run (hard limit in code).
- **Rate limit**: Max 10 records/second (hard limit in code).
- **Server subnet block**: Refuses to produce records with IPs in `<MGMT_SUBNET>/24`.
- **Traceability**: Every record tagged with `test_scenario`, `test_run_id`, and `test_scenario_id` for Splunk filtering.

## Verifying Results

After injection, use these Splunk queries:

```spl
# Find all investigations from a test run
index=sasp_investigations test_run_id="<run_id>"
| table investigation_id, source_ip, score, severity, test_scenario

# Verify negative controls produced zero investigations
index=sasp_investigations test_scenario=baseline test_run_id="<run_id>"
| stats count

# Detection feed dashboard filter
index=sasp_detections source_ip="100.64.0.*"
| table _time, source_ip, dest_ip, anomaly_score, model_name
```

## Integration Tests

```bash
# Requires live Kafka + Triton
KAFKA_BOOTSTRAP_SERVERS=<S2_IP>:9092 pytest -m "requires_kafka and requires_triton" \
    sasp/tests/integration/test_detection_scenarios.py -v
```

## VM Traffic Generator

For full E2E testing through the physical network:

```bash
# From attacker VM on 192.168.30.x
./vm_traffic_generator.sh 192.168.30.200         # All scenarios
./vm_traffic_generator.sh 192.168.30.200 exfil   # Single scenario
```

Requires: `hping3`, `ncat` installed on the attacker VM. Target VM just needs to be reachable.
