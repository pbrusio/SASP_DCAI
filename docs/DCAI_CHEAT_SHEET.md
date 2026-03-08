# 300-640 DCAI Cheat Sheet — NX-OS Commands, Acronyms & Lab Mapping

> Built from live SASP lab work on Nexus 93180YC-EX (NX-OS 10.3(8))
> Aligned to Implementing Cisco Data Center AI Infrastructure v1.0 (300-640)

---

# PART 1: ACRONYM REFERENCE

## Networking / Lossless Ethernet

| Acronym | Full Name | What It Does | Exam Objective |
|---------|-----------|-------------|----------------|
| **PFC** | Priority-based Flow Control | Sends PAUSE frames per CoS priority to prevent drops on a specific traffic class (e.g., RoCE). Unlike 802.3x PAUSE which stops ALL traffic, PFC is selective. | 3.1.a |
| **ECN** | Explicit Congestion Notification | Marks packets (CE bit in IP header) instead of dropping them when queues fill. Endpoints reduce rate proactively. Works with DCTCP/RoCE CC. | 3.1.a |
| **ETS** | Enhanced Transmission Selection | Allocates bandwidth percentages across traffic classes (e.g., 50% RoCE, 30% storage, 20% best-effort). Part of DCB. | 3.1.a |
| **DCB** | Data Center Bridging | IEEE 802.1Qbb/Qaz umbrella for PFC + ETS + DCBX. Makes Ethernet lossless for storage/RDMA. | 3.1.a |
| **DCBX** | Data Center Bridging Capability Exchange | LLDP-based protocol that auto-negotiates PFC/ETS settings between switch and NIC. Ensures both ends agree on lossless config. | 3.1.a |
| **RoCE** | RDMA over Converged Ethernet | RDMA protocol running directly over Ethernet (v1) or UDP/IP (v2). Enables zero-copy, kernel-bypass networking. | 3.1.b |
| **RoCEv2** | RoCE version 2 | RoCE encapsulated in UDP/IP — routable across L3 boundaries. Uses UDP port 4791. This is what modern AI fabrics use. | 3.1.b |
| **RDMA** | Remote Direct Memory Access | Hardware reads/writes remote server memory without involving the remote CPU or OS kernel. Zero-copy, ultra-low latency. | 3.1.b |
| **QoS** | Quality of Service | Classification, marking, queuing, and scheduling of traffic. In AI DC: ensures RoCE/storage traffic gets lossless treatment. | 3.1.c |
| **DSCP** | Differentiated Services Code Point | 6-bit field in IP header for traffic marking. RoCE typically uses DSCP 26 (AF31). Switch classifies based on this. | 3.1.c |
| **CoS** | Class of Service | 3-bit field in 802.1Q VLAN tag (0-7). PFC operates per CoS value. DSCP maps to CoS for PFC enforcement. | 3.1.c |
| **MTU** | Maximum Transmission Unit | Largest frame size. AI/RoCE requires jumbo frames: 9216 bytes on switch, 9000 on server NICs. | 3.1.c |
| **ECMP** | Equal-Cost Multi-Path | Distributes traffic across multiple equal-cost paths. Critical for leaf-spine AI fabrics to maximize bisection bandwidth. | 3.1.d |
| **LAG** | Link Aggregation Group | Bundles multiple physical links into one logical link for bandwidth + redundancy. Also called port-channel. | 3.1.d |

## Compute / GPU

