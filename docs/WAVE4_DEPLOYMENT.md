# SASP Wave 4 — Remote Deployment Plan

**Created:** 2026-02-28
**Status:** Complete (2026-03-02)
**Pre-req:** All 26 stories complete (local code). This plan deploys to real infrastructure.

> **Note:** Deployment plan executed and completed 2026-03-02. See [`activities_log.md`](../activities_log.md) for execution notes, issues encountered, and resolutions.

> **CRITICAL:** Do NOT install any drivers or packages on the UCS servers without explicit approval.
> These servers took significant effort to configure.

---

## Server Inventory

| IP | Host | Role | Hardware | Current State |
|----|------|------|----------|---------------|
| <S2_IP> | S2 (C240 M5) | Collection/Training | Tesla T4 | Running: zookeeper, kafka, goflow2, syslog-ng |
| <S1_IP> | S1 (C220 M5) | Inference | Tesla T4 | Running: sasp-triton (both models READY), sasp-morpheus (CPU mode pipeline) |
| <WORKSTATION_IP> | Workstation (<WORKSTATION_USER>) | Kafka Bridge | RTX 5080 | Running: kafka_bridge (387+ investigations completed) |
| <MAC_STUDIO_IP> | Mac Studio | Sanitizer + LLM (all agents) | M3 Ultra 96GB | Running: Sanitizer (port 9095), LM Studio + Nemotron-3-Nano (port 1234). IMPORTANT: LM Studio must listen on 0.0.0.0 (resets on reboot) |
| <SPLUNK_IP> | Splunk | SIEM | — | Running. HEC enabled. 5 SASP dashboards populated |
| <SWITCH_IP> | Cat9200L | Network | — | NetFlow v9 flowing to GoFlow2 |

## Key Credentials

All secrets are stored in `.env` (not committed). See `.env.example` for the template.

| Item | Env Var | Notes |
|------|---------|-------|
| Splunk HEC Token | `SPLUNK_HEC_TOKEN` | From Morpheus-Ingest HEC input |
| Splunk HEC URL | `SPLUNK_HEC_URL` | `http://<SPLUNK_IP>:8088/services/collector/event` |
| Splunk API | — | `https://<SPLUNK_IP>:8089` |
| Splunk Creds | `SPLUNK_USER` / `SPLUNK_PASS` | Set in `.env` |
| Existing Splunk Index | — | `morpheus` |
| S2 Compose File | — | `/data/kafka/docker-compose.yml` |
| S1 Morpheus Clone | — | `/mnt/storage1/Morpheus/` |
| S1 Morpheus Script | — | `/mnt/storage1/Morpheus/morpheus_to_splunk.py` |

---

## Task List (Execute in Order)

### Phase 1: Fix Data Collection (S2 — <S2_IP>)

The root cause of GoFlow2 crash-looping is that Kafka/Zookeeper are not running.
The existing compose file at `/data/kafka/docker-compose.yml` defines zookeeper, kafka, goflow2, and syslog services.

**Task 1.1 — Start Kafka and Zookeeper**
```bash
ssh user@<S2_IP>
cd /data/kafka
docker compose up -d zookeeper
# Wait ~10 seconds for Zookeeper to initialize
docker compose up -d kafka
# Wait ~15 seconds for Kafka to register
docker compose restart goflow2
# Verify
docker ps  # All 4 containers should be healthy
docker logs goflow2 --tail 20  # Should show "producing" messages, not broker errors
```

**Task 1.2 — Create SASP Kafka Topics**
```bash
# From S2, exec into the kafka container
docker exec -it kafka kafka-topics --bootstrap-server localhost:9092 --list
# Existing topics should appear (if any from previous GoFlow2 runs)

# Create SASP-specific topics
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic netflow-sanitized --partitions 3 --replication-factor 1
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic syslog-sanitized --partitions 3 --replication-factor 1
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic ise-sanitized --partitions 3 --replication-factor 1
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic morpheus-detections --partitions 3 --replication-factor 1
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic detection-dlq --partitions 1 --replication-factor 1

# Verify
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --list
```

**Task 1.3 — Verify NetFlow Ingestion**
```bash
# Check if GoFlow2 is receiving and producing NetFlow data
docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic netflow-raw --max-messages 5 --timeout-ms 10000
# If no messages: Cat9200L (<SWITCH_IP>) may not be sending NetFlow yet — see Task 5.1
```

**Task 1.4 — Deploy Sanitizer Service (needs approval)**
```bash
# This requires building/pulling the SASP sanitizer Docker image
# Review docker-compose.s2.yml from the SASP repo first
# DO NOT run without explicit approval — this adds a new container to S2
```

