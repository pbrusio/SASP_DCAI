# Cisco DCAI (300-640) Study Guide

> **Learn AI Infrastructure through SASP** - A GPU-accelerated security analytics platform
> 
> This guide maps DCAI exam objectives to practical implementation on real hardware.
> Real configs, real screenshots, real understanding.

---

## Exam Overview

| Domain | Weight | Readiness | Key Gaps |
|--------|--------|-----------|----------|
| 1.0 AI Fundamentals and Applications | 20% | **Strong** | None — theory well covered |
| 2.0 AI Infrastructure Components and Architecture | 30% | **Good** | Need `fio`/`iperf` benchmarks (2.1, 2.3) |
| 3.0 AI Infrastructure Deployment and Data Management | 30% | **Moderate** | Fabric layer gap — 3.3 Orchestration (ND/APIC/Intersight) |
| 4.0 AI Infrastructure Operations and Troubleshooting | 20% | **Emerging** | Need 4.4 troubleshooting scenarios (PFC storm, NCCL timeout) |

### v1.0 Exam Topics Cross-Reference

> The 300-640 DCAI v1.0 exam topics have been restructured. This study guide's body sections use an earlier numbering. Use this table to locate content by v1.0 objective.

| v1.0 Objective | Description | Study Guide Section(s) | Notes |
|----------------|-------------|----------------------|-------|
| **1.1** | AI/ML workload types (a-g) | §1.1 Workload Types + §1.3 Use Cases | Expanded — now includes GenAI, agentic AI, traditional AI/ML |
| **1.2** | Benchmark/profiling concepts (a-d) | §4.1 Benchmarks | **New objective** — synthetic vs. real-world benchmarks/workloads |
| **1.3** | AI interaction with infrastructure (a-e) | §1.6.b AI Canvas (partial) | **New objective** — NL interfaces, MCP, API interaction, CLI gen, workflow automation |
| **1.4** | Infrastructure architecture (a-e) | §1.4 Types of AI Infrastructure | Refocused — edge/centralized inferencing, public/hybrid/on-prem |
| **1.5** | Lifecycle stages (a-c) | §1.2 AI Lifecycle | Refocused to Day 0 / Day 1 / Day 2 |
| **2.1** | Design requirements (a-e) | §2.1-2.5 Evaluate sections | Consolidated — network, compute, storage, power/cooling, hybrid |
| **2.2** | Integrations (a-d) | §1.6 Cisco Solutions + §3.3 Orchestration | AI Canvas, Nexus Dashboard, Hyperfabric AI, Intersight |
| **2.3** | Security architecture (a-e) | §2.5 Hybrid (partial) | **New objective** — workload security, data protection, segmentation, IAM, logging |
| **3.1** | Configure components (a-f) | §3.2 UCS + §3.3 Orchestration | Network/storage connectivity, UCS profiles, firmware, rack discovery |
| **3.2** | System policies (a-f) | §3.1 High-Perf Networks | NTP, system QoS, LLFC, PFC, vNIC, storage policies |
| **4.1** | Benchmarking/profiling tools (a-e) | §4.1 Benchmarks | Packet analysis, infrastructure, GPU, CPU, workload tools |
| **4.2** | Monitor/maintain (a-f) | §4.2-4.3 Monitoring + System Health | Expanded — adds timing protocols, temperature, load distribution |
| **4.3** | Troubleshoot (a-e) | §4.4 Troubleshooting | Network, storage, compute, integration, AI workload application |

## Lab Environment

| Component | Specs | Role |
|-----------|-------|------|
| **Server 1 (C220 M5)** | Xeon, 512GB RAM, Tesla T4 16GB | GPU Inference |
| **Server 2 (C240 M5)** | Xeon, 512GB RAM, Tesla T4 16GB | Data Collection + Training |
| **Network** | ConnectX-4 LX 25GbE (RDMA) | GPU-to-GPU communication |
| **Workstation** | RTX 5080 16GB | LLM Reasoning |
| **Mac Studio** | M3 Ultra 96GB | Heavy LLM workloads |

---

# Domain 1.0: AI Fundamentals and Applications (20%)

## 1.1 Describe AI/ML Workload Types

### 1.1.a RAG (Retrieval-Augmented Generation)

**The Concept:**

RAG combines retrieval (searching a knowledge base) with generation (LLM response). This grounds AI responses in real data.

```
┌─────────────────────────────────────────────────────────────────┐
│                         RAG WORKFLOW                            │
│                                                                 │
│  User Query: "Is this IP malicious?"                           │
│        │                                                        │
│        ▼                                                        │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Embed      │───►│  Vector DB   │───►│   Retrieve   │      │
│  │   Query      │    │   Search     │    │   Context    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                 │               │
│                                                 ▼               │
│                                          ┌──────────────┐      │
│                                          │  LLM + Context│      │
│                                          │  = Grounded   │      │
│                                          │    Response   │      │
│                                          └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

**SASP Implementation:**

Our threat intel agent uses RAG to look up IOCs:
- Embed the suspicious IP/domain
- Search threat intel vector database
- Inject relevant threat context into LLM prompt
- Generate informed analysis

---

### 1.1.b Training

**The Concept:**

Training is the process of teaching a model to recognize patterns in data. For AI infrastructure, this is the most compute-intensive workload.

**Training Characteristics:**

| Aspect | Training Workload |
|--------|-------------------|
| GPU Memory | High (model + gradients + optimizer state) |
| GPU Compute | Very High (forward + backward pass) |
| Network I/O | High (gradient synchronization in distributed) |
| Storage I/O | High (dataset loading) |
| Duration | Hours to weeks |

**SASP Implementation:**

We train a NetFlow anomaly detection autoencoder across 2x Tesla T4 GPUs:

```bash
# Distributed training command
torchrun --nproc_per_node=1 --nnodes=2 \
  --node_rank=0 --master_addr=<S1_IP> --master_port=29500 \
  train_autoencoder.py --data /data/training/netflow.jsonl
```

**Key Infrastructure Requirements:**
- High GPU memory bandwidth
- Low-latency GPU interconnect (RDMA preferred)
- Fast storage for dataset access
- NCCL for gradient synchronization

---

### 1.1.c Inference

**The Concept:**

Inference is using a trained model to make predictions on new data. This is typically lower latency but higher throughput than training.

**Inference Characteristics:**

| Aspect | Inference Workload |
|--------|-------------------|
| GPU Memory | Lower (model weights only) |
| GPU Compute | Moderate (forward pass only) |
| Network I/O | Low (no gradient sync) |
| Latency | Critical (real-time requirements) |
| Throughput | High (batch processing) |

**SASP Implementation:**

Triton Inference Server hosts our models for real-time detection:

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRITON INFERENCE SERVER                      │
│                                                                 │
│  Model Repository:                                              │
│  ├── netflow-autoencoder/    (anomaly detection)               │
│  ├── auth-classifier/        (auth risk scoring)               │
│  ├── syslog-anomaly/         (log analysis)                    │
│  └── abp-nvsmi-xgb/          (crypto mining detection)        │
│                                                                 │
│  Throughput: 10,000+ inferences/second per T4                  │
│  Latency: <10ms per batch                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Actual Performance (from our lab):**

```
Inference Rate: 9,727 inf/sec
GPU Utilization: 45%
Memory Used: 2.1GB / 16GB
```

---

### 1.1.d Generative AI

**The Concept:**

Generative AI creates new content - text, images, code. In security contexts, this enables natural language investigation and report generation.

**SASP Implementation:**

Our LLM agents (running on RTX 5080 and Mac Studio) provide:
- Natural language incident reports
- Investigation reasoning
- ATT&CK mapping explanations
- Executive summaries

```
┌─────────────────────────────────────────────────────────────────┐
│                    GENERATIVE AI IN SASP                        │
│                                                                 │
│  Detection: "Anomaly score 0.94 on flow from 10.1.50.25"       │
│        │                                                        │
│        ▼                                                        │
│  LLM Agent generates:                                           │
│                                                                 │
│  "At 03:47 UTC, the NetFlow anomaly model detected unusual     │
│   traffic from host 10.1.50.25 (jsmith-workstation). The       │
│   traffic pattern matches lateral movement indicators:          │
│   - Connections to 47 unique internal hosts (baseline: 3)      │
│   - SMB traffic to finance servers (first occurrence)          │
│   - Activity outside normal working hours                       │
│                                                                 │
│   ATT&CK Mapping: T1021.002 (SMB/Windows Admin Shares)         │
│                                                                 │
│   Recommended Actions:                                          │
│   1. Isolate host pending investigation                        │
│   2. Review authentication logs for jsmith                     │
│   3. Check for credential exposure"                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1.2 Describe the AI Lifecycle

**The AI Lifecycle:**

