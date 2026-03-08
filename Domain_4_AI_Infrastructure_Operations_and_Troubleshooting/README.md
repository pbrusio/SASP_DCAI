# Domain 4: AI Infrastructure Operations and Troubleshooting (20%)

> **Objectives use "IMPLEMENT", "MONITOR", and "TROUBLESHOOT"** - This is hands-on.
> Your lab directly covers all of this.

---

## Objectives

| Objective | Topic | Verb | Evidence |
|-----------|-------|------|----------|
| 4.1 | Benchmarks | IMPLEMENT | 📸 NCCL results |
| 4.2 | Monitoring | IMPLEMENT | 📸 Splunk dashboards |
| 4.3 | System messages/management | MONITOR | 📸 + Configs |
| 4.4 | Troubleshooting | TROUBLESHOOT | 📝 Runbooks |

---

## 4.1 Benchmarks

### NCCL Benchmarks — ✅ Completed Feb 27

**All-Reduce Performance (actual results):**

| Network | Bandwidth @ 1GB | Latency | Efficiency | Status |
|---------|-----------------|---------|------------|--------|
| TCP (1GbE mgmt) | **0.12 GB/s** | 9,185 ms | N/A | ✅ Captured |
| RDMA/RoCE (25GbE ConnectX-4) | **2.91 GB/s** | 368 ms | 93.1% | ✅ Captured |
| **Improvement** | **24.25x** | **25x faster** | Near line-rate | |

**Evidence files:**
- `4.1_Benchmarks/nccl_allreduce_tcp_baseline_results.png` — TCP terminal output
- `4.1_Benchmarks/nccl_allreduce_roce_25gbe_results.png` — RoCE terminal output
- `4.1_Benchmarks/nccl_benchmark_results.md` — full analysis + impact on training

**Commands:**
```bash
# TCP baseline (actual command used)
mpirun -np 2 -H <S1_IP>:1,<S2_IP>:1 \
  --mca btl_tcp_if_include eno1 --mca oob_tcp_if_include eno1 \
  -x NCCL_DEBUG=INFO -x NCCL_SOCKET_IFNAME=eno1 -x NCCL_IB_DISABLE=1 \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1

# RoCE with DSCP marking (actual command used)
mpirun -np 2 -H <S1_IP>:1,<S2_IP>:1 \
  --mca btl_tcp_if_include eno1 --mca oob_tcp_if_include eno1 \
  -x NCCL_DEBUG=INFO -x NCCL_IB_DISABLE=0 \
  -x NCCL_IB_GID_INDEX=3 -x NCCL_IB_TC=104 \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1
```

### Inference Benchmarks

**Triton perf_analyzer:**
```bash
perf_analyzer -m model_name --concurrency-range 1:16
```

| Metric | Result |
|--------|--------|
| Throughput | 9,727 inf/sec |
| Latency p99 | 8.2 ms |

### Evidence Status

| Screenshot | Folder | Status |
|------------|--------|--------|
| `nccl_allreduce_tcp_baseline_results.png` | 4.1_Benchmarks/ | ✅ Feb 27 |
| `nccl_allreduce_roce_25gbe_results.png` | 4.1_Benchmarks/ | ✅ Feb 27 |
| `nccl_benchmark_results.md` (full write-up) | 4.1_Benchmarks/ | ✅ Feb 27 |
| `triton_perf_analyzer.png` | 4.1_Benchmarks/ | ⏳ |
| `cuda_bandwidth_test.png` | 4.1_Benchmarks/ | ⏳ |

---

## 4.2 Monitoring

### GPU Monitoring

**nvidia-smi:**
```bash
nvidia-smi --query-gpu=timestamp,name,temperature.gpu,utilization.gpu,memory.used \
  --format=csv -l 5
```

**DCGM:**
```bash
dcgmi dmon -e 100,101,102,103,104
```

### Splunk Dashboards

| Dashboard | Purpose | Status |
|-----------|---------|--------|
| GPU Health | Temp, util, memory, power | ✅ Created |
| Crypto Detection | Mining detection events | ✅ Created |
| Inference Metrics | Throughput, latency | ⏳ |
| Network Telemetry | Flow rates, errors | ⏳ |

### Evidence Status

| Screenshot | Folder | Status |
|------------|--------|--------|
| `nvidia_smi_output.png` | 4.2_Monitoring/ | ✅ |
| `splunk_detection_dashboard.png` | 4.2_Monitoring/ | ✅ |
| `splunk_detection_feed_dashboard.png` | 4.2_Monitoring/ | ✅ Mar 2 |
| `splunk_ai_system_health_dashboard.png` | 4.2_Monitoring/ | ✅ Mar 2 |
| `triton_models_ready.png` | 4.2_Monitoring/ | ✅ |
| `splunk_gpu_dashboard.png` | 4.2_Monitoring/ | ✅ Mar 2 |
| `dcgmi_dmon_output.png` | 4.2_Monitoring/ | ⏳ |

---

## 4.3 System Messages and Management

### 4.3.a Operational Telemetry

**Streaming Telemetry (Nexus):**
```
telemetry
  destination-group 1
    ip address <SPLUNK_IP> port 8086 protocol gRPC
  sensor-group 1
    path sys/ch/ftslot-1/ft depth 0
  subscription 1
    dst-grp 1
    snsr-grp 1
    sample-interval 10000
```

