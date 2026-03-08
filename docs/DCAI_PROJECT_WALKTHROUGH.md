# DCAI Project Walkthrough

> **Build an AI Security Platform mapped to DCAI Exam Objectives**
> 
> Step-by-step implementation with exam objective alignment.

---

## Project Overview

**SASP (Secure AI Security Platform)** demonstrates real-world AI infrastructure skills:

| Component | DCAI Coverage |
|-----------|---------------|
| GPU compute (Tesla T4) | Domain 1, 2, 3 |
| Distributed training (NCCL) | Domain 2, 3, 4 |
| High-speed networking (RoCE) | Domain 3 |
| Inference serving (Triton) | Domain 1, 2 |
| Monitoring (Splunk) | Domain 4 |
| Containerization (Docker) | Domain 1, 3 |

---

# Phase 1: Infrastructure Setup

## Step 1.1: Verify GPU Hardware

**Exam Objectives:** 1.5.b Compute and GPUs, 2.2 Compute deployment

```bash
# Check GPU is detected
$ lspci | grep -i nvidia
3b:00.0 3D controller: NVIDIA Corporation TU104GL [Tesla T4] (rev a1)

# Check NVIDIA driver
$ nvidia-smi
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.154.05   Driver Version: 535.154.05   CUDA Version: 12.2    |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  Tesla T4            On   | 00000000:3B:00.0 Off |                    0 |
| N/A   42C    P8    10W /  70W |      0MiB / 15360MiB |      0%      Default |
+-------------------------------+----------------------+----------------------+
```

**📸 Screenshot: `nvidia-smi.png`**

**Key Points for Exam:**
- Tesla T4: 16GB GDDR6, 70W TDP, Turing architecture
- Good for inference (INT8 tensor cores)
- Moderate for training (limited memory)

---

## Step 1.2: Install Container Runtime

**Exam Objectives:** 1.5.c Containerization

```bash
# Install Docker
$ curl -fsSL https://get.docker.com | sh
$ sudo usermod -aG docker $USER

# Install NVIDIA Container Toolkit
$ distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
$ curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
$ curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-docker.list

$ sudo apt-get update
$ sudo apt-get install -y nvidia-container-toolkit
$ sudo systemctl restart docker

# Verify GPU access in containers
$ docker run --rm --gpus all nvidia/cuda:12.2-base nvidia-smi
```

**Key Points for Exam:**
- NVIDIA Container Toolkit enables GPU passthrough
- `--gpus all` flag grants container GPU access
- Runtime can be set in docker-compose with `runtime: nvidia`

---

## Step 1.3: Configure RDMA Networking

**Exam Objectives:** 3.1.b RoCE, 2.1 Network deployment

```bash
# Install Mellanox OFED drivers
$ sudo ./mlnxofedinstall --add-kernel-support

# Verify RDMA device
$ ibstat
CA 'mlx5_0'
    CA type: MT4117
    Number of ports: 1
    Port 1:
        State: Active
        Physical state: LinkUp
        Rate: 25 Gb/sec
        Link layer: Ethernet

# Configure IP for RDMA interface
$ sudo ip addr add <RDMA_S1_IP>/24 dev enp59s0f0
$ sudo ip link set enp59s0f0 mtu 9000
$ sudo ip link set enp59s0f0 up

# Enable RoCEv2
$ sudo cma_roce_mode -d mlx5_0 -p 1 -m 2

# Test RDMA connectivity
# Server 1:
$ rping -s -a <RDMA_S1_IP> -v

# Server 2:
$ rping -c -a <RDMA_S1_IP> -v -C 10
```

**📸 Screenshot: `ibstat.png`**

**Key Points for Exam:**
- RoCEv2 uses UDP/IP, routable across L3
- MTU 9000 (jumbo frames) improves throughput
- PFC required on switch for lossless operation

---

# Phase 2: Data Collection Layer

## Step 2.1: Deploy Kafka

**Exam Objectives:** 1.5.d Orchestration