```
┌─────────────────────────────────────────────────────────────────┐
│                       AI LIFECYCLE                              │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │  Data    │──►│  Train   │──►│  Deploy  │──►│  Monitor │    │
│  │Collection│   │  Model   │   │  Model   │   │  & Ops   │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│       │                                              │         │
│       │              ┌──────────┐                    │         │
│       └──────────────│  Retrain │◄───────────────────┘         │
│                      │  (Loop)  │                              │
│                      └──────────┘                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**SASP Implementation Across Lifecycle:**

| Phase | Component | Implementation |
|-------|-----------|----------------|
| **Data Collection** | GoFlow2, Syslog | NetFlow from IOS-XE, ISE auth logs |
| **Data Storage** | Kafka | 30-day retention, 50GB limit |
| **Data Preparation** | Python/cuDF | Feature extraction, normalization |
| **Training** | PyTorch + NCCL | Distributed across 2x T4 |
| **Deployment** | Triton | Model repository, versioning |
| **Inference** | Morpheus | Real-time pipeline processing |
| **Monitoring** | Splunk | Dashboards, alerts, drift detection |
| **Retraining** | Scheduled jobs | Incorporate new labeled data |

---

## 1.3 Describe AI Use Cases

**Security-Focused AI Use Cases in SASP:**

| Use Case | AI Technique | Business Value |
|----------|--------------|----------------|
| **Network Anomaly Detection** | Autoencoder | Detect unknown attacks |
| **Crypto Mining Detection** | XGBoost classifier | Protect compute resources |
| **User Behavior Analytics** | Digital Fingerprinting | Insider threat detection |
| **Auth Risk Scoring** | Gradient boosting | Prioritize investigation |
| **Incident Investigation** | LLM agents | Reduce analyst workload |
| **Threat Intelligence** | RAG | Contextualize alerts |

---

## 1.4 Describe the Types of AI Infrastructure

### 1.4.a Cloud

**Characteristics:**
- Elastic scaling
- Pay-per-use
- Managed services
- Internet connectivity required

**When to Use:**
- Variable workloads
- Rapid experimentation
- Limited capital budget

### 1.4.b Hybrid

**Characteristics:**
- Training in cloud, inference on-prem
- Sensitive data stays local
- Burst capacity to cloud

**When to Use:**
- Data sovereignty requirements
- Predictable baseline + variable peaks

### 1.4.c On-Premises

**Characteristics:**
- Full control
- Predictable costs
- No data egress
- Capital investment

**When to Use:**
- Air-gapped environments
- Regulatory requirements
- Consistent high utilization

**SASP Implementation:**

Our platform is **100% on-premises** because:
- Federal/air-gap capability required
- Sensitive security data cannot leave network
- Predictable performance requirements
- No per-inference costs

### 1.4.d Edge AI

**Characteristics:**
- Processing at data source
- Low latency
- Limited compute
- Intermittent connectivity

**SASP Edge Consideration:**

Future: Deploy lightweight models on network devices for real-time detection at the edge, with full analysis on central infrastructure.

---

## 1.5 Describe Components for AI Environments

### 1.5.a Network

**Critical for AI Workloads:**

| Requirement | Why It Matters | SASP Implementation |
|-------------|----------------|---------------------|
| **Bandwidth** | Gradient sync, data movement | 25GbE ConnectX-4 |
| **Latency** | Training iteration time | RDMA/RoCEv2 |
| **Lossless** | GPU memory is limited | PFC, ECN |

**SASP Network Architecture:**

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  ┌─────────────────┐           ┌─────────────────┐             │
│  │   Server 1      │           │   Server 2      │             │
│  │   (C220 M5)     │           │   (C240 M5)     │             │
│  │                 │           │                 │             │
│  │   ┌─────────┐   │           │   ┌─────────┐   │             │
│  │   │  T4 GPU │   │           │   │  T4 GPU │   │             │
│  │   └────┬────┘   │           │   └────┬────┘   │             │
│  │        │ PCIe   │           │        │ PCIe   │             │
│  │   ┌────┴────┐   │           │   ┌────┴────┐   │             │
│  │   │ConnectX │   │◄──RDMA───►│   │ConnectX │   │             │
│  │   │  4 LX   │   │  25GbE    │   │  4 LX   │   │             │
│  │   └─────────┘   │           │   └─────────┘   │             │
│  └─────────────────┘           └─────────────────┘             │
│                                                                 │
│  NCCL Performance:                                              │
│  - TCP: 3.4 GB/s                                               │
│  - RDMA: ~12 GB/s (expected with RoCE)                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### 1.5.b Compute and GPUs Deployment (NVLink)

**GPU Interconnect Technologies:**

| Technology | Bandwidth | Use Case |
|------------|-----------|----------|
| **PCIe 4.0 x16** | 32 GB/s | GPU to CPU |
| **PCIe 5.0 x16** | 64 GB/s | GPU to CPU (newer) |
| **NVLink 3.0** | 600 GB/s | GPU to GPU (same node) |
| **NVLink 4.0** | 900 GB/s | GPU to GPU (H100) |
| **InfiniBand HDR** | 200 Gb/s | GPU to GPU (multi-node) |
| **RoCEv2** | 25-100 Gb/s | GPU to GPU (Ethernet) |

**SASP Compute:**

| Server | GPU | Memory | Interconnect |
|--------|-----|--------|--------------|
| C220 M5 | Tesla T4 | 16GB GDDR6 | PCIe 3.0 x16 |
| C240 M5 | Tesla T4 | 16GB GDDR6 | PCIe 3.0 x16 |

*Note: T4 doesn't have NVLink. Multi-GPU communication uses NCCL over network.*

**Tesla T4 Specifications:**

```
GPU Architecture: Turing
CUDA Cores: 2560
Tensor Cores: 320
Memory: 16GB GDDR6
Memory Bandwidth: 320 GB/s
TDP: 70W
Form Factor: Single-slot, passive cooling
```

---

### 1.5.c Virtualization and Containerization

**Container Benefits for AI:**

- Reproducible environments
- Dependency isolation
- Easy scaling
- Version control

**SASP Containerization:**

```yaml
# docker-compose.yml (Server 2)
services:
  kafka:
    image: confluentinc/cp-kafka:7.5.0
    
  goflow2:
    image: netsampler/goflow2:latest
    ports:
      - "2055:2055/udp"
    
  morpheus:
    image: nvcr.io/nvidia/morpheus/morpheus:24.10
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
```

**GPU Passthrough Options:**

| Method | Isolation | Use Case |
|--------|-----------|----------|
| **Full passthrough** | Complete | Single workload per GPU |
| **vGPU (NVIDIA GRID)** | Partial | Multi-tenant |
| **MIG (A100/H100)** | Hardware | Guaranteed resources |
| **MPS** | None | Shared access |

*SASP uses full passthrough - each T4 dedicated to its server.*

---

### 1.5.d Orchestration

**Orchestration Options:**

| Tool | Scope | SASP Usage |
|------|-------|------------|
| **docker-compose** | Single node | Current deployment |
| **Kubernetes** | Multi-node | Future consideration |
| **Slurm** | HPC clusters | Not used |
| **Ray** | Distributed Python | Potential for training |

**SASP Orchestration:**

Currently using docker-compose for simplicity. Each server runs independently with Kafka as the integration point.

```
┌─────────────────┐         ┌─────────────────┐
│    Server 1     │         │    Server 2     │
│  docker-compose │◄─Kafka─►│  docker-compose │
│                 │         │                 │
│  - Triton       │         │  - Kafka        │
│  - Morpheus     │         │  - GoFlow2      │
│                 │         │  - Zookeeper    │
└─────────────────┘         └─────────────────┘
```

---

### 1.5.e Monitoring

**AI Infrastructure Monitoring:**

| Layer | Metrics | Tool |
|-------|---------|------|
| **GPU** | Utilization, memory, temp, power | nvidia-smi, DCGM |
| **Model** | Latency, throughput, accuracy | Triton metrics |
| **Pipeline** | Events/sec, backpressure | Morpheus metrics |
| **Infrastructure** | CPU, memory, network | Prometheus, Splunk |

**SASP Monitoring Stack:**

```
┌─────────────────────────────────────────────────────────────────┐
│                      MONITORING ARCHITECTURE                    │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │ nvidia-smi  │    │   Triton    │    │  Morpheus   │        │
│  │  telemetry  │    │   metrics   │    │   metrics   │        │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘        │
│         │                  │                  │                │
│         └──────────────────┼──────────────────┘                │
│                            │                                   │
│                            ▼                                   │
│                     ┌─────────────┐                            │
│                     │   SPLUNK    │                            │
│                     │             │                            │
│                     │ Dashboards: │                            │
│                     │ - GPU Health│                            │
│                     │ - Detection │                            │
│                     │ - Throughput│                            │
│                     └─────────────┘                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### 1.5.f Storage (SAN, Fibre Channel, NVMe, Block and File)

**Storage Considerations for AI:**

| Workload | Storage Need | IOPS | Throughput |
|----------|--------------|------|------------|
| **Training data** | High capacity, sequential read | Moderate | High |
| **Checkpoints** | Fast write, moderate capacity | High | High |
| **Model repository** | Low latency, moderate capacity | Moderate | Moderate |
| **Inference cache** | Very low latency | Very High | Moderate |

**Storage Technologies:**

| Technology | Latency | Use Case |
|------------|---------|----------|
| **NVMe SSD** | <100μs | Hot data, model loading |
| **SAS SSD** | ~200μs | Warm data, datasets |
| **NVMe-oF** | Network + NVMe | Shared fast storage |
| **Fibre Channel** | ~500μs | Enterprise SAN |
| **NFS** | ~1ms+ | Shared datasets |

**SASP Storage:**

| Server | Storage | Mount | Purpose |
|--------|---------|-------|---------|
| S1 | Local NVMe | /mnt/storage1 | Morpheus workspace |
| S2 | Local SATA | /data | Kafka, training data |

---

## 1.6 Describe Cisco AI Solutions