| Acronym | Full Name | What It Does | Exam Objective |
|---------|-----------|-------------|----------------|
| **NVLink** | NVIDIA Link | High-bandwidth GPU-to-GPU interconnect (up to 900 GB/s on H100). Bypasses PCIe for multi-GPU communication. | 1.5.b |
| **GDR** | GPU Direct RDMA | NIC reads/writes GPU memory directly via PCIe — no CPU staging buffer needed. Requires MOFED + peer_mem kernel module. | 3.1.b |
| **NCCL** | NVIDIA Collective Communications Library | GPU-optimized library for all-reduce, broadcast, etc. Auto-selects transport: NVLink > GDR > IB/RoCE > TCP. | 4.1 |
| **PCIe** | Peripheral Component Interconnect Express | Bus connecting GPU/NIC to CPU. Gen3 x16 = ~16 GB/s, Gen4 x16 = ~32 GB/s, Gen5 x16 = ~64 GB/s. | 2.2 |
| **UCS** | Unified Computing System | Cisco server platform. C-Series (rack) and B-Series (blade). Managed via Intersight or UCSM. | 3.2 |
| **CIMC** | Cisco Integrated Management Controller | BMC for UCS C-Series servers. Web GUI for BIOS, GPU passthrough, vNIC config, power management. | 3.2 |
| **HBM** | High Bandwidth Memory | GPU-attached stacked DRAM. A100=80GB HBM2e (2 TB/s), H100=80GB HBM3 (3.35 TB/s). | 2.2 |

## AI / ML Pipeline

| Acronym | Full Name | What It Does | Exam Objective |
|---------|-----------|-------------|----------------|
| **RAG** | Retrieval-Augmented Generation | LLM queries a knowledge base before answering — reduces hallucination, adds domain-specific data. | 1.1.a |
| **LLM** | Large Language Model | Foundation model trained on text (GPT, LLaMA, Nemotron). Our agents use Nemotron-3-Nano for triage/investigation. | 1.1.d |
| **ONNX** | Open Neural Network Exchange | Portable model format. PyTorch/TF export to ONNX, Triton serves it. Our autoencoder + classifier are ONNX. | 1.1.c |
| **MSE** | Mean Squared Error | Loss function for autoencoders. High MSE = input doesn't match reconstruction = anomaly. Our threshold: 0.05. | 1.1.c |
| **DDP** | Distributed Data Parallel | PyTorch's multi-GPU training strategy. Each GPU has full model copy, gradients synchronized via NCCL all-reduce. | 1.1.b |
| **HEC** | HTTP Event Collector | Splunk's REST API for ingesting data (port 8088). Our pipeline sends detections to Splunk via HEC. | 4.3 |
| **DLQ** | Dead Letter Queue | Kafka topic for failed/unprocessable messages. Our Kafka bridge sends bad detections to `detection-dlq`. | 4.3.d |

## Mellanox / NIC

| Acronym | Full Name | What It Does | Exam Objective |
|---------|-----------|-------------|----------------|
| **MOFED** | Mellanox OpenFabrics Enterprise Distribution | Driver package for ConnectX NICs. Includes `mlx5_core`, `mlx5_ib`, RDMA libraries, `mlnx_qos` tools. | 3.1.b |
| **ConnectX** | Mellanox ConnectX | SmartNIC family. CX-4 LX = 25GbE, CX-5 = 100GbE, CX-6 Dx = 200GbE, CX-7 = 400GbE. Ours: CX-4 LX 25GbE. | 1.5.a |
| **VPI** | Virtual Protocol Interconnect | ConnectX capability to run InfiniBand OR Ethernet on same port. Set via `mlxconfig`. | 3.1.b |
| **GID** | Global Identifier | RoCE endpoint address. Index 0 = RoCEv1, Index 3+ = RoCEv2 (routable). NCCL_IB_GID_INDEX=3. | 3.1.b |

---

# PART 2: NX-OS COMMAND CHEAT SHEET

## Classification — Telling the Switch What Traffic Is (3.1.c QoS)

### What we configured:
The switch needs to identify RoCE traffic. We match on DSCP 26 (AF31) — the marking that Mellanox NICs stamp on RoCE packets — and assign it to qos-group 3.

```
! Create a class-map that matches RoCE traffic by DSCP value
class-map type qos match-all ROCE-CLASSIFY
  match dscp 26
```

**What this means:**
- `type qos` = ingress classification policy (what comes IN)
- `match-all` = ALL conditions must match (only one here)
- `match dscp 26` = DSCP decimal 26 = AF31 = the standard marking for RoCE traffic
- Traffic matching this class gets processed by the linked policy-map

