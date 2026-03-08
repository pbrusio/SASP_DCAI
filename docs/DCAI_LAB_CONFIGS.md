# DCAI Lab Configurations

> **Actual configurations from the SASP lab environment**
> 
> Copy-paste ready configs with explanations mapped to DCAI exam objectives.

---

## Lab Topology

> For the full 6-host topology (including Workstation, Mac Studio, and Splunk), see [`README.md`](../README.md).
> For NX-OS QoS/PFC/ECN command reference, see [`DCAI_CHEAT_SHEET.md`](./DCAI_CHEAT_SHEET.md).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SASP LAB TOPOLOGY                                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        MANAGEMENT NETWORK                           │   │
│  │                         <MGMT_SUBNET>/24                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                      │                      │                   │
│           │ .34                  │ .32                  │ .33               │
│  ┌────────┴────────┐    ┌────────┴────────┐    ┌────────┴────────┐        │
│  │   Server 1      │    │   Server 2      │    │   Cat9200L      │        │
│  │   C220 M5       │    │   C240 M5       │    │   Switch        │        │
│  │                 │    │                 │    │                 │        │
│  │   Tesla T4      │    │   Tesla T4      │    │   NetFlow       │        │
│  │   Morpheus      │    │   Kafka         │    │   Source        │        │
│  │   Triton        │    │   GoFlow2       │    │                 │        │
│  │   Splunk Fwd    │    │   Training      │    │                 │        │
│  └────────┬────────┘    └────────┬────────┘    └─────────────────┘        │
│           │                      │                                         │
│           │ .34                  │ .32                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         RDMA NETWORK                                │   │
│  │                        <RDMA_SUBNET>/24                              │   │
│  │                    (ConnectX-4 LX 25GbE)                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# 1. Network Device Configurations

## 1.1 IOS-XE NetFlow Configuration (Cat9200L)

**Exam Objective:** 1.5.a Network, 4.3.a Operational telemetry

```cisco
! ============================================
! NetFlow Configuration for AI Data Collection
! Cat9200L - IOS-XE 17.x
! ============================================

! Define the flow exporter
flow exporter NETFLOW_TO_MORPHEUS
 description Export NetFlow to SASP for ML analysis
 destination <S2_IP>
 transport udp 2055
 template data timeout 30
 option interface-table
 option sampler-table

! Define the flow record (using flexible NetFlow)
flow record NETFLOW_RECORD
 match ipv4 source address
 match ipv4 destination address
 match ipv4 protocol
 match transport source-port
 match transport destination-port
 collect counter bytes
 collect counter packets
 collect timestamp sys-uptime first
 collect timestamp sys-uptime last
 collect transport tcp flags

! Define the flow monitor
flow monitor MORPHEUS_MONITOR
 exporter NETFLOW_TO_MORPHEUS
 record NETFLOW_RECORD
 cache timeout active 60

! Apply to interfaces
interface GigabitEthernet1/0/1
 description Uplink to Core
 ip flow monitor MORPHEUS_MONITOR input
 ip flow monitor MORPHEUS_MONITOR output

interface Vlan30
 description User VLAN
 ip flow monitor MORPHEUS_MONITOR input
 ip flow monitor MORPHEUS_MONITOR output

! Verification commands
! show flow exporter NETFLOW_TO_MORPHEUS statistics
! show flow monitor MORPHEUS_MONITOR cache
! show flow monitor MORPHEUS_MONITOR statistics
```

**Screenshot Placeholder:** `[netflow_show_exporter.png]`

---

## 1.2 ISE Syslog Configuration

**Exam Objective:** 4.3.d Log correlation

```
! ISE Configuration (GUI Path)
! Administration → System → Logging → Remote Logging Targets

Remote Logging Target:
  Name: SASP-Collector
  IP Address: <S2_IP>
  Port: 514
  Protocol: UDP
  
Logging Categories:
  ☑ AAA Audit
  ☑ AAA Diagnostics
  ☑ Authentication Flow
  ☑ RADIUS Accounting
  ☑ TACACS Accounting
```