```bash
# Create directory structure
$ mkdir -p /data/kafka
$ cd /data/kafka

# Create docker-compose.yml (see DCAI_LAB_CONFIGS.md)
$ docker-compose up -d

# Verify
$ docker ps
CONTAINER ID   IMAGE                        STATUS         PORTS
5cb691baf4c5   confluentinc/cp-kafka:7.5.0  Up 2 hours     0.0.0.0:9092->9092/tcp
6e59920ae4ff   confluentinc/cp-zookeeper    Up 2 hours     2181/tcp
```

---

## Step 2.2: Deploy NetFlow Collector

**Exam Objectives:** 1.5.a Network, 4.3.a Telemetry

```bash
# Add GoFlow2 to docker-compose.yml
$ docker-compose up -d goflow2

# Create Kafka topic
$ docker exec kafka kafka-topics --create \
    --topic netflow-raw \
    --bootstrap-server localhost:9092 \
    --partitions 3

# Configure retention (30 days, 50GB)
$ docker exec kafka kafka-configs --alter \
    --entity-type topics \
    --entity-name netflow-raw \
    --add-config retention.ms=2592000000,retention.bytes=53687091200 \
    --bootstrap-server localhost:9092
```

---

## Step 2.3: Configure Network Device Export

**Exam Objectives:** 1.5.a Network

```cisco
! IOS-XE Configuration
flow exporter NETFLOW_TO_MORPHEUS
 destination <S2_IP>
 transport udp 2055
 template data timeout 30

flow monitor MORPHEUS_MONITOR
 exporter NETFLOW_TO_MORPHEUS
 record netflow ipv4 original-input

interface Vlan30
 ip flow monitor MORPHEUS_MONITOR input
 ip flow monitor MORPHEUS_MONITOR output
```

**📸 Screenshot: `netflow_show_exporter.png`**

---

## Step 2.4: Verify Data Flow

**Exam Objectives:** 4.3.a Telemetry

```bash
# Check flows arriving
$ docker exec kafka kafka-console-consumer \
    --bootstrap-server localhost:9092 \
    --topic netflow-raw \
    --from-beginning \
    --max-messages 5

{"type":"NETFLOW_V9","src_addr":"<MAC_STUDIO_IP>","dst_addr":"35.153.98.116",...}

# Check flow rate
$ START=$(docker exec kafka kafka-run-class kafka.tools.GetOffsetShell \
    --broker-list localhost:9092 --topic netflow-raw --time -1 | \
    awk -F: '{sum+=$3} END {print sum}')
$ sleep 60
$ END=$(docker exec kafka kafka-run-class kafka.tools.GetOffsetShell \
    --broker-list localhost:9092 --topic netflow-raw --time -1 | \
    awk -F: '{sum+=$3} END {print sum}')
$ echo "Flows per minute: $((END - START))"
Flows per minute: 427
```

---

# Phase 3: Training Infrastructure

## Step 3.1: NCCL Benchmark (TCP Baseline)

**Exam Objectives:** 4.1 Benchmarks, 2.1 Network deployment

```bash
# Clone NCCL tests
$ git clone https://github.com/NVIDIA/nccl-tests.git
$ cd nccl-tests
$ make MPI=1 CUDA_HOME=/usr/local/cuda

# Run TCP baseline
$ NCCL_DEBUG=INFO NCCL_IB_DISABLE=1 \
  mpirun -np 2 --host <S1_IP>:1,<S2_IP>:1 \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1

# Results:
#       size    algbw   busbw
  1073741824    3.44    6.88    # 3.4 GB/s over TCP
```

**📸 Screenshot: `nccl_benchmark_tcp.png`**

---

## Step 3.2: NCCL Benchmark (RDMA)

**Exam Objectives:** 4.1 Benchmarks, 3.1.b RoCE

```bash
# Run with RDMA
$ NCCL_DEBUG=INFO NCCL_IB_HCA=mlx5_0 NCCL_SOCKET_IFNAME=enp59s0f0 \
  mpirun -np 2 --host <RDMA_S1_IP>:1,<RDMA_S2_IP>:1 \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1

# Expected Results:
#       size    algbw   busbw
  1073741824   12.31   24.62    # ~12 GB/s over RDMA
```