```
! Policy-map that takes classified traffic and assigns it to a queue
policy-map type qos ROCE-CLASSIFY
  class ROCE-CLASSIFY
    set qos-group 3
```

**What this means:**
- `set qos-group 3` = internally tags this traffic as group 3
- qos-group is an internal switch label — it travels with the packet through the switch pipeline
- Queuing and network-qos policies then use qos-group 3 to apply special treatment

### Apply to interface:
```
interface Ethernet1/38
  service-policy type qos input ROCE-CLASSIFY
```
- `type qos input` = apply classification on ingress (incoming packets)

### Verify:
```
n9k# show policy-map interface ethernet 1/38 type qos
```
**Shows:** Hit counts per class — confirms traffic IS being classified

---

## Network QoS — Making a Traffic Class Lossless (3.1.a PFC)

### What we configured:
This is the **system-level** policy that makes qos-group 3 lossless by enabling PFC.

```
policy-map type network-qos ROCE-COMPLETE
  class type network-qos c-8q-nq3
    pause pfc-cos 3
    mtu 9216
  class type network-qos c-8q-nq-default
    mtu 9216
```

**What this means:**
- `type network-qos` = system-wide QoS behavior (not per-interface)
- `c-8q-nq3` = built-in NX-OS class for queue 3 in the 8-queue model
- `pause pfc-cos 3` = **THE KEY COMMAND** — enables PFC on CoS 3. When queue 3 fills, the switch sends 802.1Qbb PAUSE frames to the sender for priority 3 ONLY
- `mtu 9216` = allows jumbo frames (required for RoCE efficiency)
- Default class also gets MTU 9216 so normal traffic can use jumbos too

### Apply at system level:
```
system qos
  service-policy type network-qos ROCE-COMPLETE
```
- `system qos` = global config context (applies to ALL ports)
- Only ONE network-qos policy can be active system-wide

### Verify:
```
n9k# show policy-map system type network-qos
```
**Shows:** Which classes have PFC enabled, MTU per class, drop policy

---

## Ingress Queuing — Buffer Management (3.1.a Congestion Control)

### What we configured:
Controls how deep the ingress buffers can fill before PFC fires.

```
policy-map type queuing ROCE-INQ
  class type queuing c-in-q3
    pause buffer-size 27456 pause-threshold 12480 resume-threshold 12480
```

**What this means:**
- `type queuing` + `c-in-q3` = ingress queue for traffic class 3
- `buffer-size 27456` = total ingress buffer allocated (bytes). This is the platform minimum on 93180YC-EX
- `pause-threshold 12480` = when buffer fills to this level, send PFC PAUSE
- `resume-threshold 12480` = when buffer drains to this level, send PFC RESUME (un-pause)
- Same pause/resume = aggressive PFC — fire as soon as possible, resume immediately

### Apply at system level:
```
system qos
  service-policy type queuing input ROCE-INQ
```

### Verify:
```
n9k# show queuing interface ethernet 1/38
```
**Shows:** Per-queue buffer depths, pause/resume thresholds, packet/byte counters

---

## Interface-Level PFC — Enabling Per-Port (3.1.a PFC)

### What we configured:
Each interface that carries RoCE traffic must have PFC explicitly enabled.

```
interface Ethernet1/38
  description S2-RoCE-Mellanox-25G
  switchport
  switchport access vlan 810
  mtu 9216
  no negotiate auto
  speed 25000
  priority-flow-control mode on
  service-policy type qos input ROCE-CLASSIFY
  no shutdown
```

**What each line means:**
| Command | Purpose |
|---------|---------|
| `mtu 9216` | Jumbo frames for RoCE efficiency (header overhead amortization) |
| `no negotiate auto` | Force speed, don't auto-negotiate (stability for RoCE) |
| `speed 25000` | Lock at 25 Gbps |
| `priority-flow-control mode on` | **Enable PFC on this port** — works with network-qos `pause pfc-cos 3` |
| `service-policy type qos input ROCE-CLASSIFY` | Classify incoming traffic (DSCP 26 → qos-group 3) |

