# SASP_DCAI

> **Secure AI Security Platform** — A GPU-accelerated security analytics platform.
> Built as a hands-on project for the Cisco DCAI (300-640) certification — passed March 2026.

---

## Overview

This repository serves two purposes:

1. **DCAI Exam Preparation** — Documentation and evidence mapped to exam objectives
2. **SASP Project** — Working implementation of an AI-powered security platform

37/37 SASP stories complete. Wave 7 (2026-03-04): ISE DFP model (14-feature autoencoder), per-feature error attribution, cross-model correlation, 5 Triton models. 167 unit tests pass.

- **Exam tracking:** [`EVIDENCE_CHECKLIST.md`](./EVIDENCE_CHECKLIST.md) — every objective mapped to evidence
- **Timeline & operational notes:** [`activities_log.md`](./activities_log.md)
- **Version history:** [`CHANGELOG.md`](./CHANGELOG.md)

---

## Lab Topology

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              SASP LAB TOPOLOGY                                        │
│                                                                                      │
│                      ┌────────────────────────────────┐                              │
│                      │    Cat9200L (Core Switch)       │                              │
│                      │    NetFlow source               │                              │
│                      │    GWs: <MGMT_SUBNET_PATTERN>          │                              │
│                      │          <WORKSTATION_SUBNET_PATTERN>        │                              │
│                      └───┬────┬────┬────┬────┬────┬───┘                              │
│                          │    │    │    │    │    │                                    │
│                          │    │    │    │    │    │  mgmt uplink                      │
│                          │    │    │    │    │    │                                    │
│    ┌─────────────────────┼────┼────┼────┼────┼────┼──────────────────────────────┐   │
│    │  MANAGEMENT NETWORK  │    │    │    │    │    │  (<MGMT_SUBNET>/24)             │   │
│    └─────────────────────┼────┼────┼────┼────┼────┼──────────────────────────────┘   │
│                          │    │    │    │    │                                        │
│               .34        │.32 │.33 │.80 │    │                                       │
│    ┌──────────────┐ ┌────┴───┐│   ┌┴───┐│   │                                       │
│    │ S1 (C220 M5) │ │S2      ││   │Splnk│   │                                       │
│    │ Tesla T4     │ │C240 M5 ││   │SIEM │   │                                       │
│    │ Triton (5    │ │Tesla T4││   │6 db │   │                                       │
│    │  models)     │ │Kafka   ││   └─────┘   │                                       │
│    │ Morpheus     │ │GoFlow2 ││             │                                        │
│    └──────┬───────┘ └───┬────┘│             │                                        │
│           │             │     │             │                                         │
│    ┌──────┴─────────────┴─────┴─────────────┴──────────────────────────────────┐     │
│    │          Nexus 93180YC-EX (NX-OS 10.3(8))                                  │     │
│    │          PFC + ECN + QoS (DSCP 26 → CoS 3 lossless)                        │     │
│    │                                                                            │     │
│    │  RDMA FABRIC (<RDMA_SUBNET>/24, VLAN 810) — ConnectX-4 LX 25GbE            │     │
│    │  E1/44 ←→ S1 (.34)    E1/38 ←→ S2 (.32)    E1/32 ←→ VM (.120)            │     │
│    └────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│    ┌─────────────────────────────────────────────────────────────────────────────┐   │
│    │  WORKSTATION SUBNET (<WORKSTATION_SUBNET>/24)                                       │   │
│    │                                                                             │   │
│    │  ┌────────────────┐             ┌────────────────┐                          │   │
│    │  │ Workstation    │             │ Mac Studio     │                          │   │
│    │  │ <WORKSTATION_IP> │             │ <MAC_STUDIO_IP> │                          │   │
│    │  │ RTX 5080       │             │ M3 Ultra 96GB  │                          │   │
│    │  │                │             │                │                          │   │
│    │  │ ⚡ DEV-ONLY    │             │ Sanitizer :9091│                          │   │
│    │  │ (power off     │             │ Bridge    :9093│                          │   │
│    │  │  when idle)    │             │ ISE Brdg  :9096│                          │   │
│    │  │                │             │ LLM       :1234│                          │   │
│    │  │ Code + venv    │             │ (Nemotron-3-   │                          │   │
│    │  │ intact for GPU │             │  Nano, all 4   │                          │   │
│    │  │ workloads      │             │  agents)       │                          │   │
│    │  └────────────────┘             └────────────────┘                          │   │
│    └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### End-to-End Data Flow