---

### Phase 2: Set Up Inference Server (S1 — <S1_IP>)

**Task 2.1 — Create Triton Model Repository**
```bash
ssh user@<S1_IP>
mkdir -p /mnt/storage1/triton-models/netflow-anomaly/1/
mkdir -p /mnt/storage1/triton-models/auth-risk/1/
```

**Task 2.2 — Copy Model Configs**
Copy from local SASP repo to S1:
```bash
# From your local machine
scp sasp/models/inference/triton_configs/netflow-anomaly/config.pbtxt user@<S1_IP>:/mnt/storage1/triton-models/netflow-anomaly/
scp sasp/models/inference/triton_configs/auth-risk/config.pbtxt user@<S1_IP>:/mnt/storage1/triton-models/auth-risk/
```

**Task 2.3 — Train Models on Real Data (after Task 1.3)**
Models need real traffic data to train. Two options:
- **Option A:** Export training data from Kafka on S2, train on S1 GPU
- **Option B:** Train on S2 GPU (also has T4), export ONNX, copy to S1

```bash
# Option A flow:
# 1. On S2: python -m sasp.scripts.data.export_training_data --topic netflow-raw --output /tmp/netflow_train.parquet
# 2. scp to S1
# 3. On S1: python -m sasp.models.training.netflow_autoencoder --data /path/to/netflow_train.parquet
# 4. On S1: python -m sasp.models.training.auth_classifier --data /path/to/auth_train.parquet
# 5. Copy ONNX outputs to /mnt/storage1/triton-models/*/1/model.onnx
```

**Task 2.4 — Start Triton (needs approval)**
```bash
# Uses NVIDIA Triton container — needs T4 driver compatibility confirmed
# DO NOT start without explicit approval
docker run --gpus all -p 8000:8000 -p 8001:8001 -p 8002:8002 \
  -v /mnt/storage1/triton-models:/models \
  nvcr.io/nvidia/tritonserver:24.01-py3 \
  tritonserver --model-repository=/models
```

**Task 2.5 — Start Morpheus Pipeline (needs approval)**
```bash
# After Triton is serving models
# Copy Morpheus pipeline YAMLs to S1
# DO NOT start without explicit approval
```

---

### Phase 3: Set Up LLM Layer (Mac Studio — localhost)

All 4 SASP agents (triage, investigate, threat_intel, report) use Nemotron-3-Nano-30B-A3B-MLX
served via LM Studio's OpenAI-compatible API on localhost:1234.

**Task 3.1 — Load Model in LM Studio** *(Done 2026-03-01)*
- Open LM Studio on Mac Studio
- Load `NVIDIA-Nemotron-3-Nano-30B-A3B-MLX-8bit` (already downloaded)
- Enable the local server (defaults to port 1234)

**Task 3.2 — Verify OpenAI-Compatible API** *(Done 2026-03-01)*
```bash
curl http://localhost:1234/v1/models
# Should list nvidia/nemotron-3-nano

curl http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"nvidia/nemotron-3-nano","messages":[{"role":"user","content":"Respond with OK"}],"max_tokens":50}'
# Should return a chat completion response
```

**Task 3.3 — Agent Config Alignment** *(Done 2026-03-01)*
The SASP agent configs in `sasp/agents/state.py` point all agents to:
- Model: `nvidia/nemotron-3-nano` (env: `LLM_MODEL`)
- Endpoint: `http://localhost:1234` (env: `LLM_ENDPOINT`)
- API format: OpenAI `/v1/chat/completions` via `sasp/agents/llm_client.py`

The OpenAI-compatible API format works across LM Studio, vLLM, Ollama `/v1/`, TGI,
and cloud providers — swapping the serving layer requires only changing the endpoint
and model name (zero code changes).

---

### Phase 4: Configure Splunk (<SPLUNK_IP>)

**Task 4.1 — Create SASP Indexes**
```bash
# Via Splunk REST API — credentials from .env
curl -k -u $SPLUNK_USER:$SPLUNK_PASS https://<SPLUNK_IP>:8089/services/data/indexes \
  -d name=sasp_detections -d datatype=event
curl -k -u $SPLUNK_USER:$SPLUNK_PASS https://<SPLUNK_IP>:8089/services/data/indexes \
  -d name=sasp_investigations -d datatype=event
curl -k -u $SPLUNK_USER:$SPLUNK_PASS https://<SPLUNK_IP>:8089/services/data/indexes \
  -d name=sasp_metrics -d datatype=event
```

