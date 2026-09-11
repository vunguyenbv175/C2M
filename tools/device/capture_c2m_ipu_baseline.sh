#!/bin/sh
# capture_c2m_ipu_baseline.sh — READ_ONLY IPU baseline (no sysfs/debugfs writes).
# Usage: sh tools/device/capture_c2m_ipu_baseline.sh [label]
# Missing nodes are recorded as UNKNOWN, never fatal.
set -u
LABEL="${1:-ipu}"
BASE="${C2M_CAPTURE_BASE:-/mnt/mmc}"
TS="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo unknown_time)"
SAFE_LABEL="$(echo "$LABEL" | tr '/ ' '__')"
OUT="${BASE}/ipu_${SAFE_LABEL}_${TS}"
mkdir -p "$OUT" || exit 1
log() { echo "[ipu-baseline] $*"; }
has() { command -v "$1" >/dev/null 2>&1; }
run_to() { name="$1"; shift; { echo "# $*"; "$@"; } >"$OUT/$name" 2>&1 || true; }
copy_proc() { src="$1"; dst="$2"; if [ -r "$src" ]; then cat "$src" >"$OUT/$dst" 2>/dev/null || true; fi; }
log "label=$LABEL out=$OUT"
run_to date.txt date
run_to uname.txt uname -a
copy_proc /proc/cmdline proc_cmdline.txt
copy_proc /proc/meminfo proc_meminfo.txt
copy_proc /proc/iomem proc_iomem.txt
copy_proc /proc/buddyinfo proc_buddyinfo.txt
copy_proc /proc/pagetypeinfo proc_pagetypeinfo.txt
copy_proc /proc/modules proc_modules.txt
copy_proc /proc/mounts proc_mounts.txt
if has lsmod; then run_to lsmod.txt lsmod; fi
if has ps; then run_to ps.txt ps; run_to ps_w.txt ps w; fi
: >"$OUT/processes.tsv"
for p in /proc/[0-9]*; do
  [ -d "$p" ] || continue
  pid="${p#/proc/}"
  comm="$(cat "$p/comm" 2>/dev/null || true)"
  cmd="$(tr '\000' ' ' <"$p/cmdline" 2>/dev/null || true)"
  printf '%s\t%s\t%s\n' "$pid" "$comm" "$cmd" >>"$OUT/processes.tsv"
done
for p in /proc/[0-9]*; do
  [ -d "$p" ] || continue
  pid="${p#/proc/}"
  comm="$(cat "$p/comm" 2>/dev/null || true)"
  cmd="$(tr '\000' ' ' <"$p/cmdline" 2>/dev/null || true)"
  case "$comm $cmd" in
    *adas*|*cardv*|*mutualism*)
      d="$OUT/proc_${pid}_${comm}"
      mkdir -p "$d"
      [ -r "$p/status" ] && cat "$p/status" >"$d/status.txt" 2>/dev/null || true
      [ -r "$p/cmdline" ] && tr '\000' ' ' <"$p/cmdline" >"$d/cmdline.txt" 2>/dev/null || true
      ls -l "$p/task" >"$d/tasks.txt" 2>/dev/null || true
      { for f in "$p"/fd/*; do [ -e "$f" ] || continue; printf '%s -> ' "${f##*/}"; readlink "$f" 2>/dev/null || true; done; } >"$d/fd.txt" 2>/dev/null || true
      [ -r "$p/maps" ] && cat "$p/maps" >"$d/maps.txt" 2>/dev/null || true
      ;;
  esac
done
ls -la /dev >"$OUT/dev_listing.txt" 2>&1 || true
ls -la /dev/mi* >"$OUT/dev_mi.txt" 2>&1 || true
if has dmesg; then
  dmesg >"$OUT/dmesg_full.txt" 2>&1 || true
  grep -Ei 'mmap_reserved|mma|cma|ipu|dla|riscv|ccif|scl|vif|isp|sensor|imx|tp9950|sc7a20|adas|cardv|ringbuf|raw_adas|mi_sys|oom|alloc|fail|error|timeout|hang|panic|watchdog' "$OUT/dmesg_full.txt" >"$OUT/dmesg_filtered.txt" 2>&1 || true
fi
: >"$OUT/ipu_nodes.tsv"
for n in \
  /proc/mi_modules/mi_ipu/task_channel \
  /proc/mi_modules/mi_ipu/heap_stat \
  /proc/mi_modules/mi_ipu/version \
  /proc/mi_modules/mi_ipu/debug_hal/freq \
  /proc/mi_modules/mi_sys_mma/vb_pool_global \
  /proc/mi_modules/mi_ipu/ipu_log \
  /sys/devices/soc0/soc_id \
  /sys/class/mstar/msys/CHIP_ID \
  /sys/class/thermal/thermal_zone0/temp; do
  if [ -r "$n" ]; then
    safe="$(echo "$n" | tr '/' '_')"
    cat "$n" >"$OUT/node${safe}.txt" 2>/dev/null || true
    printf '%s\tPRESENT\n' "$n" >>"$OUT/ipu_nodes.tsv"
  else
    printf '%s\tUNKNOWN (absent)\n' "$n" >>"$OUT/ipu_nodes.tsv"
  fi
done
{
  echo "label=$LABEL"; echo "timestamp=$TS"; echo "output=$OUT"
  echo "mode=read-only-no-sysfs-writes"
  echo "missing=UNKNOWN (never SAME)"
} >"$OUT/MANIFEST.txt"
if command -v sha256sum >/dev/null 2>&1; then (cd "$(dirname "$OUT")" && find "$(basename "$OUT")" -type f ! -name 'SHA256SUMS.txt' -print | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done >"$(basename "$OUT")/SHA256SUMS.txt" 2>/dev/null) || true; fi
log "done: $OUT"
echo "$OUT"
