# SASP_DCAI Evidence Checklist

> **Cisco 300-640 DCAI** — Documentation and evidence tracker mapped to exam objectives.
>
> Evidence types: 📸 Screenshot · ⌨️ Config/Code block · 📝 Written analysis · 🗂️ File exists

**Legend:** ✅ Done · ⏳ Pending (capturable now) · 🔄 Need access/hardware · 🪁 Skip/N/A

**Lab devices:** `N9K-1` = Nexus 9K (NX-OS) · `C9200L` = Catalyst (IOS-XE) · `C220/C240 M5` = UCS servers (CIMC)

---

## Progress Summary

| Domain | Weight | Evidence Items | Done | Pending | Blocked |
|--------|--------|----------------|------|---------|---------|
| Domain 1 — AI Fundamentals | 20% | 6 objectives (theory) | 6 | 0 | 0 |
| Domain 2 — Components & Architecture | 30% | 13 items | 8 | 3 | 1 |
| Domain 3 — Deployment & Data Mgmt | 30% | 27 items | 20 | 4 | 3 |
| Domain 4 — Operations & Troubleshooting | 20% | 16 items | 7 | 5 | 4 |
| **Totals** | **100%** | **62 items** | **41** | **12** | **8** |

---

## Exam Readiness Alignment (v1.0 Objectives)

> Consolidated view: every v1.0 exam objective mapped to project evidence, Cisco U coursework, and Cisco doc review.
>
> **Legend:** ✅ Complete · 🔶 Partial · ⏳ Not started · 🆕 New topic (not yet in project)

### 1.0 Explain AI Concepts and AI Infrastructure Architecture

| v1.0 Obj | Topic | Project Evidence | Cisco U (AI Net Arch 54%) | Docs Reviewed | Status | Next Action |
|----------|-------|-----------------|--------------------------|---------------|--------|-------------|
| 1.1a | Traditional AI/ML | ✅ Study guide §1.1 + SASP impl | 🔶 Partial | DCAIE, AI PODs AAG | ✅ | — |
| 1.1b | GenAI | 🔶 Study guide mentions GenAI | 🔶 Partial | Agentic Era WP | 🔶 | Expand GenAI section in study guide |
| 1.1c | Agentic AI | 🔶 AI Canvas section exists | 🔶 Partial | Agentic Era WP, AI Canvas | 🔶 | Expand agentic AI coverage |
| 1.1d | Inferencing | ✅ Triton deployment + study guide | 🔶 Partial | AI PODs AAG, Hyperfabric RA | ✅ | — |
| 1.1e | Training | ✅ Distributed training setup + guide | 🔶 Partial | AI PODs AAG, Hyperfabric RA | ✅ | — |
| 1.1f | Fine-tuning | ✅ Study guide covers concept | 🔶 Partial | AI PODs AAG | ✅ | — |
| 1.1g | RAG | ✅ Study guide + SASP agent impl | 🔶 Partial | Agentic Era WP | ✅ | — |
| **1.2a** | **Benchmarks** | 🔶 NCCL TCP + RoCE benchmarks captured (Feb 27) | 🔶 Partial | DCAIE, Hyperfabric RA | 🔶 | perf_analyzer/fio/iperf still needed |
| **1.2b** | **Profiling tools** | ⏳ Concepts in guide, no captures | 🔶 Partial | DCAIAOT | ⏳ | **Add profiling tool taxonomy** |
| **1.2c** | **Synthetic vs real benchmarks** | ⏳ Not yet covered | 🔶 Partial | DCAIE | ⏳ | **Add comparison to study guide** |
| **1.2d** | **Synthetic vs real workloads** | ⏳ Not yet covered | 🔶 Partial | AI PODs AAG | ⏳ | **Add comparison to study guide** |
| **1.3a** | **NL interfaces** | 🆕 AI Canvas section (partial) | 🔶 Partial | **AI Canvas** | 🆕 | **Expand AI Canvas NL content** |
| **1.3b** | **MCP** | 🆕 Brief mention in AI Canvas | 🔶 Partial | **AI Canvas** | 🆕 | **Add MCP explanation** |
| **1.3c** | **API interaction** | 🔶 Triton API in project | 🔶 Partial | AI Canvas | 🔶 | Frame as AI-infra API pattern |
| **1.3d** | **CLI generation** | 🆕 Not yet covered | 🔶 Partial | AI Canvas (lab-dependent) | 🆕 | **Add CLI gen concept section** |
| **1.3e** | **Workflow automation** | 🆕 health_check.sh is adjacent | 🔶 Partial | AI Canvas | 🆕 | **Add workflow automation section** |
| 1.4a | Edge inferencing | 🔶 Study guide §1.4.d (brief) | 🔶 Partial | DCAIE, Hyperfabric RA | 🔶 | Expand edge inferencing |
| 1.4b | Centralized inferencing | ✅ Study guide §1.4.c + SASP | 🔶 Partial | AI PODs AAG | ✅ | — |
| 1.4c | Public cloud | ✅ Study guide §1.4.a | 🔶 Partial | DCAIE | ✅ | — |
| 1.4d | Hybrid cloud | ✅ Study guide §1.4.b + §2.5 | 🔶 Partial | Agentic Era WP, Hyperfabric GS | ✅ | — |
| 1.4e | On-premises | ✅ Study guide §1.4.c + entire lab | 🔶 Partial | AI PODs AAG | ✅ | — |
| 1.5a | Day 0 | ✅ Project = Day 0 (HW setup) | 🔶 Partial | DCAIE, Hyperfabric GS | ✅ | — |
| 1.5b | Day 1 | ✅ Project = Day 1 (config/deploy) | 🔶 Partial | DCAIE, AI PODs AAG | ✅ | — |
| 1.5c | Day 2 | 🔶 Monitoring exists, gaps in ops | 🔶 Partial | DCAIAOT, AI PODs AAG | 🔶 | Complete monitoring + troubleshooting |

