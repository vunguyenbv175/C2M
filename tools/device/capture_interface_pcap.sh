#!/bin/sh
# Finite, passive packet capture for a transport interface already identified
# by runtime evidence. No interface name is assumed.
set -u

IFACE="${1:-}"
LABEL="${2:-capture}"
SECONDS="${3:-60}"
BASE="${C2M_CAPTURE_BASE:-/mnt/mmc}"

if [ -z "$IFACE" ]; then
    echo "usage: $0 <verified-interface> [label] [seconds]" >&2
    exit 2
fi
case "$SECONDS" in
    ''|*[!0-9]*) echo "seconds must be a positive integer" >&2; exit 2 ;;
esac
[ "$SECONDS" -gt 0 ] || { echo "seconds must be > 0" >&2; exit 2; }
[ -d "/sys/class/net/$IFACE" ] || { echo "interface not found: $IFACE" >&2; exit 3; }
command -v tcpdump >/dev/null 2>&1 || { echo "tcpdump is not installed on this C2M image" >&2; exit 4; }

TS="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo unknown_time)"
SAFE_IFACE="$(echo "$IFACE" | tr '/ ' '__')"
SAFE_LABEL="$(echo "$LABEL" | tr '/ ' '__')"
OUTDIR="${BASE}/c2m_pcap_${TS}_${SAFE_LABEL}"
PCAP="${OUTDIR}/${SAFE_IFACE}.pcap"
mkdir -p "$OUTDIR" || exit 1

{
    echo "timestamp=$TS"
    echo "interface=$IFACE"
    echo "label=$LABEL"
    echo "duration_seconds=$SECONDS"
    echo "snaplen=0"
    echo "filter=none"
    echo "mode=passive"
} >"$OUTDIR/MANIFEST.txt"

if command -v ip >/dev/null 2>&1; then
    ip addr show dev "$IFACE" >"$OUTDIR/ip_addr.txt" 2>&1 || true
    ip link show dev "$IFACE" >"$OUTDIR/ip_link.txt" 2>&1 || true
fi
if command -v ifconfig >/dev/null 2>&1; then
    ifconfig "$IFACE" >"$OUTDIR/ifconfig.txt" 2>&1 || true
fi
cat /proc/net/arp >"$OUTDIR/proc_net_arp.txt" 2>/dev/null || true
netstat -anp >"$OUTDIR/netstat_before.txt" 2>&1 || true

echo "[c2m-pcap] passive capture on $IFACE for ${SECONDS}s -> $PCAP"

# Avoid assuming BusyBox `timeout` syntax. Start tcpdump ourselves, sleep for
# a finite interval, send INT so tcpdump flushes a valid pcap, then wait.
tcpdump -i "$IFACE" -s 0 -U -w "$PCAP" >"$OUTDIR/tcpdump_stdout.txt" 2>"$OUTDIR/tcpdump_stderr.txt" &
PID=$!
trap 'kill -INT "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; exit 130' INT TERM HUP
sleep "$SECONDS"
kill -INT "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
trap - INT TERM HUP

netstat -anp >"$OUTDIR/netstat_after.txt" 2>&1 || true
if command -v sha256sum >/dev/null 2>&1 && [ -f "$PCAP" ]; then
    sha256sum "$PCAP" >"$OUTDIR/pcap.sha256" 2>/dev/null || true
fi
ls -l "$PCAP" >"$OUTDIR/pcap_size.txt" 2>&1 || true

echo "[c2m-pcap] done: $OUTDIR"
echo "$OUTDIR"
