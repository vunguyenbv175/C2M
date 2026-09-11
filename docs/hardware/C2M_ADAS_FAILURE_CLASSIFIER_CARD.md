# C2M ADAS Failure Classifier Card — Operator Sheet (A–H)

**Source:** `docs/reverse/VI_RUNTIME_FAILURE_CLASSIFIER_V1.md` (semantics preserved; G/H split from old E).
**Safety:** all commands `READ_ONLY`. Use captures from `run_c2m_runtime_capture.sh` (or `collect_baseline.sh`).

## Minimum inputs (always)

```text
processes.tsv / ps.txt / ps_w.txt / dmesg_filtered.txt / dmesg_full.txt
proc_<pid>_*/{status,threads.tsv,fd.txt} for adas/cardv/mutualism
proc_sysvipc_shm.txt / dev shm listings / ports_of_interest.txt / proc_net_tcp*.txt
config_hashes.tsv (hashes only) / high_value_files.tsv
TWO timestamped captures ~30 s apart for churn checks
```

## Decision table (return EXACTLY one)

| Class | Name | Rule (observable) |
|---|---|---|
| A | process absent | no `adas`/`mutualism` in processes/ps; no crash keywords in dmesg |
| B | crash/restart | `adas` present now + `segfault/sigsegv/abort/assert/killed/core` in dmesg, OR PID churn across the two captures |
| C | alive but no frames | `adas`+`cardv` alive but SHM/fd shows no `raw_adas`, or GetBuf timeout/seq stall; check threads (cardv x8 / adas x2 expected), `fd.txt`, SHM listings |
| D | frames ok, IPU/model fail | frames present + `ipucreate/model init/cnn/npu` error or ret != 0 in dmesg/status/IPU log; confirm binary via `high_value_files.tsv` |
| E | inference ok, calib/warning gate suppresses | frames + IPU ok, zero warnings; check `install_calib_state`, `enable_vehicle`, heavy/regular gates, thresholds (hashes only; decode private copy off-device, never publish bytes) |
| F | inference ok, display/audio fails | warnings produced (ScreenService/message evidence) but nothing on screen/speaker; `:26012` (`:659C`) absent or `Send*ToScreen` silent; check `ports_of_interest.txt`, `proc_net_tcp.txt`, `netstat/ss` |
| G | license/feature block | `adas` alive + `Bit_Login/ReadFeature/CheckOut` ret != 0 or empty feature set; name-only `.bitanswer.volume` check; codes only, never secrets |
| H | startup-decode/order block | `adas.flag`/`calib.flag` absent/decode-fail/MD5-churn, or `mutualism` never execs, or producer-after-consumer timeout (no `adas` + no crash + startup-order evidence) |

## Rules

```text
Report:  ADAS_FAILURE_CLASS = A/B/C/D/E/F/G/H/UNKNOWN
NEVER report generic "ADAS broken".
Absence of text is NOT proof: C-vs-D needs frame counters; E-vs-F needs warning/message evidence; G needs return codes; H needs two timestamps.
Host helper (A–F/OK/UNKNOWN; G–H manual for now):
  python3 tools/device/classify_adas_state.py <capture_dir>
```

## Evidence template (`06_adas_compare/classification.md`, SAFE_WRITE_OUTPUT_ONLY)

```text
ADAS_FAILURE_CLASS =
EN capture =
VI capture =
compare.json verdict =
distinguishing lines (file:line, quoted, max 20) =
missing files (stay UNKNOWN) =
operator / timestamp =
```
