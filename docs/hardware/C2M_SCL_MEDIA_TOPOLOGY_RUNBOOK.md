# C2M SCL / Media Topology Runbook — Capture only (no channel changes)

**Safety:** `READ_ONLY`. Goal: live mapping `sensor → VIF → ISP → SCL → preview / recorder / raw_adas`.

## 0. Collect

```sh
sh tools/device/capture_c2m_media_topology.sh [label]
# writes C2M_HW_<date>/09_media_topology/media_<label>_<ts>/ : cmdline, modules/lsmod, dmesg (+vif/isp/scl/sensor/imx/tp9950),
# /dev listing, VIF/ISP/SCL proc discovery, adas/cardv threads+fd (ringbuf_vehicle/raw_adas sightings),
# shm listings, 1920x1440/10Hz flag sightings, MANIFEST + hashes
```

## 1. Recover (workstation review, READ_ONLY artifacts)

For each stage if exposed: `device ID / channel IDs / port IDs / format / width / height / stride / fps / crop / buffer depth / physaddrs only if safe`.

```text
Sensor: imx415_MIPI chmap=1 / tp9950_MIPI chmap=2 sightings (dmesg/modules)
VIF/ISP/SCL: proc/debugfs nodes if present; else threads+fd+dmesg clues (record UNKNOWN, never SAME)
Endpoints: preview / recorder / raw_adas (ringbuf_vehicle) consumers from fd + threads + shm
Stock ADAS input: 1920x1440 vehicle_run_freq=10 (flag baseline; live dims UNKNOWN until metadata captured)
```

## 2. One-copy experiment plan (PREPARE ONLY — do NOT execute here)

Preferred order for a FUTURE approved bench (needs IPU SAFE PASS first):

```text
Tier 1 HW ONE_COPY (preferred): SCL StretchBuf → custom tensor buffer → MI_SYS_FlushInvCache → IPU Invoke
Tier 2 ZERO_COPY (only after Tier 1 proven): alias MI_SYS/MMA handle directly as tensor addr (needs aligned stride + lifetime Get→Invoke→Put proof)
Tier 3 CPU fallback (DISCOURAGED for full frames): cv::resize/Bgr2YuvNv12 on ARMv7 (no NEON) — allowed ONLY for ≤64x64 K≤3 crops; never full 1920x1440 per frame
```

Do NOT change any channel in this phase. This phase is capture only.
