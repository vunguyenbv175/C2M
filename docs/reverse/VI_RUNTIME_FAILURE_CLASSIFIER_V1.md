# VI Runtime Failure Classifier V1 (Static State Machine + Classes A–H)

**Mode:** static definition + read-only runtime procedure. No firmware modification,
no flash, no kills/restarts/edits. Device files unavailable; every live transition is
therefore RUNTIME_DEPENDENT or UNKNOWN until captured.
Prior A–F (`EN_VI_ADAS_REGRESSION_CONCLUSION_V1.md:10`) is extended to A–H without
changing prior semantics: A–F meanings preserved, G–H split out license vs
startup-decode blocks that were previously lumped into E.

## 1. Process-start state machine (static labels)

Labels: STATICALLY SAME = proven identical scripts/strings/symbols;
DIFFERENT = proven static delta; RUNTIME_DEPENDENT = same code, live inputs decide;
UNKNOWN = needs `llvm-objdump`/device logs.

```text
boot (U-Boot comp9 decoder SAME per prior; kernel payload DIFFERENT opaque +2 B,
      bootargs DIFFERENT by VI fb 8 MiB — causality UNKNOWN)
  → run.sh [STATICALLY SAME: 1584 B 796e555a… both]
      requires /customer/minieye/config/adas.flag + calib.flag else exit 1 [SAME]
      base64 -d → adas_de/calib_de.flag + MD5-compare-refresh [SAME]
      grep --enable_vehicle=false → exit 1 [SAME]
      → ./mutualism [SAME command]
  → adas_checkcalib.sh [STATICALLY SAME: 1145 B 518f22e9… both]
      state 1/2 → res 0; state 0 → res 1 [SAME]
  → SystemInit(unsigned) [DIFFERENT size 124→100, SAME MI_SYS_Init/MI_SCL_CreateDevice/
      IPUCreateDevice sequence; delta is logging path per prior — functional impact UNKNOWN]
  → MI_SYS_Init [STATICALLY SAME vocabulary: cardv x2 / adas x1; return codes UNKNOWN → RUNTIME_DEPENDENT]
  → MI_SCL_CreateDevice + VIF/ISP/SCL setup [SAME vocab (12/12/86); IDs/format/res/fps UNKNOWN → RUNTIME_DEPENDENT]
  → MI_SYS_MMA_Alloc / MI_SYS_Mmap [SAME counts; success/failure UNKNOWN → RUNTIME_DEPENDENT]
  → pthread_create: cardv x8 / adas x2 [SAME counts; guard predicates UNKNOWN → RUNTIME_DEPENDENT]
      ├──→ CameraReader (adas x14 SAME) → frames [RUNTIME_DEPENDENT: w/h/stride/fmt/seq/ts/fps UNKNOWN]
      │     → CRingBuf raw_adas (cardv) → RequestWriteFrame → CommitWrite [SAME contract per prior]
      │     → ringbuf_vehicle consumer (adas) [SAME endpoint]
      ├──→ IPUCreateDevice → model load via m0/AES (models identical, m0 self-consistent) [STATICALLY SAME blobs]
      ├──→ RunLane → LaneCalib → UpdateInstallCalibState → install_calib_state [SAME code per prior; live gate inputs UNKNOWN]
      ├──→ Bit_Login / ReadFeature / CheckOutSn/Features (byte-identical) + license_root_path +
      │     UUID/custom-info/.bitanswer.volume [STATICALLY SAME code; INPUT_DEPENDENT state]
      └──→ ScreenService :26012 + cardv Send*ToScreen (core senders SAME; VI adds SendGPSSpeedToScreen) [SAME core; display-only failure LOW]
  → warnings/display (FCW/HMW/LDW/PCW/SAG/VB audio assets; VI re-records 5, keeps FCW/HMW identical) [DIFFERENT assets, SAME classes]
```

No transition above is CONFIRMED failed statically. The machine is a procedure, not a verdict.

## 2. Runtime classes A–H (preserve A–F, split E, add G–H)