---

## 1.3 QoS Configuration for RoCE (Nexus Example)

**Exam Objective:** 3.1.a Congestion control, 3.1.c QoS

```cisco
! ============================================
! QoS for RoCE Traffic - Nexus 9000
! ============================================

! Enable QoS and PFC
feature qos

! Define class-maps
class-map type qos match-all ROCE-TRAFFIC
  match dscp 26

class-map type qos match-all STORAGE-TRAFFIC
  match dscp 24

class-map type queuing ROCE-QUEUE
  match qos-group 3

class-map type queuing STORAGE-QUEUE
  match qos-group 4

! Define network-qos policy (system level)
policy-map type network-qos LOSSLESS-POLICY
  class type network-qos c-8q-nq3
    pause pfc-cos 3
    mtu 9216
  class type network-qos c-8q-nq-default
    mtu 9216

! Apply network-qos
system qos
  service-policy type network-qos LOSSLESS-POLICY

! Define QoS policy for classification
policy-map type qos CLASSIFY-AI-TRAFFIC
  class ROCE-TRAFFIC
    set qos-group 3
  class STORAGE-TRAFFIC
    set qos-group 4
  class class-default
    set qos-group 0

! Define queuing policy
policy-map type queuing AI-QUEUING
  class type queuing ROCE-QUEUE
    bandwidth percent 50
  class type queuing STORAGE-QUEUE
    bandwidth percent 30
  class type queuing class-default
    bandwidth percent 20

! Apply to interfaces
interface Ethernet1/1
  description GPU Server 1
  mtu 9216
  service-policy type qos input CLASSIFY-AI-TRAFFIC
  service-policy type queuing output AI-QUEUING
  priority-flow-control mode on

! Verification
! show queuing interface ethernet 1/1
! show policy-map interface ethernet 1/1
! show interface priority-flow-control
```

---

## 1.4 ECN Configuration

**Exam Objective:** 3.1.a Congestion control (ECN)

```cisco
! ============================================
! ECN Configuration - Nexus 9000
! ============================================

! Enable ECN on queuing policy
policy-map type queuing ECN-ENABLED
  class type queuing ROCE-QUEUE
    bandwidth percent 50
    random-detect minimum-threshold 150 kbytes maximum-threshold 3000 kbytes drop-probability 100 weight 0 ecn
  class type queuing class-default
    bandwidth percent 50

! Apply to interface
interface Ethernet1/1
  service-policy type queuing output ECN-ENABLED

! Verification
! show queuing interface ethernet 1/1 | include ECN
```

---

# 2. Server Configurations

## 2.1 Docker Compose - Server 2 (Data Collection)

**Exam Objective:** 1.5.c Containerization, 1.5.d Orchestration

```yaml
# /data/kafka/docker-compose.yml
# Server 2 (<S2_IP>) - Data Collection Stack

version: '3'
services:
  # Zookeeper for Kafka coordination
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    volumes:
      - ./zookeeper-data:/var/lib/zookeeper/data
      - ./zookeeper-logs:/var/lib/zookeeper/log
    restart: unless-stopped

  # Kafka message broker
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
      # Performance tuning for AI workloads
      KAFKA_NUM_PARTITIONS: 3
      KAFKA_LOG_RETENTION_HOURS: 720  # 30 days
      KAFKA_LOG_RETENTION_BYTES: 53687091200  # 50GB
    volumes:
      - ./kafka-data:/var/lib/kafka/data
    restart: unless-stopped

  # GoFlow2 - NetFlow collector
  goflow2:
    image: netsampler/goflow2:latest
    container_name: goflow2
    depends_on:
      - kafka
    ports:
      - "2055:2055/udp"   # NetFlow v5/v9
      - "6343:6343/udp"   # sFlow
    command: ["-transport=kafka", "-transport.kafka.brokers=kafka:9092", "-transport.kafka.topic=netflow-raw", "-format=json"]
    restart: unless-stopped

  # Syslog collector
  syslog:
    image: balabit/syslog-ng:latest
    container_name: syslog
    ports:
      - "514:514/udp"
      - "514:514/tcp"
    volumes:
      - ./syslog-ng.conf:/etc/syslog-ng/syslog-ng.conf
      - ./syslog-data:/var/log
    restart: unless-stopped
```

