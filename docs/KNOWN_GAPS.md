# Known Gaps and Stub Implementations

> Last updated: March 2026 (v1.0-dcai tag)
>
> This document surfaces all known incomplete or stub components in one
> place. Everything listed here works well enough for the DCAI exam
> demonstration but would need attention before production use.

---

## Agent Tools

### asset_lookup

**Status:** Stub — returns `{"status": "unknown"}` for all IPs
**Impact:** Agent investigations cannot correlate detections with asset
owner or classification. Severity scoring may be less accurate.
**Path to fix:** Wire to a CMDB or flat JSON asset inventory. Set
`ASSET_INVENTORY_PATH` env var to a JSON file keyed by IP address.
See `sasp/agents/tools/asset_lookup.py` for implementation notes.

### baseline_query

**Status:** Stub — returns default baseline (mean=0, std=1) for all IPs
**Impact:** Agent investigations cannot compare current behavior against
historical baseline. Triage quality is reduced.
**Path to fix:** Load per-user baseline stats from the ISE-DFP
`scaler.json` artifact. See `sasp/agents/tools/baseline_query.py` for
implementation notes.

---

## Detection Models

### netflow-anomaly

**Status:** Uncalibrated weights
**Impact:** All NetFlow records are flagged as anomalous. Detection
outputs from this model are not meaningful until retrained on real
Cat9200L traffic.
**Path to fix:** Run `train_pipeline.py` against real Cat9200L NetFlow
data:
```bash
python -m sasp.scripts.data.train_pipeline \
    --from-kafka --topic netflow-sanitized \
    --bootstrap-servers <S2_IP>:9092 \
    --retrain \
    --output-dir ./models/netflow-anomaly-v2
```

### All Triton Models (General)

**Status:** Trained on synthetic data only
**Impact:** Anomaly thresholds are calibrated to synthetic distributions,
not real environment telemetry. Detection accuracy on real traffic is
unknown.
**Path to fix:** Retrain each model against real environment telemetry.
See training pipeline scripts in `sasp/scripts/data/`.

---

## Infrastructure

### ABP and SID Detector Daemons

**Status:** Not auto-started on S1
**Impact:** ABP (GPU anomaly) and SID (sensitive info) detections are
inactive unless manually started after reboot.
**Path to fix:** SSH to S1 and run:
```bash
./scripts/start_abp_detector.sh
./scripts/start_sid_detector.sh
```
Consider adding systemd unit files for persistence across reboots.

### No Live ISE/Syslog Feeds

**Status:** All ISE and syslog data is synthetic (from generators)
**Impact:** Only NetFlow is a live data source (from Cat9200L). ISE DFP
detections in Splunk are real Triton inference results but on synthetic
test data.
**Path to fix:** Connect a real Cisco ISE deployment or syslog source.

### Service Persistence

**Status:** All services run via `nohup` — will die on reboot
**Impact:** Full environment bring-up requires manual restart of all
services after any server reboot.
**Path to fix:** Create systemd unit files for each service. See
`docs/WAVE4_DEPLOYMENT.md` for the current manual bring-up sequence.
