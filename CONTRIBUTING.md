# Contributing to SASP

## Prerequisites

- Python 3.10+
- Git

## Development Setup

```bash
# Clone the repository
git clone <repo-url>
cd SASP_DCAI

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with all development dependencies
pip install -e '.[dev,ml,agents,ui]'

# Verify installation
python -c "import sasp; print(sasp.__version__)"
```

## Dependency Groups

| Group | Purpose | Install |
|-------|---------|---------|
| (core) | Base runtime — Pydantic, Kafka, requests | `pip install -e .` |
| `[dev]` | Testing + linting — pytest, ruff, mypy | `pip install -e '.[dev]'` |
| `[ml]` | ML training — PyTorch, ONNX, sklearn, pandas | `pip install -e '.[ml]'` |
| `[agents]` | LLM agents — LangGraph, langchain-core | `pip install -e '.[agents]'` |
| `[ui]` | Chat interface — Gradio | `pip install -e '.[ui]'` |

For full development: `pip install -e '.[dev,ml,agents,ui]'`

## Running Tests

```bash
# Run all local tests (no external services needed)
make test-all

# Individual test suites
make test-unit          # Unit tests only
make test-integration   # Integration tests (mocked services)
make test-adversarial   # Adversarial security tests

# Full test suite including live service tests (requires running infrastructure)
make test-all-full
```

### Test Markers

Tests that require running infrastructure use pytest markers:

- `@pytest.mark.requires_kafka` — needs a live Kafka broker
- `@pytest.mark.requires_triton` — needs a live Triton Inference Server
- `@pytest.mark.requires_llm` — needs a running LLM endpoint (OpenAI-compatible)
- `@pytest.mark.adversarial` — adversarial security tests

## Code Quality

```bash
# Lint (auto-fix)
make lint

# Lint (check only)
make lint-check

# Type checking
make typecheck

# Verify all files compile
make compile-check

# Validate config files (XML, YAML)
make validate-configs
```

## Code Style

- Line length: 100 characters
- Formatter/linter: ruff
- Type hints: on all function signatures
- Docstrings: brief, on public functions and classes
- Logging: module-level `logger = logging.getLogger(__name__)`
- Imports: relative within the sasp package

## Multi-Server Deployment

SASP runs across multiple servers. Each server has its own docker-compose file:

### Startup Order

1. **Server 2 (<S2_IP>)** — Data collection layer
   ```bash
   cd sasp/infrastructure/docker
   docker-compose -f docker-compose.s2.yml up -d
   ```
   Starts: Zookeeper, Kafka, GoFlow2, syslog-ng, Sanitizer

2. **Server 1 (<S1_IP>)** — Inference layer
   ```bash
   docker-compose -f docker-compose.s1.yml up -d
   ```
   Starts: Triton, Morpheus pipelines, Splunk forwarder

3. **Mac Studio (<MAC_STUDIO_IP>)** — Sanitizer + LLM (all agents)
   ```bash
   #
   # LM Studio serves Nemotron-3-Nano via OpenAI-compatible API on :1234
   # Start LM Studio, load nvidia/nemotron-3-nano, enable server
   # IMPORTANT: Set LM Studio to listen on 0.0.0.0 (resets to localhost on reboot)
   # Verify: curl http://localhost:1234/v1/models
   #
   # Sanitizer service runs in venv on port 9095
   # Verify: curl http://localhost:9095/health
   ```

4. **Workstation (<WORKSTATION_IP>)** — Kafka Bridge
   ```bash
   python -m sasp.agents.kafka_bridge
   # Connects to Kafka on S2, LLM on Mac Studio (<MAC_STUDIO_IP>:1234)
   ```

5. **Splunk (<SPLUNK_IP>)** — SIEM
   ```bash
   cd sasp/ui/splunk_dashboards
   ./deploy_dashboards.sh
   ```

### Environment Variables

Copy `.env.example` to `.env` and configure for your environment:
```bash
cp sasp/infrastructure/docker/.env.example sasp/infrastructure/docker/.env
```

Key variables: `KAFKA_BOOTSTRAP_SERVERS`, `SPLUNK_HEC_URL`, `SPLUNK_HEC_TOKEN`, `TRITON_SERVER_URL`, `LLM_ENDPOINT`, `LLM_MODEL`

## Model Training

```bash
# Unified pipeline: scaler + threshold from existing model (quick path)
python -m sasp.scripts.data.train_pipeline \
    --from-kafka --max-records 100000 \
    --onnx-model /path/to/netflow_autoencoder.onnx \
    --output-dir models/netflow-anomaly-v2

# Unified pipeline: full retrain (scaler + autoencoder + threshold)
python -m sasp.scripts.data.train_pipeline \
    --from-kafka --max-records 100000 \
    --retrain \
    --output-dir models/netflow-anomaly-v2

# Train auth classifier (standalone)
python -m sasp.models.training.auth_classifier \
    --data data/auth_features.parquet \
    --output-dir models/

# Deploy models to Triton
./sasp/models/inference/deploy_models.sh /mnt/storage1/triton-models ./models
```

## Deployment Runbook

For the full deployment procedure (service startup, environment configuration, and validation),
see [`docs/WAVE4_DEPLOYMENT.md`](./docs/WAVE4_DEPLOYMENT.md).

## Project Structure

See `sasp/README.md` for the full architecture diagram and directory layout.