---

## 2.2 Syslog-ng Configuration

**Exam Objective:** 4.3.d Log correlation

```conf
# /data/kafka/syslog-ng.conf
@version: 3.38
@include "scl.conf"

# Accept syslog from network
source s_network {
    udp(port(514));
    tcp(port(514));
};

# Parse ISE logs
parser p_ise {
    csv-parser(
        columns("timestamp", "ise_node", "message_code", "message")
        delimiters(",")
    );
};

# Write to file (for backup)
destination d_file {
    file("/var/log/ise.log");
};

# Future: Send to Kafka
# destination d_kafka {
#     kafka(
#         bootstrap-servers("kafka:9092")
#         topic("ise-raw")
#     );
# };

# Log path
log {
    source(s_network);
    destination(d_file);
};
```

---

## 2.3 Docker Compose - Server 1 (Inference)

**Exam Objective:** 1.5.c Containerization, 1.1.c Inference

```yaml
# /mnt/storage1/morpheus/docker-compose.yml
# Server 1 (<S1_IP>) - Inference Stack

version: '3.8'
services:
  # Triton Inference Server
  triton:
    image: nvcr.io/nvidia/tritonserver:24.01-py3
    container_name: triton
    runtime: nvidia
    ports:
      - "8000:8000"   # HTTP
      - "8001:8001"   # gRPC
      - "8002:8002"   # Metrics
    volumes:
      - ./models:/models
    command: ["tritonserver", "--model-repository=/models", "--strict-model-config=false"]
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    restart: unless-stopped

  # Morpheus pipeline (example)
  morpheus:
    image: nvcr.io/nvidia/morpheus/morpheus:24.10-runtime
    container_name: morpheus
    runtime: nvidia
    depends_on:
      - triton
    volumes:
      - ./workspace:/workspace
      - ./models:/models
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - KAFKA_BOOTSTRAP_SERVERS=<S2_IP>:9092
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    restart: unless-stopped
```

---

## 2.4 Triton Model Repository Structure

**Exam Objective:** 1.1.c Inference, 3.2 Compute deployment

```
/mnt/storage1/models/
├── netflow-autoencoder/
│   ├── config.pbtxt
│   └── 1/
│       └── model.onnx
├── auth-classifier/
│   ├── config.pbtxt
│   └── 1/
│       └── model.onnx
├── syslog-anomaly/
│   ├── config.pbtxt
│   └── 1/
│       └── model.onnx
└── abp-nvsmi-xgb/
    ├── config.pbtxt
    └── 1/
        └── xgboost.json
```

**Example config.pbtxt:**

```protobuf
# /mnt/storage1/models/netflow-autoencoder/config.pbtxt
name: "netflow-autoencoder"
backend: "onnxruntime"
max_batch_size: 64

input [
  {
    name: "input"
    data_type: TYPE_FP32
    dims: [ 12 ]  # 12 features
  }
]

output [
  {
    name: "output"
    data_type: TYPE_FP32
    dims: [ 12 ]  # reconstruction
  },
  {
    name: "anomaly_score"
    data_type: TYPE_FP32
    dims: [ 1 ]
  }
]

instance_group [
  {
    count: 2
    kind: KIND_GPU
    gpus: [ 0 ]
  }
]

dynamic_batching {
  preferred_batch_size: [ 16, 32, 64 ]
  max_queue_delay_microseconds: 100
}
```

---

# 3. RDMA/RoCE Configurations

## 3.1 ConnectX-4 Driver Installation

**Exam Objective:** 3.1.b RoCE/RoCEv2