> **Resource:** [Cisco Data Center AI Training Video](https://www.cisco.com/c/en/us/solutions/data-center/ai-ml-solutions.html) — Deep dive into AI Canvas and AgenticOps (covers Domain 1.6 and 4.3 theory gaps).

### 1.6.a AI PODs

> **Resource:** [Cisco AI POD for Enterprise Training and Fine-Tuning Design Guide](https://www.cisco.com/c/en/us/solutions/data-center/ai-ml-solutions.html)

**What It Is:**

Pre-validated, turnkey AI infrastructure combining:
- Cisco UCS compute (X-Series or C-Series)
- Cisco Nexus networking (9000 series)
- NVIDIA GPUs (A100, H100, L40S)
- Storage partners (NetApp, Pure Storage, etc.)
- Validated designs with tested configurations

**Key Architecture Points (exam-relevant):**

```
┌─────────────────────────────────────────────────────────────────┐
│                       CISCO AI POD                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Compute: UCS X-Series / C-Series                        │   │
│  │  - GPU nodes: H100/A100 per server                       │   │
│  │  - CPU nodes: for data preprocessing                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Network: Nexus 9000 Leaf-Spine                          │   │
│  │  - RoCEv2 / InfiniBand                                   │   │
│  │  - Lossless Ethernet (PFC + ECN)                         │   │
│  │  - 100/400GbE uplinks                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Storage: Pure Storage / NetApp                          │   │
│  │  - NVMe-oF for high-speed data access                    │   │
│  │  - Tiered: hot (NVMe) → warm (SAS) → cold (object)      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Management: Intersight + Nexus Dashboard                │   │
│  │  - Centralized lifecycle management                      │   │
│  │  - GPU telemetry correlation                             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Relevance to SASP:**

Our lab is essentially a mini AI POD — UCS servers with T4 GPUs, connected via high-speed networking. Understanding the full POD architecture shows how our lab scales to enterprise.

### 1.6.b AI Canvas

> **Resource:** [Cisco AI Canvas: AgenticOps for Networking](https://www.cisco.com/c/en/us/solutions/ai-canvas.html)

**What It Is:**

Cisco AI Canvas is more than a reference architecture tool — it is Cisco's platform for **AgenticOps**, which uses a "Deep Network Model" to provide:
- **Generative troubleshooting** — AI-driven root cause analysis
- **Predictive capacity planning** — forecast infrastructure needs
- **Automated remediation** — self-healing network configurations
- **Natural language queries** — ask questions about network state

**Key Concept — Deep Network Model:**

The Deep Network Model is a digital twin of the entire network that enables:
1. "What-if" analysis for configuration changes
2. Anomaly detection across the fabric
3. Compliance verification against best practices

**Exam Relevance:**

Understand how AI Canvas utilizes the Deep Network Model for generative troubleshooting — this connects to Domain 4.3 (system messages and management).

### 1.6.c Hyperfabric AI

> **Resource:** [Cisco Nexus Hyperfabric AI Solution Overview](https://www.cisco.com/c/en/us/products/switches/nexus-hyperfabric.html)

**What It Is:**

Cisco's next-generation AI-optimized network fabric with a **Meraki-like SaaS management model** for AI clusters:
- **Cloud-managed** — simplified operations via SaaS dashboard
- **AI workload-aware** — automatic optimization for training/inference traffic
- **Zero-touch provisioning** — automated fabric deployment
- **Built-in RoCE optimization** — automatic PFC/ECN/QoS tuning

**Key Differentiators:**

| Feature | Traditional Nexus | Hyperfabric AI |
|---------|-------------------|----------------|
| Management | CLI / Nexus Dashboard | SaaS (Meraki-like) |
| RoCE Config | Manual PFC/ECN/QoS | Automated |
| GPU Awareness | None (network only) | GPU topology-aware routing |
| Provisioning | Manual | Zero-touch |
| Telemetry | Streaming telemetry | AI-correlated insights |

**Exam Relevance:**

Know the value proposition: Hyperfabric AI simplifies Day-0/Day-1/Day-2 operations for AI clusters by automating the lossless Ethernet configuration that is otherwise manual on standard Nexus.

---

# Domain 2.0: AI Infrastructure Components and Architecture (30%)

## 2.1 Evaluate Network Deployment Based on AI Workload Requirements

### Bandwidth Requirements

**Distributed Training Bandwidth:**

For gradient synchronization, bandwidth determines training iteration time.

| Factor | Impact |
|--------|--------|
| Model size | Larger model = more gradients to sync |
| Batch size | Larger batch = less frequent sync |
| # of nodes | More nodes = more all-reduce traffic |

**Calculation Example:**

```
Model: 100M parameters (400MB at FP32)
Gradient size: 400MB per iteration
Sync frequency: Every batch
Nodes: 2

Required bandwidth for <10% overhead:
400MB / 0.1s = 4 GB/s minimum
```

**SASP Measurement:**

```bash
# NCCL all-reduce benchmark
$ all_reduce_perf -b 8 -e 1G -f 2 -g 1

# Results (TCP):
# Size      Bandwidth
# 1GB       3.4 GB/s
```

### Latency Requirements

**Training Latency:**

| Component | Typical Latency |
|-----------|-----------------|
| GPU compute | 1-100ms |
| PCIe transfer | <1ms |
| Network (TCP) | 50-200μs |
| Network (RDMA) | 1-5μs |

**Inference Latency:**

Real-time detection requires end-to-end latency < 100ms:

```
Data in → Preprocess → Inference → Postprocess → Alert
         ↓           ↓            ↓
        10ms        5ms          5ms         = 20ms total
```

### Redundancy and Scalability

**Network Redundancy Patterns:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    DUAL-HOMED DESIGN                            │
│                                                                 │
│         ┌────────────────────────────────┐                     │
│         │         Spine Layer            │                     │
│         │    ┌─────────┐  ┌─────────┐   │                     │
│         │    │ Spine 1 │  │ Spine 2 │   │                     │
│         │    └────┬────┘  └────┬────┘   │                     │
│         │         │            │         │                     │
│         └─────────┼────────────┼─────────┘                     │
│                   │            │                               │
│         ┌─────────┼────────────┼─────────┐                     │
│         │         │    Leaf    │         │                     │
│         │    ┌────┴────┐  ┌────┴────┐   │                     │
│         │    │ Leaf 1  │  │ Leaf 2  │   │                     │
│         │    └────┬────┘  └────┬────┘   │                     │
│         └─────────┼────────────┼─────────┘                     │
│                   │            │                               │
│              ┌────┴────────────┴────┐                          │
│              │      GPU Server      │                          │
│              │   (Dual 25GbE NICs)  │                          │
│              └──────────────────────┘                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2.2 Evaluate Compute Deployment Based on AI Workload Requirements

### GPU Selection Criteria

| Factor | Training | Inference |
|--------|----------|-----------|
| **Memory** | Critical (model + gradients) | Important (model + batch) |
| **Compute (TFLOPS)** | Critical | Important |
| **Tensor Cores** | Critical | Important |
| **Power** | Less critical | Critical (density) |
| **Cost** | High-end justified | Cost-sensitive |

**NVIDIA GPU Comparison:**

| GPU | Memory | FP32 TFLOPS | TDP | Use Case |
|-----|--------|-------------|-----|----------|
| T4 | 16GB | 8.1 | 70W | Inference |
| A10 | 24GB | 31.2 | 150W | Training/Inference |
| A100 | 40/80GB | 19.5 | 400W | Training |
| H100 | 80GB | 67 | 700W | Large-scale training |

**SASP GPU Choice (Tesla T4):**

- ✅ 16GB sufficient for security models
- ✅ 70W TDP fits UCS cooling
- ✅ Inference-optimized (INT8 tensor cores)
- ✅ Cost-effective for lab
- ⚠️ Limited for large model training

### Virtualization Support

**GPU Virtualization Options:**

| Option | Technology | Isolation | Overhead |
|--------|------------|-----------|----------|
| Bare metal | N/A | None | None |
| Passthrough | VFIO | Full | Minimal |
| vGPU | NVIDIA GRID | Partial | 5-10% |
| MIG | A100/H100 | Hardware | Minimal |

**SASP Deployment:**

Using bare metal Docker with GPU passthrough:

```yaml
# docker-compose.yml
services:
  morpheus:
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
```

---

## 2.3 Evaluate Storage Deployment Based on AI Workload Requirements

### Storage Performance Requirements

**Training Data Access Patterns:**

| Pattern | Characteristic | Storage Need |
|---------|---------------|--------------|
| **Sequential read** | Large dataset streaming | High throughput |
| **Random read** | Data augmentation | High IOPS |
| **Checkpoint write** | Periodic model save | Burst write |

**SASP Storage Configuration:**

```bash
# Check storage performance
$ fio --name=randread --rw=randread --bs=4k --size=1G --numjobs=4

# Results:
# IOPS: 45,000
# Bandwidth: 180 MB/s
```

### Capacity Planning

**Storage Sizing for SASP:**

| Data Type | Retention | Daily Volume | Total |
|-----------|-----------|--------------|-------|
| NetFlow (Kafka) | 30 days | 600 MB | 18 GB |
| Training datasets | Permanent | - | 50 GB |
| Model checkpoints | 5 versions | 500 MB | 2.5 GB |
| Splunk indexes | 90 days | 1 GB | 90 GB |

---

## 2.4 Evaluate Power, Efficiency, and Sustainability

### Power Consumption

**SASP Power Budget:**

| Component | Power (W) |
|-----------|-----------|
| C220 M5 (base) | 300 |
| T4 GPU | 70 |
| C240 M5 (base) | 400 |
| T4 GPU | 70 |
| **Total** | **840W** |

**GPU Power Monitoring:**

```bash
$ nvidia-smi --query-gpu=power.draw --format=csv
power.draw [W]
45.23 W  # Idle
68.50 W  # Under load
```

### Power Usage Effectiveness (PUE)

**Formula:**

```
PUE = Total Facility Power / IT Equipment Power

PUE 1.0 = Perfect (impossible)
PUE 1.2 = Excellent
PUE 1.5 = Average
PUE 2.0 = Inefficient
```

**Optimization Strategies:**

- Hot/cold aisle containment
- Free cooling when possible
- Efficient power distribution
- Right-size cooling

---

## 2.5 Evaluate Hybrid AI Deployment with Cloud Integration

### Secure Connectivity

**Hybrid Patterns:**

| Pattern | Data Location | Compute Location |
|---------|--------------|------------------|
| Cloud training | Cloud | Cloud |
| Edge inference | Local | Local |
| Cloud burst | Local primary | Cloud overflow |
| Federated | Distributed | Distributed |

### Data Synchronization

**Considerations:**

- Bandwidth costs for large datasets
- Data sovereignty requirements
- Consistency guarantees
- Encryption in transit

**SASP Approach:**

Fully on-premises (air-gap capable). No cloud integration required for federal deployment scenarios.

---

# Domain 3.0: AI Infrastructure Deployment and Data Management (30%)

## 3.1 Configure High-Performance Networks for AI Workloads

> **Key Resource:** [Intelligent Lossless Ethernet for AI/ML Workloads (White Paper)](https://www.cisco.com/c/en/us/products/collateral/switches/nexus-9000-series-switches/white-paper-c11-738488.html) — This is the "Bible" for Domain 3.1. Covers exact buffer thresholds for RoCEv2, PFC watchdog timers, and ECN marking profiles.

### 3.1.a Congestion Control Mechanisms (PFC, ECN, ETS)

**Priority Flow Control (PFC):**

PFC provides lossless Ethernet by pausing specific traffic classes when congestion is detected.

```
┌─────────────────────────────────────────────────────────────────┐
│                    PFC OPERATION                                │
│                                                                 │
│  Sender ────────────────────────────────► Receiver             │
│                                                                 │
│           Buffer filling up!                                    │
│                    │                                            │
│                    ▼                                            │
│  Sender ◄────── PAUSE Frame (Priority 3) ─── Receiver          │
│                                                                 │
│  Sender stops Priority 3 traffic                               │
│  Other priorities continue                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Explicit Congestion Notification (ECN):**

ECN marks packets instead of dropping them, allowing end-hosts to slow down gracefully.

```
┌─────────────────────────────────────────────────────────────────┐
│                    ECN OPERATION                                │
│                                                                 │
│  IP Header ECN Field:                                          │
│  ┌────┬────┐                                                   │
│  │ 00 │ Not ECN-Capable                                        │
│  │ 01 │ ECN-Capable (ECT(1))                                   │
│  │ 10 │ ECN-Capable (ECT(0))                                   │
│  │ 11 │ Congestion Experienced (CE)                            │
│  └────┴────┘                                                   │
│                                                                 │
│  Switch sets CE bit when queue > threshold                     │
│  Receiver echoes in TCP header                                 │
│  Sender reduces window                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Enhanced Transmission Selection (ETS):**

ETS allocates bandwidth among traffic classes.

```
┌─────────────────────────────────────────────────────────────────┐
│                    ETS BANDWIDTH ALLOCATION                     │
│                                                                 │
│  Priority │ Traffic Type    │ Bandwidth │ Scheduling           │
│  ─────────┼─────────────────┼───────────┼─────────────────────  │
│     7     │ Network Control │    5%     │ Strict Priority      │
│     6     │ Reserved        │    -      │ -                    │
│     5     │ RoCE            │   50%     │ ETS (Lossless)       │
│     4     │ Reserved        │    -      │ -                    │
│     3     │ Best Effort     │   45%     │ ETS                  │
│     2     │ Reserved        │    -      │ -                    │
│     1     │ Background      │    -      │ -                    │
│     0     │ Best Effort     │    -      │ -                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3.1.b RDMA over Converged Ethernet (RoCE, RoCEv2)

**What is RDMA?**

Remote Direct Memory Access allows direct memory-to-memory transfers without CPU involvement.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  TRADITIONAL TCP                    RDMA                        │
│  ───────────────                    ────                        │
│                                                                 │
│  Application                        Application                 │
│      │                                  │                       │
│      ▼                                  │                       │
│  TCP Stack (CPU)                        │ (bypassed)            │
│      │                                  │                       │
│      ▼                                  │                       │
│  IP Stack (CPU)                         │ (bypassed)            │
│      │                                  │                       │
│      ▼                                  ▼                       │
│  NIC Driver (CPU)                   NIC (hardware)              │
│      │                                  │                       │
│      ▼                                  ▼                       │
│    NIC ──────────────────────────────► NIC                      │
│                                                                 │
│  Latency: 50-200μs                  Latency: 1-5μs             │
│  CPU: High                          CPU: Near zero              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**RoCE vs RoCEv2:**

| Feature | RoCE v1 | RoCE v2 |
|---------|---------|---------|
| Encapsulation | Ethernet | UDP/IP |
| Routing | L2 only | L3 routable |
| Port | N/A | UDP 4791 |
| Deployment | Same subnet | Across subnets |

**SASP RoCE Configuration (ConnectX-4):**

```bash
# Verify RDMA device
$ ibstat
CA 'mlx5_0'
    Port 1:
        State: Active
        Physical state: LinkUp
        Rate: 25 Gb/sec
        Link layer: Ethernet

# Test RDMA connectivity
$ rping -s -a <RDMA_S1_IP> -v  # Server
$ rping -c -a <RDMA_S1_IP> -v  # Client
```

**Soft-RoCE Workaround (no physical RDMA NIC needed):**

If ConnectX NICs are not yet installed, use `rdma_rxe` (Soft-RoCE) to simulate RoCEv2 over standard Ethernet. This provides valid `ibstat` and `rping` evidence for proof-of-concept:

```bash
# Load Soft-RoCE kernel module
$ sudo modprobe rdma_rxe

# Create RXE device on existing Ethernet interface
$ sudo rdma link add rxe0 type rxe netdev eno1

# Verify RDMA device appears
$ ibstat
CA 'rxe0'
    Port 1:
        State: Active
        Link layer: Ethernet

# Test RDMA connectivity (same commands as hardware RoCE)
$ rping -s -a <S1_IP> -v     # Server side
$ rping -c -a <S1_IP> -v -C 10  # Client side
```

*Note: Soft-RoCE performance is lower than hardware RoCE (software-emulated), but it demonstrates RDMA concepts and generates valid evidence.*

---

### 3.1.c Quality of Service (QoS)

**QoS for AI Traffic:**

| Traffic Type | Priority | DSCP | Treatment |
|--------------|----------|------|-----------|
| RoCE/RDMA | High | 26 (AF31) | Lossless |
| Storage | High | 24 (CS3) | Low latency |
| Management | Medium | 16 (CS2) | Reliable |
| Bulk data | Low | 0 (BE) | Best effort |

**Switch Configuration Example (Nexus):**

```
! Define class-maps
class-map type qos match-all RDMA
  match dscp 26

class-map type qos match-all STORAGE
  match dscp 24

! Define policy-map
policy-map type qos AI-QOS
  class RDMA
    set qos-group 5
  class STORAGE
    set qos-group 4
  class class-default
    set qos-group 0

! Apply to interface
interface Ethernet1/1
  service-policy type qos input AI-QOS
```

---

### 3.1.d Load Distribution

**ECMP for AI Clusters:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ECMP LOAD BALANCING                          │
│                                                                 │
│                      ┌─────────┐                               │
│                      │  Spine  │                               │
│                      └────┬────┘                               │
│                           │                                     │
│              ┌────────────┼────────────┐                       │
│              │            │            │                       │
│         ┌────┴────┐  ┌────┴────┐  ┌────┴────┐                 │
│         │ Leaf 1  │  │ Leaf 2  │  │ Leaf 3  │                 │
│         └────┬────┘  └────┬────┘  └────┬────┘                 │
│              │            │            │                       │
│         GPU Servers distributed across leaves                  │
│                                                                 │
│  Hash-based distribution on:                                   │
│  - Source/Dest IP                                              │
│  - Source/Dest Port                                            │
│  - Protocol                                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3.2 Configure High-Performance Compute and Storage Using Cisco UCS

### 3.2.a Domain Profiles

**UCS Domain Profile Components:**

- Port policies
- VLAN policies
- VSAN policies (if FC)
- Network connectivity policies

### 3.2.b Power Policy

**Power Capping for AI:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    UCS POWER POLICY                             │
│                                                                 │
│  Policy: AI-POWER-POLICY                                        │
│                                                                 │
│  Power Capping: Enabled                                        │
│  Cap Value: 1000W                                              │
│  Priority: Performance                                         │
│                                                                 │
│  GPU Considerations:                                            │
│  - T4: 70W TDP (efficient)                                     │
│  - A100: 400W TDP (may need cap adjustment)                    │
│  - Monitor actual draw vs cap                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2.c Storage Policies

**Local Storage for AI:**

- Boot from M.2 SSD
- Data on NVMe drives
- RAID configuration based on workload

### 3.2.d LAN Connectivity and vNIC Policies

**vNIC Configuration for RoCE:**

| vNIC | Purpose | MTU | RDMA |
|------|---------|-----|------|
| vNIC0 | Management | 1500 | No |
| vNIC1 | RoCE Primary | 9000 | Yes |
| vNIC2 | RoCE Secondary | 9000 | Yes |
| vNIC3 | Storage | 9000 | Optional |

### 3.2.e QoS Policies and System Classes

**UCS QoS System Classes:**

| Class | Priority | CoS | Weight | MTU |
|-------|----------|-----|--------|-----|
| Platinum | Strict | 5 | N/A | 9216 |
| Gold | High | 4 | 8 | 9216 |
| Silver | Normal | 2 | 4 | 9216 |
| Bronze | Low | 1 | 2 | 9216 |
| Best Effort | Any | 0 | 1 | 9216 |

### 3.2.f NTP Policy

**Time Synchronization for AI:**

Critical for:
- Log correlation
- Distributed training synchronization
- Certificate validation

```
! NTP Configuration
ntp server 192.168.1.1 prefer
ntp server 192.168.1.2
ntp source-interface mgmt0
```

---

## 3.3 Deploy AI-Ready Fabrics Using Cisco Orchestration Tools

> **Lab Access:** Use [Cisco dCloud](https://dcloud.cisco.com) "Nexus Dashboard Insights" labs for hands-on experience with 3.3.a and 3.3.d without additional hardware purchases.

### 3.3.a Nexus Dashboard

> **Resource:** [Nexus Dashboard Insights for AI Clusters User Guide](https://www.cisco.com/c/en/us/support/cloud-systems-management/nexus-dashboard-insights/series.html) — Focus on "GPU-to-Network Telemetry Correlation."

**Capabilities:**

- Centralized management of Nexus fabric
- Fabric discovery and topology visualization
- Policy deployment and compliance
- Analytics and insights

**AI-Specific Features (Nexus Dashboard Insights):**

```
┌─────────────────────────────────────────────────────────────────┐
│               NEXUS DASHBOARD FOR AI CLUSTERS                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Fabric Overview                                         │   │
│  │  - Leaf-spine topology visualization                     │   │
│  │  - GPU server connectivity mapping                       │   │
│  │  - Interface utilization heatmap                         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  GPU-to-Network Telemetry Correlation                    │   │
│  │  - Correlate GPU utilization with network congestion     │   │
│  │  - Identify PFC pause frame storms                       │   │
│  │  - Track ECN marking rates per interface                 │   │
│  │  - Map NCCL traffic flows across the fabric              │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Policy Compliance                                       │   │
│  │  - Verify QoS policies applied to all GPU-facing ports   │   │
│  │  - Check PFC/ECN configuration consistency               │   │
│  │  - Alert on MTU mismatches                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Exam Focus Areas:**
- How Nexus Dashboard discovers and visualizes the AI fabric
- How Insights correlates GPU metrics with network events
- Policy deployment workflow (create → validate → deploy → verify)

### 3.3.b APIC

**ACI for AI Workloads:**

- Micro-segmentation for GPU clusters
- QoS policy automation
- Multi-site connectivity
- Integration with container orchestration

### 3.3.c Hyperfabric

**AI-Optimized Features:**

- Automated RoCE configuration
- Congestion-aware routing
- GPU topology awareness
- Performance telemetry

*(See expanded coverage in [1.6.c Hyperfabric AI](#16c-hyperfabric-ai))*

### 3.3.d Intersight

> **Resource:** [Managing UCS AI Infrastructure with Cisco Intersight](https://www.cisco.com/c/en/us/products/cloud-systems-management/intersight/index.html) — Focus on how Intersight manages GPU profiles and firmware via cloud.

**Intersight for AI Infrastructure:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTERSIGHT CAPABILITIES                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Inventory & Health                                     │   │
│  │  - Server inventory (CPU, memory, storage, GPU)        │   │
│  │  - GPU detection and monitoring (temp, util, ECC)      │   │
│  │  - Firmware compliance checking                        │   │
│  │  - Hardware advisories and alerts                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Server Profiles (AI-Optimized)                         │   │
│  │  - GPU passthrough configuration                       │   │
│  │  - BIOS settings for AI (VT-d, ACS, NUMA)             │   │
│  │  - Boot policy (UEFI for GPU servers)                  │   │
│  │  - vNIC policies (RoCE-enabled, MTU 9000)             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  GPU Firmware Management                                │   │
│  │  - NVIDIA driver version tracking                      │   │
│  │  - Firmware update orchestration                       │   │
│  │  - GPU profile assignment (MIG, vGPU, passthrough)     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Kubernetes Integration                                 │   │
│  │  - IKS (Intersight Kubernetes Service)                 │   │
│  │  - GPU operator deployment                             │   │
│  │  - Monitoring integration                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Exam Focus Areas:**
- How Intersight discovers and inventories GPU hardware
- Server profile workflow: create template → derive profile → deploy
- GPU firmware lifecycle management via cloud
- Difference between CIMC (local) and Intersight (cloud) management

---

# Domain 4.0: AI Infrastructure Operations and Troubleshooting (20%)

## 4.1 Implement Benchmarks to Evaluate AI Infrastructure Performance

### NCCL Benchmarks

**All-Reduce Benchmark:**

```bash
# Install NCCL tests
$ git clone https://github.com/NVIDIA/nccl-tests.git
$ cd nccl-tests
$ make MPI=1

# Run all-reduce (measures collective communication)
$ mpirun -np 2 --host server1,server2 \
    ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1
```

**SASP NCCL Results:**

```
#       size    time   algbw   busbw
         8     0.02    0.00    0.00
       128     0.02    0.01    0.01
      2048     0.03    0.07    0.14
     32768     0.06    0.55    1.09
    524288     0.19    2.72    5.44
   8388608     2.44    3.44    6.88
  67108864    19.21    3.49    6.99
 536870912   154.12    3.48    6.97

Avg bus bandwidth: 3.4 GB/s (TCP)
Expected with RDMA: ~12 GB/s
```

### GPU Benchmarks

**GPU Memory Bandwidth:**

```bash
# CUDA bandwidth test
$ /usr/local/cuda/extras/demo_suite/bandwidthTest

# Results:
Host to Device:   12.5 GB/s
Device to Host:   13.2 GB/s
Device to Device: 288.1 GB/s  # T4 spec: 320 GB/s
```

### Inference Benchmarks

**Triton perf_analyzer:**

```bash
$ perf_analyzer -m abp-nvsmi-xgb \
    --concurrency-range 1:16 \
    -u localhost:8000

# Results:
Concurrency: 8
Throughput: 9,727 infer/sec
Latency p99: 8.2 ms
```

**Latency vs. Throughput Analysis (exam-critical):**

The DCAI exam expects understanding of how **batch size impacts p99 latency**. Generate a full analysis:

```bash
# Generate CSV output for graphing
$ perf_analyzer -m abp-nvsmi-xgb \
    --concurrency-range 1:16 \
    --measurement-interval 10000 \
    -u localhost:8000 \
    -f perf_results.csv
```

**Expected Relationship:**

```
Throughput ↑                  Latency ↑
     │    ╱─────────────          │         ╱──────
     │   ╱                        │        ╱
     │  ╱                         │       ╱
     │ ╱                          │      ╱
     │╱                           │─────╱
     └──────────────────          └──────────────────
       Concurrency →                Concurrency →

Key insight: Throughput plateaus while latency
continues rising — the "knee" is optimal operating point.
```

| Batch Size | Throughput | p99 Latency | Analysis |
|------------|-----------|-------------|----------|
| 1 | ~2,000 inf/s | ~1 ms | Low utilization |
| 4 | ~6,000 inf/s | ~3 ms | Good balance |
| 8 | ~9,700 inf/s | ~8 ms | **Optimal** |
| 16 | ~10,200 inf/s | ~18 ms | Diminishing returns |
| 32 | ~10,400 inf/s | ~35 ms | Latency too high |

**Key Exam Points:**
- Larger batch sizes improve throughput but increase latency
- The optimal batch size is where throughput plateaus before latency spikes
- p99 latency matters more than average for real-time inference
- Dynamic batching in Triton automatically optimizes this trade-off

### Storage Benchmarks

**fio (Flexible I/O Tester):**

```bash
# Random read IOPS (simulates model loading, data augmentation)
$ fio --name=randread --rw=randread --bs=4k --size=1G --numjobs=4 \
    --ioengine=libaio --direct=1 --runtime=60

# Sequential read throughput (simulates dataset streaming)
$ fio --name=seqread --rw=read --bs=1M --size=4G --numjobs=1 \
    --ioengine=libaio --direct=1 --runtime=60

# Mixed workload (simulates training checkpoint + data read)
$ fio --name=mixed --rw=randrw --rwmixread=70 --bs=64k --size=2G \
    --numjobs=4 --ioengine=libaio --direct=1 --runtime=60
```

**Why This Matters:** Storage benchmarks prove whether your storage subsystem can keep the GPU fed with data. If storage IOPS is too low, the GPU sits idle waiting for data — a common bottleneck the exam tests for.

---

## 4.2 Implement Monitoring of AI Data Center Infrastructures

### Nexus Dashboard Monitoring

**Key Metrics:**

- Interface utilization
- Error counters
- QoS drops
- ECN marking rate
- PFC pause frames

### Intersight Monitoring

**Server Health:**

- CPU utilization
- Memory utilization
- GPU metrics (via NVIDIA driver)
- Power consumption
- Thermal status

### DCGM (Data Center GPU Manager)

```bash
# Start DCGM
$ nv-hostengine

# Monitor GPUs
$ dcgmi dmon -e 100,101,102,103,104,155,156

# Metrics:
# 100: GPU Utilization
# 101: Memory Utilization  
# 102: ECC Errors
# 103: GPU Temperature
# 104: Power Usage
# 155: PCIe TX Throughput
# 156: PCIe RX Throughput
```

---

## 4.3 Monitor AI Infrastructure Using System Messages and Management Tools

### 4.3.a Operational Telemetry

**Streaming Telemetry Configuration:**

```
! Nexus telemetry configuration
telemetry
  destination-group 1
    ip address <SPLUNK_IP> port 8086 protocol gRPC
  sensor-group 1
    path sys/ch/ftslot-1/ft depth 0
    path sys/ch/supslot-1/sup/sensor depth 0
  subscription 1
    dst-grp 1
    snsr-grp 1
    sample-interval 10000
```

### 4.3.b System Health

**Health Check Workflow:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    HEALTH CHECK FLOW                            │
│                                                                 │
│  1. GPU Health                                                  │
│     $ nvidia-smi -q | grep -E "GPU|Memory|Temp|Power"          │
│                                                                 │
│  2. Network Health                                              │
│     $ ibstat (RDMA)                                            │
│     $ ethtool -S eth0 | grep -i error                          │
│                                                                 │
│  3. Storage Health                                              │
│     $ df -h                                                     │
│     $ iostat -x 1                                              │
│                                                                 │
│  4. Container Health                                            │
│     $ docker ps                                                 │
│     $ docker stats                                             │
│                                                                 │
│  5. Service Health                                              │
│     $ curl localhost:8000/v2/health/ready (Triton)             │
│     $ curl localhost:8088/services/collector (Splunk HEC)      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3.c Alerts

**SASP Alert Configuration (Splunk):**

```spl
| Alert: GPU Temperature Critical
index=morpheus sourcetype="nvidia-smi"
| where gpu_temp > 85
| alert

| Alert: Inference Latency High  
index=morpheus sourcetype="triton"
| where latency_p99 > 100
| alert

| Alert: Detection Spike
index=morpheus sourcetype="morpheus:*"
| timechart count by detection_type
| where count > threshold
| alert
```

### 4.3.d Log Correlation

**Correlating Events:**

```spl
| Correlate GPU event with detection
index=morpheus
| transaction gpu_id maxspan=1m
| where eventcount > 1
| table _time, gpu_id, events
```

---

## 4.4 Troubleshoot AI Infrastructure

> **Key Resource:** [Troubleshooting RoCEv2 on Cisco Nexus 9000](https://www.cisco.com/c/en/us/support/switches/nexus-9000-series-switches/products-troubleshooting-guides-list.html) — Interactive guide covering "Why did my NCCL job fail?" which is a primary 300-640 troubleshooting topic.

### Common Issues and Solutions

**Issue: NCCL Timeout**

```
Symptoms:
- Training hangs
- "NCCL timeout" in logs
- Workers become unresponsive

Troubleshooting:
$ export NCCL_DEBUG=INFO
$ export NCCL_DEBUG_SUBSYS=ALL

Common causes:
1. Firewall blocking ports (29500, etc.)
2. MTU mismatch (check both NIC and switch)
3. Network unreachable (routing issue)
4. GPU memory exhausted (OOM during allreduce)
5. PFC deadlock (see PFC Storm below)
6. Asymmetric link speeds between nodes
```

**Detailed NCCL Timeout Diagnosis:**

```bash
# Step 1: Enable verbose NCCL logging
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=ALL

# Step 2: Look for transport selection in logs
# Good: "NCCL INFO NET/IB : Using [0]mlx5_0:1/RoCE"
# Bad:  "NCCL INFO NET/Socket : Using [0]eno1"  (fell back to TCP)

# Step 3: Check if nodes can reach each other
nc -zv <RDMA_S1_IP> 29500   # From node 1
nc -zv <RDMA_S2_IP> 29500   # From node 0

# Step 4: Check for MTU mismatch
ip link show enp59s0f0 | grep mtu   # Should be 9000
# On switch:
# show interface Ethernet1/44 | include MTU

# Step 5: Check for PFC pause frames (congestion indicator)
# On switch:
# show interface Ethernet1/44 priority-flow-control
# Look for: Tx pause count incrementing = congestion upstream

# Step 6: Check GPU memory availability
nvidia-smi --query-gpu=memory.free --format=csv
```

---

**Issue: PFC Storm (Exam-Critical Troubleshooting Scenario)**

```
Symptoms:
- Network-wide slowdown or hang
- PFC pause frame counters incrementing rapidly on multiple interfaces
- Training jobs timeout across the entire fabric
- "Head-of-line blocking" — even non-RDMA traffic is affected

Root Cause:
A PFC storm occurs when pause frames propagate backwards through the
fabric, causing a chain reaction of pauses ("pause frame propagation").
This can be triggered by:
1. A slow receiver (faulty NIC or overloaded server)
2. Buffer exhaustion on a single switch port
3. Incorrect PFC watchdog timer configuration
```

**PFC Storm Diagnosis Steps:**

```bash
# Step 1: Identify which interfaces are generating excessive pauses
# On Nexus switch:
show interface priority-flow-control
# Look for: interfaces with rapidly incrementing Tx Pause counts

# Step 2: Check PFC watchdog (should be enabled to break storms)
show queuing pfc-queue interface Ethernet1/44
# PFC watchdog should show "enabled" — if not, that's the problem

# Step 3: Enable PFC watchdog to auto-recover
# Configuration:
priority-flow-control watch-dog-interval on

# Step 4: Check buffer utilization
show queuing interface Ethernet1/44
# Look for: shared buffer pool exhaustion

# Step 5: Identify the slow receiver
# Check server-side NIC stats:
ethtool -S enp59s0f0 | grep pause
# High rx_pause_ctrl = this server is being paused
# High tx_pause_ctrl = this server is causing pauses

# Step 6: Check for ECN marking (proactive congestion signal)
show queuing interface Ethernet1/44 | include ECN
# ECN marks should appear BEFORE PFC pauses
# If no ECN marks but PFC pauses = ECN not configured (fix this)
```

**Prevention:**
- Enable PFC watchdog on all switch ports
- Configure ECN thresholds (ECN should trigger before PFC)
- Use DCBX for automatic PFC negotiation
- Monitor PFC counters in Nexus Dashboard Insights

---

**Issue: GPU Out of Memory**

```
Symptoms:
- CUDA OOM error
- Training crashes

Troubleshooting:
$ nvidia-smi
$ watch -n 1 nvidia-smi

Solutions:
1. Reduce batch size
2. Enable gradient checkpointing
3. Use mixed precision (FP16)
4. Distribute across more GPUs
```

**Issue: Slow Inference**

```
Symptoms:
- High latency
- Low throughput

Troubleshooting:
$ perf_analyzer -m model_name --concurrency-range 1:32

Common causes:
1. Model not optimized (use TensorRT)
2. Batch size too small (underutilizing GPU)
3. Batch size too large (p99 latency spike)
4. CPU bottleneck in preprocessing
5. Network latency (if remote Triton)
6. Storage I/O bottleneck (model loading)
```

**Issue: RDMA Not Working**

```
Symptoms:
- NCCL falls back to TCP
- Low bandwidth
- NCCL_DEBUG shows "NET/Socket" instead of "NET/IB"

Troubleshooting:
$ ibstat
$ ibv_devinfo
$ rping -s / rping -c

Common causes:
1. Missing kernel modules (lsmod | grep mlx5 or rdma_rxe)
2. Incorrect IP configuration on RDMA interface
3. PFC not enabled on switch port
4. Incorrect DSCP marking (switch and NIC must agree)
5. GID index mismatch (NCCL_IB_GID_INDEX)
6. Firewall blocking UDP 4791 (RoCEv2)
```

---

# Quick Reference

## Key Commands

| Purpose | Command |
|---------|---------|
| GPU status | `nvidia-smi` |
| GPU detailed | `nvidia-smi -q` |
| RDMA status | `ibstat` |
| RDMA devices | `ibv_devinfo` |
| NCCL debug | `NCCL_DEBUG=INFO` |
| Triton health | `curl localhost:8000/v2/health/ready` |
| Container logs | `docker logs <container>` |

## Key Ports

| Service | Port | Protocol |
|---------|------|----------|
| Triton HTTP | 8000 | TCP |
| Triton gRPC | 8001 | TCP |
| Triton Metrics | 8002 | TCP |
| Kafka | 9092 | TCP |
| NCCL | 29500+ | TCP |
| RoCEv2 | 4791 | UDP |
| NetFlow | 2055 | UDP |
| Syslog | 514 | UDP/TCP |
| Splunk HEC | 8088 | TCP |

## Key Files (SASP)

| Purpose | Location |
|---------|----------|
| Kafka compose | `/data/kafka/docker-compose.yml` |
| Morpheus workspace | `/mnt/storage1/Morpheus/` |
| Training data | `/data/training/` |
| Model repository | `/mnt/storage1/models/` |

---

# Cisco U Training Progress

> **Course:** DCAIE — Designing Cisco AI Infrastructure (300-640 Exam Prep)
> **Platform:** [Cisco U](https://u.cisco.com)
>
> The DCAIE course is Cisco's official exam preparation for the **entire 300-640 blueprint**. It is organized into tracks, each covering a cluster of objectives.

## Overall DCAIE Course → Blueprint Coverage

| DCAI Domain | Weight | DCAIE Course Coverage |
|-------------|--------|----------------------|
| 1.0 AI Fundamentals and Applications | 20% | ✅ Full — AI workloads, lifecycle, use cases, Cisco solutions |
| 2.0 AI Infrastructure Components and Architecture | 30% | ✅ Full — network, compute, storage, power, hybrid evaluation |
| 3.0 AI Infrastructure Deployment and Data Management | 30% | ✅ Full — high-perf networking, UCS config, fabric orchestration |
| 4.0 AI Infrastructure Operations and Troubleshooting | 20% | ✅ Full — benchmarks, monitoring, telemetry, troubleshooting |

> The DCAIE course covers **all 57 exam objective items** across all 4 domains.

## AI Network Architectures Track (In Progress)

| Metric | Value | Date |
|--------|-------|------|
| Track Completion | **54.55%** | Feb 19, 2026 |
| Post-Assessment Score | **84%** | Feb 19, 2026 |
| Courses in Track | 5 of 5 enrolled | — |

**Screenshot:** `docs/cisco_u_progress/cisco_u_ai_network_architectures_progress.png`

### Blueprint Mapping — AI Network Architectures Track

This track covers AI networking concepts end-to-end, spanning theory through deployment and troubleshooting:

| Topic Area | DCAI Objectives Covered | Domain |
|------------|------------------------|--------|
| AI/ML Workload Network Requirements | 1.1.b Training, 1.1.c Inference (network I/O characteristics) | Domain 1 (20%) |
| Components for AI Environments — Network | 1.5.a Network (spine-leaf, InfiniBand vs Ethernet, NVLink) | Domain 1 (20%) |
| Cisco AI Solutions — Network-centric | 1.6.a AI PODs, 1.6.c Hyperfabric AI | Domain 1 (20%) |
| Evaluate Network Deployment | 2.1 Network Deployment (topology, bandwidth, latency trade-offs) | Domain 2 (30%) |
| Evaluate Hybrid AI Deployment | 2.5 Hybrid AI (cloud-burst networking, interconnects) | Domain 2 (30%) |
| Lossless Ethernet — PFC, ECN, ETS | 3.1.a Congestion Control Mechanisms | Domain 3 (30%) |
| RoCE / RoCEv2 | 3.1.b RDMA over Converged Ethernet | Domain 3 (30%) |
| QoS for AI Workloads | 3.1.c Quality of Service | Domain 3 (30%) |
| Load Distribution / ECMP | 3.1.d Load Distribution | Domain 3 (30%) |
| AI-Ready Fabric Architectures | 3.3.a Nexus Dashboard, 3.3.b APIC, 3.3.c Hyperfabric | Domain 3 (30%) |
| Network Benchmarks (NCCL, iperf) | 4.1 Benchmarks (network performance evaluation) | Domain 4 (20%) |
| Network Monitoring & Telemetry | 4.2 Monitoring, 4.3.a Operational Telemetry | Domain 4 (20%) |
| NCCL Transport & Network Troubleshooting | 4.4 Troubleshooting (PFC storms, NCCL timeouts, RDMA failures) | Domain 4 (20%) |

**Objective Count:** This single track touches **~20 sub-objectives** across all 4 domains — roughly **35% of the full exam blueprint**.

**Key Takeaway:** The 84% post-assessment score on this track indicates solid understanding of AI networking concepts spanning the entire exam. Since Domain 3 is 30% of the exam and the weakest current area, this track provides the highest-value foundation. The remaining 45% of the track likely deepens fabric orchestration and troubleshooting — directly targeting the 3.3 and 4.4 gaps.

### Readiness Impact

| Domain | Before Cisco U | After Track Completion (projected) |
|--------|---------------|-----------------------------------|
| 1.0 Fundamentals | Strong | Strong (networking theory reinforced) |
| 2.0 Architecture | Good | Good+ (2.1 network evaluation concepts solidified) |
| 3.0 Deployment | Moderate | **Good** (core 3.1 + partial 3.3 coverage) |
| 4.0 Operations | Emerging | Emerging+ (4.1 benchmarks + 4.4 troubleshooting context) |

### Remaining DCAIE Tracks

| Track | Primary Objectives | Priority |
|-------|-------------------|----------|
| AI Compute and Storage | 1.5.b-f, 2.2, 2.3, 2.4, 3.2.a-f | Medium — already strong from lab work |
| AI Infrastructure Operations | 4.1, 4.2, 4.3.a-d, 4.4 | **High** — directly targets weakest domain |
| AI Fabric Orchestration | 3.3.a-d (ND, APIC, Hyperfabric, Intersight) | **High** — addresses primary fabric gap |

---

# Self-Assessment

After studying, you should be able to answer:

## Domain 1
1. What's the difference between training and inference workloads?
2. When would you use RAG vs fine-tuning?
3. What makes on-premises AI infrastructure suitable for air-gapped environments?

## Domain 2
1. Why is RDMA preferred for distributed training?
2. How do you size GPU memory for a workload?
3. What's the difference between NVLink and RoCE?

## Domain 3
1. Explain how PFC prevents packet loss.
2. What's the purpose of ECN in AI networks?
3. How would you configure QoS for RoCE traffic?

## Domain 4
1. What NCCL benchmark would you run to test multi-node performance?
2. How do you diagnose a CUDA OOM error?
3. What would cause NCCL to fall back to TCP?
4. How does batch size impact p99 latency in Triton inference?
5. What is a PFC storm and how do you diagnose/prevent it?
6. Walk through diagnosing a failed NCCL job using `NCCL_DEBUG=INFO` output.
7. How does ECN relate to PFC in preventing congestion?

---

---

# Cisco Official Reference Library (300-640 DCAI v1.0)

> Complete Cisco-official documentation mapped to every v1.0 exam objective.
> Sources prioritize Cisco docs, training, white papers, and validated design guides.

## Core Reference Documents

These documents are referenced repeatedly across objectives — bookmark these first:

| Abbrev | Full Title | Primary Use |
|--------|-----------|-------------|
| **DCAIE** | [DCAIE — AI Solutions on Cisco Infrastructure Essentials](https://www.cisco.com/c/en/us/training-events/training-certifications/exams/current-list/dcai-300-640.html) | Architecture, design, deployment — broad exam prep |
| **DCAIAOT** | [DCAIAOT — Operate and Troubleshoot AI Solutions on Cisco Infrastructure](https://www.cisco.com/c/en/us/training-events/training-certifications/) | Monitoring, troubleshooting, telemetry, Splunk labs |
| **AI PODs AAG** | [Cisco AI PODs At-a-Glance](https://www.cisco.com/c/en/us/solutions/data-center/ai-ml-solutions.html) | Lifecycle, training/fine-tuning/inference, observability, Intersight/ND |
| **Agentic Era WP** | [AI Infrastructure for the Agentic Era](https://www.cisco.com/c/en/us/solutions/data-center/ai-ml-solutions.html) | AI evolution, agentic AI, lifecycle, workload types |
| **AI Canvas** | [Cisco AI Canvas](https://www.cisco.com/c/en/us/solutions/ai-canvas.html) | NL interfaces, MCP, cross-domain telemetry, agent workflows, HITL |
| **Hyperfabric GS** | [Nexus Hyperfabric Getting Started](https://www.cisco.com/c/en/us/products/switches/nexus-hyperfabric.html) | Blueprint/design/onboarding/deploy/claim/bind workflow |
| **Hyperfabric RA** | [Hyperfabric AI Enterprise RA Datasheet](https://www.cisco.com/c/en/us/products/switches/nexus-hyperfabric.html) | NVIDIA-aligned AI architecture, topology, storage, security, testing |
| **N9300-FX3 DS** | [Nexus 9300-FX3 Datasheet](https://www.cisco.com/c/en/us/products/switches/nexus-9000-series-switches/) | AI/ML fabric transport (PFC/ECN/DCB/ETS/DCBX/WRED), telemetry, PTP |
| **NX-OS QoS** | [NX-OS QoS Configuration Guide (Nexus 9000)](https://www.cisco.com/c/en/us/support/switches/nexus-9000-series-switches/) | System/network QoS, LLFC, PFC, PFC watchdog, DLB |
| **IMM Guide** | [Intersight Managed Mode Configuration Guide](https://www.cisco.com/c/en/us/support/cloud-systems-management/intersight/) | UCS domain/server profiles, policies, firmware |
| **ISight Storage BP** | [Intersight Storage Best Practices Guide](https://www.cisco.com/c/en/us/support/cloud-systems-management/intersight/) | FC/iSCSI/NVMe-oF/NVMe-over-RoCEv2, storage policies |
| **APIC Faults Guide** | [APIC Faults/Events/System Messages Guide](https://www.cisco.com/c/en/us/support/cloud-systems-management/application-policy-infrastructure-controller-apic/) | ACI operations, faults, events, audit logs, retention |
| **ACI Design Guide** | [Cisco ACI Design Guide](https://www.cisco.com/c/en/us/solutions/data-center-virtualization/application-centric-infrastructure/) | Fabric architecture, segmentation, RBAC |
| **RoCEv2 GPU WP** | [RoCEv2 GPU Storage White Paper](https://www.cisco.com/c/en/us/products/collateral/switches/nexus-9000-series-switches/) | RoCEv2 storage networking deployment guidance |
| **MDS FC Guide** | [MDS FC Interfaces Configuration Guide](https://www.cisco.com/c/en/us/support/storage-networking/mds-9000-series-multilayer-switches/) | FC interface and storage connectivity |
| **NDFC Docs** | [Nexus Dashboard Fabric Controller Docs Hub](https://www.cisco.com/c/en/us/support/cloud-systems-management/nexus-dashboard-fabric-controller/) | Integration, operations, day-2 workflows |
| **ISight Device Mgmt** | [Intersight Device Management Docs](https://www.cisco.com/c/en/us/support/cloud-systems-management/intersight/) | Device status/health, day-2 device management |

---

## 1.0 Explain AI Concepts and AI Infrastructure Architecture

### 1.1 Describe AI and ML workload types

*Sub-objectives: (a) traditional AI/ML, (b) GenAI, (c) agentic AI, (d) inferencing, (e) training, (f) fine-tuning, (g) RAG*

| Resource | Coverage |
|----------|----------|
| Agentic Era WP | GenAI → multimodal → agentic AI evolution; pre-training, fine-tuning, inferencing, RAG |
| AI PODs AAG | Training, fine-tuning, inferencing workload performance/scalability |
| Hyperfabric RA | LLM training, fine-tuning, inferencing, RAG workload examples |
| DCAIE | Official course framing for AI workloads on Cisco infrastructure |

### 1.2 Explain AI workload benchmark and profiling concepts

*Sub-objectives: (a) benchmark, (b) profiling tools, (c) synthetic vs real-world benchmarks, (d) synthetic vs real-world workloads*

| Resource | Coverage |
|----------|----------|
| DCAIE | Foundational AI workload/architecture/design understanding |
| AI PODs AAG | Performance/scalability + CVD/validated design positioning |
| Hyperfabric RA | "Testing and certification" scope — benchmark/test framing |
| DCAIAOT | Telemetry/log-correlation troubleshooting → profiling mindset |

### 1.3 Explain concepts for using AI to interact with infrastructure and applications

*Sub-objectives: (a) natural language interfaces, (b) MCP, (c) API interaction, (d) CLI generation, (e) workflow automation*

| Resource | Coverage |
|----------|----------|
| **AI Canvas** | **Primary source** — NL interaction, MCP, cross-domain telemetry retrieval, agent recommendations, HITL approvals, workflow execution |
| DCAIE | Official training umbrella for AI solution practices |

> **Note:** CLI generation (1.3.d) is more likely reinforced in Cisco U labs/course material than a standalone public doc page.

### 1.4 Explain AI infrastructure architecture concepts

*Sub-objectives: (a) edge inferencing, (b) centralized inferencing, (c) public cloud, (d) hybrid cloud, (e) on-premises*

| Resource | Coverage |
|----------|----------|
| DCAIE | Architecture/design foundations on Cisco DC infrastructure |
| Agentic Era WP | Enterprise AI infrastructure architecture + lifecycle |
| AI PODs AAG | On-prem validated stacks; lifecycle/operations integration |
| Hyperfabric RA + GS | On-prem AI cluster + cloud-managed operational model |

### 1.5 Explain AI infrastructure lifecycle stages

*Sub-objectives: (a) Day 0, (b) Day 1, (c) Day 2*

| Resource | Coverage |
|----------|----------|
| DCAIE | Deploy/migrate/operate framing = Day 0/1/2 foundation |
| DCAIAOT | Explicit lifecycle management + monitoring/troubleshooting |
| AI PODs AAG | Prevalidated CVDs + Intersight + ND + observability = day-0/1/2 |
| Hyperfabric GS | Blueprint/design/onboarding/deploy/claim/bind workflow |

---

## 2.0 Design AI Infrastructure Architecture

### 2.1 Determine requirements for AI infrastructure design

*Sub-objectives: (a) network, (b) compute, (c) storage, (d) power/cooling, (e) cloud hybrid*

| Sub | Resource | Coverage |
|-----|----------|----------|
| a-c | Hyperfabric RA | Hardware, networking topologies, cluster sizing, storage architecture |
| a-c | AI PODs AAG | Accelerated compute, high-perf networking, storage platform |
| a | N9300-FX3 DS | AI/ML fabric transport features + telemetry + ECMP |
| c | ISight Storage BP | Local storage, FC/IP SAN, NVMe-oF variants |
| d | AI PODs AAG | Energy-efficient designs / sustainability / ROI |
| d | DCAIE | Design principles umbrella |
| e | Agentic Era WP | Enterprise architecture context |
| e | Hyperfabric GS | Cloud-managed service / shared responsibility for on-prem |

### 2.2 Determine integrations with AI infrastructure deployment

*Sub-objectives: (a) Cisco AI Canvas, (b) Nexus Dashboard, (c) HyperFabric AI, (d) Intersight*

| Sub | Resource | Coverage |
|-----|----------|----------|
| a | AI Canvas | Cross-domain telemetry + agentic workspace + approvals |
| b | N9300-FX3 DS | ND platform + integrated services (NDFC/NDI/NDO) |
| b | NDFC Docs | Official product docs entry point |
| c | Hyperfabric GS + RA | Full Hyperfabric AI deployment/operations |
| d | AI PODs AAG | Intersight as part of AI POD operations stack |
| d | IMM Guide | Domain/server profile constructs + policies |

### 2.3 Describe AI security architecture concepts

*Sub-objectives: (a) AI workload security, (b) data protection, (c) segmentation/micro-segmentation, (d) IAM, (e) logging/monitoring*

| Resource | Coverage |
|----------|----------|
| AI PODs AAG | AI Defense, Hypershield, observability, enterprise security/compliance |
| Hyperfabric RA | Dedicated Security section in solution scope |
| ACI Design Guide | Fabric architecture + policy constructs / RBAC for segmentation |
| APIC Faults Guide | Logging, events, audit logs, system messages, retention |
| DCAIAOT | Monitoring / log correlation / telemetry troubleshooting |

---

## 3.0 Deploy and Configure AI Infrastructure Architecture

### 3.1 Configure AI infrastructure components

*Sub-objectives: (a) network connectivity, (b) storage connectivity, (c) UCS domain profiles, (d) UCS server profiles, (e) server firmware, (f) rack server discovery/registration*

| Sub | Resource | Coverage |
|-----|----------|----------|
| a | Hyperfabric GS | Fabric blueprinting, cabling, switch port config, onboarding |
| a | N9300-FX3 DS | AI/ML fabric networking capabilities |
| a | RoCEv2 GPU WP | AI fabric transport / storage network design |
| b | ISight Storage BP | FC/IP SAN, DAS, iSCSI boot, NVMe-oF incl. NVMe/RoCEv2 |
| b | MDS FC Guide | FC interface config foundation |
| b | RoCEv2 GPU WP | Storage over RoCEv2 deployment/troubleshooting |
| c | IMM Guide — Domain Profiles | Domain profile overview, templates, deriving, policies |
| d | IMM Guide — Server Profiles | Server profile creation, policy groupings (compute/network) |
| e | IMM Guide | "Managing Firmware" + firmware policy in profile categories |
| f | Hyperfabric GS | Claim devices, claim codes, bind devices, onboarding flow |
| f | ISight Device Mgmt | Device status/health and management context |
| f | IMM Guide | Setup and lifecycle framework |

### 3.2 Configure system policies

*Sub-objectives: (a) NTP, (b) system QoS, (c) LLFC, (d) PFC, (e) vNIC, (f) storage*

| Sub | Resource | Coverage |
|-----|----------|----------|
| a | IMM Guide — Switch Policies | NTP Policy behavior in Intersight-managed UCS |
| a | N9300-FX3 DS | PTP support (timing policy adjacency) |
| b | NX-OS QoS | Main guide / network QoS chapters |
| b | RoCEv2 GPU WP | Practical QoS/RDMA deployment guidance |
| c | NX-OS QoS — LLFC chapter | Link Level Flow Control configuration |
| d | NX-OS QoS — PFC chapter | PFC fundamentals, config, verification, PFC watchdog |
| d | N9300-FX3 DS | PFC/ECN/DCB context in AI fabrics |
| e | IMM Guide — Server Profiles | Network policy / adapter config / LAN connectivity |
| f | ISight Storage BP | Storage config and policy guidance in IMM/ISM |
| f | IMM Guide — Server Profiles | SAN/iSCSI/LAN connectivity policy grouping |

---

## 4.0 Operate and Troubleshoot AI Infrastructure Architecture

### 4.1 Identify benchmarking and profiling tools

*Sub-objectives: (a) packet analysis, (b) infrastructure, (c) GPU, (d) CPU, (e) workload*

| Resource | Coverage |
|----------|----------|
| DCAIAOT | Telemetry analysis, log correlation, troubleshooting labs with Splunk |
| AI PODs AAG | Observability, OpenTelemetry extensions, workload optimization |
| Hyperfabric RA | Testing/certification section in scope |

> **Note:** The exact tool-by-category list (packet/GPU/CPU/workload profilers) is primarily reinforced in Cisco U labs and vendor tooling docs.

### 4.2 Monitor and maintain AI infrastructure

*Sub-objectives: (a) system status, (b) telemetry, (c) load distribution, (d) temperature, (e) timing protocols, (f) logs*

| Sub | Resource | Coverage |
|-----|----------|----------|
| a | ISight Device Mgmt | Device status/health |
| a | DCAIAOT | Monitoring focus |
| b | DCAIAOT | Telemetry analysis, Splunk |
| b | AI PODs AAG | Observability / OpenTelemetry extensions |
| b | N9300-FX3 DS | Telemetry / model-driven telemetry |
| c | NX-OS QoS — DLB chapter | Policy-driven Dynamic Load Balancing |
| c | N9300-FX3 DS | ECMP and AI congestion/flow-control capabilities |
| d | DCAIAOT | Monitoring/troubleshooting lifecycle |
| d | ISight Device Mgmt | Platform observability |
| e | DCAIAOT | Explicitly includes timing protocols in troubleshooting outcomes |
| e | N9300-FX3 DS | PTP/SyncE/PTP boundary clock support |
| f | APIC Faults Guide | Faults, events, audit logs, system messages, retention |
| f | DCAIAOT | Log correlation and telemetry analysis |

### 4.3 Troubleshoot AI infrastructure issues

*Sub-objectives: (a) network, (b) storage, (c) compute, (d) integration, (e) AI workload application*

| Sub | Resource | Coverage |
|-----|----------|----------|
| a | DCAIAOT | Monitor/diagnose/resolve infrastructure issues |
| a | NX-OS QoS | QoS/PFC/LLFC/DLB troubleshooting |
| a | APIC Faults Guide | ACI-side fault/event/log analysis |
| b | ISight Storage BP | Troubleshooting FC on Cisco UCS, verify/boot/storage protocol flows |
| b | RoCEv2 GPU WP + MDS FC Guide | Storage networking troubleshooting |
| c | DCAIAOT | Compute component troubleshooting scope |
| c | IMM Guide / ISight Device Mgmt | Profile/policy/device health operational context |
| d | AI Canvas | Cross-domain telemetry + evidence + approval-gated workflows |
| d | NDFC Docs + ISight Device Mgmt | Integration touchpoints and operations |
| d | Hyperfabric GS | Onboarding/claim/bind/deploy troubleshooting |
| e | DCAIAOT | Explicit lab for unresponsive AI app using Splunk Enterprise |
| e | AI PODs AAG | Workload ops/optimization/observability |

---

## Coverage Strength Assessment

| Area | Cisco Public Doc Coverage |
|------|--------------------------|
| **Strongest** | 2.x design/integrations, 3.x deployment/config (Intersight + NX-OS QoS), 4.2/4.3 monitoring & troubleshooting |
| **Course/Lab-dependent** | 1.2 benchmark/profiling nuance, 1.3.d CLI generation, 4.1 exact tool taxonomy |

> Course pages confirm the topic direction for lab-dependent areas, but the full tool lists and CLI generation details are reinforced in Cisco U labs rather than standalone public docs.

## Lab Access (No Hardware Required)

| Platform | What You Get |
|----------|-------------|
| [Cisco dCloud](https://dcloud.cisco.com) | Nexus Dashboard Insights labs, Intersight labs — free with Cisco account |
| [Cisco Modeling Labs (CML)](https://www.cisco.com/c/en/us/products/cloud-systems-management/modeling-labs/index.html) | Virtual Nexus 9000 for fabric simulation |

---

*This guide aligns with the SASP (Secure AI Security Platform) project. As implementation evolves, this document will be updated.*