### 2.0 Design AI Infrastructure Architecture

| v1.0 Obj | Topic | Project Evidence | Cisco U (AI Net Arch 54%) | Docs Reviewed | Status | Next Action |
|----------|-------|-----------------|--------------------------|---------------|--------|-------------|
| 2.1a | Network requirements | ✅ N9K config + topology + NCCL TCP/RoCE benchmarks (Feb 27) | ✅ Core track topic | Hyperfabric RA, N9300-FX3 DS | ✅ | — |
| 2.1b | Compute requirements | ✅ CIMC GPU/CPU/memory evidence | 🔶 Partial | AI PODs AAG, Hyperfabric RA | ✅ | — |
| 2.1c | Storage requirements | 🔶 Storage inventory captured | 🔶 Partial | ISight Storage BP | 🔶 | **Run fio benchmarks** |
| 2.1d | Power/cooling | 🔶 Power cap configured, need load data | 🔶 Partial | AI PODs AAG | 🔶 | **Capture CIMC power summary under load** |
| 2.1e | Cloud hybrid | ✅ Study guide §2.5 | 🔶 Partial | DCAIE, Hyperfabric GS | ✅ | — |
| 2.2a | AI Canvas integration | 🔶 Study guide §1.6.b | 🔶 Partial | **AI Canvas** | 🔶 | **Expand AI Canvas integration details** |
| 2.2b | Nexus Dashboard | 🔶 NDFC screenshots captured (fabric, inventory, switch overview) | 🔶 Partial | N9300-FX3 DS, NDFC Docs | 🔶 | Add policy deployment view |
| 2.2c | HyperFabric AI | ✅ Study guide §1.6.c + §3.3.c | 🔶 Partial | Hyperfabric GS + RA | ✅ | — |
| 2.2d | Intersight | 🔄 Blocked → dCloud | 🔶 Partial | IMM Guide, AI PODs AAG | ⏳ | **dCloud Intersight lab** |
| **2.3a** | **AI workload security** | 🆕 SASP has security analytics | ⏳ Not in track | AI PODs AAG | 🆕 | **Add AI workload security section** |
| **2.3b** | **Data protection** | 🆕 Not explicitly covered | ⏳ Not in track | Hyperfabric RA | 🆕 | **Add data protection section** |
| **2.3c** | **Segmentation** | 🔶 Study guide mentions ACI | ⏳ Not in track | ACI Design Guide | 🔶 | **Expand segmentation content** |
| **2.3d** | **IAM** | 🆕 Not yet covered | ⏳ Not in track | ACI Design Guide (RBAC) | 🆕 | **Add IAM section** |
| **2.3e** | **Logging/monitoring (security)** | 🔶 Splunk dashboards exist | ⏳ Not in track | APIC Faults Guide, DCAIAOT | 🔶 | **Frame Splunk work as security monitoring** |

### 3.0 Deploy and Configure AI Infrastructure Architecture

| v1.0 Obj | Topic | Project Evidence | Cisco U (AI Net Arch 54%) | Docs Reviewed | Status | Next Action |
|----------|-------|-----------------|--------------------------|---------------|--------|-------------|
| 3.1a | Network connectivity | ✅ PFC/QoS on N9K + topology + ECN configured + zero drops verified (Feb 27) | ✅ Core track topic | Hyperfabric GS, N9300-FX3 DS, RoCEv2 GPU WP | ✅ | — |
| 3.1b | Storage connectivity | 🔶 Storage controller captured | 🔶 Partial | ISight Storage BP, MDS FC Guide | 🔶 | **fio benchmarks + storage policy detail** |
| 3.1c | UCS domain profiles | ✅ CIMC BIOS/power/storage config | ⏳ Compute track | IMM Guide — Domain Profiles | ✅ | — |
| 3.1d | UCS server profiles | ✅ CIMC server profile evidence | ⏳ Compute track | IMM Guide — Server Profiles | ✅ | — |
| 3.1e | Server firmware | 🔶 CIMC shows firmware, no management capture | ⏳ Compute track | IMM Guide | 🔶 | **Capture firmware management view** |
| 3.1f | Rack server discovery | 🆕 Not yet covered (standalone CIMC) | ⏳ Compute track | Hyperfabric GS, ISight Device Mgmt | 🆕 | **dCloud — Intersight discovery workflow** |
| 3.2a | NTP policy | ✅ CIMC NTP configured + screenshot | 🔶 Partial | IMM Guide — Switch Policies | ✅ | — |
| 3.2b | System QoS | ✅ N9K QoS policy-maps applied | ✅ Core track topic | NX-OS QoS, RoCEv2 GPU WP | ✅ | — |
| 3.2c | LLFC | ⏳ Not yet configured | 🔶 Partial | NX-OS QoS — LLFC chapter | ⏳ | **Configure LLFC on N9K + capture** |
| 3.2d | PFC | ✅ N9K PFC on E1/44, E1/50 | ✅ Core track topic | NX-OS QoS — PFC chapter, N9300-FX3 DS | ✅ | — |
| 3.2e | vNIC policy | 🔶 vNIC eth0 captured, eth1 pending | 🔶 Partial | IMM Guide — Server Profiles | 🔶 | **Capture vNIC eth1 + RoCE vNIC** |
| 3.2f | Storage policy | 🔶 Boot order captured, RAID detail pending | 🔶 Partial | ISight Storage BP, IMM Guide | 🔶 | **Capture RAID controller detail** |

### 4.0 Operate and Troubleshoot AI Infrastructure Architecture

