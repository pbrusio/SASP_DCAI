# SASP - Secure AI Security Platform

> **GPU-accelerated security analytics with LLM-powered investigation**
> 
> The "meta" play: AI that secures networks, secured against AI attacks.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SASP ARCHITECTURE                                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DATA SOURCES                                   │   │
│  │  NetFlow (IOS-XE) │ ISE Auth │ Syslog │ DNS (future)              │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      INPUT SANITIZATION                             │   │
│  │  • Strip injection patterns                                        │   │
│  │  • Validate schemas                                                │   │
│  │  • Encode special chars                                            │   │
│  │  • Log originals (forensics)                                       │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      KAFKA MESSAGE BUS                              │   │
│  │  netflow-raw │ ise-auth │ syslog-raw │ sanitized-*                 │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DETECTION LAYER (GPU)                          │   │
│  │                                                                     │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│  │  │  NetFlow    │  │   Auth      │  │  Syslog     │                 │   │
│  │  │ Autoencoder │  │ Classifier  │  │ Autoencoder │                 │   │
│  │  │    (T4)     │  │    (T4)     │  │    (T4)     │                 │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                 │   │
│  │                                                                     │   │
│  │  Morpheus Pipeline → Triton Inference → Kafka (detections)         │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      REASONING LAYER (LLM)                          │   │
│  │                                                                     │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │   │
│  │  │  Triage   │  │Investigate│  │  Threat   │  │  Report   │       │   │
│  │  │  Agent    │  │   Agent   │  │   Intel   │  │  Agent    │       │   │
│  │  │(Mac-Nano) │  │(Mac-Nano) │  │(Mac-Nano) │  │(Mac-Nano) │       │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │   │
│  │                                                                     │   │
│  │  LangGraph Orchestration → Tool Calls → Human Approval Queue       │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      SECURITY LAYER                                 │   │
│  │  • Output validation                                               │   │
│  │  • Guardian agent (watches primary agents)                         │   │
│  │  • Tool sandboxing (read-only vs write)                           │   │
│  │  • Immutable audit trail                                          │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      PRESENTATION LAYER                             │   │
│  │  Splunk Dashboards │ Chat Interface │ Alert Notifications          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
sasp/
├── README.md                      # This file
│
├── infrastructure/                # Deployment configs
│   ├── docker/
│   │   ├── docker-compose.s1.yml  # Server 1 (inference)
│   │   ├── docker-compose.s2.yml  # Server 2 (collection/training)
│   │   └── .env.example
│   ├── configs/
│   │   ├── kafka/
│   │   ├── triton/
│   │   └── morpheus/
│   └── scripts/
│       ├── setup_rdma.sh
│       ├── health_check.sh
│       └── backup_kafka.sh
│
├── sanitizer/                     # Input sanitization
│   ├── __init__.py
│   ├── base.py                    # Base sanitizer class
│   ├── patterns.py                # Injection pattern library
│   ├── netflow.py                 # NetFlow-specific
│   ├── syslog.py                  # Syslog-specific
│   ├── ise.py                     # ISE-specific
│   └── tests/
│       ├── test_injection.py
│       └── test_patterns.py
│
├── models/                        # ML models
│   ├── training/
│   │   ├── netflow_autoencoder.py
│   │   ├── auth_classifier.py
│   │   ├── syslog_autoencoder.py
│   │   └── distributed_trainer.py
│   ├── inference/
│   │   ├── triton_configs/
│   │   │   ├── netflow-anomaly/
│   │   │   ├── auth-risk/
│   │   │   └── syslog-anomaly/
│   │   └── morpheus_pipelines/
│   │       └── detection_pipeline.yaml
│   ├── evaluation/
│   │   ├── metrics.py
│   │   └── adversarial_tests.py
│   └── registry/
│       └── model_versions.json
│
├── agents/                        # LLM reasoning
│   ├── __init__.py
│   ├── graph.py                   # LangGraph workflow
│   ├── state.py                   # Agent state schema
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── triage.py              # Fast Y/N decision
│   │   ├── investigate.py         # Evidence gathering
│   │   ├── threat_intel.py        # IOC/reputation
│   │   └── report.py              # Generate report
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── splunk_query.py
│   │   ├── ise_lookup.py
│   │   ├── asset_lookup.py
│   │   ├── threat_intel.py
│   │   ├── baseline_query.py
│   │   ├── mitre_mapper.py
│   │   └── ticket_create.py
│   └── security/
│       ├── __init__.py
│       ├── prompt_templates/
│       │   ├── triage.txt
│       │   ├── investigate.txt
│       │   └── report.txt
│       ├── output_validator.py
│       ├── guardian.py            # Watches primary agents
│       └── audit.py               # Immutable logging
│
├── ui/                            # User interfaces
│   ├── chat/
│   │   └── app.py                 # Gradio/Streamlit
│   └── splunk_dashboards/
│       ├── gpu_health.xml
│       ├── detections.xml
│       ├── investigations.xml
│       └── ai_health.xml
│
├── scripts/                       # Utility scripts
│   ├── data/
│   │   ├── export_training_data.py
│   │   └── label_flows.py
│   └── benchmark/
│       ├── nccl_benchmark.sh
│       └── inference_benchmark.py
│
└── tests/                         # Test suite
    ├── unit/
    ├── integration/
    └── adversarial/
        ├── test_prompt_injection.py
        └── test_model_evasion.py