```
                        ┌─── NetFlow Pipeline ───────────────────────────────────┐
                        │                                                        │
Cat9200L ──NetFlow v9──▶ GoFlow2 (S2) → Kafka (netflow-raw)                     │
                                              │                                  │
                                              ▼                                  │
                                    Sanitizer (Mac Studio)                       │
                                    21 injection patterns                        │
                                    + 15 ML features                             │
                                              │                                  │
                                              ▼                                  │
                                  Kafka (netflow-sanitized)                      │
                                              │                                  │
                                              ▼                                  │
                                   Morpheus (S1, CPU mode)                       │
                                              │                                  │
                                              ▼                                  │
                                    Triton (S1, T4 GPU)                          │
                                    netflow-anomaly model                        │
                                              │                                  │
                                              ▼                                  │
                                 Kafka (morpheus-detections) ────────┐           │
                        └────────────────────────────────────────────┤           │
                                                                     │           │
                        ┌─── GPU Anomaly Pipeline ───────────────┐   │           │
                        │                                        │   │           │
                        │  nvidia-smi (S1) → abp_detector (S1)  │   │           │
                        │          → Triton (abp-nvsmi)          │   │           │
                        │          → Kafka (abp-detections) ─────┤   │           │
                        └────────────────────────────────────────┘   │           │
                                                                     │           │
                        ┌─── Sensitive Info Pipeline ────────────┐   │           │
                        │                                        │   │           │
                        │  Syslog (S2) → Kafka (syslog-sanitized)│   │           │
                        │      → sid_detector (S1, BERT tokenize)│   │           │
                        │      → Triton (sid-minibert)           │   │           │
                        │      → Kafka (sid-detections) ─────────┤   │           │
                        └────────────────────────────────────────┘   │           │
                                                                     │           │
                        ┌─── ISE DFP Pipeline ─────────────────┐   │           │
                        │                                        │   │           │
                        │  ISE (Mac Studio) → Kafka (ise-raw)   │   │           │
                        │      → Sanitizer → Kafka (ise-sanitized)   │           │
                        │      → dfp_detector (S1, 14-feat AE)  │   │           │
                        │      → Triton (ise-dfp)                │   │           │
                        │      → Kafka (ise-dfp-detections) ────┤   │           │
                        └────────────────────────────────────────┘   │           │
                                                                     │           │
                     ┌───────────────────────────────────────────────┘           │
                     ▼                                                           │
           Kafka Bridge (Mac Studio :9093)                                       │
           Consumes: morpheus-detections,                                        │
                     abp-detections,                                             │
                     sid-detections,                                             │
                     ise-dfp-detections                                          │
                     │                                                           │
                     ▼                                                           │
          LangGraph Agents (Mac Studio :1234)                                    │
          triage → investigate → threat_intel → report                           │
                     │                                                           │
                     ▼                                                           │
             Guardian Validation                                                 │
                     │                                                           │
                     ▼                                                           │
              Splunk HEC (SIEM)                                                  │
              6 dashboards: Detections, Investigations,                          │
              AI Health, GPU Health, RoCE Network, ISE Activity                  │
```

### Triton Models (S1, Tesla T4)

| Model | Type | Purpose |
|-------|------|---------|
| netflow-anomaly | Autoencoder (15→15) | NetFlow anomaly detection |
| auth-risk | Classifier (7→3) | Auth event risk scoring |
| abp-nvsmi | XGBoost (18→2) | GPU anomaly / crypto mining detection |
| sid-minibert | BERT (256→10) | Sensitive info (PII/credentials) in syslog |
| ise-dfp | Autoencoder (14→14) | ISE behavioral anomaly (digital fingerprinting) |

### Workstation (RTX 5080) — Dev-Only

The Workstation previously ran the Kafka Bridge 24/7 but has been migrated to Mac Studio (Wave 5). The bridge has zero GPU dependency, so running the 5080 for a CPU-only Python process was unnecessary power draw. The Workstation code and venv remain intact at `/home/<WORKSTATION_USER>/Documents/SASP_DCAI` for when GPU workloads are needed (model training, running larger LLMs, etc.).

---

## Repository Structure

