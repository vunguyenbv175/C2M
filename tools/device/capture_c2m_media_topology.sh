#!/bin/sh
# capture_c2m_media_topology.sh — READ_ONLY SCL/media topology (capture only, no channel changes).
# Usage: sh tools/device/capture_c2m_media_topology.sh [label]
# Goal: live mapping sensor -> VIF -> ISP -> SCL -> preview/recorder/raw_adas.
set -u
LABEL="${1:-media}"
BASE="${C2M_CAPTURE_BASE:-/mnt/mmc}"
TS="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo unknown_time)"
SAFE_LABEL="$(echo "$LABEL" | tr '/ ' '__')"
OUT="${BASE}/media_${SAFE_LABEL}_${TS}"
mkdir -p "$OUT" || exit 1
log() { echo "[media-topology] $*"; }
has() { command -v "$1" >/dev/null 2>&1; }
run_to() { name="$1"; shift; { echo "# $*"; "$@"; } >"$OUT/$name" 2>&1 || true; }
copy_proc() { src="$1"; dst="$2"; if [ -r "$src" ]; then cat "$src" >"$OUT/$dst" 2>/dev/null || true; fi; }
log "label=$LABEL out=$OUT"
run_to date.txt date
run_to uname.txt uname -a
copy_proc /proc/cmdline proc_cmdline.txt
copy_proc /proc/modules proc_modules.txt
copy_proc /proc/meminfo proc_meminfo.txt
copy_proc /proc/sysvipc/shm proc_sysvipc_shm.txt
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
    *adas*|*cardv*)
      d="$OUT/proc_${pid}_${comm}"
      mkdir -p "$d"
      [ -r "$p/status" ] && cat "$p/status" >"$d/status.txt" 2>/dev/null || true
      ls -l "$p/task" >"$d/tasks.txt" 2>/dev/null || true
      { for f in "$p"/fd/*; do [ -e "$f" ] || continue; printf '%s -> ' "${f##*/}"; readlink "$f" 2>/dev/null || true; done; } >"$d/fd.txt" 2>/dev/null || true
      ;;
  esac
done
ls -la /dev >"$OUT/dev_listing.txt" 2>&1 || true
for d in /dev/shm /tmp /run /var/run; do
  [ -e "$d" ] || continue
  safe="$(echo "$d" | tr '/' '_')"
  ls -laR "$d" >"$OUT/list${safe}.txt" 2>&1 || true
done
if has dmesg; then
  dmesg >"$OUT/dmesg_full.txt" 2>&1 || true
  grep -Ei 'vif|isp|scl|sensor|imx415|tp9950|chmap|ringbuf|raw_adas|1920|1440|vehicle_run_freq|scl|vpe|divp|mmap|mma' "$OUT/dmesg_full.txt" >"$OUT/dmesg_filtered.txt" 2>&1 || true
fi
: >"$OUT/media_nodes.tsv"
for n in /proc/mi_modules/mi_scl /proc/mi_modules/mi_vif /proc/mi_modules/mi_isp /proc/mi_modules/mi_sys_mma; do
  if [ -e "$n" ]; then printf '%s\tPRESENT\n' "$n" >>"$OUT/media_nodes.tsv"; else printf '%s\tUNKNOWN (absent)\n' "$n" >>"$OUT/media_nodes.tsv"; fi
done
{
  echo '# ringbuf/raw_adas/SCL sightings (clues only, capture phase makes no topology claim)'
  grep -Ei 'ringbuf|raw_adas|ringbuf_vehicle|scl|vif|isp' "$OUT/processes.tsv" 2>/dev/null || true
  echo '---'
  grep -Ei 'ringbuf|raw_adas|scl|vif|isp|imx|tp9950' "$OUT/dmesg_filtered.txt" 2>/dev/null || true
} >"$OUT/topology_clues.txt"
{
  echo "label=$LABEL"; echo "timestamp=$TS"; echo "output=$OUT"
  echo "mode=capture-only-no-channel-changes"
  echo "policy=no physaddr publication unless safe; missing=UNKNOWN"
} >"$OUT/MANIFEST.txt"
if command -v sha256sum >/dev/null 2>&1; then (cd "$(dirname "$OUT")" && find "$(basename "$OUT")" -type f | sort | xargs sha256sum >"$(basename "$OUT")/SHA256SUMS.txt" 2>/dev/null) || true; fi
log "done: $OUT"
echo "$OUT"
