# NCCL All-Reduce Benchmark Results

## TCP vs RDMA/RoCE Comparison

**Date:** February 27, 2026  
**Test:** `all_reduce_perf -b 8 -e 1G -f 2 -g 1`

---

## Environment

| Component | Server 1 (t4server1) | Server 2 (t4server2) |
|-----------|---------------------|---------------------|
| Model | Cisco UCS C220 M5 | Cisco UCS C240 M5 |
| GPU | Tesla T4 (16GB) | Tesla T4 (16GB) |
| PCIe | 3.0 x16 | 3.0 x16 |
| RDMA NIC | ConnectX-4 LX 25GbE | ConnectX-4 LX 25GbE |
| IP (RDMA) | <RDMA_S1_IP> | <RDMA_S2_IP> |
| IP (Mgmt) | <S1_IP> | <S2_IP> |

### Switch Configuration

| Setting | Value |
|---------|-------|
| Switch | Nexus 9000 |
| Ports | E1/38 (S2), E1/42 (S1) |
| VLAN | 810 (access mode) |
| MTU | 9216 (jumbo frames) |
| Speed | 25G (forced) |
| PFC | Enabled |
| FEC | Off |

---

## Results Summary

| Metric | TCP (1GbE) | RDMA/RoCE (25GbE) | Improvement |
|--------|------------|-------------------|-------------|
| **Bandwidth @ 1GB** | 0.12 GB/s | 2.91 GB/s | **24.3x** |
| **Time for 1GB** | 9.19 seconds | 368 ms | **25x faster** |
| **Wire Efficiency** | N/A | 93.1% | Near line-rate |
| **Avg Bus Bandwidth** | 0.064 GB/s | 1.18 GB/s | **18.4x** |

---

## Detailed Results

### Test 1: TCP Baseline (1GbE Management Network)

```
Network: Socket (TCP/IP)
Interface: eno1 (192.168.0.x)
NCCL_IB_DISABLE=1
```

| Size | Count | Time (μs) | Bandwidth (GB/s) |
|------|-------|-----------|------------------|
| 8 B | 2 | 170 | 0.00 |
| 1 KB | 256 | 271 | 0.00 |
| 64 KB | 16384 | 852 | 0.08 |
| 1 MB | 262144 | 9,275 | 0.11 |
| 16 MB | 4194304 | 144,163 | 0.12 |
| 256 MB | 67108864 | 2,296,709 | 0.12 |
| 1 GB | 268435456 | 9,185,453 | **0.12** |

### Test 2: RDMA/RoCE (25GbE ConnectX-4 LX)

```
Network: IB (RoCE v2)
Interface: rocep216s0f0 / rocep175s0f0
NCCL_IB_DISABLE=0
```

| Size | Count | Time (μs) | Bandwidth (GB/s) |
|------|-------|-----------|------------------|
| 8 B | 2 | 48 | 0.00 |
| 1 KB | 256 | 50 | 0.02 |
| 64 KB | 16384 | 127 | 0.52 |
| 1 MB | 262144 | 563 | 1.86 |
| 16 MB | 4194304 | 6,471 | 2.59 |
| 256 MB | 67108864 | 93,162 | 2.88 |
| 1 GB | 268435456 | 368,605 | **2.91** |

---

## Performance Analysis

### Bandwidth Scaling

```
         TCP          RDMA         
1GB   ████████████   ████████████████████████████████████████████████  2.91 GB/s
       0.12 GB/s     
       
256MB ████████████   ████████████████████████████████████████████████  2.88 GB/s
       0.12 GB/s

16MB  ████████████   ███████████████████████████████████████████       2.59 GB/s
       0.12 GB/s

1MB   ███████████    ██████████████████████████████                    1.86 GB/s
       0.11 GB/s
```

### Latency Comparison (Small Messages)

| Size | TCP | RDMA | Improvement |
|------|-----|------|-------------|
| 8 B | 170 μs | 48 μs | 3.5x |
| 64 B | 181 μs | 48 μs | 3.8x |
| 256 B | 222 μs | 49 μs | 4.5x |
| 1 KB | 271 μs | 50 μs | 5.4x |

