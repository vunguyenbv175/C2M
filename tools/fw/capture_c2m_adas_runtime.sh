#!/bin/sh
# capture_c2m_adas_runtime.sh — READ-ONLY C2M ADAS runtime capture (EN/VI last-mile).
# Safety: never writes to firmware, never restarts/kills/edits services,
# never dumps secret file contents. Only writes under OUTDIR and only
# records SHA-256/size/mode of persistent config (no file bytes, no base64 decode).
# Intended use (on device, BusyBox/ash):
#   sh tools/fw/capture_c2m_adas_runtime.sh en   # -> $BASE/capture_en_<ts>/
#   sh tools/fw/capture_c2m_adas_runtime.sh vi   # -> $BASE/capture_vi_<ts>/
# Then compare offline with tools/fw/compare_c2m_runtime_capture.py
set -u
LABEL="${1:-unknown}"
BASE="${C2M_CAPTURE_BASE:-/mnt/mmc}"
TS="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo unknown_time)"
OUT="${BASE}/capture_${LABEL}_${TS}"
mkdir -p "$OUT" || exit 1
log() { echo "[capture] $*"; }
has() { command -v "$1" >/dev/null 2>&1; }
run_to() {
  name="$1"; shift
  { echo "# $*"; "$@"; } >"$OUT/$name" 2>&1 || true
}
copy_proc() {
  src="$1"; dst="$2"
  if [ -r "$src" ]; then cat "$src" >"$OUT/$dst" 2>/dev/null || true; fi
}
log "label=$LABEL out=$OUT base=$BASE ts=$TS"
run_to date.txt date
run_to uname.txt uname -a
copy_proc /proc/cmdline proc_cmdline.txt
copy_proc /proc/meminfo proc_meminfo.txt
copy_proc /proc/iomem proc_iomem.txt
copy_proc /proc/buddyinfo proc_buddyinfo.txt
copy_proc /proc/pagetypeinfo proc_pagetypeinfo.txt
copy_proc /proc/modules proc_modules.txt
copy_proc /proc/uptime proc_uptime.txt
copy_proc /proc/loadavg proc_loadavg.txt
copy_proc /proc/mounts proc_mounts.txt
copy_proc /proc/mtd proc_mtd.txt
copy_proc /proc/partitions proc_partitions.txt
copy_proc /proc/interrupts proc_interrupts.txt
copy_proc /proc/net/dev proc_net_dev.txt
copy_proc /proc/net/unix proc_net_unix.txt
copy_proc /proc/net/tcp proc_net_tcp.txt
copy_proc /proc/net/tcp6 proc_net_tcp6.txt
copy_proc /proc/net/udp proc_net_udp.txt
copy_proc /proc/net/udp6 proc_net_udp6.txt
copy_proc /proc/sysvipc/shm proc_sysvipc_shm.txt
copy_proc /proc/sysvipc/msg proc_sysvipc_msg.txt
copy_proc /proc/sysvipc/sem proc_sysvipc_sem.txt
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
    *adas*|*cardv*|*mutualism*|*Screen*|*screen*)
      d="$OUT/proc_${pid}_${comm}"
      mkdir -p "$d"
      [ -r "$p/status" ] && cat "$p/status" >"$d/status.txt" 2>/dev/null || true
      [ -r "$p/stat" ] && cat "$p/stat" >"$d/stat.txt" 2>/dev/null || true
      [ -r "$p/cmdline" ] && tr '\000' ' ' <"$p/cmdline" >"$d/cmdline.txt" 2>/dev/null || true
      [ -r "$p/maps" ] && cat "$p/maps" >"$d/maps.txt" 2>/dev/null || true
      [ -r "$p/smaps" ] && grep -E '^(Size|Rss|Pss|Shared|Private|Name)' "$p/smaps" >"$d/smaps_summary.txt" 2>/dev/null || true
      [ -r "$p/limits" ] && cat "$p/limits" >"$d/limits.txt" 2>/dev/null || true
      [ -r "$p/wchan" ] && cat "$p/wchan" >"$d/wchan.txt" 2>/dev/null || true
      ls -l "$p/task" >"$d/tasks.txt" 2>/dev/null || true
      for t in "$p"/task/*; do
        [ -d "$t" ] || continue
        tid="${t##*/}"
        tcomm="$(cat "$t/comm" 2>/dev/null || true)"
        tstat="$(cat "$t/stat" 2>/dev/null | cut -c1-300 || true)"
        printf '%s\t%s\t%s\n' "$tid" "$tcomm" "$tstat" >>"$d/threads.tsv" 2>/dev/null || true
      done
      { for f in "$p"/fd/*; do [ -e "$f" ] || continue; printf '%s -> ' "${f##*/}"; readlink "$f" 2>/dev/null || true; done; } >"$d/fd.txt" 2>/dev/null || true
      cat "$p/stack" >"$d/stack.txt" 2>/dev/null || true
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
  grep -Ei 'cmdline|mmap_reserved|mmap|fb |cma|mma|ion|carveout|vif|isp|scl|ipu|sensor|imx|sc7a20|gsensor|adas|cardv|ringbuf|raw_adas|mi_sys|mmd|oom|alloc|fail|error|timeout|segfault|abort|restart|watchdog' "$OUT/dmesg_full.txt" >"$OUT/dmesg_filtered.txt" 2>&1 || true