| v1.0 Obj | Topic | Project Evidence | Cisco U (AI Net Arch 54%) | Docs Reviewed | Status | Next Action |
|----------|-------|-----------------|--------------------------|---------------|--------|-------------|
| 4.1a | Packet analysis tools | ⏳ Not yet captured | 🔶 Partial | DCAIAOT | ⏳ | **Add packet analysis tool section** |
| 4.1b | Infrastructure tools | ⏳ Need iperf3 capture | 🔶 Partial | AI PODs AAG | ⏳ | **Run iperf3 + capture** |
| 4.1c | GPU tools | 🔶 nvidia-smi exists, need dcgmi + perf_analyzer | 🔶 Partial | DCAIAOT | 🔶 | **Run dcgmi dmon + perf_analyzer** |
| 4.1d | CPU tools | ⏳ Not yet captured | 🔶 Partial | Hyperfabric RA | ⏳ | **Add CPU profiling tool coverage** |
| 4.1e | Workload tools | ⏳ Need perf_analyzer for Triton | 🔶 Partial | DCAIAOT | ⏳ | **Run perf_analyzer --concurrency-range** |
| 4.2a | System status | ✅ nvidia-smi + docker ps + Triton health | 🔶 Partial | ISight Device Mgmt, DCAIAOT | ✅ | — |
| 4.2b | Telemetry | ⏳ Config written, not deployed | 🔶 Partial | DCAIAOT, N9300-FX3 DS | ⏳ | **Deploy N9K streaming telemetry** |
| 4.2c | Load distribution | ⏳ ECMP not yet configured | 🔶 Partial | NX-OS QoS — DLB, N9300-FX3 DS | ⏳ | **Configure ECMP + capture** |
| 4.2d | Temperature | ✅ nvidia-smi shows 40°C | 🔶 Partial | DCAIAOT, ISight Device Mgmt | ✅ | — |
| 4.2e | Timing protocols | ⏳ NTP done, PTP not configured | 🔶 Partial | DCAIAOT, N9300-FX3 DS (PTP) | ⏳ | **Add PTP/timing protocol coverage** |
| 4.2f | Logs | ✅ Splunk dashboards + HEC pipeline | 🔶 Partial | APIC Faults Guide, DCAIAOT | ✅ | — |
| 4.3a | Network troubleshooting | 🔶 PFC storm doc in guide, no live capture | 🔶 Partial | DCAIAOT, NX-OS QoS, APIC Faults | 🔶 | **Complete PFC storm runbook + capture** |
| 4.3b | Storage troubleshooting | ⏳ Not yet covered | 🔶 Partial | ISight Storage BP, RoCEv2 GPU WP | ⏳ | **Add storage troubleshooting scenario** |
| 4.3c | Compute troubleshooting | 🔶 GPU OOM in guide, need more | 🔶 Partial | DCAIAOT, IMM Guide | 🔶 | **Expand compute troubleshooting** |
| 4.3d | Integration troubleshooting | 🆕 Not yet covered | 🔶 Partial | AI Canvas, NDFC Docs, Hyperfabric GS | 🆕 | **Add integration troubleshooting section** |
| 4.3e | AI workload app troubleshooting | 🔶 NCCL timeout in guide, need full scenario | 🔶 Partial | DCAIAOT, AI PODs AAG | 🔶 | **Complete NCCL timeout runbook + Splunk lab** |

### Summary by Status

| Status | Count | Percentage |
|--------|-------|------------|
| ✅ Complete | 28 | 51% |
| 🔶 Partial (need more evidence or doc review) | 18 | 33% |
| ⏳ Not started (capturable now) | 3 | 5% |
| 🆕 New v1.0 topics (not yet in project) | 6 | 11% |
| **Total sub-objectives** | **55** | **100%** |

### Priority Actions (Ordered)

**Tier 1 — New v1.0 Topics (🆕 exam risk):**
1. Add AI security architecture section (2.3a-e) — 5 sub-objectives, entirely new
2. Add AI-infrastructure interaction content (1.3a-e) — NL, MCP, workflow automation
3. Add integration troubleshooting (4.3d) — cross-domain workflows

**Tier 2 — Benchmark/Lab Captures (⏳ evidence gaps):**
4. Run `perf_analyzer` + `fio` + `iperf3` + `dcgmi dmon` — covers 1.2, 4.1a-e
5. ~~Run Soft-RoCE setup~~ — NICs installed, use real ConnectX-4 for `ibstat`/`rping` screenshots
6. ~~NCCL TCP benchmark capture~~ — ✅ **Done Feb 27** (`nccl_allreduce_tcp_baseline_results.png`)

**Tier 3 — dCloud Labs (🔄 access-dependent):**
7. Nexus Dashboard Insights lab — covers 2.2b, 4.2b
8. Intersight lab — covers 2.2d, 3.1f
9. N9K streaming telemetry — covers 4.2b