---

## ECN — Marking Instead of Dropping (3.1.a Congestion Control)

```
policy-map type queuing ECN-ENABLED
  class type queuing ROCE-QUEUE
    bandwidth percent 50
    random-detect minimum-threshold 150 kbytes maximum-threshold 3000 kbytes \
      drop-probability 100 weight 0 ecn
```

**What this means:**
- `random-detect` = WRED (Weighted Random Early Detection)
- `minimum-threshold 150 kbytes` = start marking packets when queue reaches 150 KB
- `maximum-threshold 3000 kbytes` = 100% mark probability at 3000 KB
- `ecn` = mark the CE (Congestion Experienced) bit instead of dropping
- Endpoints running DCTCP or RoCE CC see the ECN mark and voluntarily slow down
- **PFC is the safety net, ECN is the proactive signal** — together they provide lossless + low-latency

---

## ETS — Bandwidth Allocation (3.1.a Congestion Control)

```
policy-map type queuing AI-QUEUING
  class type queuing ROCE-QUEUE
    bandwidth percent 50
  class type queuing STORAGE-QUEUE
    bandwidth percent 30
  class type queuing class-default
    bandwidth percent 20
```

**What this means:**
- ETS guarantees minimum bandwidth per traffic class during congestion
- RoCE gets at least 50% — can burst higher if other classes are idle
- `bandwidth percent` is a minimum guarantee, not a hard cap
- Ensures training/inference traffic isn't starved by bulk data transfers

---

# PART 3: VERIFICATION COMMANDS — What to Run & What to Look For

## PFC Status (3.1.a) — "Is PFC actually firing?"

```
n9k# show interface priority-flow-control
```

**Output from our lab:**
```
Port               Mode Oper(sobm)  RxPPP      TxPPP
Ethernet1/32       On   On (sobm)   0          22145    ← PFC fired! 22K pause frames sent TO the VM
Ethernet1/38       On   On (sobm)   0          0        ← Zero — Mellanox handles its own flow control
Ethernet1/44       On   On (sobm)   22145      0        ← Received 22K pause frames FROM Eth1/32
```

**What this tells you:**
- `TxPPP` = pause frames SENT by this port (telling the connected device to slow down)
- `RxPPP` = pause frames RECEIVED by this port (this port was told to slow down)
- Our PFC demo: VM (Eth1/32) was told to pause 22,145 times while RDMA traffic (Eth1/38) flowed uninterrupted
- This proves PFC **selectively** pauses non-priority senders to protect RoCE flows

---

## QoS Policy Verification (3.1.c)

```
n9k# show policy-map system type network-qos
```
**Look for:** `Congestion-control: PFC-cos value: 3` under the c-8q-nq3 class

```
n9k# show policy-map interface ethernet 1/38 type qos
```
**Look for:** Hit counts on `ROCE-CLASSIFY` class — confirms DSCP 26 packets are being matched

```
n9k# show class-map type qos
```
**Look for:** Your class-map definitions — `match dscp 26` for RoCE

---

## Queuing & Buffers (3.1.a)

```
n9k# show queuing interface ethernet 1/38
```
**Look for:**
- `q3` (queue 3) has PFC enabled
- Buffer allocation sizes
- Packet counts per queue (shows traffic distribution)

---

## Interface Counters & Errors (4.3.b System Health)

```
n9k# show interface ethernet 1/38 counters
```
**Look for:** InOctets, OutOctets, InUcastPkts, OutUcastPkts — traffic is flowing

```
n9k# show interface ethernet 1/38 counters errors
```
**Look for:** Rcv-Err, OutDiscards — should be 0 if PFC is working (no drops on lossless class)

---

## DCBX Negotiation

```
n9k# show lldp neighbors detail
```
**Look for:** DCBX TLVs showing PFC/ETS negotiation with ConnectX NIC

---

# PART 4: SERVER-SIDE COMMANDS (RoCE / RDMA)

## Mellanox NIC Configuration (3.1.b RoCEv2)

