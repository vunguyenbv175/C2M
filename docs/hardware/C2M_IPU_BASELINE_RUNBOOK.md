# C2M IPU Baseline Runbook — Read-only (no sysfs writes)

**Safety:** collection `READ_ONLY`. No writes to sysfs/debugfs unless separately approved. Missing nodes = UNKNOWN.

## 0. Collect

```sh
sh tools/device/capture_c2m_ipu_baseline.sh [label]
# writes C2M_HW_<date>/08_ipu_baseline/ipu_<label>_<ts>/ : lsmod, modules, meminfo, iomem, buddyinfo,
# pagetypeinfo, dmesg (+filtered ipu/mma/scl/vif/isp/sensor/ringbuf/raw_adas/mi_sys), /dev/mi* + /dev listing,
# adas/cardv process dirs (status/threads/fd/maps), IPU proc/debugfs discovery (task_channel, ipu_log,
# heap_stat, vb_pool_global, freq, version), temperature if exposed, MANIFEST + hashes
```

Discovery logic: script probes a fixed candidate list (`/proc/mi_modules/mi_ipu/*`, `/sys/.../dla/*`, `/dev/mi_ipu`, `/dev/mi/*`) and records `PRESENT` vs `UNKNOWN (absent)` per node — never fails the run on absence.

## 1. What to look at first (READ_ONLY review on workstation)

```text
dmesg_filtered.txt: mmap_reserved fb / mma / cma / ipu / dla / riscv / timeout / hang / OOM / alloc fail
proc_cmdline.txt: LX_MEM / mma_heap / cma / mmap_reserved=fb window
proc_meminfo/buddyinfo/pagetypeinfo + heap_stat/vb_pool_global: headroom for custom (do NOT invent free RAM)
task_channel / ipu_log presence: coexistence proof path
version/freq nodes: lib T_0.0.1_210525 vs kernel expectations
```

## 2. Evidence

`08_ipu_baseline/ipu_<label>_<ts>/` + note which nodes were UNKNOWN. Gate `ipu_baseline_done` requires EN capture; VI capture optional but recommended.