**Tier 4 — Partial → Complete (🔶 finish what's started):**
10. LLFC configuration on N9K (3.2c)
11. PFC storm + NCCL timeout full runbooks (4.3a, 4.3e)
12. CIMC captures: vNIC eth1, RAID detail, power summary, firmware mgmt (3.1e, 3.2e-f, 2.1d)

---

## Gap Analysis

> Based on external evaluation of evidence and study materials.

| Domain | Readiness | Observations |
|--------|-----------|--------------|
| 1.0 AI Fundamentals | **Strong** | Study Guide is comprehensive. RAG vs. Training vs. Inference trade-offs correctly identified. |
| 2.0 Architecture | **Good** | Solid evidence on CIMC and GPU inventory. Gap: 2.1/2.3 Benchmarking (`fio`/`iperf`) to prove the "why" behind design choices. |
| 3.0 Deployment | **Moderate** | Strength: UCS BIOS and Policy config. Gap: The "Fabric" layer. Exam is heavy on 3.3 Orchestration (Nexus Dashboard/APIC) which current standalone setup hasn't integrated yet. |
| 4.0 Operations | **Emerging** | Splunk dashboards and `health_check.sh` are great. Need more focus on 4.4 Troubleshooting scenarios (e.g., diagnosing a PFC storm or an NCCL timeout). |

### Strategic Suggestions

1. **Bridge the Fabric Gap (3.3):** Use [Cisco dCloud](https://dcloud.cisco.com) or Cisco Modeling Labs (CML). dCloud has specific "Nexus Dashboard Insights" labs for Domain 3.3 and 4.2 screenshots/experience without additional hardware.

2. **Hardware Workaround (3.1b):** While waiting for ConnectX-4 NICs, simulate RoCEv2 using **Soft-RoCE (`rdma_rxe`)** on Linux. This allows running `ibstat` and `rping` over standard Ethernet — perfect for generating the "Proof of Concept" evidence required in Domain 3.1.b.
   ```bash
   # Load Soft-RoCE kernel module
   sudo modprobe rdma_rxe
   # Add RXE device on existing Ethernet interface
   sudo rdma link add rxe0 type rxe netdev eno1
   # Verify
   ibstat
   rping -s -a <ip>
   ```

3. **Benchmarking (4.1):** Don't just show Triton is "Ready." Use `perf_analyzer` (part of Triton SDK) to generate a **Latency vs. Throughput graph**. The DCAI exam specifically looks for understanding of how batch size impacts p99 latency.
   ```bash
   perf_analyzer -m abp-nvsmi-xgb \
       --concurrency-range 1:16 \
       --measurement-interval 10000 \
       -f perf_results.csv
   ```

### Blueprint-Aligned Resource Links

| Domain | Topic | Resource |
|--------|-------|----------|
| 1.6.a | AI PODs | [Cisco AI POD for Enterprise Training and Fine-Tuning Design Guide](https://www.cisco.com/c/en/us/solutions/data-center/ai-ml-solutions.html) — UCS X-Series + Pure Storage POD architecture |
| 1.6.b | AI Canvas | [Cisco AI Canvas: AgenticOps for Networking](https://www.cisco.com/c/en/us/solutions/ai-canvas.html) — Deep Network Model for generative troubleshooting |
| 1.6.c | Hyperfabric AI | [Cisco Nexus Hyperfabric AI Solution Overview](https://www.cisco.com/c/en/us/products/switches/nexus-hyperfabric.html) — Meraki-like SaaS management for AI clusters |
| 3.1.a/c | Lossless Ethernet | [Intelligent Lossless Ethernet for AI/ML Workloads (White Paper)](https://www.cisco.com/c/en/us/products/collateral/switches/nexus-9000-series-switches/white-paper-c11-738488.html) — Buffer thresholds for RoCEv2 ("the Bible" for Domain 3.1) |
| 3.3.a | Nexus Dashboard | [Nexus Dashboard Insights for AI Clusters User Guide](https://www.cisco.com/c/en/us/support/cloud-systems-management/nexus-dashboard-insights/series.html) — GPU-to-Network Telemetry Correlation |
| 3.3.d | Intersight | [Managing UCS AI Infrastructure with Cisco Intersight](https://www.cisco.com/c/en/us/products/cloud-systems-management/intersight/index.html) — GPU profiles and firmware via cloud |
| 4.4 | Troubleshooting | [Troubleshooting RoCEv2 on Cisco Nexus 9000](https://www.cisco.com/c/en/us/support/switches/nexus-9000-series-switches/products-troubleshooting-guides-list.html) — "Why did my NCCL job fail?" primary 300-640 troubleshooting topic |

---

## Domain 1: AI Fundamentals and Applications (20%)

> Theory domain — all objectives use **DESCRIBE**. Study guide covers this domain. No hands-on evidence required.

| # | Objective | Evidence Type | Status | File / Location |
|---|-----------|---------------|--------|-----------------|
| 1.1 | AI/ML workload types (RAG, Training, Inference, GenAI) | 📝 Study Guide | ✅ | `docs/DCAI_STUDY_GUIDE.md` |
| 1.2 | AI lifecycle (data → train → deploy → monitor → retrain) | 📝 Study Guide | ✅ | `docs/DCAI_STUDY_GUIDE.md` |
| 1.3 | AI use cases (anomaly detection, crypto mining, UBA, etc.) | 📝 Study Guide | ✅ | `docs/DCAI_STUDY_GUIDE.md` |
| 1.4 | Types of AI infrastructure (cloud, hybrid, on-prem, edge) | 📝 Study Guide | ✅ | `docs/DCAI_STUDY_GUIDE.md` |
| 1.5 | Components for AI environments (network, compute, storage, etc.) | 📝 Study Guide | ✅ | `docs/DCAI_STUDY_GUIDE.md` |
| 1.6 | Cisco AI solutions (AI PODs, AI Canvas, Hyperfabric AI) | 📝 Study Guide | ✅ | `docs/DCAI_STUDY_GUIDE.md` |

---

## Domain 2: AI Infrastructure Components and Architecture (30%)

> Analysis domain — all objectives use **EVALUATE**.

### 2.1 — Evaluate Network Deployment

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| NCCL all-reduce TCP baseline result | 📸 Screenshot | ✅ | `4.1_Benchmarks/nccl_allreduce_tcp_baseline_results.png` |
| NCCL all-reduce RDMA result | 📸 Screenshot | ✅ | `4.1_Benchmarks/nccl_allreduce_roce_25gbe_results.png` |
| ConnectX-4 LX NIC — link info / `ethtool -i` + `ip a` | 📸 Screenshot | ✅ | `2.1_Network_Deployment/connectx4_link_info.png` |
| Network topology diagram | 📝 Written/diagram | ⏳ | `2.1_Network_Deployment/network_topology.md` |

### 2.2 — Evaluate Compute Deployment ✅

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| GPU inventory (NVIDIA T4 PCIe 16GB 70W, Slot 2) | 📸 Screenshot | ✅ | `2.2_Compute_Deployment/cimc_gpu_inventory.png` |
| PCI adapters inventory (T4 + VIC 1387 + SAS HBA) | 📸 Screenshot | ✅ | `2.2_Compute_Deployment/cimc_pci_adapters_inventory.png` |
| Memory inventory (512GB DDR4, 2666 MHz DIMMs) | 📸 Screenshot | ✅ | `2.2_Compute_Deployment/cimc_memory_inventory.png` |
| Docker + NVIDIA runtime config | 🗂️ File exists | ✅ | `sasp/infrastructure/docker/docker-compose.s1.yml` |

### 2.3 — Evaluate Storage Deployment

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| Storage controller inventory (Cisco 12G Modular SAS HBA) | 📸 Screenshot | ✅ | `2.3_Storage_Deployment/cimc_storage_inventory.png` |
| Storage mounts — `lsblk` + `df -h` output | 📸 Screenshot | ✅ | See `4.2_Monitoring/nvidia_smi_output.png` (multi-purpose) |
| `fio` benchmark results (IOPS / throughput) | 📸 Screenshot | ⏳ | `2.3_Storage_Deployment/fio_benchmark.png` |

### 2.4 — Evaluate Power, Efficiency, and Sustainability

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| `nvidia-smi` power draw (9W idle / 70W TDP, Tesla T4) | 📸 Screenshot | ✅ | `4.2_Monitoring/nvidia_smi_output.png` (multi-purpose) |
| CIMC chassis power summary / power cap readings | 📸 Screenshot | ⏳ | `2.4_Power_Efficiency_Sustainability/cimc_power_summary.png` |

### 2.5 — Evaluate Hybrid AI Deployment

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| On-prem justification (air-gap, federal use case) | 📝 Study Guide | ✅ | `docs/DCAI_STUDY_GUIDE.md` §2.5 |
| Hybrid pattern comparison table | 📝 Study Guide | ✅ | `Domain_2_*/README.md` |

---

## Domain 3: AI Infrastructure Deployment and Data Management (30%)

> Hands-on domain — objectives use **CONFIGURE** and **DEPLOY**.

### 3.1a — Congestion Control (PFC, ECN, ETS) — N9K-1 (NX-OS)

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| N9K-1 `show interface E1/44 priority-flow-control` (PFC On) | 📸 Screenshot | ✅ | `3.1a_Congestion_Control_PFC_ECN_ETS/n9k_show_pfc_interfaces_and_qos_policy.png` |
| N9K-1 `show interface E1/50 priority-flow-control` (PFC On) | 📸 Screenshot | ✅ | `3.1a_Congestion_Control_PFC_ECN_ETS/n9k_show_pfc_interfaces_and_qos_policy.png` |
| N9K-1 `show policy-map type network-qos` (ROCE-LOSSLESS class) | 📸 Screenshot | ✅ | `3.1a_Congestion_Control_PFC_ECN_ETS/n9k_show_pfc_interfaces_and_qos_policy.png` |
| N9K-1 E1/32 PFC config (`switchport mode trunk`) + `show interface E1/32 priority-flow-control detail` (Priority3 Tx: 13,177 frames) | 📸 Screenshot | ✅ | `3.1a_Congestion_Control_PFC_ECN_ETS/n9k_pfc_eth1_32_config_and_counters.png` |
| N9K-1 ECN configuration | ⌨️ Config block | ⏳ | `3.1a_Congestion_Control_PFC_ECN_ETS/n9k_ecn_config.md` |

### 3.1b — RoCE / RoCEv2

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| `ibstat` output (RDMA link Active, 25Gb) | 📸 Screenshot | ✅ | `3.1b_RoCE_RoCEv2/ibstat_output.png` |
| `rping` connectivity test (server + client) | 📸 Screenshot | ✅ | `3.1b_RoCE_RoCEv2/rping_test.png` |
| NCCL RDMA benchmark (shows IB transport) | 📸 Screenshot | ✅ | `4.1_Benchmarks/nccl_allreduce_roce_25gbe_results.png` |

### 3.1c — Quality of Service (QoS) — N9K-1 (NX-OS)

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| N9K-1 ROCE-LOSSLESS `class-map type network-qos` + `pause no-drop` config | 📸 Screenshot | ✅ | `3.1c_QoS/n9k_qos_roce_lossless_config.png` |
| N9K-1 complete QoS policy-map applied to interfaces | ⌨️ Config block | ⏳ | `3.1c_QoS/n9k_qos_full_config.md` |

### 3.1d — Load Distribution

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| ECMP config / `show ip route` equal-cost paths | ⌨️ Config block | ⏳ | `3.1d_Load_Distribution/ecmp_config.md` |

### 3.2a — UCS Domain Profiles / BIOS ✅

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| BIOS → Processor settings | 📸 Screenshot | ✅ | `3.2a_Domain_Profiles/cimc_bios_processor_settings.png` |
| BIOS → Memory settings | 📸 Screenshot | ✅ | `3.2a_Domain_Profiles/cimc_bios_memory_settings.png` |
| BIOS → I/O settings (VT-d, PCIe, NVMe) | 📸 Screenshot | ✅ | `3.2a_Domain_Profiles/cimc_bios_io_settings.png` |

### 3.2b — Power Policy ✅

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| CIMC Power Cap configuration | 📸 Screenshot | ✅ | `3.2b_Power_Policy/cimc_power_cap_configuration.png` |
| BIOS → Power/Performance settings | 📸 Screenshot | ✅ | `3.2b_Power_Policy/cimc_bios_power_performance_settings.png` |

### 3.2c — Storage Policies

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| CIMC Boot Order (UEFI, ubuntu boot target) | 📸 Screenshot | ✅ | `3.2c_Storage_Policies/cimc_boot_order.png` |
| CIMC RAID / storage controller config | 📸 Screenshot | ⏳ | `3.2c_Storage_Policies/cimc_storage_controller_config.png` — need RAID detail view |

### 3.2d — LAN Connectivity / vNIC Policies

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| vNIC eth0 properties (MLOM, VLAN 800, MTU 1500) | 📸 Screenshot | ✅ | `3.2d_LAN_Connectivity_vNIC_Policies/cimc_vnic_eth0_properties.png` |
| vNIC eth1 properties (second vNIC) | 📸 Screenshot | ⏳ | `3.2d_LAN_Connectivity_vNIC_Policies/cimc_vnic_eth1_properties.png` |
| RoCE vNIC (MTU 9000, jumbo frames) | 📸 Screenshot | 🪁 N/A — ConnectX-4 LX is a PCIe NIC, not managed via CIMC vNIC policies | — |

### 3.2e — QoS Policies / System Classes

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| CIMC Adapter QoS / system class config | 📸 Screenshot | ⏳ | `3.2e_QoS_Policies_System_Classes/cimc_qos_system_classes.png` |

### 3.2f — NTP Policy ✅

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| CIMC NTP config (enabled, synced to stratum 3) | 📸 Screenshot | ✅ | `3.2f_NTP_Policy/cimc_ntp_configuration.png` |

### 3.3a — Nexus Dashboard

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| Nexus Dashboard overview / fabric discovery | 📸 Screenshot | ✅ | `3.3a_Nexus_Dashboard/nd_fabric_overview.png` |
| NDFC Manage → Fabrics list (AI-Fabric, eBGP VXLAN EVPN, ASN 65000) | 📸 Screenshot | ✅ | `3.3a_Nexus_Dashboard/nd_fabric_list.png` |
| AI-Fabric Interfaces tab (leaf01, 209 interfaces) | 📸 Screenshot | ✅ | `3.3a_Nexus_Dashboard/nd_fabric_interfaces.png` |
| NDFC Inventory → Switches (leaf01, leaf02, spine01 — Normal mode) | 📸 Screenshot | ✅ | `3.3a_Nexus_Dashboard/nd_switch_inventory.png` |
| leaf01 switch detail flyout (alarms, NX-OS version, uptime) | 📸 Screenshot | ✅ | `3.3a_Nexus_Dashboard/nd_switch_detail_leaf01.png` |
| leaf01 full Switch Overview (perf, interfaces, VXLAN info) | 📸 Screenshot | ✅ | `3.3a_Nexus_Dashboard/nd_switch_overview_leaf01.png` |
| Policy deployment view | 📸 Screenshot | 🔄 Need access | `3.3a_Nexus_Dashboard/nd_policy_deployment.png` |

### 3.3b — APIC

> 🪁 Skipping — not in scope for this lab environment.

### 3.3c — Hyperfabric AI

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| Hyperfabric concepts + key features | 📝 Study Guide | ✅ | `docs/DCAI_STUDY_GUIDE.md` §3.3c |

### 3.3d — Intersight

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| Intersight server inventory view | 📸 Screenshot | 🔄 Need access | `3.3d_Intersight/intersight_server_inventory.png` |
| Intersight server profile | 📸 Screenshot | 🔄 Need access | `3.3d_Intersight/intersight_server_profile.png` |
| Intersight GPU monitoring | 📸 Screenshot | 🔄 Need access | `3.3d_Intersight/intersight_gpu_monitoring.png` |

---

## Domain 4: AI Infrastructure Operations and Troubleshooting (20%)

> Hands-on domain — objectives use **IMPLEMENT**, **MONITOR**, **TROUBLESHOOT**.

### 4.1 — Implement Benchmarks

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| NCCL all-reduce — TCP result (bandwidth table) | 📸 Screenshot | ✅ | `4.1_Benchmarks/nccl_allreduce_tcp_baseline_results.png` |
| NCCL all-reduce — RDMA/RoCE result (2.91 GB/s, 93.1% efficiency) | 📸 Screenshot | ✅ | `4.1_Benchmarks/nccl_allreduce_roce_25gbe_results.png` |
| NCCL TCP vs RoCE detailed write-up | 📝 Analysis | ✅ | `4.1_Benchmarks/nccl_benchmark_results.md` |
| Splunk — SASP RoCE Network Health during peak load (20.77/20.25 Gbps, 83%/81% link util) | 📸 Screenshot | ✅ | `4.1_Benchmarks/splunk_roce_network_health_peak_20gbps.png` |
| Triton `perf_analyzer` — throughput + latency | 📸 Screenshot | ⏳ | `4.1_Benchmarks/triton_perf_analyzer.png` |
| CUDA `bandwidthTest` output | 📸 Screenshot | ⏳ | `4.1_Benchmarks/cuda_bandwidth_test.png` |

### 4.2 — Implement Monitoring

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| `nvidia-smi` — Tesla T4, 40°C, 9W/70W, 0% util, CUDA 13.1 | 📸 Screenshot | ✅ | `4.2_Monitoring/nvidia_smi_output.png` — also has `lsblk` + `df -h` |
| Triton startup — 10 models READY (abp-nvsmi-xgb, ransomware, phishing, etc.) | 📸 Screenshot | ✅ | `4.2_Monitoring/triton_models_ready.png` |
| Splunk — Morpheus Crypto Mining Detection dashboard | 📸 Screenshot | ✅ | `4.2_Monitoring/splunk_detection_dashboard.png` |
| Splunk — SASP Detection Feed (Total/Critical/High counts, Detection Types, Recent Detections) | 📸 Screenshot | ✅ Mar 2 | `4.2_Monitoring/splunk_detection_feed_dashboard.png` |
| Splunk — SASP AI System Health (agent response times, guardian approval rate, Ollama endpoint, error rate) | 📸 Screenshot | ✅ Mar 2 | `4.2_Monitoring/splunk_ai_system_health_dashboard.png` |
| Splunk — SASP RoCE Network Health dashboard (7.66 Gbps, 30.7% util) | 📸 Screenshot | ✅ | `4.2_Monitoring/splunk_roce_network_health_dashboard.png` |
| Splunk — SASP RoCE Network Health baseline (0.00 Gbps, idle state) | 📸 Screenshot | ✅ | `4.2_Monitoring/splunk_roce_health_baseline_idle.png` |
| Splunk — GPU Infrastructure Health (S1/S2 util, GPU memory, GPU temp over time, Triton throughput/latency, model version info — auth-risk + netflow-anomaly READY) | 📸 Screenshot | ✅ Mar 2 | `4.2_Monitoring/splunk_gpu_dashboard.png` |
| `dcgmi dmon` GPU metrics stream | 📸 Screenshot | ⏳ | `4.2_Monitoring/dcgmi_dmon_output.png` |
| Triton metrics endpoint output (`/metrics`) | 📸 Screenshot | ⏳ | `4.2_Monitoring/triton_metrics_endpoint.png` |

### 4.3a — Operational Telemetry

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| N9K-1 streaming telemetry config (gRPC destination) | ⌨️ Config block | 🔄 Need access | `4.3a_Operational_Telemetry/n9k_telemetry_config.md` |
| nvidia-smi telemetry → Splunk HEC pipeline | ⌨️ Code block | ⏳ | `4.3a_Operational_Telemetry/nvidia_smi_to_splunk.md` |

### 4.3b — System Health

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| `health_check.sh` script | 🗂️ File exists | ✅ | `sasp/infrastructure/scripts/health_check.sh` |
| `docker ps` — goflow2, kafka, zookeeper running | 📸 Screenshot | ✅ | `4.3b_System_Health/docker_ps_output.png` |
| Health check script terminal output | 📸 Screenshot | ⏳ | `4.3b_System_Health/health_check_output.png` |

### 4.3c — Alerts

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| Splunk alert definitions (GPU temp, latency thresholds) | 📸 Screenshot | ⏳ | `4.3c_Alerts/splunk_alert_definitions.png` |
| Splunk alert triggered / fired event | 📸 Screenshot | ⏳ | `4.3c_Alerts/splunk_alert_triggered.png` |

### 4.3d — Log Correlation

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| Splunk SPL correlation query | ⌨️ Code block | ⏳ | `4.3d_Log_Correlation/splunk_correlation_query.md` |
| Correlated event result in Splunk | 📸 Screenshot | ⏳ | `4.3d_Log_Correlation/splunk_correlation_result.png` |

### 4.4 — Troubleshooting

| Item | Evidence Type | Status | File / Notes |
|------|---------------|--------|--------------|
| Troubleshooting runbook (NCCL, OOM, RDMA, Inference) | 📝 Written | ⏳ | `4.4_Troubleshooting/troubleshooting_runbook.md` |
| `NCCL_DEBUG=INFO` debug output example | 📸 Screenshot | ⏳ | `4.4_Troubleshooting/nccl_debug_output.png` |

---

## SASP Code Scaffold

> Project implementation files — support the lab and demonstrate hands-on competency.

### Existing (Scaffold ✅)

| File | Purpose | Status |
|------|---------|--------|
| `sasp/sanitizer/base.py` | Input sanitizer base class (injection defense) | ✅ |
| `sasp/sanitizer/patterns.py` | Injection pattern regex library | ✅ |
| `sasp/sanitizer/__init__.py` | Package init | ✅ |
| `sasp/agents/graph.py` | LangGraph investigation workflow (full graph wired) | ✅ |
| `sasp/agents/state.py` | Agent state schema | ✅ |
| `sasp/agents/__init__.py` | Package init | ✅ |
| `sasp/infrastructure/docker/docker-compose.s1.yml` | Server 1 stack (Triton, Morpheus) | ✅ |
| `sasp/infrastructure/docker/docker-compose.s2.yml` | Server 2 stack (Kafka, GoFlow2) | ✅ |
| `sasp/infrastructure/scripts/health_check.sh` | Health check script | ✅ |

### Implementation ✅ Complete

All 10 files above are implemented and deployed. See [`CHANGELOG.md`](./CHANGELOG.md) for version history.

---

## Reference Documents

> Key deployment guides and project summaries.

| Document | Description |
|----------|-------------|
| `docs/Morpheus_Deployment_Details.md` | Complete Morpheus build-out guide: GPU drivers, Docker, Triton, Kafka, Splunk HEC, all pipelines, troubleshooting log |
| `activities_log.md` | Living session log — timeline, issues, operational status |
| `docs/DCAI_STUDY_GUIDE.md` | DCAI 300-640 exam study guide |
| `4.1_Benchmarks/nccl_benchmark_results.md` | NCCL TCP vs RoCE analysis — CPU overhead, GPU utilization, wire efficiency |

---

## What to Capture Next (Priority Order)

### Do Now — No blockers

**HIGH PRIORITY (gap-closing):**

1. ~~**Soft-RoCE setup**~~ → ✅ **Done** — real ConnectX-4 LX: `ibstat_output.png`, `rping_test.png`, `connectx4_link_info.png`
2. **Triton `perf_analyzer`** — generate Latency vs. Throughput graph with `--concurrency-range 1:16` → covers 4.1 (exam expects batch size vs. p99 analysis)
3. **`fio` benchmark** — random read IOPS + sequential throughput → covers 2.3 (proves the "why" behind storage choices)
4. ~~**NCCL TCP benchmark**~~ — ✅ **Done Feb 27** → `4.1_Benchmarks/nccl_allreduce_tcp_baseline_results.png` + `nccl_benchmark_results.md`
5. ~~**`iperf3` network benchmark**~~ — N/A; NCCL TCP/RoCE results + CPU overhead analysis in `nccl_benchmark_results.md` cover 2.1 network evidence adequately

**CIMC captures:**

6. **CIMC → Chassis Power Summary** — power readings under load → covers 2.4
7. **CIMC → vNIC eth1** screenshot → covers 3.2d
8. **CIMC → QoS System Classes** screenshot → covers 3.2e
9. **CIMC → RAID config detail** (drill into MRAID controller) → covers 3.2c
10. **CIMC → Power Supply readings** (C220 + C240) → covers 2.4

**Monitoring & troubleshooting:**

11. **CUDA `bandwidthTest`** → covers 4.1
12. **`dcgmi dmon`** metrics stream → covers 4.2
13. **Splunk GPU health dashboard** → covers 4.2
14. **Splunk alert definitions** → covers 4.3c
15. **`health_check.sh` terminal output** → covers 4.3b
16. **N9K-1 ECN config** + complete QoS policy applied to interfaces → covers 3.1a, 3.1c
17. **Network topology diagram / doc** → covers 2.1
18. **PFC storm troubleshooting scenario** — document diagnosis steps → covers 4.4
19. **NCCL timeout troubleshooting scenario** — document with `NCCL_DEBUG=INFO` output → covers 4.4

**SASP Application (Phase 1 first — unblocks everything downstream):**

20. ~~**Implement `NetFlowSanitizer`**~~ — ✅ **Done** (v0.1.0). Live on Mac Studio, processing netflow-raw → netflow-sanitized with 15 ML features
21. ~~**Create `sasp/agents/nodes/triage.py`**~~ — ✅ **Done** (v0.1.0). Full LLM-powered triage with Nemotron-3-Nano
22. ~~**Create `sasp/agents/security/guardian.py` + `audit.py`**~~ — ✅ **Done** (v0.1.0). 5 validation checks + HMAC-signed audit
23. ~~**Wire Kafka consumer**~~ — ✅ **Done** (v0.2.0). `kafka_bridge.py` on Workstation, 387+ investigations completed

**Morpheus / Triton operational:**

24. **Switch ABP pipeline to `from-kafka`** (swap `from-file` → `from-kafka` in the mpirun command) — streaming live data
25. **Production Kafka config** — add `replication-factor`, persistent volume mounts to `docker-compose.s2.yml`
26. **Run remaining Morpheus pipelines** — benchmark phishing-bert-onnx, log-parsing-onnx throughput (not yet captured)

**dCloud labs (schedule these):**

27. **Cisco dCloud — Nexus Dashboard Insights lab** → covers 3.3a, 4.2
28. **Cisco dCloud — Intersight lab** → covers 3.3d

### ✅ ConnectX-4 LX NICs Installed (Feb 27) — Soft-RoCE Workaround No Longer Needed

> ConnectX-4 LX 25GbE NICs are now installed and operational in both servers. Use real hardware for all RDMA evidence.

- `ibstat` output (real hardware) → still needed, capture from t4server1/t4server2 → covers 3.1b
- `rping` connectivity test → rping verified Feb 27, capture screenshot → covers 3.1b
- NCCL RDMA benchmark → ✅ **Done** (`4.1_Benchmarks/nccl_allreduce_roce_25gbe_results.png`, 2.91 GB/s)
- RoCE vNIC screenshot (jumbo frames MTU 9000) → capture from CIMC → covers 3.2d

### Unblocked via Cisco dCloud (formerly portal-blocked)

> Use [Cisco dCloud](https://dcloud.cisco.com) "Nexus Dashboard Insights" labs for hands-on experience and screenshots.

- Nexus Dashboard screenshots (3.3a) → dCloud lab
- Intersight screenshots (3.3d) → dCloud lab or Intersight trial
- N9K streaming telemetry config (4.3a) → dCloud lab

---

## Cisco U Training Progress

> Formal Cisco training evidence — demonstrates structured exam preparation alongside hands-on lab work.

> The DCAIE course covers the **entire 300-640 blueprint** (all 4 domains, all 57 objective items).

| Track | Course | Completion | Post-Assessment | Blueprint Coverage (~sub-objectives) | Screenshot |
|-------|--------|------------|-----------------|--------------------------------------|------------|
| AI Network Architectures | DCAIE | **100%** | **84%** | ~20 sub-objectives across all 4 domains: 1.1.b-c, 1.5.a, 1.6.a/c, 2.1, 2.5, 3.1.a-d, 3.3.a-c, 4.1, 4.2, 4.3.a, 4.4 | `docs/cisco_u_progress/cisco_u_ai_network_architectures_progress.png` |
| AI Compute and Storage | DCAIE | **100%** | — | 1.5.b-f, 2.2, 2.3, 2.4, 3.2.a-f | ✅ |
| AI Infrastructure Operations | DCAIAOT | **100%** | — | 4.1, 4.2, 4.3.a-d, 4.4 | ✅ |
| AI Fabric Orchestration | — | — | — | 3.3.a-d (ND, APIC, Hyperfabric, Intersight) | ⏳ |

**Impact:** The DCAIE and DCAIAOT learning paths are complete, covering Domains 1-2 and Domain 4 respectively. Combined with hands-on lab work, this provides comprehensive coverage of the 300-640 blueprint. The remaining AI Fabric Orchestration track (Domain 3.3) was addressed through dCloud labs and study materials.

---

*Last updated: 2026-03-08*
