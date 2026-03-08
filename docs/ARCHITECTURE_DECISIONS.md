# SASP Architecture Decision Records

## ADR-001: LangGraph for Agent Orchestration

**Decision:** Use LangGraph (from LangChain) for multi-agent workflow orchestration.

**Context:** We needed a framework to coordinate multiple LLM agents (triage, investigate, threat_intel, report) with conditional routing, state management, and human-in-the-loop approval.

**Alternatives Considered:**
- **AutoGen (Microsoft):** More autonomous agent-to-agent communication. Rejected because SASP needs deterministic, auditable workflows — not free-form agent chat. Security operations require predictable routing paths.
- **CrewAI:** Higher-level abstraction with role-based agents. Rejected because it lacks fine-grained state control and conditional routing. SASP needs explicit graph edges (triage → investigate vs triage → skip).
- **Custom orchestration:** Building our own state machine. Rejected to avoid reinventing graph execution, state checkpointing, and error handling.

**Consequences:**
- Workflow is a compiled StateGraph with typed state (InvestigationState TypedDict)
- Conditional routing via `add_conditional_edges` for triage decisions and guardian validation
- Node wrapping (`_safe_node`) provides uniform error handling
- Trade-off: LangGraph dependency adds complexity, but the typed state machine is a strong fit for security workflows

---

## ADR-002: Ollama for Air-Gap LLM Inference

**Decision:** Use Ollama as the LLM serving layer, running locally on the workstation (8B models) and Mac Studio (70B models).

**Context:** SASP targets environments that may be air-gapped or have strict data sovereignty requirements. Security investigation data cannot leave the network.

**Alternatives Considered:**
- **Cloud APIs (OpenAI, Anthropic, etc.):** Best model quality but incompatible with air-gap requirements. Investigation data contains sensitive network telemetry and potential IOCs.
- **vLLM:** Production-grade serving but requires NVIDIA GPUs and more complex setup. Would work on T4s but we need Apple Silicon support for the Mac Studio.
- **llama.cpp:** Lower-level, faster on CPU but lacks the simple HTTP API and model management that Ollama provides.
- **Text Generation Inference (TGI):** Hugging Face's server. GPU-only, no Apple Silicon support.

**Consequences:**
- Simple HTTP API (`/api/generate`) with retries (see `_call_ollama` in triage.py)
- Models: llama3:8b for fast triage/investigate, llama3:70b for deep analysis
- Trade-off: Lower quality than cloud models, but 100% on-premises with zero data exfiltration risk
- Fallback behavior: nodes default to "skip" if Ollama is unreachable

---

## ADR-003: Sanitizer-Before-Model Architecture

**Decision:** All input data passes through a sanitizer layer before reaching ML models or LLM agents.

**Context:** SASP processes untrusted network telemetry (NetFlow, syslog, ISE RADIUS). This data could contain:
- Prompt injection attacks embedded in hostnames, usernames, or syslog messages
- SQL injection in field values
- Command injection attempts
- Data exfiltration URLs

If unsanitized data reaches the LLM agents, it could manipulate investigation outcomes.

**Alternatives Considered:**
- **Sanitize at model input only:** Only clean data before LLM prompts. Rejected because ML models can also be influenced by adversarial inputs, and unsanitized data in reports creates XSS risks in Splunk dashboards.
- **Sanitize at output only:** Check agent outputs but not inputs. Rejected because this allows injection to propagate through the entire pipeline before being caught.
- **No sanitization (trust the data):** Rejected outright — network telemetry is attacker-controlled.

**Consequences:**
- Defense in depth: sanitize inputs AND validate outputs (Guardian agent)
- 21 injection patterns across 5 categories (prompt, SQL, command, exfiltration, evasion)
- Data-source-specific sanitizers (NetFlowSanitizer, SyslogSanitizer, ISESanitizer)
- Strict mode: reject suspicious data. Permissive mode: sanitize and pass through.
- Performance cost: every record is regex-checked. Acceptable for security.

---

## ADR-004: Guardian Agent Pattern

**Decision:** A separate Guardian agent validates all outputs from primary agents before they reach the user or external systems.

**Context:** LLM agents can produce:
- Hallucinated tool calls (referencing tools that don't exist)
- Ungrounded claims (asserting facts not supported by evidence)
- Inconsistent severity ratings
- PII in reports (SSN, credit card numbers in investigation output)
- Prompt injection propagation (if input sanitization was bypassed)

**Alternatives Considered:**
- **Self-validation:** Each agent validates its own output. Rejected because an agent that has been successfully prompt-injected cannot be trusted to validate itself.
- **Rule-based post-processing:** Simple regex/rule checks on output. Partially adopted — the Guardian uses rules, not another LLM call, to avoid recursive injection risk.
- **Human review for everything:** Route all outputs to human. Rejected because it defeats the purpose of automation for low/medium severity events.

**Consequences:**
- GuardianAgent runs 5 checks: output injection, tool call validation, evidence grounding, severity consistency, PII policy compliance
- Three outcomes: approve (auto-deliver), reject (discard + alert), needs_human_review (queue for analyst)
- Guardian does NOT use LLM — it's purely rule-based to avoid prompt injection affecting the validator
- All decisions are HMAC-signed in the audit log for tamper detection

---

## ADR-005: HMAC-Signed Audit Trail

**Decision:** All agent actions are logged to an append-only JSONL file with HMAC-SHA256 signatures per entry.

**Context:** Security investigations must have an auditable trail. If an agent is compromised or produces incorrect results, we need to reconstruct what happened.

**Alternatives Considered:**
- **Database logging:** Write to PostgreSQL or SQLite. Rejected because it adds a dependency and databases can be modified in place.
- **Blockchain/merkle tree:** Tamper-evident chain. Over-engineered for this use case.
- **Syslog forwarding:** Send to a remote syslog server. Good as a secondary mechanism but doesn't provide per-entry integrity verification.

**Consequences:**
- Each log entry gets an HMAC-SHA256 signature computed from the entry content
- `verify_audit_integrity()` can check all entries in a log file
- HMAC key is configurable via `AUDIT_HMAC_KEY` environment variable
- Trade-off: HMAC key must be protected; if compromised, new entries can be forged (but existing entries can't be modified without detection)