fi
if has ifconfig; then run_to ifconfig_a.txt ifconfig -a; fi
if has ip; then run_to ip_addr.txt ip addr; run_to ip_link.txt ip link; run_to ip_route.txt ip route; fi
if has netstat; then run_to netstat_anp.txt netstat -anp; fi
if has ss; then run_to ss_lntup.txt ss -lntup; fi
{
  echo '# socket lines containing 26012 (ADAS ScreenService) or 8080 (cardv WS candidate)'
  grep -E '26012|8080' "$OUT/netstat_anp.txt" 2>/dev/null || true
  echo '# raw /proc net entries: 26012=0x659C, 8080=0x1F90'
  grep -Ei ':(659C|1F90) ' "$OUT"/proc_net_tcp*.txt "$OUT"/proc_net_udp*.txt 2>/dev/null || true
} >"$OUT/ports_of_interest.txt"
: >"$OUT/config_hashes.tsv"
for f in /customer/minieye/config/adas.flag /customer/minieye/config/calib.flag /customer/minieye/config/produce_de.flag /customer/minieye/config/adas_de.flag /customer/minieye/config/calib_de.flag /customer/minieye/config/produce.flag; do
  [ -e "$f" ] || continue
  sz="$(wc -c <"$f" 2>/dev/null || echo '?')"
  md=""; sha=""
  if has md5sum; then md="$(md5sum "$f" 2>/dev/null | awk '{print $1}')"; fi
  if has sha256sum; then sha="$(sha256sum "$f" 2>/dev/null | awk '{print $1}')"; fi
  mode="$(ls -l "$f" 2>/dev/null || true)"
  printf '%s\t%s\tmd5=%s\tsha256=%s\t%s\n' "$f" "$sz" "$md" "$sha" "$mode" >>"$OUT/config_hashes.tsv"
done
: >"$OUT/high_value_files.tsv"
for f in /customer/minieye/adas/adas /bootconfig/bin/cardv; do
  [ -e "$f" ] || continue
  sz="$(wc -c <"$f" 2>/dev/null || echo '?')"
  sha=""
  if has sha256sum; then sha="$(sha256sum "$f" 2>/dev/null | awk '{print $1}')"; fi
  printf '%s\t%s\t%s\n' "$f" "$sz" "$sha" >>"$OUT/high_value_files.tsv"
done
{
  echo "label=$LABEL"
  echo "timestamp=$TS"
  echo "output=$OUT"
  echo "collector=read-only-no-secrets"
  echo "expected_screenservice_port=26012"
  echo "candidate_cardv_ws_port=8080"
  echo "policy=config-hashes-only-no-file-bytes"
} >"$OUT/MANIFEST.txt"
log "done: $OUT"
echo "$OUT"