```

---

## Implementation Phases

### Phase 0: Foundation ✅
- [x] Hardware setup (2x T4, UCS servers)
- [x] NetFlow collection (GoFlow2 → Kafka)
- [x] Morpheus/Triton deployment
- [x] Splunk integration
- [x] RDMA networking (ConnectX-4 LX 25GbE installed, RoCE verified)

### Phase 1: Data Layer ✅
- [x] GoFlow2 running
- [x] Kafka retention configured
- [x] ISE syslog parsing (SASP-003)
- [x] Generic syslog parsing (SASP-003)
- [x] Training data export (SASP-006)
- [x] Kafka detection bridge (SASP-005)

### Phase 2: Input Sanitization ✅
- [x] Injection pattern library — 21 patterns, 5 categories (SASP-007)
- [x] Base sanitizer class (SASP-004)
- [x] Data source sanitizers — NetFlow, Syslog, ISE (SASP-007)
- [x] Unit tests with adversarial examples (SASP-009)
- [x] Kafka integration — sanitizer service (SASP-008)

### Phase 3: Detection Models ✅
- [x] Feature engineering — 15-feature extractor (SASP-010)
- [x] Train netflow-autoencoder — symmetric AE with thresholds (SASP-011)
- [x] Train auth-classifier — 3-class feedforward (SASP-012)
- [x] Export to ONNX (SASP-011, SASP-012)
- [x] Triton deployment configs (SASP-013)
- [x] Morpheus pipeline YAMLs (SASP-013)
- [x] Adversarial model testing (SASP-014)

### Phase 4: LLM Agents ✅
- [x] LangGraph workflow (SASP-020)
- [x] Tool implementations — 6 tools (SASP-016)
- [x] Hardened prompts — 4 templates with guardrails (SASP-017)
- [x] Output validator (SASP-019)
- [x] Guardian agent — 5 validation checks (SASP-018)
- [x] Audit logging — HMAC-signed JSONL (SASP-019)
- [x] Human approval queue (SASP-020)

### Phase 5: Presentation ✅
- [x] Splunk dashboards — 4 dashboards + deploy script (SASP-023)
- [x] Chat interface — Gradio Blocks UI (SASP-024)
- [x] Documentation (SASP-026)

### Phase 6: Testing ✅
- [x] Agent integration tests (SASP-021)
- [x] Adversarial agent tests (SASP-022)
- [x] CI smoke tests + Makefile (SASP-025)

---

## Hardware Allocation

| Hardware | Role | Workload |
|----------|------|----------|
| **S1 (C220 M5)** | Inference | Triton (netflow-anomaly + auth-risk on T4 GPU), Morpheus pipeline (CPU mode) |
| **S2 (C240 M5)** | Collection | Kafka, GoFlow2, syslog-ng |
| **Workstation (RTX 5080)** | Kafka Bridge | Consumes morpheus-detections, runs LangGraph investigations, posts to Splunk |
| **Mac Studio (M3 Ultra)** | LLM + Sanitizer | All 4 agents via Nemotron-3-Nano (LM Studio :1234), Sanitizer service (:9095) |

---

## Key Differentiators

### 1. Security of AI Systems
Not just using AI for security - securing the AI itself:
- Input sanitization against prompt injection
- Output validation
- Guardian agent watching primary agents
- Immutable audit trail

### 2. Air-Gap Capable
- 100% on-premises
- No cloud dependencies
- Federal/classified environment ready

### 3. Multi-GPU Architecture
- Distributed training across T4s
- RDMA for efficient gradient sync
- Heterogeneous inference (T4 + consumer GPUs + Apple Silicon)

### 4. End-to-End Pipeline
- Raw data → Detection → Investigation → Report
- Automated with human-in-the-loop for critical decisions

---

## Getting Started

```bash
# Clone
git clone https://github.com/yourusername/sasp.git
cd sasp

# Server 2: Start data collection
cd infrastructure/docker
docker-compose -f docker-compose.s2.yml up -d

# Server 1: Start inference
docker-compose -f docker-compose.s1.yml up -d

# Verify
./scripts/health_check.sh
```

---

## Related Documentation

- [DCAI Study Guide](../docs/DCAI_STUDY_GUIDE.md)
- [Lab Configurations](../docs/DCAI_LAB_CONFIGS.md)
- [Project Walkthrough](../docs/DCAI_PROJECT_WALKTHROUGH.md)

---

*Version: 0.2.0 | Status: Operational — Full E2E pipeline live (2026-03-02)*