```bash
#!/bin/bash
# install_mlx_drivers.sh
# Install Mellanox OFED for ConnectX-4

# Download MLNX_OFED
wget https://content.mellanox.com/ofed/MLNX_OFED-5.8-1.0.1.1/MLNX_OFED_LINUX-5.8-1.0.1.1-ubuntu22.04-x86_64.tgz

# Extract
tar -xzf MLNX_OFED_LINUX-5.8-1.0.1.1-ubuntu22.04-x86_64.tgz
cd MLNX_OFED_LINUX-5.8-1.0.1.1-ubuntu22.04-x86_64

# Install
sudo ./mlnxofedinstall --add-kernel-support

# Load modules
sudo modprobe mlx5_core
sudo modprobe mlx5_ib
sudo modprobe ib_uverbs

# Update initramfs
sudo update-initramfs -u

# Reboot required
sudo reboot
```

---

## 3.2 RDMA Network Configuration

**Exam Objective:** 3.1.b RoCE/RoCEv2

```bash
# /etc/netplan/01-rdma.yaml
# RDMA Network Configuration

network:
  version: 2
  ethernets:
    enp59s0f0:  # ConnectX-4 port
      addresses:
        - <RDMA_S1_IP>/24  # Server 1
      mtu: 9000
      # No gateway - isolated RDMA network
```

```bash
# Apply netplan
sudo netplan apply

# Verify interface
ip addr show enp59s0f0
```

---

## 3.3 RoCE Configuration

**Exam Objective:** 3.1.b RoCE/RoCEv2

```bash
#!/bin/bash
# configure_roce.sh
# Configure RoCE on ConnectX-4

# Set RoCE mode to RoCEv2 (routable)
sudo cma_roce_mode -d mlx5_0 -p 1 -m 2

# Set DSCP to Priority mapping
# DSCP 26 -> Priority 3 (matches switch config)
sudo mlnx_qos -i enp59s0f0 --trust=dscp

# Enable PFC on priority 3
sudo mlnx_qos -i enp59s0f0 --pfc=0,0,0,1,0,0,0,0

# Verify settings
mlnx_qos -i enp59s0f0

# Set ECN on the interface
sudo sysctl -w net.ipv4.tcp_ecn=1
```

---

## 3.4 RDMA Verification Commands

**Exam Objective:** 4.1 Benchmarks

```bash
# ============================================
# RDMA Verification and Testing
# ============================================

# Check RDMA devices
$ ibstat
CA 'mlx5_0'
    CA type: MT4117
    Number of ports: 1
    Port 1:
        State: Active
        Physical state: LinkUp
        Rate: 25 Gb/sec
        Link layer: Ethernet

# Check device info
$ ibv_devinfo
hca_id: mlx5_0
    transport: InfiniBand (0)
    fw_ver: 14.32.1010
    node_guid: b8ce:f603:0038:a71a
    sys_image_guid: b8ce:f603:0038:a71a
    vendor_id: 0x02c9
    vendor_part_id: 4117
    hw_ver: 0x0
    phys_port_cnt: 1
        port: 1
            state: PORT_ACTIVE (4)
            max_mtu: 4096 (5)
            active_mtu: 4096 (5)
            sm_lid: 0
            port_lid: 0
            port_lmc: 0x00
            link_layer: Ethernet

# Test RDMA connectivity (run on both servers)
# Server 1:
$ rping -s -a <RDMA_S1_IP> -v

# Server 2:
$ rping -c -a <RDMA_S1_IP> -v -C 10
ping data: rdma-ping-0: ABCDEFGHIJKLMNOPQRSTUVWXYZ
ping data: rdma-ping-1: BCDEFGHIJKLMNOPQRSTUVWXYZAB
...
client DISCONNECT EVENT...

# Bandwidth test
# Server 1:
$ ib_write_bw -d mlx5_0

# Server 2:
$ ib_write_bw -d mlx5_0 <RDMA_S1_IP>
---------------------------------------------------------------------------------------
                    RDMA_Write BW Test
 Dual-port       : OFF
 Number of qps   : 1
 Connection type : RC
 TX depth        : 128
 CQ Moderation   : 100
 Mtu             : 4096[B]
 Link type       : Ethernet
 GID index       : 3
 Max inline data : 0[B]
 rdma_cm QPs     : OFF
 Data ex. method : Ethernet
---------------------------------------------------------------------------------------
 #bytes     #iterations    BW peak[MB/sec]    BW average[MB/sec]   MsgRate[Mpps]
 65536      5000           3050.00            3048.50              0.048749
---------------------------------------------------------------------------------------
```

