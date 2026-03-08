# Changelog

All notable changes to SASP are documented in this file.

## [0.3.1] - 2026-03-04

### Fixed

**Polish Pass: Operational Cleanup**
- `scripts/start_ise_bridge.sh` — fixed `exec python` → `exec "${PROJECT_DIR}/.venv/bin/python3"` (same bug as bridge); removed redundant `source .venv/bin/activate` block
- `sasp/agents/security/audit.py` — default log path changed from `/var/log/sasp/audit.jsonl` → `logs/audit.jsonl` (writable by `pb` user); added startup warning when default HMAC key is in use
- `sasp/agents/tools/asset_lookup.py` — `logger.warning` → `logger.debug` for missing data file (no asset inventory wired up yet)
- `sasp/agents/tools/baseline_query.py` — `logger.warning` → `logger.debug` for missing data file (baselines are future initiative)

### Added
- `scripts/start_sanitizer.sh` — startup script for sanitizer, matching `start_bridge.sh` pattern
- `logs/` directory with `.gitkeep` for audit log output

### Changed
- `.gitignore` — added `*.pkl`, `*.jsonl`, `*.csv`, `logs/` for generated training artifacts

### Removed
- Deleted stale temp files: `tmp0g_zru9g.pkl`, `tmpz5j28kwe.pkl`

---

## [0.3.0] - 2026-03-03

### Added

**Wave 6: Deployment Readiness**
- Unified training pipeline (`sasp/scripts/data/train_pipeline.py`) — one-command workflow: Kafka export → feature extraction → scaler fit → optional retrain → threshold computation
- ISE-to-Splunk bridge (`sasp/agents/ise_splunk_bridge.py`) — Kafka consumer for ISE auth events (port 9096)
- Detector daemon Dockerfile (`sasp/models/inference/Dockerfile.detectors`) — Docker image for ABP + SID detectors on S1
- ISE bridge startup script (`scripts/start_ise_bridge.sh`)

### Fixed
- Guardian security checks: fixed mock targets in tests (216/228 passing, 12 remaining are infra-dependent)
- Syslog sanitizer: corrected pattern matching for edge cases
- Sanitizer injection patterns: updated test coverage

---

## [0.2.0] - 2026-03-02

### Changed

**LLM Refactor**
- Migrated all agent LLM calls from Ollama API to OpenAI-compatible API (`/v1/chat/completions`)
- All 4 agents now use Nemotron-3-Nano on Mac Studio via LM Studio
- Added `llm_client.py` with `split_thinking()` to handle `<think>` tags (thinking preserved for audit, clean JSON for parsing)
- Evidence-based confidence scoring in agent responses

**Infrastructure**
- Kafka Bridge deployed on workstation (<WORKSTATION_IP>) — consumes `morpheus-detections`, runs full LangGraph investigation pipeline, posts results to Splunk HEC
- Sanitizer service deployed on Mac Studio (port 9095) — consumes `netflow-raw`, produces `netflow-sanitized` with 15 ML features computed inline
- Morpheus pipeline deployed on S1 in CPU execution mode — Triton inference still uses T4 GPU via HTTP API
- Both Triton models (`netflow-anomaly`, `auth-risk`) serving live inference on S1

### Added

**Metrics & Monitoring**
- Agent metrics emitter (`sasp/agents/metrics.py`) — per-node timing, guardian results, tool call tracking, LLM health probes → Splunk HEC
- GPU metrics collector (`gpu_metrics_collector.sh`) deployed on S1 and S2
- Triton metrics collector (`triton_metrics_collector.py`) — Prometheus endpoint scraper → Splunk HEC
- Switch metrics collector (`switch_metrics_nxapi.py`) — N9K NX-API JSON-RPC → Splunk HEC (replaced SSH-based `switch_metrics_collector.sh`)
- RoCE Network Health Splunk dashboard with PFC counters, throughput, link utilization

**Deployment & Docs**
- Wave 4 deployment plan (`docs/WAVE4_DEPLOYMENT.md`) with 7-phase runbook
- DCAI Cheat Sheet (`docs/DCAI_CHEAT_SHEET.md`) — NX-OS commands, acronyms, lab mapping
- PFC demonstration: 22K pause frames triggered, proving selective lossless flow control

