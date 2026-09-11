# C2M AI ADAS Architecture V1 — Stock + Shadow AI + Fusion

**Status:** design (research). No code, no flash, shadow-mode first. Preserves `docs/master/CURRENT_ARCHITECTURE.md` + `docs/design/*`.
**Date:** 2026-09-11.

## 1. Layers

```text
SENSORS / STOCK                    CUSTOM (separate Linux process, killable)          OUTPUT
camera/ISP/SCL ── raw_adas ─┬─► stock ADAS ──► StockADASProvider ──┐
                            │   (FCW/PCW/LDW/TTC/lead)              │
                            └─► CustomADASProvider ────────────────┤
                                (det 5Hz + tracker 10Hz + lane      ├──► FusionEngine ──► WarningEngine ──► DisplayState ──► M4Adapter ──► stock M4
                                 7-10Hz + sign 2Hz + TL 5Hz gated,  │         ▲                             └─► VoiceManager (local WAV, priority)
                                 geometry/TTC on CPU)               │         │
GPS ──► GPSProvider ───────────────────────────────────────────────┤         │
OSM-SQLite ──► RoadDBProvider ─────────────────────────────────────┤         │
VietMap API / VIETMAP LIVE BLE ──► NavigationProvider ─────────────┘         │
                                                                                 (Web Admin /Diagnostics / Logger observe only)
```

Providers implement `IAdasProvider { Name(), Poll()->AdasState, Healthy() }` (`include/c2m/adas/adas_state.hpp` pattern); modes `STOCK/CUSTOM/FUSED/OFF`; `mode=read-only` hard gate in V0 (no stock control).

## 2. Vendor-neutral schema (Q28)

```cpp
struct PerceptionFrame {
  uint64_t timestamp_ms = 0, frame_id = 0;
  float ego_speed_kph = 0; bool stale = true; const char* model_ver = nullptr;
  struct Object { int id, cls; float x1,y1,x2,y2, conf; float dist_m; float ttc_s; bool crucial; } objects[];
  struct Lane { float poly[4]; float offset_m, curvature; int type; float conf; } lanes[]; bool Departure;
  struct Sign { int cls; float conf; float x1,y1,x2,y2; } signs[];
  struct TL { int state; float conf; } tls[];
  float road_mask_conf; // coarse only
  struct Hazard { int cls; float conf; float x1,y1,x2,y2; } hazards[];
  struct Ctx { bool night, rain, fog, glare; int scene; } ctx;
};
```

`StockADASProvider` (libflow :26012 vehicle/ped/lane + cardv :8080 AdasStatus/GPS → `AdasState`; sole drivers `fcw=(vehicleWarning.fcw!=0)`, `pcw=any(is_danger)`, `ldw=(deviate_state!=0)`, lead=crucial-only) stays the safety baseline. `CustomADASProvider` emits `PerceptionFrame` with `model_ver + ipu_ms + conf` per output; never writes stock channels. `NavigationProvider/GPSProvider/RoadDBProvider` feed `FuseSpeedLimit(camera≥0.6 > vietmap≥0.6 > osm≥0.4)` → `DisplayState.speed_limit_kmh` (already specified in `ROAD_INTELLIGENCE_DESIGN.md`).

## 3. Fusion / arbitration (Q28–29)

`FusionEngine` joins on `timestamp_ms` (±100 ms) + `frame_id`; `WarningEngine` is deterministic (no NN for thresholds — §45): TTC/debounce/hysteresis/cooldown/conf-fusion/overspeed/LDW-offset all rules + KF/EMA.

```text
stock FCW/PCW/LDW: NEVER suppressed (Phase SHADOW→AUGMENT); custom = shadow advisory
both agree → ↑confidence (log)
custom disagrees → log disagreement + ±5 s event clip (no UI change)
validated non-safety first: speed-limit HUD, hazard advisory, TL memo, scene/visibility tags
OPTIONAL_OVERRIDE only after separate validation gate (per-function, evidence-gated, reversible, default-off)
```

Phases:

```text
SHADOW:  custom subscribes passive, no display/audio; log + agreement metrics; kill-switch on
ASSIST:  custom info on Web Admin/diagnostics only (engineering view)
AUGMENT: non-safety HUD/voice (speed-limit, hazard memo, nav arrows) via DisplayState; stock warnings unchanged
FUSED:   stock + custom confidence fusion for ADVISORY text (warnings still stock-driven)
OPTIONAL_OVERRIDE: per-function selective replacement, feature-flagged, rollback-pinned; needs Phases 0–4 evidence
```

Entry/success/rollback per phase in ROADMAP §53.

## 4. Deterministic warning logic (Q45)

Keep on CPU: LDW offset/threshold, TTC (`median(dZ)/−vrel`, warn 2.0 s/urgent 1.2 s), overspeed (`fused_limit + hysteresis`), debounce (`3f enter / 5f exit`), confidence fusion (weighted, temp-smoothed), cooldown (anti-spam per class), calibration-gating (suppress LDW when `HeavyCalibStatus` bad). No NN for these.

## 5. Failure containment (Q46)

```text
separate process (custom AI) + cgroups/cpuset + nice + RSS/VSZ caps + IPU-duty cap 60% +
frame-timeout (stale_after_ms 500) + IPU-hang watchdog (kill custom only) +
invalid-result guard (NaN/range/clamp) + feature-flags per model + kill-switch file +
stock recorder/camera/ADAS/M4 never depend on custom IPC (poll, never block; stale→stock-only display)
```

Enhancement crash/OOM/hang/model-fail → stock continues normally (acceptance: pull custom power, stock warnings + recording + M4 unchanged).

## 6. Architecture verdict (Q52): E. HYBRID (A on-device + D-optional offboard)

Choose **E**, with **A (STOCK + SMALL SPECIALIZED MODELS)** as the shippable on-device core and **D (STOCK + PHONE/OFFBOARD)** as optional non-safety experimental.

```text
A core:  det-nano + tracker + lane-tiny + gated sign/TL crops + geometry — fits 0.8 TOPS time-sliced,
         per-task isolation/versioning/fine-tune, shadow-provable. CHOSEN for product.
B rejected: single multi-task elegant but HIGH conversion blast-radius, coupled data/loss, all-or-nothing Hz.
C rejected: replace-stock unjustified (stock six-blobs + TTC/LDW/PCW proven; custom unvalidated; violates KEEP STOCK).
D alone rejected as product (Wi-Fi/heat/batt/latency, offline gaps) — kept as OPTIONAL advisory offload.
E = A + D-optional + offline-teacher (DepthAnything/distill/labeling on GPU, phone/RK3588 bench, cloud overnight only).
```

Why not B/C/D alone: evidence §§15/26–27 — weak NPU + NDA toolchain punish coupling (B) and forbid safety handover (C); phone/cloud add value only when decoupled from safety (D→E-advisory).