---

# 4. NCCL Configuration

## 4.1 NCCL Environment Variables

**Exam Objective:** 2.1 Network deployment, 4.1 Benchmarks

```bash
# /etc/profile.d/nccl.sh
# NCCL Configuration for Distributed Training

# Basic settings
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=ALL

# Network interface selection
export NCCL_SOCKET_IFNAME=enp59s0f0  # RDMA interface
export NCCL_IB_HCA=mlx5_0            # Use RDMA

# Performance tuning
export NCCL_IB_DISABLE=0             # Enable InfiniBand/RoCE
export NCCL_NET_GDR_LEVEL=0          # GPU Direct RDMA (if supported)
export NCCL_IB_GID_INDEX=3           # RoCEv2 GID index

# Timeout settings
export NCCL_IB_TIMEOUT=23
export NCCL_IB_RETRY_CNT=7

# Tree reduction algorithm (good for small messages)
export NCCL_ALGO=Tree

# Buffer sizes
export NCCL_BUFFSIZE=4194304         # 4MB buffer
```

---

## 4.2 NCCL Benchmark Script

**Exam Objective:** 4.1 Benchmarks

```bash
#!/bin/bash
# run_nccl_benchmark.sh
# Run NCCL all-reduce benchmark across 2 servers

# Source environment
source /etc/profile.d/nccl.sh

# Build NCCL tests (first time only)
# git clone https://github.com/NVIDIA/nccl-tests.git
# cd nccl-tests
# make MPI=1 CUDA_HOME=/usr/local/cuda NCCL_HOME=/usr/lib/x86_64-linux-gnu

# Run all-reduce benchmark
mpirun -np 2 \
  --host <RDMA_S1_IP>:1,<RDMA_S2_IP>:1 \
  -x NCCL_DEBUG=INFO \
  -x NCCL_IB_HCA=mlx5_0 \
  -x NCCL_SOCKET_IFNAME=enp59s0f0 \
  -x LD_LIBRARY_PATH \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1

# Expected output with RDMA:
# #       size    time   algbw   busbw
# ...
# 1073741824    87.23   12.31   24.62   # ~12 GB/s with RoCE
```

---

## 4.3 TCP vs RDMA Comparison Script

**Exam Objective:** 4.1 Benchmarks

```bash
#!/bin/bash
# compare_tcp_rdma.sh
# Compare NCCL performance: TCP vs RDMA

echo "=== Testing TCP (baseline) ==="
NCCL_IB_DISABLE=1 NCCL_SOCKET_IFNAME=eno1 \
mpirun -np 2 --host <S1_IP>:1,<S2_IP>:1 \
  ./build/all_reduce_perf -b 1G -e 1G -f 2 -g 1 2>&1 | tee tcp_results.txt

echo ""
echo "=== Testing RDMA (RoCE) ==="
NCCL_IB_DISABLE=0 NCCL_IB_HCA=mlx5_0 NCCL_SOCKET_IFNAME=enp59s0f0 \
mpirun -np 2 --host <RDMA_S1_IP>:1,<RDMA_S2_IP>:1 \
  ./build/all_reduce_perf -b 1G -e 1G -f 2 -g 1 2>&1 | tee rdma_results.txt

echo ""
echo "=== Comparison ==="
echo "TCP Bandwidth:  $(grep '1073741824' tcp_results.txt | awk '{print $5}') GB/s"
echo "RDMA Bandwidth: $(grep '1073741824' rdma_results.txt | awk '{print $5}') GB/s"
```