**Task 4.2 — Deploy SASP Dashboards**
```bash
# From your local machine, using the deploy script:
# Edit sasp/ui/splunk_dashboards/deploy_dashboards.sh with correct Splunk credentials
SPLUNK_HOST=<SPLUNK_IP> SPLUNK_USER=$SPLUNK_USER SPLUNK_PASS=$SPLUNK_PASS \
  bash sasp/ui/splunk_dashboards/deploy_dashboards.sh
```

**Task 4.3 — Verify HEC Ingestion**
```bash
# Test HEC endpoint with SASP index
curl -k http://<SPLUNK_IP>:8088/services/collector/event \
  -H "Authorization: Splunk $SPLUNK_HEC_TOKEN" \
  -d '{"index":"sasp_detections","event":{"test":"wave4_validation","timestamp":"2026-03-01T00:00:00Z"}}'
# Should return {"text":"Success","code":0}
```

---

### Phase 5: Network Configuration

**Task 5.1 — Configure Cat9200L NetFlow Export**
```bash
# On Cat9200L (<SWITCH_IP>) — needs console/SSH access
# Configure NetFlow v9 export to GoFlow2 on S2
configure terminal
flow exporter SASP-EXPORT
  destination <S2_IP>
  transport udp 2055
  source Vlan1
  export-protocol netflow-v9
flow monitor SASP-MONITOR
  exporter SASP-EXPORT
  record netflow ipv4 original-input
interface range GigabitEthernet1/0/1 - 48
  ip flow monitor SASP-MONITOR input
  ip flow monitor SASP-MONITOR output
end
write memory
```

**Task 5.2 — Verify NetFlow Arriving at S2**
```bash
# On S2, check GoFlow2 logs
docker logs goflow2 --tail 20
# Check Kafka topic for NetFlow data
docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic netflow-raw --max-messages 3
```

---

### Phase 6: Start SASP Agent Pipeline (Workstation — <WORKSTATION_IP>)

**Task 6.1 — Power On Workstation**
Power on the RTX 5080 workstation at <WORKSTATION_IP>.

**Task 6.2 — Set Up Python Environment**
```bash
ssh user@<WORKSTATION_IP>
cd /path/to/SASP_DCAI
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[core,agents]"
```

**Task 6.3 — Configure Environment Variables**
```bash
cp .env.example .env
# Edit .env with actual values:
# KAFKA_BOOTSTRAP=<S2_IP>:9092
# SPLUNK_HEC_TOKEN=<from Splunk HEC config>
# SPLUNK_HEC_URL=http://<SPLUNK_IP>:8088/services/collector/event
# LLM_ENDPOINT=http://<MAC_STUDIO_IP>:1234   (Mac Studio LM Studio)
# LLM_MODEL=nvidia/nemotron-3-nano
```

**Task 6.4 — Start Kafka Bridge**
```bash
source .venv/bin/activate
python -m sasp.agents.kafka_bridge
# Should connect to Kafka on S2, consume from morpheus-detections topic
# Detections flow: triage → investigate → threat_intel → report → guardian
```

---

### Phase 7: End-to-End Validation

**Task 7.1 — Validate Full Pipeline**
Generate some network traffic on the Cat9200L, then verify the chain:
```
Cat9200L → NetFlow → GoFlow2 (S2) → Kafka (netflow-raw)
→ Sanitizer → Kafka (netflow-sanitized)
→ Morpheus (S1) → Triton inference → Kafka (morpheus-detections)
→ Kafka Bridge (Workstation) → LangGraph agents (Mac Studio nemotron-3-nano)
→ Guardian validation → Splunk (sasp_detections) → Dashboard
```

**Task 7.2 — Run Integration Tests (with real services)**
```bash
# On workstation, with services running:
pytest -m requires_kafka sasp/tests/
pytest -m requires_triton sasp/tests/
pytest -m requires_llm sasp/tests/
```

**Task 7.3 — Check Splunk Dashboards**
Open `http://<SPLUNK_IP>:8000` in browser, navigate to SASP dashboards:
- Detections Overview
- Investigation Details
- AI Health Monitor
- GPU Health Monitor

---

## Quick Reference — Service Dependencies

```
Phase 1 (S2)  ──► Phase 5 (NetFlow) ──► Phase 7 (E2E)
    │                                        ▲
    └──► Phase 2 (S1) ──────────────────────┘
              ▲                              │
Phase 3 (Mac) ──► Phase 6 (Workstation) ────┘
              │
Phase 4 (Splunk) ───────────────────────────┘
```

Phases 1, 3, and 4 can run in parallel. Phase 2 needs trained models (requires data from Phase 1). Phase 6 needs all others up.

---