```
SASP_DCAI/
├── README.md                          # This file — topology, data flow, quick links
├── activities_log.md                  # Living session log — timeline, issues, resolutions
├── EVIDENCE_CHECKLIST.md              # DCAI exam objective-to-evidence mapping
├── CHANGELOG.md                       # Version history (v0.1.0, v0.2.0)
├── CONTRIBUTING.md                    # Dev setup, testing, deployment order
│
├── docs/
│   ├── DCAI_STUDY_GUIDE.md            # Exam theory — concepts, definitions, trade-offs
│   ├── DCAI_CHEAT_SHEET.md            # Exam-day reference — NX-OS commands, acronyms
│   ├── DCAI_LAB_CONFIGS.md            # Copy-paste configs from actual lab devices
│   ├── DCAI_PROJECT_WALKTHROUGH.md    # Step-by-step build guide
│   ├── ARCHITECTURE_DECISIONS.md      # ADRs — technology choice rationale
│   ├── WAVE4_DEPLOYMENT.md            # Deployment runbook — how to bring services online
│   └── Morpheus_Deployment_Details.md # Morpheus/Triton/GPU specifics
│
├── Domain_1_AI_Fundamentals_and_Applications/
│   ├── README.md
│   └── 1.1-1.6 subdirectories
│
├── Domain_2_AI_Infrastructure_Components_and_Architecture/
│   ├── README.md
│   └── 2.1-2.5 subdirectories         # CIMC screenshots
│
├── Domain_3_AI_Infrastructure_Deployment_and_Data_Management/
│   ├── README.md
│   └── 3.1-3.3 subdirectories         # PFC/QoS/RoCE evidence
│
├── Domain_4_AI_Infrastructure_Operations_and_Troubleshooting/
│   ├── README.md
│   └── 4.1-4.4 subdirectories         # Benchmarks, monitoring, troubleshooting
│
└── sasp/                              # Project implementation
    ├── README.md                      # Code architecture, module structure
    ├── sanitizer/                     # Input sanitization (21 patterns, 3 subclasses)
    ├── models/                        # ML models (autoencoder, classifier, Triton configs)
    ├── agents/                        # LLM reasoning (LangGraph, 4 agents, guardian, audit)
    ├── infrastructure/                # Docker, scripts, collectors
    └── ui/                            # Splunk dashboards, Gradio chat
```

---

## Quick Links

### Study Materials
- [DCAI Study Guide](./docs/DCAI_STUDY_GUIDE.md) — Full exam guide mapped to project
- [DCAI Cheat Sheet](./docs/DCAI_CHEAT_SHEET.md) — NX-OS commands, acronyms, lab mapping
- [Lab Configurations](./docs/DCAI_LAB_CONFIGS.md) — Actual device configs, copy-paste ready
- [Project Walkthrough](./docs/DCAI_PROJECT_WALKTHROUGH.md) — Step-by-step implementation

### SASP Project
- [Code Architecture](./sasp/README.md) — Architecture diagram and module structure
- [Architecture Decisions](./docs/ARCHITECTURE_DECISIONS.md) — ADRs for technology choices
- [Deployment Runbook](./docs/WAVE4_DEPLOYMENT.md) — How to bring all services online
- [Morpheus Details](./docs/Morpheus_Deployment_Details.md) — GPU/Triton/pipeline specifics
- [Current State](./docs/CURRENT_STATE.md) — Operational status snapshot at v1.0

### Tracking
- [Evidence Checklist](./EVIDENCE_CHECKLIST.md) — DCAI exam objective-to-evidence mapping
- [Activities Log](./activities_log.md) — Timeline, issues, operational status
- [Changelog](./CHANGELOG.md) — Version history

---

## Exam Coverage

For detailed objective-to-evidence mapping, see [`EVIDENCE_CHECKLIST.md`](./EVIDENCE_CHECKLIST.md).

| Domain | Weight | Status |
|--------|--------|--------|
| 1.0 AI Fundamentals and Applications | 20% | Complete |
| 2.0 AI Infrastructure Components and Architecture | 30% | Complete |
| 3.0 AI Infrastructure Deployment and Data Management | 30% | Complete |
| 4.0 AI Infrastructure Operations and Troubleshooting | 20% | Complete |

**Exam status: Passed — March 2026**

---

## License

Apache 2.0 — see [LICENSE](./LICENSE)

---

## Contributing

This is a personal study/portfolio project. Feel free to use as reference for your own DCAI preparation.

---

*Last Updated: March 2026 — v1.0-dcai*