---

# 5. Distributed Training Configuration

## 5.1 PyTorch Distributed Training Script

**Exam Objective:** 1.1.b Training, 2.1 Network deployment

```python
#!/usr/bin/env python3
"""
train_distributed.py
Distributed training across 2x Tesla T4 GPUs
DCAI Exam Objective: 1.1.b Training
"""

import os
import torch
import torch.distributed as dist
import torch.nn as nn
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, DistributedSampler

# Simple autoencoder for NetFlow anomaly detection
class NetFlowAutoencoder(nn.Module):
    def __init__(self, input_dim=12, latent_dim=4):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 8),
            nn.ReLU(),
            nn.Linear(8, latent_dim),
            nn.ReLU()
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 8),
            nn.ReLU(),
            nn.Linear(8, input_dim)
        )
    
    def forward(self, x):
        z = self.encoder(x)
        return self.decoder(z)

def setup(rank, world_size):
    """Initialize distributed training"""
    os.environ['MASTER_ADDR'] = '<RDMA_S1_IP>'  # Server 1
    os.environ['MASTER_PORT'] = '29500'
    
    # Initialize NCCL backend
    dist.init_process_group(
        backend='nccl',
        rank=rank,
        world_size=world_size
    )

def cleanup():
    dist.destroy_process_group()

def train(rank, world_size, epochs=10):
    setup(rank, world_size)
    
    # Create model and move to GPU
    model = NetFlowAutoencoder().to(rank)
    model = DDP(model, device_ids=[rank])
    
    # Loss and optimizer
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    
    # Load data (simplified - would load from Kafka/file)
    # dataset = NetFlowDataset('/data/training/netflow.jsonl')
    # sampler = DistributedSampler(dataset, num_replicas=world_size, rank=rank)
    # dataloader = DataLoader(dataset, batch_size=256, sampler=sampler)
    
    # Training loop
    for epoch in range(epochs):
        # sampler.set_epoch(epoch)  # Shuffle differently each epoch
        
        # Simulated batch for demo
        batch = torch.randn(256, 12).to(rank)
        
        optimizer.zero_grad()
        output = model(batch)
        loss = criterion(output, batch)  # Reconstruction loss
        loss.backward()
        optimizer.step()
        
        if rank == 0:
            print(f"Epoch {epoch}, Loss: {loss.item():.4f}")
    
    # Save model (only on rank 0)
    if rank == 0:
        torch.save(model.module.state_dict(), '/mnt/storage1/models/netflow-autoencoder.pt')
    
    cleanup()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--local_rank', type=int, default=0)
    args = parser.parse_args()
    
    world_size = int(os.environ.get('WORLD_SIZE', 2))
    train(args.local_rank, world_size)
```

---

## 5.2 Launch Distributed Training

**Exam Objective:** 1.1.b Training

```bash
#!/bin/bash
# launch_training.sh
# Launch distributed training across both servers

# On Server 1 (rank 0):
torchrun \
  --nproc_per_node=1 \
  --nnodes=2 \
  --node_rank=0 \
  --master_addr=<RDMA_S1_IP> \
  --master_port=29500 \
  train_distributed.py

# On Server 2 (rank 1):
# torchrun \
#   --nproc_per_node=1 \
#   --nnodes=2 \
#   --node_rank=1 \
#   --master_addr=<RDMA_S1_IP> \
#   --master_port=29500 \
#   train_distributed.py
```

---

# 6. Monitoring Configurations

## 6.1 GPU Monitoring Script

**Exam Objective:** 4.2 Monitoring, 4.3.a Telemetry

```bash
#!/bin/bash
# gpu_monitor.sh
# Continuous GPU monitoring with output to file

while true; do
    nvidia-smi --query-gpu=timestamp,name,pci.bus_id,driver_version,pstate,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.free,memory.used,power.draw,power.limit \
        --format=csv >> /var/log/gpu_metrics.csv
    sleep 10
done
```