**📸 Screenshot: `nccl_benchmark_rdma.png`**

**Key Points for Exam:**
- RDMA provides ~3.5x improvement over TCP
- Critical for distributed training efficiency
- Requires lossless network (PFC/ECN)

---

## Step 3.3: Distributed Training

**Exam Objectives:** 1.1.b Training

```bash
# Launch training on Server 1 (rank 0)
$ torchrun --nproc_per_node=1 --nnodes=2 --node_rank=0 \
    --master_addr=<RDMA_S1_IP> --master_port=29500 \
    train_autoencoder.py

# Launch training on Server 2 (rank 1)
$ torchrun --nproc_per_node=1 --nnodes=2 --node_rank=1 \
    --master_addr=<RDMA_S1_IP> --master_port=29500 \
    train_autoencoder.py

# Monitor GPU during training
$ watch -n 1 nvidia-smi
```

---

# Phase 4: Inference Infrastructure

## Step 4.1: Deploy Triton Inference Server

**Exam Objectives:** 1.1.c Inference, 2.2 Compute deployment

```bash
# Pull Triton image
$ docker pull nvcr.io/nvidia/tritonserver:24.01-py3

# Create model repository
$ mkdir -p /mnt/storage1/models/netflow-autoencoder/1

# Export trained model to ONNX
$ python export_to_onnx.py --input model.pt --output /mnt/storage1/models/netflow-autoencoder/1/model.onnx

# Create config.pbtxt (see DCAI_LAB_CONFIGS.md)

# Start Triton
$ docker run -d --gpus all --name triton \
    -p 8000:8000 -p 8001:8001 -p 8002:8002 \
    -v /mnt/storage1/models:/models \
    nvcr.io/nvidia/tritonserver:24.01-py3 \
    tritonserver --model-repository=/models

# Verify
$ curl localhost:8000/v2/health/ready
# Response: (empty = healthy)

$ curl localhost:8000/v2/models
# Lists loaded models
```

**📸 Screenshot: `triton_models.png`**

---

## Step 4.2: Benchmark Inference Performance

**Exam Objectives:** 4.1 Benchmarks

```bash
# Install perf_analyzer
$ docker run -it --rm --net host \
    nvcr.io/nvidia/tritonserver:24.01-py3-sdk \
    perf_analyzer -m netflow-autoencoder \
    --concurrency-range 1:16 \
    -u localhost:8000

# Results:
Concurrency: 8
Throughput: 9,727 infer/sec
Latency p99: 8.2 ms
```

---

## Step 4.3: Deploy Morpheus Pipeline

**Exam Objectives:** 1.1.c Inference, 1.5.c Containerization

```bash
# Pull Morpheus image
$ docker pull nvcr.io/nvidia/morpheus/morpheus:24.10-runtime

# Run pipeline
$ docker run --gpus all -it --rm \
    -v /mnt/storage1/morpheus:/workspace \
    nvcr.io/nvidia/morpheus/morpheus:24.10-runtime \
    morpheus run pipeline-nlp \
    --config /workspace/netflow_pipeline.yaml
```

---

# Phase 5: Monitoring Infrastructure

## Step 5.1: Configure Splunk HEC

**Exam Objectives:** 4.2 Monitoring, 4.3.c Alerts

```bash
# Enable HEC in Splunk
# Settings → Data Inputs → HTTP Event Collector → Global Settings
# Enable: Yes
# Enable SSL: No (for lab)

# Create HEC token
# Settings → Data Inputs → HTTP Event Collector → New Token
# Name: morpheus
# Source type: _json
# Index: morpheus

# Test HEC
$ curl -k http://<SPLUNK_IP>:8088/services/collector/event \
    -H "Authorization: Splunk YOUR_TOKEN" \
    -d '{"event": "test"}'
```

---

## Step 5.2: Deploy GPU Monitoring

**Exam Objectives:** 4.2 Monitoring, 4.3.a Telemetry

