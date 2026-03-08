# Domain 3: AI Infrastructure Deployment and Data Management (30%)

> **Objectives use "CONFIGURE" and "DEPLOY"** - This is hands-on.
> Actual configuration and deployment evidence required.

---

## Objectives

| Objective | Topic | Verb | Evidence |
|-----------|-------|------|----------|
| 3.1 | High-performance networks | CONFIGURE | 📸 + Configs |
| 3.2 | UCS compute/storage | CONFIGURE | 📸 CIMC Screenshots ✅ |
| 3.3 | AI-ready fabrics | DEPLOY | 📸 ND/Intersight |

---

## 3.1 High-Performance Networks

### 3.1.a Congestion Control (PFC, ECN, ETS)

**Priority Flow Control (PFC):**
- Provides lossless Ethernet
- Pauses specific traffic classes on congestion
- Required for RoCE

**ECN (Explicit Congestion Notification):**
- Marks packets instead of dropping
- Allows graceful slowdown

**ETS (Enhanced Transmission Selection):**
- Allocates bandwidth among traffic classes

| Priority | Traffic | Bandwidth | Treatment |
|----------|---------|-----------|-----------|
| 7 | Network Control | 5% | Strict |
| 5 | RoCE | 50% | Lossless |
| 3 | Best Effort | 45% | ETS |

### 3.1.b RoCE / RoCEv2

| Feature | RoCE v1 | RoCE v2 |
|---------|---------|---------|
| Encapsulation | Ethernet | UDP/IP |
| Routing | L2 only | L3 routable |
| Port | N/A | UDP 4791 |

**Status: ConnectX-4 LX NICs installed and operational (Feb 27)**

| Evidence | Status | File |
|----------|--------|------|
| `ibstat` output (RDMA link Active, 25Gb) | ✅ | `3.1b_RoCE_RoCEv2/ibstat_output.png` |
| `rping` connectivity test | ✅ | `3.1b_RoCE_RoCEv2/rping_test.png` |
| NCCL RDMA benchmark (IB transport, 2.91 GB/s) | ✅ | `4.1_Benchmarks/nccl_allreduce_roce_25gbe_results.png` |

### 3.1.c QoS

**DSCP Markings for AI:**

| Traffic | DSCP | Priority |
|---------|------|----------|
| RoCE/RDMA | 26 (AF31) | High |
| Storage | 24 (CS3) | High |
| Management | 16 (CS2) | Medium |
| Bulk | 0 (BE) | Low |

### 3.1.d Load Distribution

- ECMP for leaf-spine fabrics
- Hash-based distribution on IP/Port

---

## 3.2 UCS Compute and Storage ✅

### 3.2.a Domain Profiles / BIOS Configuration

| Screenshot | Shows | Location |
|------------|-------|----------|
| `cimc_bios_processor_settings.png` | CPU config | [3.2a_Domain_Profiles/](./3.2_UCS_Compute_and_Storage/3.2a_Domain_Profiles/) |
| `cimc_bios_memory_settings.png` | Memory config | [3.2a_Domain_Profiles/](./3.2_UCS_Compute_and_Storage/3.2a_Domain_Profiles/) |
| `cimc_bios_io_settings.png` | I/O config | [3.2a_Domain_Profiles/](./3.2_UCS_Compute_and_Storage/3.2a_Domain_Profiles/) |

### 3.2.b Power Policy

| Screenshot | Shows | Location |
|------------|-------|----------|
| `cimc_power_cap_configuration.png` | Power capping | [3.2b_Power_Policy/](./3.2_UCS_Compute_and_Storage/3.2b_Power_Policy/) |
| `cimc_bios_power_performance_settings.png` | Power/perf settings | [3.2b_Power_Policy/](./3.2_UCS_Compute_and_Storage/3.2b_Power_Policy/) |

### 3.2.c Storage Policies

**Evidence Needed:**
- RAID configuration
- Storage controller settings

### 3.2.d LAN Connectivity / vNIC Policies

| Screenshot | Shows | Location |
|------------|-------|----------|
| `cimc_vnic_eth0_properties.png` | vNIC config | [3.2d_LAN_Connectivity_vNIC_Policies/](./3.2_UCS_Compute_and_Storage/3.2d_LAN_Connectivity_vNIC_Policies/) |

### 3.2.e QoS Policies / System Classes

**Evidence Needed:**
- QoS policy configuration
- System class definitions

### 3.2.f NTP Policy