## Post-Wave 4: Autoencoder Scaler Fix (2026-03-02)

The autoencoder was trained on StandardScaler-normalized features but the Morpheus pipeline
was sending raw (unnormalized) features to Triton. The hardcoded threshold (0.05) was
calibrated in scaled space but applied to raw-space MSE — effectively meaningless.

### What was deployed

| Artifact | Location on S1 | Purpose |
|----------|---------------|---------|
| `scaler.json` | `/mnt/storage1/triton-models/netflow-anomaly/scaler.json` | StandardScaler mean/scale (JSON — avoids numpy pickle version issues) |
| `threshold.json` | `/mnt/storage1/triton-models/netflow-anomaly/threshold.json` | p95=0.3547, p99=0.7108 (computed from 50K real traffic records) |
| `morpheus_pipeline.py` | `/home/<SERVER_USER>/morpheus_pipeline.py` | Updated with `_JsonScaler` + lazy-cached threshold loading |

### Updated Morpheus container command
```bash
docker run -d \
  --name sasp-morpheus \
  --network host \
  --runtime nvidia \
  --cap-add=sys_nice \
  -e KAFKA_BOOTSTRAP_SERVERS=<S2_IP>:9092 \
  -e TRITON_URL=localhost:8000 \
  -e ANOMALY_THRESHOLD=0.05 \
  -e SCALER_PATH=/models/netflow-anomaly/scaler.json \
  -e THRESHOLD_PATH=/models/netflow-anomaly/threshold.json \
  -v /home/<SERVER_USER>/morpheus_pipeline.py:/workspace/morpheus_pipeline.py:ro \
  -v /mnt/storage1/triton-models:/models:ro \
  nvcr.io/nvidia/morpheus/morpheus:25.06-runtime \
  python3 /workspace/morpheus_pipeline.py
```

Note: Added `-v /mnt/storage1/triton-models:/models:ro` mount and `SCALER_PATH`/`THRESHOLD_PATH` env vars
compared to the original container command.

### Regenerating the scaler (unified pipeline)

Use `train_pipeline.py` which wraps the entire workflow (export → features → scaler → threshold) into one command:

```bash
# Quick path: generate scaler + threshold from existing ONNX model (no retraining)
python -m sasp.scripts.data.train_pipeline \
    --from-kafka --topic netflow-sanitized \
    --bootstrap-servers <S2_IP>:9092 \
    --max-records 100000 \
    --onnx-model /path/to/netflow_autoencoder.onnx \
    --output-dir ./models/netflow-anomaly-v2
```

Outputs `scaler.pkl`, `scaler.json`, `threshold.json`, and `netflow_autoencoder_threshold.json` to the output directory.
The Morpheus pipeline uses the JSON formats to avoid numpy/sklearn version mismatches.

> **Legacy alternative:** `generate_scaler.py` still works for standalone scaler generation without the full pipeline.

### Follow-up: Retrain model on scaled data

The current model was trained without the scaler, so anomaly detection quality is suboptimal
(~15-20% anomaly rate vs. expected ~5% at p95). To fix, use the unified pipeline with `--retrain`:

```bash
# Full retrain: scaler + autoencoder + threshold in one command
python -m sasp.scripts.data.train_pipeline \
    --from-kafka --topic netflow-sanitized \
    --bootstrap-servers <S2_IP>:9092 \
    --max-records 100000 \
    --retrain \
    --output-dir ./models/netflow-anomaly-v2

# Deploy to S1
scp ./models/netflow-anomaly-v2/scaler.json <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/netflow-anomaly/
scp ./models/netflow-anomaly-v2/threshold.json <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/netflow-anomaly/
scp ./models/netflow-anomaly-v2/netflow_autoencoder.onnx <SERVER_USER>@<S1_IP>:/mnt/storage1/triton-models/netflow-anomaly/1/model.onnx
ssh <SERVER_USER>@<S1_IP> "docker restart sasp-morpheus"
```

---

## Known Issues from Recon

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| GoFlow2 crash-looping on S2 | Kafka/Zookeeper not running — "client has run out of available brokers" | Start zookeeper + kafka first (Task 1.1) |
| No containers on S1 | Nothing deployed yet — only Morpheus images pulled | Deploy Triton + Morpheus (Tasks 2.4, 2.5) |
| Mac Studio has llama3 not nemotron-3-nano | Model not pulled yet | **Resolved:** LM Studio loaded Nemotron-3-Nano-MLX-8bit on localhost:1234 |
| Workstation powered off | User preference | Power on when ready (Task 6.1) |
| Cat9200L not sending NetFlow | Not configured for SASP | Configure flow export (Task 5.1) |