---

## Theoretical Limits

| Component | Theoretical Max | Achieved | Efficiency |
|-----------|-----------------|----------|------------|
| 25GbE NIC | 3.125 GB/s | 2.91 GB/s | **93.1%** |
| PCIe 3.0 x16 | ~8 GB/s | N/A | Not bottleneck |
| 1GbE NIC | 0.125 GB/s | 0.12 GB/s | 96% |

**Conclusion:** Network is the bottleneck, not PCIe. The ConnectX-4 LX is operating at near-theoretical maximum.

---

## Why RDMA is Faster

### TCP Path (Multiple Copies)
```
GPU Memory
    ↓ cudaMemcpy (copy 1)
CPU Memory (application buffer)
    ↓ send() syscall
Kernel Socket Buffer (copy 2)
    ↓ TCP/IP stack processing
Kernel NIC Buffer (copy 3)
    ↓ DMA to NIC
Network
    ↓ DMA from NIC
Kernel NIC Buffer (copy 4)
    ↓ TCP/IP stack processing
Kernel Socket Buffer (copy 5)
    ↓ recv() syscall
CPU Memory (copy 6)
    ↓ cudaMemcpy (copy 7)
GPU Memory
```

**Result:** 6-7 memory copies, kernel context switches, CPU interrupts

### RDMA Path (Zero Copy)
```
GPU Memory (registered region)
    ↓ RDMA write (NIC DMA)
Network
    ↓ RDMA write (NIC DMA)
GPU Memory (registered region)
```

**Result:** Zero CPU copies, kernel bypass, NIC-to-memory DMA

---

## Practical Impact on Training

### Example: 400M Parameter Model

| Metric | Calculation |
|--------|-------------|
| Parameters | 400,000,000 |
| Bytes per param | 4 (float32) |
| Gradient size | 1.6 GB |

### Time per Training Iteration

| Phase | Duration |
|-------|----------|
| Forward pass | ~100 ms |
| Backward pass | ~100 ms |
| **All-reduce (TCP)** | ~13,000 ms |
| **All-reduce (RDMA)** | ~550 ms |
| Weight update | ~10 ms |

| Network | Total Iteration | GPU Utilization |
|---------|-----------------|-----------------|
| TCP | 13.2 seconds | ~1.5% |
| RDMA | 760 ms | ~26% |

**Training speedup with RDMA: ~17x** for communication-bound workloads

---

## Commands Used

### TCP Baseline
```bash
mpirun -np 2 -H <S1_IP>:1,<S2_IP>:1 \
  --mca btl_tcp_if_include eno1 \
  --mca oob_tcp_if_include eno1 \
  -x NCCL_DEBUG=INFO \
  -x NCCL_SOCKET_IFNAME=eno1 \
  -x NCCL_IB_DISABLE=1 \
  -x LD_LIBRARY_PATH=/usr/local/cuda-12.4/lib64:$LD_LIBRARY_PATH \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1
```

### RDMA/RoCE
```bash
mpirun -np 2 -H <S1_IP>:1,<S2_IP>:1 \
  --mca btl_tcp_if_include eno1 \
  --mca oob_tcp_if_include eno1 \
  -x NCCL_DEBUG=INFO \
  -x NCCL_IB_DISABLE=0 \
  -x LD_LIBRARY_PATH=/usr/local/cuda-12.4/lib64:$LD_LIBRARY_PATH \
  ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1
```

---

## DCAI Exam Relevance

| Objective | Evidence |
|-----------|----------|
| 3.1.a Congestion Control (PFC/ECN) | Switch config with PFC enabled |
| 3.1.b RoCE/RoCEv2 | NCCL using NET/IB with RoCE transport |
| 3.1.c QoS | VLAN 810 with lossless traffic class |
| 4.1 Benchmarks | NCCL all_reduce_perf results |
| 4.2 Monitoring | nvidia-smi, NCCL_DEBUG output |

---

*Generated from live benchmark on SASP lab infrastructure*