| Screenshot | Shows | Location |
|------------|-------|----------|
| `cimc_ntp_configuration.png` | NTP settings | [3.2f_NTP_Policy/](./3.2_UCS_Compute_and_Storage/3.2f_NTP_Policy/) |

---

## 3.3 AI-Ready Fabrics / Orchestration

> **Known Gap:** This is the weakest domain area. The exam is heavy on 3.3 Orchestration. Use [Cisco dCloud](https://dcloud.cisco.com) labs to bridge this gap without additional hardware.

### 3.3.a Nexus Dashboard

**Status:** 🔄 Use dCloud "Nexus Dashboard Insights" lab

**Evidence Needed:**
- Dashboard overview / fabric topology
- GPU-to-Network telemetry correlation
- Policy deployment and compliance view

**Resource:** [Nexus Dashboard Insights for AI Clusters User Guide](https://www.cisco.com/c/en/us/support/cloud-systems-management/nexus-dashboard-insights/series.html)

### 3.3.b APIC

**Status:** 🪁 Flying a kite (not pursuing)

### 3.3.c Hyperfabric

**Status:** 📝 Theory only (new product)

**Key Concepts:**
- AI-optimized fabric with SaaS management (Meraki-like)
- Automated RoCE/PFC/ECN configuration
- GPU topology-aware routing
- Zero-touch provisioning

**Resource:** [Cisco Nexus Hyperfabric AI Solution Overview](https://www.cisco.com/c/en/us/products/switches/nexus-hyperfabric.html)

### 3.3.d Intersight

**Status:** 🔄 Use dCloud or Intersight trial

**Evidence Needed:**
- Server inventory (with GPU detection)
- Server profiles (AI-optimized BIOS, vNIC)
- GPU firmware management
- Monitoring views

**Resource:** [Managing UCS AI Infrastructure with Cisco Intersight](https://www.cisco.com/c/en/us/products/cloud-systems-management/intersight/index.html)

---

## Study Resources

- [DCAI Study Guide - Domain 3](../docs/DCAI_STUDY_GUIDE.md#domain-30-ai-infrastructure-deployment-and-data-management-30)
- [Lab Configurations](../docs/DCAI_LAB_CONFIGS.md)
- [Intelligent Lossless Ethernet for AI/ML Workloads (White Paper)](https://www.cisco.com/c/en/us/products/collateral/switches/nexus-9000-series-switches/white-paper-c11-738488.html) — "Bible" for Domain 3.1
- [Cisco dCloud](https://dcloud.cisco.com) — Free Nexus Dashboard and Intersight labs
- Cisco UCS CIMC documentation
- Mellanox OFED documentation

---

## Folder Contents

```
3.1_High_Performance_Networks/
    ├── 3.1a_Congestion_Control_PFC_ECN_ETS/
    ├── 3.1b_RoCE_RoCEv2/
    ├── 3.1c_QoS/
    └── 3.1d_Load_Distribution/

3.2_UCS_Compute_and_Storage/
    ├── 3.2a_Domain_Profiles/
    │   ├── cimc_bios_processor_settings.png  ✅
    │   ├── cimc_bios_memory_settings.png     ✅
    │   └── cimc_bios_io_settings.png         ✅
    ├── 3.2b_Power_Policy/
    │   ├── cimc_power_cap_configuration.png       ✅
    │   └── cimc_bios_power_performance_settings.png ✅
    ├── 3.2c_Storage_Policies/
    ├── 3.2d_LAN_Connectivity_vNIC_Policies/
    │   └── cimc_vnic_eth0_properties.png     ✅
    ├── 3.2e_QoS_Policies_System_Classes/
    └── 3.2f_NTP_Policy/
        └── cimc_ntp_configuration.png        ✅

3.3_AI_Ready_Fabrics_Orchestration/
    ├── 3.3a_Nexus_Dashboard/    🔄 Pending
    ├── 3.3b_APIC/               🪁 Skip
    ├── 3.3c_Hyperfabric/        📝 Theory
    └── 3.3d_Intersight/         🔄 Pending
```

### Evidence Summary

| Objective | Status | Screenshots |
|-----------|--------|-------------|
| 3.1 Networks | ✅ Complete | 4 (N9K QoS/PFC + ibstat + rping) + 3 in 4.1_Benchmarks |
| 3.2 UCS | ✅ Complete | 8 |
| 3.3 Orchestration | 🔄 Use dCloud | 0 |