| Class | Name | Definition (observable) | Minimum distinguishing commands (read-only) |
|---|---|---|---|
| A | process absent | no `adas`/`mutualism` in `processes.tsv`/`ps.txt`, no crash keywords | `cat processes.tsv; ps; ps w; grep -i adas` + `dmesg_filtered.txt` shows no segfault |
| B | starts then crashes/restarts | `adas` present now + crash keywords (`segfault/sigsegv/abort/assert/killed/core`) or PID churn across two captures 30 s apart | two timestamped captures + `dmesg_filtered.txt` + `proc_<pid>_*/status.txt` State + `stack.txt` |
| C | alive but `raw_adas`/frame input absent | `adas`+`cardv` alive, SHM/`fd` show no `raw_adas`, or GetBuf timeout/seq stall; preview may work | `proc_*_*/threads.tsv` (8 vs 2 threads?) + `proc_sysvipc_shm.txt` + `list_dev_shm.txt` + `fd.txt` + `dmesg_filtered.txt` (GetBuf/timeout) |
| D | frames arrive but IPU/model init fails | SHM/frames present, IPU/model error (`ipucreate/model init/cnn/npu` + ret !=0) | `dmesg_filtered.txt` + `proc_*_*/status.txt` + (if exposed) IPU log; `high_value_files.tsv` hashes prove which binary ran |
| E | inference alive but calib/warning/feature gate suppresses | frames + IPU ok, no warnings; `install_calib_state=0` or `enable_vehicle=false` or heavy/regular gate not passing or warning thresholds not met | `config_hashes.tsv` (hashes only) + private copy decode (never publish) + `calib`/`HeavyCalibStatus` keywords in `dmesg_filtered.txt` + warning counters if exposed |
| F | internally alive but display/audio output fails | inference/warnings produced (needs ScreenService/message evidence) but nothing on screen/speaker; `:26012` absent or `Send*ToScreen` silent | `ports_of_interest.txt` + `proc_net_tcp.txt` (`:659C`) + `netstat_anp.txt`/`ss_lntup.txt` + M4 pcap only on verified interface (separate workstream) |
| G | license/feature/custom-info gate blocks | `adas` alive, `Bit_Login/ReadFeature/CheckOut` ret !=0 or feature set empty; same binary works with different blobs | sanitized return-code capture (codes only, no secrets) + `config_hashes.tsv` + `.bitanswer.volume` existence (name only) + `license/bitanswer` keywords |
| H | startup-decode / ordering block | `adas.flag`/`calib.flag` absent/decode-fail/MD5-churn or `mutualism` never execs or producer starts after consumer timeout | `config_hashes.tsv` + `run.sh` exit path inference (no `adas` process + no crash) + `processes.tsv` timestamps + `dmesg_filtered.txt` startup order |

Rules:

- After this point do NOT report `ADAS does not work`; report exactly one of A–H or
  `UNKNOWN (missing <file>)`.
- Absence of text is NOT proof: `C vs D` needs frame counters; `E vs F` needs warning/
  message evidence; `G` needs return codes (never secrets); `H` needs two timestamped
  captures.
- Existing `tools/device/classify_adas_state.py` covers A–F/OK/UNKNOWN; extend it for G–H
  only with return-code + config-hash inputs, never file bytes.

## 3. Runtime classes vs static evidence (why A–H, not fewer)

- A/B separate *never started* (`H`/gates) from *crashed* (needs `dmesg` crash proof).
- C/D separate *no frames* (producer/alloc/thread/order) from *frames but IPU dead*
  (kernel/IPU/memory) — different capture targets (`threads/SHM/GetBuf` vs IPU logs).
- E/G/H split the old lumped `E`: calibration thresholds (E) vs license/feature codes (G)
  vs decode/order (H) have different minimum commands and different owners (calib team vs
  provisioning vs startup).
- F isolates display-only failure because VI *does* change display/GPS/`fb` (proven) but
  core senders are SAME — promoting F without inference-liveness proof would be an error.

## 4. Minimum capture (always)

From `tools/fw/capture_c2m_adas_runtime.sh` (hashes only, no secrets):

```text
date, uname, /proc/cmdline, /proc/meminfo, /proc/iomem, /proc/buddyinfo,
/proc/pagetypeinfo, /proc/modules, lsmod, ps, ps w, processes.tsv,
proc_<pid>_*/{status,stat,cmdline,maps,smaps_summary,limits,wchan,tasks,threads.tsv,fd.txt,stack},
/dev listing, /dev/shm+tmp+run listings, dmesg_full + dmesg_filtered,
net/tcp+udp, sysvipc shm/msg/sem, ifconfig/ip/netstat/ss (if present),
ports_of_interest (:659C/:1F90), config_hashes.tsv, high_value_files.tsv, MANIFEST
```

Compare EN vs VI with `tools/fw/compare_c2m_runtime_capture.py` (graceful on missing).
Classify with `tools/device/classify_adas_state.py` (extend for G–H).

## 5. Reproduction (static part)

```powershell
python C:\Users\Admin\AppData\Local\Temp\opencode\lastmile_scan.py
Get-FileHash -Algorithm SHA256 build/run_en.sh,build/run_vi.sh,build/checkcalib_en.sh,build/checkcalib_vi.sh
```

Expected: `run.sh` `796e555a…` both; `adas_checkcalib.sh` `518f22e9…` both;
`pthread_create` 8/2; `CRingBuf` 5/8; `CameraReader` 14; `LaneCalib` 23.

## 6. Conclusion

The state machine is STATICALLY SAME at every script/key/contract layer checked and
RUNTIME_DEPENDENT at every liveness layer. Classification A–H is READY (scripts
present); the *classification result* on VI is UNKNOWN until capture.