**SASP Telemetry Sources:**

| Source | Data | Destination |
|--------|------|-------------|
| nvidia-smi | GPU metrics | Splunk HEC |
| Triton | Inference metrics | Splunk HEC |
| Morpheus | Detection events | Splunk HEC |
| NetFlow | Network flows | Kafka |

### 4.3.b System Health

**Health Check Script:**
```bash
#!/bin/bash
# GPU
nvidia-smi -q | grep -E "GPU|Memory|Temp|Power"

# RDMA
ibstat | grep -E "State|Rate"

# Containers
docker ps

# Services
curl localhost:8000/v2/health/ready
```

### 4.3.c Alerts

**Splunk Alert Examples:**
- GPU temperature > 85°C
- Inference latency p99 > 100ms
- Detection spike > threshold
- Container health failure

### 4.3.d Log Correlation

**Correlating Events:**
```spl
index=morpheus
| transaction src_ip maxspan=1m
| where eventcount > 1
```

### Evidence Needed

| Screenshot | Folder | Status |
|------------|--------|--------|
| `health_check_output.png` | 4.3b_System_Health/ | ⏳ |
| `splunk_alerts.png` | 4.3c_Alerts/ | ⏳ |

---

## 4.4 Troubleshooting

### Common Issues

#### NCCL Timeout
```
Symptoms: Training hangs
Debug: NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=ALL
Check:
  1. Firewall (ports 29500+)
  2. MTU mismatch
  3. Network reachability
```

#### GPU Out of Memory
```
Symptoms: CUDA OOM error
Check: nvidia-smi
Fix:
  1. Reduce batch size
  2. Gradient checkpointing
  3. Mixed precision (FP16)
```

#### Slow Inference
```
Symptoms: High latency
Debug: perf_analyzer -m model --concurrency-range 1:32
Check:
  1. Model optimization (TensorRT)
  2. Batch size
  3. CPU bottleneck
```

#### RDMA Not Working
```
Symptoms: NCCL shows "TCP" instead of "IB"
Check: ibstat, ibv_devinfo
Fix:
  1. Kernel modules (lsmod | grep mlx)
  2. IP on RDMA interface
  3. PFC on switch
  4. DSCP marking
```

### Troubleshooting Runbook

See: [DCAI_LAB_CONFIGS.md - Troubleshooting](../docs/DCAI_LAB_CONFIGS.md#7-troubleshooting-commands)

---

## Known Gaps (from evaluation)

> **Readiness: Emerging.** Splunk dashboards and `health_check.sh` are great. Need more focus on 4.4 Troubleshooting scenarios.

**Priority actions:**
1. Document a **PFC storm** diagnosis walkthrough (see Study Guide 4.4)
2. Document an **NCCL timeout** diagnosis with `NCCL_DEBUG=INFO` output
3. Run `perf_analyzer` to generate Latency vs. Throughput analysis (batch size impact on p99)
4. Use dCloud for Nexus Dashboard monitoring evidence (4.2)

## Study Resources

- [DCAI Study Guide - Domain 4](../docs/DCAI_STUDY_GUIDE.md#domain-40-ai-infrastructure-operations-and-troubleshooting-20)
- [Lab Configurations](../docs/DCAI_LAB_CONFIGS.md)
- [Troubleshooting RoCEv2 on Cisco Nexus 9000](https://www.cisco.com/c/en/us/support/switches/nexus-9000-series-switches/products-troubleshooting-guides-list.html) — Primary 300-640 troubleshooting reference
- NVIDIA NCCL documentation
- Splunk documentation

---

## Folder Contents

```
4.1_Benchmarks/
    ├── nccl_allreduce_tcp_baseline_results.png  ✅ Feb 27
    ├── nccl_allreduce_roce_25gbe_results.png    ✅ Feb 27
    ├── nccl_benchmark_results.md                ✅ Feb 27
    ├── triton_perf_analyzer.png                 ⏳
    └── cuda_bandwidth_test.png                  ⏳

4.2_Monitoring/
    ├── nvidia_smi_output.png                    ✅
    ├── triton_models_ready.png                  ✅
    ├── splunk_detection_dashboard.png           ✅
    ├── splunk_detection_feed_dashboard.png      ✅ Mar 2
    ├── splunk_ai_system_health_dashboard.png    ✅ Mar 2
    ├── splunk_gpu_dashboard.png                 ✅ Mar 2
    └── dcgmi_dmon_output.png                    ⏳

4.3_System_Messages_and_Management/
    ├── 4.3a_Operational_Telemetry/
    ├── 4.3b_System_Health/
    ├── 4.3c_Alerts/
    └── 4.3d_Log_Correlation/

4.4_Troubleshooting/
    └── troubleshooting_runbook.md   ⏳
```

### Evidence Summary

| Objective | Status | Screenshots |
|-----------|--------|-------------|
| 4.1 Benchmarks | 🔶 NCCL done (Feb 27) — perf_analyzer/CUDA still needed | 2 + 1 write-up |
| 4.2 Monitoring | 🔶 Strong — dcgmi still needed | 6 |
| 4.3 System Mgmt | ⏳ Partial | 0 |
| 4.4 Troubleshooting | 📝 Documented | 0 |