---

## 6.2 Splunk HEC Forwarder

**Exam Objective:** 4.2 Monitoring, 4.3.c Alerts

```python
#!/usr/bin/env python3
"""
splunk_forwarder.py
Forward Morpheus detections to Splunk
"""

import json
import requests
from kafka import KafkaConsumer

SPLUNK_HEC_URL = "https://<SPLUNK_IP>:8088/services/collector/event"
SPLUNK_HEC_TOKEN = "your-hec-token"

def forward_to_splunk(event):
    """Send event to Splunk HEC"""
    payload = {
        "event": event,
        "sourcetype": "morpheus:detection",
        "index": "morpheus"
    }
    
    headers = {
        "Authorization": f"Splunk {SPLUNK_HEC_TOKEN}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(
        SPLUNK_HEC_URL,
        json=payload,
        headers=headers,
        verify=False
    )
    return response.status_code == 200

def main():
    consumer = KafkaConsumer(
        'morpheus-detections',
        bootstrap_servers='<S2_IP>:9092',
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )
    
    for message in consumer:
        detection = message.value
        if forward_to_splunk(detection):
            print(f"Forwarded: {detection.get('detection_type', 'unknown')}")

if __name__ == "__main__":
    main()
```

---

## 6.3 Splunk Dashboard - GPU Health

**Exam Objective:** 4.2 Monitoring

```xml
<!-- GPU Health Dashboard -->
<dashboard>
  <label>GPU Infrastructure Health</label>
  
  <row>
    <panel>
      <title>GPU Temperature</title>
      <chart>
        <search>
          <query>
            index=infrastructure sourcetype=nvidia-smi
            | timechart avg(temperature_gpu) by name
          </query>
        </search>
        <option name="charting.chart">line</option>
      </chart>
    </panel>
    
    <panel>
      <title>GPU Utilization</title>
      <chart>
        <search>
          <query>
            index=infrastructure sourcetype=nvidia-smi
            | timechart avg(utilization_gpu) by name
          </query>
        </search>
        <option name="charting.chart">area</option>
      </chart>
    </panel>
  </row>
  
  <row>
    <panel>
      <title>GPU Memory Usage</title>
      <chart>
        <search>
          <query>
            index=infrastructure sourcetype=nvidia-smi
            | eval pct_used = (memory_used / memory_total) * 100
            | timechart avg(pct_used) by name
          </query>
        </search>
        <option name="charting.chart">area</option>
      </chart>
    </panel>
    
    <panel>
      <title>Power Draw</title>
      <chart>
        <search>
          <query>
            index=infrastructure sourcetype=nvidia-smi
            | timechart avg(power_draw) by name
          </query>
        </search>
        <option name="charting.chart">line</option>
      </chart>
    </panel>
  </row>
</dashboard>
```

---

# 7. Troubleshooting Commands

## 7.1 Quick Health Check Script

**Exam Objective:** 4.4 Troubleshooting

```bash
#!/bin/bash
# health_check.sh
# Quick health check for SASP infrastructure

echo "=== GPU Status ==="
nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total \
    --format=csv,noheader

echo ""
echo "=== RDMA Status ==="
ibstat | grep -E "State|Rate"

echo ""
echo "=== Docker Containers ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "=== Kafka Topics ==="
docker exec kafka kafka-topics --list --bootstrap-server localhost:9092 2>/dev/null

echo ""
echo "=== NetFlow Count (last hour) ==="
docker exec kafka kafka-run-class kafka.tools.GetOffsetShell \
    --broker-list localhost:9092 --topic netflow-raw --time -1 2>/dev/null | \
    awk -F: '{sum+=$3} END {print sum " flows"}'

echo ""
echo "=== Triton Health ==="
curl -s localhost:8000/v2/health/ready && echo " Triton: Ready" || echo " Triton: Not Ready"

echo ""
echo "=== Disk Usage ==="
df -h /data /mnt/storage1 2>/dev/null | grep -v Filesystem
```

