# ISE DFP Ensemble Architecture

## What ISE-DFP Is (and Isn't)

ISE-DFP (Digital Fingerprinting) is a **behavioral anomaly detection system** for Cisco ISE authentication events. It learns what "normal" looks like for each user — when they authenticate, from which devices, at which locations, with what failure rate — and flags deviations.

**What it is:**
- An entity-centric model: one behavioral profile per user, not one global model
- A reconstruction-based detector: autoencoders learn to compress and reconstruct normal patterns; anomalies reconstruct poorly
- Purpose-built for ISE RADIUS/TACACS+ authentication telemetry

**What it is not:**
- Not a signature-based detector — it does not match known attack patterns
- Not a Morpheus DFP clone — the concept of "autoencoder on behavioral features" is borrowed from Morpheus philosophy, but every feature, rolling window, and encoding is custom-designed for ISE
- Not production-calibrated — all training data is synthetic (see `docs/KNOWN_GAPS.md`)

---

## The Entity-Centric Model

Traditional anomaly detection trains a single global model on all traffic. ISE-DFP takes an entity-centric approach: the model learns per-user behavioral fingerprints through the feature engineering layer.

The `ISEDFPFeatureExtractor` maintains **rolling windows per user**:
- 5-minute window: consecutive failure count
- 1-hour window: authentication rate, failure ratio
- 24-hour window: unique devices, unique NAS IPs

This means the autoencoder doesn't just learn "what normal authentication looks like globally" — it learns "what normal authentication looks like for this specific user's behavioral fingerprint." A service account authenticating 144 times per day is normal; an executive doing the same is an anomaly.

See [`ISE_DFP_FEATURE_GUIDE.md`](./ISE_DFP_FEATURE_GUIDE.md) for the full 14-feature reference.

---

## Why StandardScaler Over MinMax

The feature vectors are normalized with `StandardScaler` (zero-mean, unit-variance) rather than `MinMaxScaler` for three reasons:

1. **Outlier robustness.** MinMax maps the entire range to [0, 1], so a single extreme value (e.g., a brute-force burst of 500 failures) compresses all normal values into a tiny range near 0. StandardScaler preserves the relative spacing of normal values and lets outliers extend beyond the typical range — which is exactly what we want the autoencoder to struggle with.

2. **Unbounded features.** Several features (`consecutive_failures`, `auth_rate_1h`, `unique_devices_24h`) have no natural upper bound. MinMax requires knowing the max at training time; any inference value exceeding that max gets clipped to 1.0, losing anomaly signal. StandardScaler handles unseen magnitudes gracefully — a z-score of 15 is unusual but representable.

3. **Autoencoder gradient behavior.** Autoencoders with ReLU activations train more stably on zero-centered data. MinMax [0, 1] normalization biases activations positive, which can cause dead ReLU units in deeper layers.

---

## v1 Pipeline (Current Implementation)

The v1 pipeline is a single 14-dimensional autoencoder:

```
ISE Auth Event
    │
    ▼
ISEDFPFeatureExtractor (14 features)
    │
    ▼
StandardScaler (zero-mean, unit-variance)
    │
    ▼
Autoencoder (14 → 32 → 16 → 8 → 16 → 32 → 14)
    │
    ▼
MSE Reconstruction Error
    │
    ▼
Threshold Check (p99 from validation set)
    │
    ▼
Detection + Per-Feature Attribution (top 3 contributors)
```

**Strengths:**
- Simple, fast, explainable (per-feature attribution tells you why)
- Single model to deploy and monitor
- Works well for obvious anomalies (brute force, impossible travel)

**Limitations:**
- Single model must handle all 14 features simultaneously — temporal, categorical, and behavioral signals compete for bottleneck capacity
- Cannot capture temporal sequences (event ordering within a session)
- No seasonal decomposition (same-hour-different-month patterns)
- Binary threshold — no graduated confidence scoring

---

## v2 Ensemble Architecture (Planned)

The v2 architecture replaces the single autoencoder with four specialized models, each responsible for a subset of the feature space:

### The Four Models

| Model | Type | Features | What It Catches |
|-------|------|----------|----------------|
| **Isolation Forest** | Tree ensemble | All 14 | Global outliers — events that are unusual in any dimension. Fast, no training, good baseline. |
| **Autoencoder** | Neural network | Behavioral (7-9) | Reconstruction anomalies in the behavioral feature subspace. Same architecture as v1 but focused on rolling-window features. |
| **Prophet** | Time-series decomposition | Temporal (4) | Seasonal patterns — hour-of-day, day-of-week, weekend effects. Catches "this user never authenticates at 3 AM on Sundays." |
| **LSTM** | Recurrent neural network | Sequence of recent events | Session-level anomalies — unusual ordering or pacing of events within a time window. |

### Feature Space Partitioning

Each model owns a subset of the 14 features, chosen to match the model's strengths:

```
Features 0-3   (Temporal):    Prophet         → Seasonal decomposition
Features 4-6   (Categorical): Isolation Forest → Multi-dimensional outlier
Features 7-12  (Behavioral):  Autoencoder     → Reconstruction error
Features 0-13  (Sequence):    LSTM            → Event ordering patterns
Feature 13     (Contextual):  Isolation Forest → Policy set anomalies
```

The Isolation Forest sees all 14 features as a baseline detector. The other three models specialize in their respective subspaces. This partitioning ensures that temporal patterns don't compete with behavioral patterns for bottleneck capacity in the autoencoder.

---

## Bayesian Log-Odds Score Fusion

Each model produces a per-event anomaly probability (0.0 to 1.0). These are fused into a single composite score using Bayesian log-odds addition:

```python
import math

def logit(p: float, epsilon: float = 1e-6) -> float:
    """Convert probability to log-odds."""
    p = max(epsilon, min(1 - epsilon, p))
    return math.log(p / (1 - p))

def sigmoid(x: float) -> float:
    """Convert log-odds back to probability."""
    return 1.0 / (1.0 + math.exp(-x))

def bayesian_fusion(if_score, ae_score, p_score, lstm_score) -> float:
    """Fuse four model scores into a single anomaly probability.

    Each score is a probability [0, 1] from an individual model.
    Log-odds addition assumes conditional independence — reasonable
    since each model operates on a different feature subspace.
    """
    log_odds = logit(if_score) + logit(ae_score) + logit(p_score) + logit(lstm_score)
    return sigmoid(log_odds)
```

**Why log-odds fusion:**
- Mathematically principled — equivalent to naive Bayes under conditional independence
- Naturally handles model disagreement — one high score + three low scores produces a moderate composite
- No arbitrary weighting needed — each model contributes proportionally to its confidence
- The conditional independence assumption is reasonable because each model operates on a different feature subspace

**Example:**
```
Isolation Forest: 0.3  (slightly unusual globally)
Autoencoder:      0.9  (behavioral features very anomalous)
Prophet:          0.2  (normal time of day)
LSTM:             0.4  (slightly unusual event sequence)

Composite: bayesian_fusion(0.3, 0.9, 0.2, 0.4) ≈ 0.55
```

The autoencoder's strong signal lifts the composite, but the other models' low scores temper it. If the autoencoder AND Prophet both flag the event, the composite climbs much higher.

---

## Sync vs Async Execution

Not all four models need to be on the hot path. The architecture splits into synchronous (latency-sensitive) and asynchronous (batch) execution:

**Synchronous (hot path, per-event):**
- Isolation Forest — microsecond inference, no GPU needed
- Autoencoder — millisecond inference via Triton GPU

**Asynchronous (batch, periodic):**
- Prophet — fits per-user seasonal models on historical data; scoring is fast but fitting is slow. Runs hourly or daily, not per-event.
- LSTM — requires a sequence of recent events (e.g., last 20). Scores event sequences in micro-batches, not individual events.

This split means the hot path stays fast (IF + AE = < 5ms per event) while Prophet and LSTM contribute asynchronously. The fusion function uses the most recent available score from each model.

---

## Scaling: Lab to Enterprise

The v1 lab runs at ~10 events/second across 13 synthetic user profiles. Enterprise ISE deployments generate 1,000-65,000 authentication events per second across thousands of users.

### Scaling Strategy

| Component | Lab (v1) | Enterprise (v2) |
|-----------|---------|-----------------|
| Feature extraction | Single-process, in-memory rolling windows | Kafka Streams or Flink for distributed stateful processing |
| Isolation Forest | scikit-learn, single-thread | Distributed IF or reservoir sampling |
| Autoencoder | Single Triton instance, Tesla T4 | Triton with dynamic batching, multi-GPU, horizontal replicas |
| Prophet | Not implemented | Per-user model store, retrained daily via Airflow |
| LSTM | Not implemented | Triton serving with sequence batching |
| User state | Python dict per process | Redis or Apache Flink keyed state |

The key scaling challenge is **per-user state management** — the rolling windows and known-device sets must be partitioned by user across processing nodes. Kafka key-based partitioning (partition by username) ensures all events for a given user route to the same processing node.

---

## Known Limitations

1. **Synthetic training only.** All models are trained on synthetic data generated by `ise_auth_generator.py` (13 profiles, 6 anomaly scenarios). Detection accuracy on real ISE traffic is unknown.

2. **No online learning.** Models are trained offline and deployed statically. A user who changes roles, devices, or work hours will trigger false positives until the model is retrained.

3. **Conditional independence assumption.** The Bayesian fusion assumes each model's score is conditionally independent given the true label. In practice, features overlap (e.g., `auth_rate_1h` correlates with `consecutive_failures`), so the composite score may be overconfident.

4. **No feedback loop.** There is no mechanism for analysts to label detections as true/false positive and feed that back into model retraining.

5. **Single-tenant.** The feature extractor maintains per-user state in a Python dict. This works for lab scale but doesn't support multi-tenant deployments or horizontal scaling without external state management.

---

## Implementation Status

| Component | Status | Location |
|-----------|--------|----------|
| 14-feature extractor | **Done** | `sasp/models/training/ise_dfp_features.py` |
| StandardScaler pipeline | **Done** | `sasp/scripts/data/train_dfp_pipeline.py` |
| v1 Autoencoder (14-dim) | **Done** | Deployed on Triton (S1), config in `triton_configs/ise-dfp/` |
| Per-feature attribution | **Done** | `sasp/models/inference/ise_dfp_detector.py` |
| DFP detector daemon | **Done** | Running on S1:9097 |
| Synthetic data generator | **Done** | `sasp/scripts/testing/ise_auth_generator.py` |
| Isolation Forest (v2) | Planned | — |
| Focused Autoencoder (v2) | Planned | — |
| Prophet seasonal (v2) | Planned | — |
| LSTM sequence (v2) | Planned | — |
| Bayesian fusion (v2) | Planned | — |
| Distributed state (v2) | Planned | — |

---

## References

- [ISE DFP Feature Guide](./ISE_DFP_FEATURE_GUIDE.md) — Full 14-feature reference with math
- [Current State](./CURRENT_STATE.md) — Platform operational status
- [Known Gaps](./KNOWN_GAPS.md) — Stub components and calibration issues