### Fixed
- Sanitizer topic naming: `netflow-raw-sanitized` → `netflow-sanitized` (`.removesuffix("-raw")`)
- Morpheus numba CUDA context error: switched to CPU execution mode
- Triton batch overflow: added chunked inference (pipeline batch 256 > Triton max 64)
- Kafka Bridge JSON resilience: manual deserialization with try/except instead of value_deserializer

### Validated
- End-to-end pipeline live: Cat9200L → GoFlow2 → Kafka → Sanitizer → Morpheus → Triton → Bridge → LLM Agents → Splunk
- 387 investigations completed with full triage/investigate/threat_intel/report/guardian flow
- All 5 Splunk dashboards populated with live data
- 194/214 tests passing (`make test-all`); 20 failures are pre-existing mock targets (not regressions)

---

## [0.1.0] - 2026-02-28

### Added

**Foundation (SASP-001 through SASP-004)**
- Project scaffolding: `pyproject.toml` with core/dev/ml/agents/ui dependency groups
- Environment variable template: `.env.example` covering all platform components
- Infrastructure configs: `syslog-ng.conf`, `splunk_forwarder.py`
- Python package structure with all subpackages and `__init__.py` files

**Data Layer (SASP-005, SASP-006)**
- Kafka detection bridge: consumes Morpheus detections, routes to LangGraph investigation
- Training data export utility: Kafka-to-Parquet with time-range filtering and labeling

**Input Sanitization (SASP-007 through SASP-009)**
- 21 injection patterns across 5 categories (prompt, SQL, command, exfiltration, evasion)
- Data-source-specific sanitizers: NetFlowSanitizer, SyslogSanitizer, ISESanitizer
- Kafka sanitizer service with topic routing and strict/permissive modes
- Sanitizer unit test suite with adversarial bypass attempts

**Detection Models (SASP-010 through SASP-014)**
- NetFlow feature engineering: 15-feature extractor with aggregate window features and IP entropy
- NetFlow autoencoder: symmetric encoder-decoder with reconstruction error thresholds (95th/99th percentile)
- Auth risk classifier: 3-class feedforward network with class-weighted CrossEntropyLoss
- Triton model configs: `config.pbtxt` for netflow-anomaly and auth-risk models
- Morpheus pipeline YAMLs: end-to-end Kafka-to-detection pipelines
- Model deployment script: copies ONNX models and configs to Triton repository
- Adversarial model tests: perturbation, flow-splitting, port-hopping, slow-scan evasion
- Evaluation metrics: ROC-AUC, precision-recall, detection-at-FPR

**LLM Agent Pipeline (SASP-015 through SASP-020)**
- Agent nodes: triage, investigate, threat_intel, report with Ollama API integration
- Agent tools: splunk_query, ise_lookup, asset_lookup, threat_intel, baseline_query, mitre_mapper
- Prompt templates: safety-guarded system prompts for all agent roles
- Guardian agent: 5-check output validation (injection, tool calls, grounding, severity, PII)
- Audit logger: HMAC-signed JSONL audit trail with integrity verification
- Output validator: PII detection, HTML/base64/URL safety checks
- LangGraph workflow: compiled state graph with conditional routing and error handling

**Testing (SASP-021, SASP-022, SASP-025)**
- Agent integration tests: full pipeline with mocked Ollama (happy, skip, escalate, rejection paths)
- Adversarial agent tests: prompt injection through detection data, model evasion attempts
- CI smoke tests: sanitizer, detection, agent pipeline, audit integrity
- Makefile: test-unit, test-integration, test-adversarial, lint, typecheck targets

**Presentation (SASP-023, SASP-024)**
- Splunk dashboards: detections, investigations, AI health, GPU health (4 XML dashboards)
- Dashboard deployment script using Splunk REST API
- Gradio chat UI: three-panel layout with detection feed, chat, and investigation details
- Chat Dockerfile for containerized deployment

**Documentation (SASP-026)**
- CONTRIBUTING.md: development setup, testing, deployment, model training
- Architecture Decision Records: LangGraph, Ollama, sanitizer-first, guardian pattern, HMAC audit
- CHANGELOG.md (this file)
- README phase checklist updated to reflect completion