```bash
# Start nvidia-smi telemetry
$ nvidia-smi dmon -s pucvmet -d 10 | while read line; do
    curl -k http://<SPLUNK_IP>:8088/services/collector/event \
        -H "Authorization: Splunk YOUR_TOKEN" \
        -d "{\"event\": \"$line\", \"sourcetype\": \"nvidia-smi\"}"
done &
```

---

## Step 5.3: Create Splunk Dashboards

**Exam Objectives:** 4.2 Monitoring

Create dashboards for:
1. GPU Health (temperature, utilization, memory)
2. Inference Metrics (throughput, latency)
3. Detection Events (anomalies, alerts)
4. Network Telemetry (flow rates, errors)

**📸 Screenshot: `splunk_gpu_dashboard.png`**
**📸 Screenshot: `splunk_detection_dashboard.png`**

---

# Phase 6: Integration and Testing

## Step 6.1: End-to-End Test

**Exam Objectives:** 4.1 Benchmarks, 4.4 Troubleshooting

```bash
# 1. Verify data collection
$ docker exec kafka kafka-console-consumer \
    --bootstrap-server localhost:9092 \
    --topic netflow-raw \
    --max-messages 1

# 2. Check Morpheus processing
$ docker logs morpheus | tail -20

# 3. Verify Triton inference
$ curl localhost:8000/v2/models/netflow-autoencoder/stats

# 4. Check Splunk ingestion
# index=morpheus | head 10

# 5. Monitor GPU health
$ nvidia-smi
```

---

## Step 6.2: Generate Test Traffic

```bash
# Generate synthetic anomalous traffic for testing
$ hping3 -S -p 443 --flood target-ip  # SYN flood (controlled lab)

# Or use traffic replay
$ tcpreplay -i eth0 --topspeed attack_traffic.pcap
```

---

# Exam Objective Coverage Matrix

| Phase | Step | Exam Objectives Covered |
|-------|------|-------------------------|
| 1 | GPU Verify | 1.5.b, 2.2 |
| 1 | Container Setup | 1.5.c |
| 1 | RDMA Config | 2.1, 3.1.b |
| 2 | Kafka Deploy | 1.5.d |
| 2 | NetFlow Collector | 1.5.a, 4.3.a |
| 2 | Network Config | 1.5.a |
| 3 | NCCL TCP | 4.1, 2.1 |
| 3 | NCCL RDMA | 4.1, 3.1.b |
| 3 | Distributed Training | 1.1.b |
| 4 | Triton Deploy | 1.1.c, 2.2 |
| 4 | Inference Benchmark | 4.1 |
| 4 | Morpheus Pipeline | 1.1.c, 1.5.c |
| 5 | Splunk HEC | 4.2, 4.3.c |
| 5 | GPU Monitoring | 4.2, 4.3.a |
| 5 | Dashboards | 4.2 |
| 6 | E2E Test | 4.1, 4.4 |

---

# Appendix: Quick Reference Commands

## GPU Commands

```bash
nvidia-smi                          # GPU status
nvidia-smi -q                       # Detailed info
nvidia-smi dmon                     # Live monitoring
nvidia-smi --query-gpu=...          # Custom queries
```

## RDMA Commands

```bash
ibstat                              # RDMA device status
ibv_devinfo                         # Device capabilities
rping -s/-c                         # RDMA ping test
ib_write_bw                         # Bandwidth test
```

## Kafka Commands

```bash
kafka-topics --list                 # List topics
kafka-topics --describe             # Topic details
kafka-console-consumer              # Read messages
kafka-configs --alter               # Modify settings
```

## Docker Commands

```bash
docker ps                           # Running containers
docker logs <container>             # Container logs
docker stats                        # Resource usage
docker exec -it <container> bash    # Shell access
```

## Triton Commands

```bash
curl localhost:8000/v2/health/ready # Health check
curl localhost:8000/v2/models       # List models
perf_analyzer -m <model>            # Benchmark
```

---

*This walkthrough aligns with DCAI exam objectives and provides hands-on experience with AI infrastructure components.*
