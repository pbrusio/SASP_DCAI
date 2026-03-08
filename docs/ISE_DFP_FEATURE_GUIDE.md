# ISE DFP Feature Engineering Guide

## Overview

The ISE Digital Fingerprinting (DFP) model is a **14-dimensional autoencoder** that learns the "normal" behavioral fingerprint of each ISE user. At inference time, it reconstructs the 14-feature vector and measures reconstruction error (MSE). High MSE = the event doesn't look like what this user normally does = anomaly.

**These features are 100% custom-designed for SASP's ISE use case.** They are NOT from NVIDIA Morpheus DFP or any other framework. The concept of "autoencoder on behavioral features" is borrowed from Morpheus philosophy, but every feature, rolling window, and encoding was purpose-built for ISE RADIUS/TACACS+ authentication events.

The autoencoder architecture is:
```
Encoder: 14 -> 32 -> 16 -> 8 (bottleneck)
Decoder: 8 -> 16 -> 32 -> 14
Loss: MSE between input and reconstruction
```

---

## Feature Reference

### Feature 0: `hour_sin` -- Time of Day (Sine Component)

**What it captures:** Cyclical encoding of the hour the authentication occurred.

**Math:**
```
hour = event_hour + event_minute / 60.0
hour_sin = sin(2 * pi * hour / 24)
```

**Why cyclical encoding:** A naive hour value (0-23) has a discontinuity -- hour 23 and hour 0 are numerically far apart but temporally adjacent. Sine/cosine encoding places them close together in 2D space, which the autoencoder can learn from.

**Example values:**
| Time  | hour_sin |
|-------|----------|
| 00:00 |  0.000   |
| 06:00 |  1.000   |
| 12:00 |  0.000   |
| 18:00 | -1.000   |

**What anomaly looks like:** A user who always authenticates between 8-5 PM suddenly authenticating at 3 AM will have hour_sin/hour_cos values the model has never reconstructed for that behavioral profile, driving up reconstruction error on these features.

---

### Feature 1: `hour_cos` -- Time of Day (Cosine Component)

**What it captures:** Second component of the cyclical time encoding. Together with `hour_sin`, uniquely identifies the hour.

**Math:**
```
hour_cos = cos(2 * pi * hour / 24)
```

**Example values:**
| Time  | hour_cos |
|-------|----------|
| 00:00 |  1.000   |
| 06:00 |  0.000   |
| 12:00 | -1.000   |
| 18:00 |  0.000   |

**Why both sin and cos:** `sin` alone cannot distinguish 6 AM from 6 PM (both = 1.0 and -1.0 depending on rounding). The pair `(sin, cos)` maps to a unique point on the unit circle for every hour.

---

### Feature 2: `day_of_week` -- Day of the Week

**What it captures:** Integer encoding of the weekday: Monday=0, Tuesday=1, ... Sunday=6.

**Math:**
```
day_of_week = datetime.weekday()   # Python: Mon=0, Sun=6
```

**What anomaly looks like:** A user whose profile shows Monday-Friday activity suddenly authenticating on Saturday.

**Note:** This is a linear encoding (not cyclical). The model learns that values 0-4 cluster together (weekdays) and 5-6 are different. A cyclical encoding wasn't used here because the weekday/weekend boundary is the behavioral boundary, not the Sun-Mon wrap.

---

### Feature 3: `is_weekend` -- Weekend Flag

**What it captures:** Binary indicator: 1.0 if Saturday or Sunday, 0.0 otherwise.

**Math:**
```
is_weekend = 1.0 if weekday >= 5 else 0.0
```

**Why separate from day_of_week:** This gives the model an explicit weekday/weekend signal. The day_of_week feature provides granularity (which specific day), while this provides the coarse split the model needs to learn "this user never authenticates on weekends."

---

### Feature 4: `auth_result_code` -- Authentication Result

**What it captures:** Whether this specific authentication attempt passed or failed.

**Math:**
```
PASS -> 0.0
FAIL -> 1.0
(unknown -> 1.0, conservative default)
```

**What anomaly looks like:** A user who has a 100% PASS rate suddenly getting FAIL results. On its own this feature doesn't scream anomaly -- it's the combination with `consecutive_failures` and `failure_rate_1h` that makes failure patterns detectable.

---

### Feature 5: `auth_type_code` -- Authentication Protocol

**What it captures:** The ISE authentication method used.

**Math:**
```
802.1X   -> 0.0   (wired/wireless port-based NAC)
TACACS+  -> 1.0   (device administration)
Other    -> 2.0   (catch-all)
```