```bash
# Set RoCEv2 mode (routable — UDP/IP encapsulation)
sudo cma_roce_mode -d mlx5_0 -p 1 -m 2

# Trust DSCP markings from the application (not CoS from switch)
sudo mlnx_qos -i enp59s0f0 --trust=dscp

# Enable PFC on priority 3 (must match switch: pfc-cos 3)
sudo mlnx_qos -i enp59s0f0 --pfc=0,0,0,1,0,0,0,0
#                                     ^ priority 3 = ON

# Verify all QoS settings on the NIC
mlnx_qos -i enp59s0f0
```

**What `--pfc=0,0,0,1,0,0,0,0` means:**
- 8 priorities (0-7), one bit each
- Only priority 3 has PFC enabled
- Must match switch config (`pause pfc-cos 3`)
- If these don't match, PFC won't work — packets get dropped instead of paused

---

## RDMA Verification (3.1.b, 4.1)

```bash
# Check RDMA device is active
ibstat
# Look for: State: Active, Rate: 25 Gb/sec, Link layer: Ethernet

# Detailed device info (firmware, GID table)
ibv_devinfo
# Look for: port_state: PORT_ACTIVE, link_layer: Ethernet

# RDMA ping test (verify RDMA connectivity end-to-end)
# Server 1: rping -s -a <RDMA_S1_IP> -v
# Server 2: rping -c -a <RDMA_S1_IP> -v -C 10
# Look for: "rdma-ping-0: ABCDEFG..." = RDMA working

# RDMA bandwidth test
# Server 1: ib_write_bw -d mlx5_0
# Server 2: ib_write_bw -d mlx5_0 <RDMA_S1_IP>
# Our result: 3050 MB/sec peak (24.4 Gbps on 25G link = 97.6% efficiency)
```

---

## NCCL Benchmark (4.1 Benchmarks)

```bash
# TCP baseline (disable RDMA)
mpirun -np 2 -H <S1_IP>:1,<S2_IP>:1 \
  -x NCCL_IB_DISABLE=1 -x NCCL_SOCKET_IFNAME=eno1 \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1
# Result: 0.12 GB/s @ 1GB

# RDMA/RoCE (enable RDMA)
mpirun -np 2 -H <S1_IP>:1,<S2_IP>:1 \
  -x NCCL_IB_DISABLE=0 -x NCCL_IB_HCA=mlx5_0 \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1
# Result: 2.91 GB/s @ 1GB — 24.3x faster, 93.1% wire efficiency
```

**Key NCCL environment variables:**
| Variable | Value | Purpose |
|----------|-------|---------|
| `NCCL_IB_DISABLE=0` | 0 = use RDMA | Forces NCCL to use RoCE instead of TCP |
| `NCCL_IB_HCA=mlx5_0` | NIC device name | Tells NCCL which RDMA NIC to use |
| `NCCL_SOCKET_IFNAME=eno1` | Management NIC | Control plane (MPI bootstrap) uses this |
| `NCCL_IB_GID_INDEX=3` | GID table index | Selects RoCEv2 addressing (routable) |
| `NCCL_NET_GDR_LEVEL=0` | 0 = disabled | GPU Direct RDMA (needs peer_mem module) |

---

# PART 5: EXAM OBJECTIVE MAPPING — What We Did Today

## 3.1.a Congestion Control (PFC, ECN, ETS) — 30% of exam

| What We Did | Evidence | Command |
|-------------|----------|---------|
| Configured PFC on N9K for RoCE | `pause pfc-cos 3` in network-qos policy | `show policy-map system type network-qos` |
| Set ingress buffer thresholds | `pause-threshold 12480 resume-threshold 12480` | `show queuing interface ethernet 1/38` |
| **Triggered real PFC pause frames** | 22,145 PFC frames on Eth1/32 Tx | `show interface priority-flow-control` |
| Proved PFC is selective | Eth1/38 (RDMA) had 0 PFC while VM was paused | `show interface priority-flow-control` |
| Demonstrated oversubscription scenario | 34.5 Gbps into 25G port | `ib_write_bw` + `iperf3 -u -S 0x68` |

