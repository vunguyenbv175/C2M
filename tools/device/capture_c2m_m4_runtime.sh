#!/bin/sh
# capture_c2m_m4_runtime.sh — READ_ONLY M4 passive capture (no injection, no transmit).
# Usage: sh tools/device/capture_c2m_m4_runtime.sh [label]
# Collects ports/conns/procs/threads/fd//proc/net/ScreenService/libflow/26012/8080/usb/192.168.32.123/screen nodes.
set -u
LABEL="${1:-m4}"
BASE="${C2M_CAPTURE_BASE:-/mnt/mmc}"
TS="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo unknown_time)"
SAFE_LABEL="$(echo "$LABEL" | tr '/ ' '__')"
OUT="${BASE}/m4_${SAFE_LABEL}_${TS}"
mkdir -p "$OUT" || exit 1
log() { echo "[m4-capture] $*"; }
has() { command -v "$1" >/dev/null 2>&1; }
run_to() { name="$1"; shift; { echo "# $*"; "$@"; } >"$OUT/$name" 2>&1 || true; }
copy_proc() { src="$1"; dst="$2"; if [ -r "$src" ]; then cat "$src" >"$OUT/$dst" 2>/dev/null || true; fi; }
log "label=$LABEL out=$OUT"
run_to date.txt date
run_to uname.txt uname -a
copy_proc /proc/cmdline proc_cmdline.txt
copy_proc /proc/net/dev proc_net_dev.txt
copy_proc /proc/net/unix proc_net_unix.txt
copy_proc /proc/net/tcp proc_net_tcp.txt
copy_proc /proc/net/tcp6 proc_net_tcp6.txt
copy_proc /proc/net/udp proc_net_udp.txt
copy_proc /proc/net/udp6 proc_net_udp6.txt
copy_proc /proc/net/arp proc_net_arp.txt
copy_proc /proc/net/route proc_net_route.txt
copy_proc /proc/sysvipc/shm proc_sysvipc_shm.txt
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
    *adas*|*cardv*|*Screen*|*screen*|*flow*|*goahead*|*hostapd*)
      d="$OUT/proc_${pid}_${comm}"
      mkdir -p "$d"
      [ -r "$p/cmdline" ] && tr '\000' ' ' <"$p/cmdline" >"$d/cmdline.txt" 2>/dev/null || true
      [ -r "$p/status" ] && cat "$p/status" >"$d/status.txt" 2>/dev/null || true
      ls -l "$p/task" >"$d/tasks.txt" 2>/dev/null || true
      { for f in "$p"/fd/*; do [ -e "$f" ] || continue; printf '%s -> ' "${f##*/}"; readlink "$f" 2>/dev/null || true; done; } >"$d/fd.txt" 2>/dev/null || true
      ;;
  esac
done
if has netstat; then run_to netstat_anp.txt netstat -anp; fi
if has ss; then run_to ss_lntup.txt ss -lntup; fi
if has ifconfig; then run_to ifconfig_a.txt ifconfig -a; fi
if has ip; then run_to ip_addr.txt ip addr; run_to ip_link.txt ip link; run_to ip_route.txt ip route; fi
{
  echo '# 26012=0x659C ScreenService default; 8080=0x1F90 cardv WS candidate'
  grep -E '26012|8080' "$OUT/netstat_anp.txt" 2>/dev/null || true
  grep -Ei ':(659C|1F90) ' "$OUT"/proc_net_tcp*.txt "$OUT"/proc_net_udp*.txt 2>/dev/null || true
  echo '# libflow/ScreenService sightings in cmdlines'
  grep -Ei 'screen|flow|26012|8080' "$OUT/processes.tsv" 2>/dev/null || true
} >"$OUT/ports_of_interest.txt"
ls -la /dev >"$OUT/dev_listing.txt" 2>&1 || true
mkdir -p "$OUT/sys_class_net"
for n in /sys/class/net/*; do
  [ -e "$n" ] || continue
  ifname="${n##*/}"; d="$OUT/sys_class_net/$ifname"; mkdir -p "$d"
  for f in address operstate carrier mtu; do [ -r "$n/$f" ] && cat "$n/$f" >"$d/$f" 2>/dev/null || true; done
done
mkdir -p "$OUT/usb"
for u in /sys/bus/usb/devices/*; do
  [ -d "$u" ] || continue
  id="${u##*/}"; d="$OUT/usb/$id"; mkdir -p "$d"
  for f in idVendor idProduct manufacturer product serial; do [ -r "$u/$f" ] && cat "$u/$f" >"$d/$f" 2>/dev/null || true; done
done
{ echo "ips_of_interest: 192.168.32.123 (record only if present in net tables, never probe)"; grep -r "192.168.32.123" "$OUT" 2>/dev/null || echo "not sighted"; } >"$OUT/peer_192_168_32_123.txt"
{
  echo "label=$LABEL"; echo "timestamp=$TS"; echo "output=$OUT"
  echo "mode=passive-read-only-no-transmit"
  echo "policy=L0-L1-only; L2-gated; L3-L4-BLOCKED"
} >"$OUT/MANIFEST.txt"
if command -v sha256sum >/dev/null 2>&1; then (cd "$(dirname "$OUT")" && find "$(basename "$OUT")" -type f ! -name 'SHA256SUMS.txt' -print | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done >"$(basename "$OUT")/SHA256SUMS.txt" 2>/dev/null) || true; fi
log "done: $OUT"
echo "$OUT"
