# Domain 2: AI Infrastructure Components and Architecture (30%)

> **All objectives use "EVALUATE"** - This is analysis-based.
> Understand tradeoffs, make recommendations, assess requirements.

---

## Objectives

| Objective | Topic | Verb | Evidence |
|-----------|-------|------|----------|
| 2.1 | Network deployment | EVALUATE | 📝 Analysis |
| 2.2 | Compute deployment | EVALUATE | 📸 CIMC Screenshots |
| 2.3 | Storage deployment | EVALUATE | 📝 Analysis |
| 2.4 | Power/efficiency | EVALUATE | 📸 CIMC Screenshots |
| 2.5 | Hybrid AI deployment | EVALUATE | 📝 Analysis |

---

## 2.1 Network Deployment Evaluation

**Requirements to evaluate:**
- Bandwidth (gradient sync, data movement)
- Latency (training iteration time)
- Redundancy (fault tolerance)
- Scalability (adding nodes)
- Security (isolation, encryption)

**SASP Implementation:**

| Requirement | Solution | Evidence |
|-------------|----------|----------|
| Bandwidth | 25GbE ConnectX-4 LX | ✅ **2.91 GB/s RoCE** (Feb 27) — `4.1_Benchmarks/nccl_allreduce_roce_25gbe_results.png` |
| Latency | RoCEv2 (368ms for 1GB all-reduce) | ✅ **24x faster than TCP** — `4.1_Benchmarks/nccl_benchmark_results.md` |
| Redundancy | Dual-homed design | Network diagram (⏳ diagram still needed) |
| Scalability | Leaf-spine ready | Architecture docs |

---

## 2.2 Compute Deployment Evaluation

**Requirements to evaluate:**
- CPU resources
- GPU resources and connectivity
- Memory
- Virtualization support
- Scalability/redundancy
- Workload types

**SASP Implementation:**

| Component | Specification | Evidence |
|-----------|---------------|----------|
| Server | Cisco UCS C220 M5 / C240 M5 | CIMC screenshots |
| GPU | Tesla T4 (16GB GDDR6, 70W) | `cimc_gpu_inventory.png` |
| Memory | 512GB DDR4 | CIMC inventory |
| Virtualization | Docker + NVIDIA runtime | docker-compose files |

### Evidence Files

| Screenshot | Location | Shows |
|------------|----------|-------|
| `cimc_gpu_inventory.png` | [2.2_Compute_Deployment/](./2.2_Compute_Deployment/) | GPU detected in CIMC |
| `cimc_pci_adapters_inventory.png` | [2.2_Compute_Deployment/](./2.2_Compute_Deployment/) | PCI adapter list |

---

## 2.3 Storage Deployment Evaluation

**Requirements to evaluate:**
- Capacity (dataset size, checkpoints)
- Performance (IOPS, throughput)
- Redundancy/availability
- Scalability

**SASP Implementation:**

| Storage | Type | Use Case |
|---------|------|----------|
| S1 /mnt/storage1 | Local NVMe | Morpheus workspace, models |
| S2 /data | Local SATA | Kafka, training data |

**Storage Technologies (for exam):**

| Technology | Latency | Use Case |
|------------|---------|----------|
| NVMe SSD | <100μs | Hot data, model loading |
| NVMe-oF | Network + NVMe | Shared fast storage |
| Fibre Channel | ~500μs | Enterprise SAN |
| NFS | ~1ms+ | Shared datasets |

---

## 2.4 Power/Efficiency Evaluation

**Requirements to evaluate:**
- Power consumption
- Cooling requirements
- PUE (Power Usage Effectiveness)
- Renewable energy

**SASP Implementation:**

| Component | Power |
|-----------|-------|
| C220 M5 base | ~300W |
| C240 M5 base | ~400W |
| Tesla T4 | 70W TDP |
| **Total** | ~840W |

**PUE Formula:**
```
PUE = Total Facility Power / IT Equipment Power

1.0 = Perfect (impossible)
1.2 = Excellent
1.5 = Average
2.0 = Inefficient
```

---

## 2.5 Hybrid AI Deployment Evaluation

**Requirements to evaluate:**
- Secure connectivity
- Data synchronization
- Workload mobility

**Patterns:**

| Pattern | Data | Compute | Use Case |
|---------|------|---------|----------|
| Cloud training | Cloud | Cloud | Rapid experimentation |
| Edge inference | Local | Local | Low latency |
| Cloud burst | Local primary | Cloud overflow | Variable demand |

**SASP Approach:**
- 100% on-premises (air-gap capable)
- No cloud integration required
- Suitable for federal/classified environments

---

## Known Gaps (from evaluation)

> **Readiness: Good.** Solid evidence on CIMC and GPU inventory. Gaps in 2.1/2.3 Benchmarking (`fio`/`iperf`) to prove the "why" behind design choices.

**Priority actions:**
1. Run `fio` benchmark for storage IOPS/throughput → proves storage can feed GPU
2. Run `iperf3` network baseline → proves bandwidth before/after RoCE
3. Run NCCL TCP benchmark → shows multi-node communication baseline

## Study Resources

- [DCAI Study Guide - Domain 2](../docs/DCAI_STUDY_GUIDE.md#domain-20-ai-infrastructure-components-and-architecture-30)
- Tesla T4 specifications
- Cisco UCS documentation

---

## Folder Contents

```
2.1_Network_Deployment/
2.2_Compute_Deployment/
    ├── cimc_gpu_inventory.png           ✅
    ├── cimc_pci_adapters_inventory.png  ✅
    └── cimc_memory_inventory.png        ✅
2.3_Storage_Deployment/
    └── cimc_storage_inventory.png       ✅
2.4_Power_Efficiency_Sustainability/
2.5_Hybrid_AI_Deployment/
```

### Screenshots Needed / Status

| Screenshot | Folder | Status |
|------------|--------|--------|
| NCCL TCP baseline (0.12 GB/s) | 4.1_Benchmarks/ | ✅ `nccl_allreduce_tcp_baseline_results.png` (Feb 27) |
| NCCL RoCE result (2.91 GB/s) | 4.1_Benchmarks/ | ✅ `nccl_allreduce_roce_25gbe_results.png` (Feb 27) |
| ConnectX-4 ethtool / link info (`ethtool -i` + `ip a`) | 2.1_Network_Deployment | ✅ `connectx4_link_info.png` |
| `iperf3` network benchmark | — | 🪁 N/A — NCCL TCP/RoCE results cover network evidence |
| `fio` storage benchmark | 2.3_Storage_Deployment | ⏳ |
| Power readings | 2.4_Power_Efficiency | ⏳ |
