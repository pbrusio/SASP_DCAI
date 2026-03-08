# Morpheus Deployment Details

## Complete Build-Out Documentation

**Date:** February 27, 2026  
**Platform:** NVIDIA Morpheus 25.06 on Tesla T4 GPUs

---

## Table of Contents

1. [Prerequisites and Dependencies](#prerequisites-and-dependencies)
2. [GPU Driver Installation](#gpu-driver-installation)
3. [Docker and NVIDIA Container Toolkit](#docker-and-nvidia-container-toolkit)
4. [Storage Configuration](#storage-configuration)
5. [Triton Inference Server](#triton-inference-server)
6. [Morpheus Runtime](#morpheus-runtime)
7. [Pipeline Execution](#pipeline-execution)
8. [Kafka Message Bus](#kafka-message-bus)
9. [Splunk HEC Integration](#splunk-hec-integration)
10. [Available Models and Pipelines](#available-models-and-pipelines)
11. [Troubleshooting Encountered](#troubleshooting-encountered)

---

## Prerequisites and Dependencies

### Server Hardware

| Component | Server 1 (t4server1) | Server 2 (t4server2) |
|-----------|---------------------|---------------------|
| Model | Cisco UCS C220 M5 | Cisco UCS C240 M5 |
| GPU | NVIDIA Tesla T4 (16GB GDDR6) | NVIDIA Tesla T4 (16GB GDDR6) |
| RAM | 512 GB | 512 GB |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| Kernel | 5.15.0-170-generic | 5.15.0-170-generic |

### Network Configuration

| Network | IP Address | Purpose |
|---------|------------|---------|
| Management (S1) | <S1_IP> | SSH, Docker, Triton |
| Management (S2) | <S2_IP> | SSH, Docker, Kafka |
| RDMA (S1) | <RDMA_S1_IP> | GPU communication |
| RDMA (S2) | <RDMA_S2_IP> | GPU communication |

---

## GPU Driver Installation

### Initial State Issues

Both servers initially had the `nouveau` open-source driver loaded, which blocks NVIDIA driver installation.

### Nouveau Blacklisting

```bash
# Create blacklist file
sudo bash -c 'echo -e "blacklist nouveau\noptions nouveau modeset=0" > /etc/modprobe.d/blacklist-nouveau.conf'

# Update initramfs
sudo update-initramfs -u

# Reboot
sudo reboot
```

### NVIDIA Driver Installation

```bash
# Verify nouveau is unloaded
lsmod | grep nouveau
# Should return nothing

# Download driver (version 590.48.01)
wget https://us.download.nvidia.com/tesla/590.48.01/NVIDIA-Linux-x86_64-590.48.01.run
chmod +x NVIDIA-Linux-x86_64-590.48.01.run

# Install (select: NVIDIA Proprietary, No DKMS, No 32-bit)
sudo ./NVIDIA-Linux-x86_64-590.48.01.run

# Verify installation
nvidia-smi
```

### Verified Driver Output

```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 590.48.01              Driver Version: 590.48.01      CUDA Version: 13.1    |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
|   0  Tesla T4                       Off | 00000000:5E:00.0 Off  |                    0 |
| N/A   39C    P8               9W /  70W |      0MiB / 15360MiB  |      0%      Default |
+-----------------------------------------+------------------------+----------------------+
```

### Enable Persistence Mode

```bash
sudo nvidia-smi -pm 1
```

---

## Docker and NVIDIA Container Toolkit

### Docker Installation

```bash
sudo apt update
sudo apt install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

### NVIDIA Container Toolkit Installation

```bash
# Add NVIDIA GPG key
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

# Add repository
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install
sudo apt update
sudo apt install -y nvidia-container-toolkit
```

### Configure Docker Runtime

```bash
# Configure NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker

# Verify GPU access in Docker
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

---

## Storage Configuration

### Problem: Root Partition Too Small

Default Ubuntu install left only 54GB on root, insufficient for Morpheus images (~15GB each).

### Solution: Redirect Docker Storage

**Server 1:** Used `/mnt/storage1` (880GB SSD)

```bash
# Stop Docker
sudo systemctl stop docker

# Create Docker data directory
sudo mkdir -p /mnt/storage1/docker

# Configure Docker
sudo tee /etc/docker/daemon.json << 'EOF'
{
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    },
    "data-root": "/mnt/storage1/docker"
}
EOF

# Restart Docker
sudo systemctl start docker

# Verify
docker info | grep "Docker Root Dir"
# Output: Docker Root Dir: /mnt/storage1/docker
```

**Server 2:** Used `/data` (916GB SSD)

```bash
sudo mkdir -p /data/docker
sudo tee /etc/docker/daemon.json << 'EOF'
{
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    },
    "data-root": "/data/docker"
}
EOF
```

---

## Triton Inference Server

### Pull Triton Models Image

```bash
docker pull nvcr.io/nvidia/morpheus/morpheus-tritonserver-models:25.06
```

### Extract Models to Host

```bash
# Create models directory
mkdir -p /mnt/storage1/triton-models

# Extract models from container
docker run --rm \
  -v /mnt/storage1/triton-models:/models \
  nvcr.io/nvidia/morpheus/morpheus-tritonserver-models:25.06 \
  cp -r /models/* /models/

# Verify models
ls /mnt/storage1/triton-models/
```

### Available Models

| Model | Type | Purpose |
|-------|------|---------|
| `abp-nvsmi-xgb` | XGBoost | Crypto mining detection (nvidia-smi data) |
| `abp-pcap-xgb` | XGBoost | Network anomaly detection (PCAP data) |
| `phishing-bert-onnx` | BERT/ONNX | Phishing email detection |
| `ransomw-model-short-rf` | Random Forest | Ransomware detection (short sequences) |
| `ransomw-model-medium-rf` | Random Forest | Ransomware detection (medium sequences) |
| `ransomw-model-long-rf` | Random Forest | Ransomware detection (long sequences) |
| `log-parsing-onnx` | ONNX | Log structure extraction |
| `sid-minibert-onnx` | MiniBERT/ONNX | Sensitive Information Detection (PII) |

### Start Triton Server

```bash
docker run --rm -d \
  --name triton-server \
  --runtime=nvidia \
  --gpus=all \
  -p 8000:8000 \
  -p 8001:8001 \
  -p 8002:8002 \
  -v /mnt/storage1/triton-models:/models \
  nvcr.io/nvidia/tritonserver:25.01-py3 \
  tritonserver --model-repository=/models --model-control-mode=explicit --load-model=*
```

### Verify Triton is Running

```bash
# Check container
docker logs triton-server

# Test HTTP endpoint
curl -s localhost:8000/v2/health/ready
# Output: {"ready":true}

# List loaded models
curl -s localhost:8000/v2/models | jq
```

### Triton Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8000 | HTTP | REST API |
| 8001 | gRPC | High-performance RPC |
| 8002 | HTTP | Metrics (Prometheus format) |

---

## Morpheus Runtime

### Pull Morpheus Image

```bash
docker pull nvcr.io/nvidia/morpheus/morpheus:25.06-runtime
```

### Image Size

- `morpheus:25.06-runtime`: ~15GB
- `morpheus-tritonserver-models:25.06`: ~8GB

### Clone Morpheus Repository (for example data)

```bash
cd /mnt/storage1
git clone --depth 1 https://github.com/nv-morpheus/Morpheus.git

# Install Git LFS for large files
sudo apt install -y git-lfs
git lfs install

# Fetch example data
cd Morpheus
./scripts/fetch_data.py fetch examples
```

---

## Pipeline Execution

### ABP (Anomalous Behavior Profiling) Pipeline

This pipeline detects cryptocurrency mining by analyzing nvidia-smi metrics.

#### Command

```bash
docker run --rm -ti --runtime=nvidia --gpus=all --net=host \
  -v /mnt/storage1/Morpheus:/workspace \
  -w /workspace \
  nvcr.io/nvidia/morpheus/morpheus:25.06-runtime \
  morpheus --log_level=DEBUG \
  run --num_threads=8 --pipeline_batch_size=1024 --model_max_batch_size=1024 \
  pipeline-fil --columns_file=data/columns_fil.txt \
  from-file --filename=examples/data/nvsmi.jsonlines \
  deserialize \
  preprocess \
  inf-triton --model_name=abp-nvsmi-xgb --server_url=localhost:8000 \
  monitor --description="Inference Rate" --smoothing=0.001 --unit=inf \
  add-class \
  serialize --include 'mining' \
  to-file --filename=.tmp/output/abp_nvsmi_detections.jsonlines --overwrite
```

#### Pipeline Stages Explained

| Stage | Purpose |
|-------|---------|
| `from-file` | Read input JSON lines |
| `deserialize` | Parse JSON to Morpheus messages |
| `preprocess` | Transform data for ML model |
| `inf-triton` | Send to Triton for GPU inference |
| `monitor` | Display throughput metrics |
| `add-class` | Add classification labels |
| `serialize` | Convert back to JSON |
| `to-file` | Write output |

#### Results

```
Inference Rate: 9,727.82 inf/sec
Total samples: 1,242
Pipeline completed successfully
```

#### Output Sample

```json
{"mining":false}
{"mining":false}
...
{"mining":true}
{"mining":true}
```

The model correctly identified the transition from normal GPU usage to cryptocurrency mining behavior in the test dataset.

---

## Kafka Message Bus

### Deployment Location

Server 2 (t4server2) - `/data/kafka/`

### Docker Compose Configuration

```yaml
version: '3'
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    volumes:
      - ./zookeeper-data:/var/lib/zookeeper/data
      - ./zookeeper-logs:/var/lib/zookeeper/log

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: kafka
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://<S2_IP>:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    volumes:
      - ./kafka-data:/var/lib/kafka/data
```

### Start Kafka

```bash
cd /data/kafka
docker-compose up -d
docker-compose ps
```

### Create Topics

```bash
docker exec -it kafka kafka-topics --create \
  --bootstrap-server localhost:9092 \
  --topic morpheus-input \
  --partitions 1 \
  --replication-factor 1

docker exec -it kafka kafka-topics --create \
  --bootstrap-server localhost:9092 \
  --topic morpheus-output \
  --partitions 1 \
  --replication-factor 1
```

### Streaming Pipeline Command

```bash
docker run --rm -ti --runtime=nvidia --gpus=all --net=host \
  -v /mnt/storage1/Morpheus:/workspace \
  -w /workspace \
  nvcr.io/nvidia/morpheus/morpheus:25.06-runtime \
  morpheus --log_level=INFO \
  run --num_threads=8 --pipeline_batch_size=1024 --model_max_batch_size=1024 \
  pipeline-fil --columns_file=data/columns_fil.txt \
  from-kafka --bootstrap_servers=<S2_IP>:9092 --input_topic=morpheus-input \
  deserialize \
  preprocess \
  inf-triton --model_name=abp-nvsmi-xgb --server_url=localhost:8000 \
  monitor --description="Inference Rate" --smoothing=0.001 --unit=inf \
  add-class \
  serialize --include 'mining' \
  to-kafka --bootstrap_servers=<S2_IP>:9092 --output_topic=morpheus-output
```

---

## Splunk HEC Integration

### Architecture

```
[Data Sources] → [Kafka] → [Morpheus Pipeline] → [Kafka] → [Python HEC Script] → [Splunk]
```

### HEC Configuration (Splunk Side)

- Endpoint: `https://<splunk-server>:8088/services/collector/event`
- Token: Pre-configured in Splunk
- Index: `morpheus_detections`
- Sourcetype: `morpheus:detection`

### Python HEC Sender Script

```python
#!/usr/bin/env python3
"""
Kafka to Splunk HEC bridge for Morpheus detections
"""
import json
import requests
from kafka import KafkaConsumer

KAFKA_BOOTSTRAP = "<S2_IP>:9092"
KAFKA_TOPIC = "morpheus-output"
SPLUNK_HEC_URL = "https://splunk.example.com:8088/services/collector/event"
SPLUNK_HEC_TOKEN = "your-hec-token"

consumer = KafkaConsumer(
    KAFKA_TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

for message in consumer:
    event = {
        "event": message.value,
        "sourcetype": "morpheus:detection",
        "index": "morpheus_detections"
    }
    
    response = requests.post(
        SPLUNK_HEC_URL,
        headers={"Authorization": f"Splunk {SPLUNK_HEC_TOKEN}"},
        json=event,
        verify=False
    )
    
    if response.status_code != 200:
        print(f"Error sending to Splunk: {response.text}")
```

### Splunk Dashboards Created

| Dashboard | Purpose |
|-----------|---------|
| Crypto Mining Detection | Real-time mining alerts, GPU utilization trends |
| Network Anomalies | Unusual traffic patterns, potential exfiltration |
| Phishing Detection | Email threat analysis, sender reputation |
| Ransomware Indicators | File system behavior anomalies |
| PII Detection | Sensitive data exposure alerts |

---

## Available Models and Pipelines

### Pipeline Types

| Pipeline | CLI Command | Use Case |
|----------|-------------|----------|
| FIL (Forest Inference Library) | `pipeline-fil` | XGBoost/Random Forest models |
| NLP | `pipeline-nlp` | BERT/Transformer models |
| AE (AutoEncoder) | `pipeline-ae` | Anomaly detection |

### Model-Pipeline Mapping

| Model | Pipeline Type | Input Format |
|-------|--------------|--------------|
| abp-nvsmi-xgb | pipeline-fil | nvidia-smi JSON |
| abp-pcap-xgb | pipeline-fil | PCAP features JSON |
| phishing-bert-onnx | pipeline-nlp | Email text |
| ransomw-model-*-rf | pipeline-fil | AppShield features |
| log-parsing-onnx | pipeline-nlp | Raw log lines |
| sid-minibert-onnx | pipeline-nlp | Text content |

### Throughput Benchmarks

| Model | Throughput | GPU Memory |
|-------|------------|------------|
| abp-nvsmi-xgb | 9,727 inf/sec | ~500 MB |
| phishing-bert-onnx | ~1,000 inf/sec | ~2 GB |
| log-parsing-onnx | ~2,000 inf/sec | ~1.5 GB |

---

## Troubleshooting Encountered

### Issue 1: Nouveau Driver Blocking NVIDIA

**Symptom:** `nvidia-smi` returns "NVIDIA-SMI has failed"

**Solution:** Blacklist nouveau and rebuild initramfs (see GPU Driver Installation section)

### Issue 2: Docker Storage Full

**Symptom:** `no space left on device` when pulling images

**Solution:** Redirect Docker data-root to larger volume (see Storage Configuration section)

### Issue 3: Git LFS Not Installed

**Symptom:** `git: 'lfs' is not a git command`

**Solution:**
```bash
sudo apt install -y git-lfs
git lfs install
```

### Issue 4: Pipeline Preprocess Fails

**Symptom:** `TypeError: object of type 'NoneType' has no len()`

**Cause:** Missing `--columns_file` argument for FIL pipeline

**Solution:** Add `--columns_file=data/columns_fil.txt` to pipeline-fil command

### Issue 5: Triton Connection Refused

**Symptom:** `Connection refused` to localhost:8001

**Cause:** Morpheus README showed gRPC port (8001), but HTTP port (8000) works better

**Solution:** Use `--server_url=localhost:8000` for HTTP endpoint

### Issue 6: Docker Compose Not Found

**Symptom:** `docker: unknown command: docker compose`

**Cause:** Ubuntu docker.io package doesn't include compose plugin

**Solution:**
```bash
sudo apt install -y docker-compose
docker-compose up -d  # Note the hyphen
```

### Issue 7: VIC RDMA Not Exposing Devices

**Symptom:** `ibv_devices` returns empty list

**Cause:** Cisco VIC 1457 doesn't expose RDMA verbs for GPU communication (designed for NVMe-oF, not GPUDirect)

**Solution:** Purchased Mellanox ConnectX-4 LX NICs for true RoCE/RDMA support

---

## Current State Summary

### Working Components

| Component | Server | Status |
|-----------|--------|--------|
| NVIDIA Driver 590.48.01 | Both | ✅ Installed |
| Docker + NVIDIA Runtime | Both | ✅ Configured |
| Triton Inference Server | S1 | ✅ Running |
| Morpheus Runtime | S1 | ✅ Available |
| Kafka (Zookeeper + Broker) | S2 | ✅ Running |
| ABP Pipeline | S1 | ✅ Tested (9,727 inf/sec) |
| ConnectX-4 RDMA | Both | ✅ Working (2.91 GB/s) |
| QoS/PFC/ECN | Switch | ✅ Configured |

### Pending Work

- [ ] Multi-node Triton deployment (load balancing)
- [ ] Streaming pipeline with live data
- [ ] Full Splunk dashboard deployment
- [ ] Custom model training for NetFlow data
- [ ] Production Kafka configuration (replication, persistence)

---

## File Locations Summary

| Item | Path |
|------|------|
| Morpheus repo | `/mnt/storage1/Morpheus/` |
| Triton models | `/mnt/storage1/triton-models/` |
| Docker data (S1) | `/mnt/storage1/docker/` |
| Docker data (S2) | `/data/docker/` |
| Kafka data | `/data/kafka/` |
| Pipeline output | `/mnt/storage1/Morpheus/.tmp/output/` |
| Example data | `/mnt/storage1/Morpheus/examples/data/` |
| Column definitions | `/mnt/storage1/Morpheus/data/columns_fil.txt` |

---

## Commands Quick Reference

### Start Services

```bash
# Triton (S1)
docker start triton-server

# Kafka (S2)
cd /data/kafka && docker-compose up -d
```

### Run ABP Pipeline

```bash
docker run --rm -ti --runtime=nvidia --gpus=all --net=host \
  -v /mnt/storage1/Morpheus:/workspace \
  -w /workspace \
  nvcr.io/nvidia/morpheus/morpheus:25.06-runtime \
  morpheus --log_level=INFO \
  run --num_threads=8 --pipeline_batch_size=1024 --model_max_batch_size=1024 \
  pipeline-fil --columns_file=data/columns_fil.txt \
  from-file --filename=examples/data/nvsmi.jsonlines \
  deserialize \
  preprocess \
  inf-triton --model_name=abp-nvsmi-xgb --server_url=localhost:8000 \
  monitor --description="Inference Rate" --smoothing=0.001 --unit=inf \
  add-class \
  serialize --include 'mining' \
  to-file --filename=.tmp/output/abp_nvsmi_detections.jsonlines --overwrite
```

### Check GPU Status

```bash
nvidia-smi
docker exec triton-server nvidia-smi
```

### Check Kafka Topics

```bash
docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092
```

---

*This document captures approximately 2 weeks of hands-on Morpheus deployment work, including troubleshooting, configuration, and validation.*