---

## 7.2 Common Issues Reference

**Exam Objective:** 4.4 Troubleshooting

```bash
# ============================================
# TROUBLESHOOTING REFERENCE
# ============================================

# Issue: NCCL timeout during training
# Symptoms: Training hangs, "NCCL timeout" in logs
# Debug:
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=ALL
# Check:
# 1. Firewall: sudo ufw status
# 2. Port reachable: nc -zv <RDMA_S1_IP> 29500
# 3. RDMA working: rping -c -a <RDMA_S1_IP>

# Issue: GPU out of memory
# Symptoms: CUDA OOM error
# Check:
nvidia-smi
# Solutions:
# 1. Reduce batch size
# 2. Use gradient checkpointing
# 3. Use mixed precision: torch.cuda.amp

# Issue: Triton model load failure
# Symptoms: Model shows UNAVAILABLE in model repository
# Debug:
curl localhost:8000/v2/models/model-name
docker logs triton | tail -50
# Check:
# 1. config.pbtxt syntax
# 2. Model file exists
# 3. Input/output dimensions match

# Issue: No NetFlow arriving
# Symptoms: Empty Kafka topic
# Check:
sudo tcpdump -i any udp port 2055 -c 5
docker logs goflow2 | tail -20
# Verify:
# 1. NetFlow exporter config on switch
# 2. Firewall allows UDP 2055
# 3. GoFlow2 container running

# Issue: RDMA not working (fallback to TCP)
# Symptoms: NCCL shows "TCP" instead of "IB"
# Check:
ibstat
ibv_devinfo
# Verify:
# 1. Kernel modules loaded: lsmod | grep mlx
# 2. IP configured on RDMA interface
# 3. PFC enabled on switch
# 4. DSCP marking correct
```

---

# 8. Kafka Topic Management

## 8.1 Topic Configuration

**Exam Objective:** 1.5.d Orchestration

```bash
# Create topic with retention settings
docker exec kafka kafka-topics --create \
  --topic netflow-raw \
  --bootstrap-server localhost:9092 \
  --partitions 3 \
  --replication-factor 1 \
  --config retention.ms=2592000000 \
  --config retention.bytes=53687091200

# Verify topic configuration
docker exec kafka kafka-topics --describe \
  --topic netflow-raw \
  --bootstrap-server localhost:9092

# Modify retention
docker exec kafka kafka-configs --alter \
  --entity-type topics \
  --entity-name netflow-raw \
  --add-config retention.ms=2592000000,retention.bytes=53687091200 \
  --bootstrap-server localhost:9092

# Check topic size
docker exec kafka kafka-log-dirs --describe \
  --bootstrap-server localhost:9092 \
  --topic-list netflow-raw
```

---

# Screenshot Placeholders

The following screenshots should be captured and added to the documentation:

| Screenshot | Description | Exam Objective |
|------------|-------------|----------------|
| `nvidia-smi.png` | GPU status output | 1.5.b, 4.2 |
| `ibstat.png` | RDMA device status | 3.1.b |
| `nccl_benchmark_tcp.png` | NCCL over TCP results | 4.1 |
| `nccl_benchmark_rdma.png` | NCCL over RDMA results | 4.1 |
| `triton_models.png` | Triton model repository | 1.1.c |
| `splunk_gpu_dashboard.png` | GPU monitoring dashboard | 4.2 |
| `splunk_detection_dashboard.png` | Detection dashboard | 4.2 |
| `netflow_show_exporter.png` | IOS-XE NetFlow config | 1.5.a |
| `kafka_topics.png` | Kafka topic list | 1.5.d |
| `cimc_gpu.png` | CIMC GPU passthrough | 3.2 |

---

*Document Version: 1.0*
*Last Updated: February 2026*
*Lab Environment: SASP (Secure AI Security Platform)*