**Key insight for exam:** PFC fires per-priority. If you don't mark traffic with the right DSCP, it lands in the default queue (no PFC) and gets **tail-dropped** instead of flow-controlled. DSCP marking is critical.

---

## 3.1.b RDMA over Converged Ethernet (RoCE, RoCEv2) — 30% of exam

| What We Did | Evidence | Command |
|-------------|----------|---------|
| Deployed ConnectX-4 LX 25GbE NICs | `ibstat` shows Active/LinkUp | `ibstat` |
| Configured RoCEv2 mode | `cma_roce_mode -m 2` | `cma_roce_mode -d mlx5_0 -p 1 -m 2` |
| Set DSCP trust on NIC | NIC trusts app DSCP, not switch CoS | `mlnx_qos --trust=dscp` |
| Enabled PFC on NIC priority 3 | Matches switch `pfc-cos 3` | `mlnx_qos --pfc=0,0,0,1,0,0,0,0` |
| Verified RDMA connectivity | `rping` successful | `rping -c -a <RDMA_S1_IP>` |
| Benchmarked RDMA bandwidth | 3050 MB/s = 97.6% of 25G | `ib_write_bw` |
| Ran NCCL all-reduce over RoCE | 2.91 GB/s (24.3x vs TCP) | `all_reduce_perf` |

**Key insight for exam:** RoCEv2 (mode 2) is routable because it uses UDP/IP encapsulation. RoCEv1 is L2 only. Always use v2 for production AI fabrics.

---

## 3.1.c Quality of Service (QoS) — 30% of exam

| What We Did | Evidence | Command |
|-------------|----------|---------|
| Created QoS classification policy | `match dscp 26` → `set qos-group 3` | `show class-map type qos` |
| Applied classification to interfaces | Input QoS on Eth1/32, 1/38, 1/44 | `show policy-map interface type qos` |
| Set jumbo MTU (9216) | Required for RoCE efficiency | `show interface ethernet 1/38` |
| Configured VLAN 810 for RoCE | Isolated RDMA network | `show vlan id 810` |

**Key insight for exam:** QoS has THREE policy types on NX-OS — they work together:
1. `type qos` = **classification** (ingress: what IS this traffic?)
2. `type network-qos` = **system behavior** (is this class lossless? what MTU?)
3. `type queuing` = **scheduling** (how much bandwidth? what buffers?)

---

## 2.1 Network Deployment for AI Workloads — 30% of exam

| What We Did | Evidence |
|-------------|----------|
| Dedicated RDMA VLAN (810) with jumbo frames | Isolated from management traffic |
| Cross-VLAN routing via N9K SVIs | VLAN 800 ↔ 810 for multi-subnet connectivity |
| Forced 25G speed (no autoneg) | Stability for RDMA — `no negotiate auto; speed 25000` |
| 3-port RoCE fabric (S1, S2, VM) | Eth1/32, 1/38, 1/44 all with PFC + QoS |

---

## 2.2 Compute Deployment for AI Workloads — 30% of exam

| What We Did | Evidence |
|-------------|----------|
| UCS C220 M5 + C240 M5 with Tesla T4 GPUs | PCIe 3.0 x16, 16 GB VRAM each |
| Triton Inference Server on GPU | 2 models loaded: netflow-anomaly (autoencoder), auth-risk (classifier) |
| Morpheus AI pipeline (CPU+GPU) | KafkaSource → Deserialize → Triton inference → WriteToKafka |
| Containerized GPU workloads | `--runtime nvidia -e NVIDIA_VISIBLE_DEVICES=all` |

---

## 4.1 Benchmarks — 20% of exam

| Benchmark | Result | Tool |
|-----------|--------|------|
| RDMA write bandwidth | 3050 MB/s (97.6% of 25G) | `ib_write_bw` |
| NCCL all-reduce (RDMA) | 2.91 GB/s | `all_reduce_perf` |
| NCCL all-reduce (TCP) | 0.12 GB/s | `all_reduce_perf` |
| RDMA vs TCP speedup | **24.3x** | Comparison |
| PFC pause frames triggered | 22,145 frames | `show interface priority-flow-control` |
| Triton inference | Both models READY, T4 GPU, 214 MiB VRAM | `curl localhost:8000/v2/health/ready` |

