# Domain 1: AI Fundamentals and Applications (20%)

> **All objectives use "DESCRIBE"** - This is theory/knowledge-based.
> Study the concepts; no hands-on evidence required.

---

## Objectives

| Objective | Topic | Verb | Evidence |
|-----------|-------|------|----------|
| 1.1 | AI/ML workload types | DESCRIBE | 📝 Study Guide |
| 1.2 | AI lifecycle | DESCRIBE | 📝 Study Guide |
| 1.3 | AI use cases | DESCRIBE | 📝 Study Guide |
| 1.4 | Types of AI infrastructure | DESCRIBE | 📝 Study Guide |
| 1.5 | Components for AI environments | DESCRIBE | 📝 Study Guide |
| 1.6 | Cisco AI solutions | DESCRIBE | 📝 Study Guide |

---

## 1.1 AI/ML Workload Types

### 1.1.a RAG (Retrieval-Augmented Generation)
- Combines retrieval with generation
- Grounds LLM responses in real data
- **SASP Use:** Threat intel lookup in agents

### 1.1.b Training
- Teaching models to recognize patterns
- Most compute-intensive workload
- Requires: High GPU memory, low-latency interconnect, NCCL
- **SASP Use:** Distributed autoencoder training across 2x T4

### 1.1.c Inference
- Using trained models for predictions
- Lower latency, higher throughput than training
- **SASP Use:** Triton serving models at 10k+ inf/sec

### 1.1.d Generative AI
- Creates new content (text, images, code)
- **SASP Use:** LLM agents for investigation and reporting

---

## 1.2 AI Lifecycle

```
Data Collection → Training → Deployment → Monitoring → Retraining
      │              │            │            │            │
   GoFlow2       PyTorch       Triton      Splunk      Scheduled
   Kafka         NCCL         Morpheus    Dashboards    Jobs
```

---

## 1.3 AI Use Cases

| Use Case | Technique | SASP Implementation |
|----------|-----------|---------------------|
| Network Anomaly Detection | Autoencoder | netflow-anomaly model |
| Crypto Mining Detection | XGBoost | abp-nvsmi-xgb |
| User Behavior Analytics | Digital Fingerprinting | Planned |
| Auth Risk Scoring | Gradient Boosting | Planned |
| Incident Investigation | LLM Agents | Planned |

---

## 1.4 Types of AI Infrastructure

| Type | Characteristics | SASP |
|------|-----------------|------|
| **Cloud** | Elastic, pay-per-use, managed | ❌ Not used |
| **Hybrid** | Training cloud, inference on-prem | ❌ Not used |
| **On-Premises** | Full control, air-gap capable | ✅ **This is us** |
| **Edge AI** | Low latency, limited compute | Future consideration |

---

## 1.5 Components for AI Environments

### 1.5.a Network
- High bandwidth for gradient sync
- Low latency for training efficiency
- **SASP:** 25GbE ConnectX-4 LX, RoCEv2

### 1.5.b Compute and GPUs (NVLink)
- GPU selection based on workload
- Interconnect: PCIe, NVLink, RoCE
- **SASP:** Tesla T4 (16GB, 70W, PCIe 3.0)

### 1.5.c Virtualization and Containerization
- Docker, Kubernetes
- GPU passthrough
- **SASP:** Docker with NVIDIA runtime

### 1.5.d Orchestration
- docker-compose, Kubernetes, Slurm
- **SASP:** docker-compose per server, Kafka for integration

### 1.5.e Monitoring
- GPU metrics, model metrics, infrastructure
- **SASP:** nvidia-smi → Splunk

### 1.5.f Storage
- NVMe for hot data, SAN for capacity
- **SASP:** Local NVMe + SATA

---

## 1.6 Cisco AI Solutions

### 1.6.a AI PODs
- Pre-validated turnkey AI infrastructure
- UCS compute + Nexus networking + NVIDIA GPUs + Storage
- **Resource:** [Cisco AI POD for Enterprise Training and Fine-Tuning Design Guide](https://www.cisco.com/c/en/us/solutions/data-center/ai-ml-solutions.html)

### 1.6.b AI Canvas
- More than a design tool — platform for **AgenticOps**
- Uses "Deep Network Model" for generative troubleshooting
- Predictive capacity planning, automated remediation
- **Resource:** [Cisco AI Canvas: AgenticOps for Networking](https://www.cisco.com/c/en/us/solutions/ai-canvas.html)

### 1.6.c Hyperfabric AI
- AI-optimized network fabric with Meraki-like SaaS management
- Automated RoCE/PFC/ECN configuration
- GPU topology-aware routing
- Zero-touch provisioning
- **Resource:** [Cisco Nexus Hyperfabric AI Solution Overview](https://www.cisco.com/c/en/us/products/switches/nexus-hyperfabric.html)

---

## Study Resources

- [DCAI Study Guide - Domain 1](../docs/DCAI_STUDY_GUIDE.md#domain-10-ai-fundamentals-and-applications-20)
- [Cisco Data Center AI Training Video](https://www.cisco.com/c/en/us/solutions/data-center/ai-ml-solutions.html) — Deep dive into AI Canvas and AgenticOps
- Cisco AI Infrastructure documentation
- NVIDIA Morpheus documentation

---

## Folder Contents

```
1.1_AI_ML_Workload_Types/
1.2_AI_Lifecycle/
1.3_AI_Use_Cases/
1.4_Types_of_AI_Infrastructure/
1.5_AI_Environment_Components/
    ├── 1.5a_Network/
    ├── 1.5b_Compute_GPUs_NVLink/
    ├── 1.5c_Virtualization_Containerization/
    ├── 1.5d_Orchestration/
    ├── 1.5e_Monitoring/
    └── 1.5f_Storage/
1.6_Cisco_AI_Solutions/
```

*Add screenshots, configs, or notes to relevant folders as you study.*