**What anomaly looks like:** A user who exclusively uses 802.1X for wireless access suddenly using TACACS+ (which is for device admin). This indicates either a compromised credential being used for lateral movement or a role change.

**ISE-specific:** These are the two primary ISE authentication protocols. 802.1X handles endpoint admission; TACACS+ handles device CLI access.

---

### Feature 6: `nas_port_type_code` -- Network Access Server Port Type

**What it captures:** How the user is connecting to the network.

**Math:**
```
Ethernet -> 0.0   (wired connection)
Wireless -> 1.0   (Wi-Fi)
Virtual  -> 2.0   (VPN or virtual port)
Other    -> 2.0   (bucketed with Virtual)
```

**What anomaly looks like:** A user who always connects via Ethernet (docked at a desk) suddenly showing Wireless or Virtual connections. Could indicate credential theft being used from a different location or access method.

---

### Feature 7: `consecutive_failures` -- Failures in 5-Minute Window

**What it captures:** Count of FAIL authentication events for this user in the 5 minutes leading up to the current event.

**Math:**
```
window = all events for this user where (current_time - event_time) <= 300 seconds
consecutive_failures = count of events in window where auth_result == "FAIL"
```

**Rolling window:** The 5-minute window slides with each event. Events older than 5 minutes are not counted.

**What anomaly looks like:** Normal users rarely have more than 0-1 failures in 5 minutes (maybe a typo). A brute-force attack or credential stuffing will produce 5, 10, 20+ failures in rapid succession. This feature directly flags password guessing attacks.

**Why 5 minutes:** Short enough to catch burst patterns (brute force), long enough to not trigger on a single mistyped password.

---

### Feature 8: `auth_rate_1h` -- Authentication Rate (1-Hour Window)

**What it captures:** Total number of authentication events (PASS + FAIL) for this user in the past hour.

**Math:**
```
window = all events for this user where (current_time - event_time) <= 3600 seconds
auth_rate_1h = count of events in window
```

**What anomaly looks like:** A user who typically authenticates 2-3 times per hour (morning login, after lunch, etc.) suddenly generating 50+ auth events. Could indicate:
- Credential stuffing (rapid failed attempts)
- A misconfigured supplicant (reauthenticating in a loop)
- A compromised account being tested from multiple locations

---

### Feature 9: `unique_devices_24h` -- Unique Devices in 24 Hours

**What it captures:** Count of distinct MAC addresses (calling_station_id) used by this user in the past 24 hours.

**Math:**
```
window = all events for this user where (current_time - event_time) <= 86400 seconds
unique_devices_24h = count of distinct calling_station_id values in window
```

**What anomaly looks like:** A user who normally uses 1-2 devices (laptop + phone) suddenly showing 5+ unique MACs. Indicators:
- Credential sharing across multiple people/devices
- MAC spoofing attempts
- Account takeover from novel devices

**ISE-specific:** `calling_station_id` is the RADIUS attribute containing the endpoint MAC address. ISE uses this for endpoint profiling and posture assessment.

---

### Feature 10: `unique_nas_24h` -- Unique NAS IPs in 24 Hours

**What it captures:** Count of distinct Network Access Server IP addresses this user authenticated through in the past 24 hours.

**Math:**
```
window = all events for this user where (current_time - event_time) <= 86400 seconds
unique_nas_24h = count of distinct nas_ip values in window
```

**What anomaly looks like:** A user who normally connects through 1-2 access points/switches suddenly showing 10+ NAS IPs. This could indicate:
- Impossible travel (user appearing in multiple physical locations)
- Lateral movement (attacker probing from different network segments)
- VPN hopping

**ISE-specific:** NAS IP identifies the switch, access point, or WLC that proxied the RADIUS request. Each NAS IP roughly maps to a physical location or network segment.

---

### Feature 11: `failure_rate_1h` -- Failure Ratio (1-Hour Window)

**What it captures:** Fraction of authentication attempts that failed in the past hour.

**Math:**
```
window = all events for this user where (current_time - event_time) <= 3600 seconds
total = count of events in window
failures = count of events in window where auth_result == "FAIL"
failure_rate_1h = failures / max(total, 1)
```

**Range:** 0.0 (all passes) to 1.0 (all failures)

**What anomaly looks like:** Normal users have failure_rate near 0.0 (occasional typo). A value of 0.8+ indicates sustained password guessing. Unlike `consecutive_failures` (which counts raw failures in 5 min), this captures the ratio over a longer window -- it stays elevated even after the attacker pauses between attempts.

**The `max(total, 1)` guard:** Prevents division by zero when the window is empty.

---

### Feature 12: `known_device_flag` -- Novel Device Indicator