---

## 4.3 Monitoring — 20% of exam

| What We Did | Exam Sub-objective | Evidence |
|-------------|-------------------|----------|
| Switch metrics collector to Splunk | 4.3.a Operational telemetry | `switch_metrics_nxapi.py` → Splunk HEC every 30s |
| PFC counters, throughput, errors | 4.3.b System health | Per-port metrics: octets, packets, PFC rx/tx, errors |
| Splunk RoCE Network dashboard | 4.3.c Alerts | Throughput gauges, PFC over time, error tracking |
| NetFlow → Kafka → ML pipeline → Splunk | 4.3.d Log correlation | Full detection pipeline with anomaly scores |

---

# PART 6: PFC DEEP DIVE — How It Actually Works

```
         NORMAL OPERATION                    CONGESTION (PFC FIRES)

   VM ──25G──▶ N9K ◀──25G── S2        VM ──25G──▶ N9K ◀──25G── S2
              │                                   │
              ▼ 25G                                ▼ 25G
              S1                                   S1

   VM: 10G iperf3 (DSCP AF31)          VM: 10G iperf3 (DSCP AF31)
   S2: 24.5G ib_write_bw               S2: 24.5G ib_write_bw
   ────────────────────                 ────────────────────
   Combined: 34.5G → S1 (25G port)     N9K queue 3 fills up!

                                        N9K sends PFC PAUSE to VM (Eth1/32 Tx)
                                        → "Stop sending priority 3 for X quanta"

                                        VM pauses, S2 RDMA keeps flowing
                                        → RDMA has HW flow control (no PFC needed)

                                        Result: 22,145 PFC frames
                                        Zero drops on RoCE traffic
```

**Why DSCP matters:** Without `-S 0x68` (DSCP AF31) on the iperf3 traffic, it lands in qos-group 0 (best-effort). Best-effort has no PFC. The switch tail-drops it. No pause frames. The test only works when traffic is classified into the lossless class.

---

# PART 7: QUICK REFERENCE CARD

## "I need to set up RoCE on a Nexus switch" — Do these in order:

```
1. feature qos

2. class-map type qos match-all ROCE-CLASSIFY
     match dscp 26

3. policy-map type qos ROCE-CLASSIFY
     class ROCE-CLASSIFY
       set qos-group 3

4. policy-map type network-qos ROCE-NQ
     class type network-qos c-8q-nq3
       pause pfc-cos 3
       mtu 9216

5. system qos
     service-policy type network-qos ROCE-NQ

6. interface Ethernet1/X
     mtu 9216
     priority-flow-control mode on
     service-policy type qos input ROCE-CLASSIFY
```

## "I need to verify RoCE is working" — Check these:

```
show interface priority-flow-control          ← PFC mode On? Any pause frames?
show policy-map system type network-qos       ← PFC-cos 3 enabled?
show policy-map interface Eth1/X type qos     ← Traffic being classified?
show queuing interface ethernet 1/X           ← Buffer depths, queue counters?
show interface ethernet 1/X counters errors   ← Zero errors/drops?
```

## "I need to verify RDMA on the server" — Check these:

```
ibstat                                        ← Device Active? Rate 25 Gb/sec?
ibv_devinfo                                   ← port_state: PORT_ACTIVE?
mlnx_qos -i <iface>                          ← PFC on priority 3? Trust DSCP?
rping -c -a <remote_ip> -v -C 10             ← RDMA connectivity works?
ib_write_bw -d mlx5_0 <remote_ip>            ← Bandwidth near line rate?
```

---

*Built from SASP lab — Nexus 93180YC-EX (NX-OS 10.3(8)), UCS C220/C240 M5, ConnectX-4 LX 25GbE, Tesla T4*
*300-640 DCAI v1.0 Exam Blueprint aligned*
