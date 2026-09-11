# c2m-ipu-smoke RUNBOOK — SAFE vs COEXIST (bench only)

> **BLOCKED_TOOLCHAIN (pre-hardware):** the skeleton binary has NO vendor-backed
> Invoke implementation. `--probe-only` (READ_ONLY) is the only executable mode.
> `--single-invoke` is hard-refused with exit 4 (`SDK_BLOCKED`) in ALL builds —
> it never returns 0 for a non-executed Invoke. SAFE/COEXIST gates stay
> `BLOCKED_TOOLCHAIN` until the matching private SDK plus a real
> `MI_SYS_Init/CreateDevice/CreateCHN/Invoke/cleanup` implementation exist.
> The steps below define the future procedure, not today's executable capability.

**Defaults:** probe-only (`READ_ONLY`). Inference is `BENCH_ONLY` on explicit request. Never edits autostart by default. `--no-stock-stop` is the only mode.

## SAFE (bench only, stock untouched) — requires SAFE PASS before COEXIST

```text
Goal: CreateDevice -> CreateCHN -> GetDesc -> single Invoke -> Destroy, no permanent stock change.
1. Record stock health BEFORE (READ_ONLY): ps, raw_adas clues, :26012 sighting, dmesg tail. [READ_ONLY]
2. Run probe-only:  ./c2m-ipu-smoke --probe-only --firmware /config/dla/ipu_firmware.bin   [READ_ONLY]
3. BLOCKED_TOOLCHAIN — do NOT expect success yet. Only after the vendor-backed build exists
   AND the operator approves bench:  ./c2m-ipu-smoke --model /tmp/smoke.sgsimg.img --image /tmp/roi.bgr --single-invoke --no-stock-stop   [BENCH_ONLY]
   Until then the binary exits 4 and produces no MI return codes, tensor descriptors, checksum, or latency.
   Model lives in /tmp (never /customer until proven). Image is a static ROI (never live ringbuf tap in SAFE).
4. Record REQUIRED outputs (10_ipu_safe/): MI_SYS_Init ret, CreateDevice ret, CreateCHN ret, channel ID,
   input count/dims/format, output count/dims, Invoke ret, latency us/ms, output XOR/checksum, cleanup ret,
   dmesg delta, stock health before/after. UNKNOWN where unmeasurable — never invent. [SAFE_WRITE_OUTPUT_ONLY]
```

If the test requires preventing stock ADAS start, use the SEPARATE explicit bench-only manual procedure (reversible run.sh guard change, documented + rolled back immediately after; never on road; default is NOT to do this).

PASS (SAFE): `CreateDevice==0, CreateCHN==0, Invoke==0, valid output, clean Destroy, no crash/hang`.

## COEXIST (only after SAFE PASS, stock ADAS alive)

```text
1. Confirm stock ADAS alive + raw_adas healthy + ScreenService healthy (READ_ONLY).
2. Single custom Invoke beside stock (BENCH_ONLY), then optionally 1 Hz while measuring stock. No continuous heavy inference.
3. Record same outputs + stock latency/FPS change in 11_ipu_coexist/. PASS needs: custom Invoke==0, stock alive,
   raw_adas healthy, ScreenService healthy, no IPU timeout/hang, no recorder/display degradation, stock change <10% target.
```

## Outputs / stop

Missing measurement = UNKNOWN. IPU hang / panic / thermal / media instability → STOP day, kill custom only, reboot, confirm stock.