**What it captures:** Whether the MAC address (calling_station_id) in this event was seen during the training phase for this user.

**Math:**
```
During training (fit()):
    For each user, collect all calling_station_id values -> known_devices[user]

During inference:
    known_device_flag = 0.0 if device in known_devices[user] else 1.0
```

**What anomaly looks like:** `known_device_flag = 1.0` means this user is authenticating from a device never seen in the training data. Combined with other features (off-hours, different NAS), this strongly indicates account compromise.

**Training dependency:** This feature's quality depends on the training data covering the user's normal device inventory. A user who gets a new laptop will trigger this until the model is retrained.

---

### Feature 13: `policy_set_code` -- ISE Policy Set

**What it captures:** Integer encoding of the ISE policy set that matched this authentication.

**Math:**
```
During training (fit()):
    Collect all unique policy_set values, sort alphabetically
    Assign sequential integers: {"Corporate_Wired": 0, "Guest_Wireless": 1, ...}

During inference:
    policy_set_code = policy_set_map.get(policy_set, len(policy_set_map))
    # Unknown policy sets get the next integer (out-of-vocabulary code)
```

**What anomaly looks like:** A user who always matches "Corporate_Wired" policy suddenly matching "Guest_Wireless" or an unknown policy. This indicates the user is connecting via an unexpected path, which could be:
- Rogue access point placement
- Policy misconfiguration exploitation
- Credential use from a guest network segment

**ISE-specific:** Policy sets in ISE define the authentication and authorization rules applied. They map to network segments, access levels, and posture requirements.

---

## How the Autoencoder Uses These Features

### Training Phase (Normal Behavior Only)
1. Collect ISE auth events from Kafka (`ise-sanitized` topic)
2. Filter to normal events only (no labeled anomalies)
3. Sort by (username, timestamp) so rolling windows accumulate correctly
4. Extract 14 features per event
5. Fit StandardScaler (zero-mean, unit-variance normalization)
6. Train autoencoder to reconstruct the scaled feature vectors
7. Compute reconstruction error (MSE) on validation set
8. Set threshold at 99th percentile of validation MSE

### Inference Phase (Live Detection)
1. Consume ISE auth event from Kafka
2. Extract 14 features (rolling windows update per-user)
3. Scale features using saved scaler (same mean/std from training)
4. Send scaled vector to Triton (ise-dfp model)
5. Get reconstructed vector back
6. Compute MSE: `mean((input - reconstruction)^2)` across all 14 features
7. If MSE > threshold_99: flag as anomaly

### Per-Feature Attribution (Top Features)
When an anomaly is detected, the detector computes which features contributed most to the reconstruction error:

```
per_feature_error[i] = (scaled_input[i] - reconstruction[i])^2
total_error = sum(per_feature_error)
contribution_pct[i] = per_feature_error[i] / total_error * 100
```

The top 3 contributors are reported as `top_features`, e.g.:
```
"consecutive_failures (45%), auth_rate_1h (30%), known_device (25%)"
```

This tells the analyst exactly WHY the model flagged this event -- not just "anomaly detected" but "anomaly because the user had 15 consecutive failures, high auth rate, and an unknown device."

---

## Feature Categories Summary

| Category | Features | What It Captures |
|----------|----------|-----------------|
| **Temporal** | hour_sin, hour_cos, day_of_week, is_weekend | When the user authenticates |
| **Categorical** | auth_result_code, auth_type_code, nas_port_type_code | What type of authentication event |
| **Behavioral** | consecutive_failures, auth_rate_1h, unique_devices_24h, unique_nas_24h, failure_rate_1h | How the user's recent activity pattern looks |
| **Contextual** | known_device_flag, policy_set_code | Whether this fits the user's known profile |

The behavioral features (rolling windows) are the most powerful anomaly indicators because they capture deviations from a user's established pattern over time, not just single-event properties.

---

## Source Files

| File | Purpose |
|------|---------|
| `sasp/models/training/ise_dfp_features.py` | Feature extractor class (ISEDFPFeatureExtractor) |
| `sasp/scripts/data/train_dfp_pipeline.py` | Training: events -> features -> scaler -> autoencoder -> ONNX |
| `sasp/models/inference/ise_dfp_detector.py` | Live inference daemon (Kafka -> features -> Triton -> detections) |
| `sasp/models/inference/triton_configs/ise-dfp/config.pbtxt` | Triton model config (14-dim ONNX autoencoder) |

---

## See Also

- Ensemble architecture and v2 roadmap: [`docs/ISE_DFP_ENSEMBLE_ARCHITECTURE.md`](./ISE_DFP_ENSEMBLE_ARCHITECTURE.md)
