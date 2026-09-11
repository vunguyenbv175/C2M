#!/bin/sh
# Read-only C2M runtime evidence collector.
# Designed for BusyBox/ash. It never restarts services or writes outside OUTDIR.
set -u

LABEL="${1:-baseline}"
BASE="${C2M_CAPTURE_BASE:-/mnt/mmc}"
TS="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo unknown_time)"
OUT="${BASE}/c2m_capture_${TS}_${LABEL}"
mkdir -p "$OUT" || exit 1

log() { echo "[c2m-capture] $*"; }
has() { command -v "$1" >/dev/null 2>&1; }
run_to() {
    name="$1"; shift
    { echo "# $*"; "$@"; } >"$OUT/$name" 2>&1 || true
}
copy_proc() {
    src="$1"; dst="$2"
    [ -r "$src" ] && cat "$src" >"$OUT/$dst" 2>/dev/null || true
}

log "output: $OUT"

run_to date.txt date
run_to uname.txt uname -a
copy_proc /proc/cmdline proc_cmdline.txt
copy_proc /proc/cpuinfo proc_cpuinfo.txt
copy_proc /proc/meminfo proc_meminfo.txt
copy_proc /proc/uptime proc_uptime.txt
copy_proc /proc/mtd proc_mtd.txt
copy_proc /proc/partitions proc_partitions.txt
copy_proc /proc/mounts proc_mounts.txt
copy_proc /proc/modules proc_modules.txt
copy_proc /proc/interrupts proc_interrupts.txt
copy_proc /proc/bus/input/devices proc_input_devices.txt

if has ps; then
    run_to ps.txt ps
    run_to ps_w.txt ps w
fi
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
        *adas*|*cardv*|*mutualism*|*goahead*|*hostapd*|*wpa_supplicant*|*Screen*|*screen*)
            d="$OUT/proc_${pid}_${comm}"
            mkdir -p "$d"
            [ -r "$p/status" ] && cat "$p/status" >"$d/status.txt" 2>/dev/null || true
            [ -r "$p/maps" ] && cat "$p/maps" >"$d/maps.txt" 2>/dev/null || true
            [ -r "$p/limits" ] && cat "$p/limits" >"$d/limits.txt" 2>/dev/null || true
            { for f in "$p"/fd/*; do [ -e "$f" ] || continue; printf '%s -> ' "${f##*/}"; readlink "$f" 2>/dev/null || true; done; } >"$d/fd.txt" 2>/dev/null
            ;;
    esac
done

copy_proc /proc/net/dev proc_net_dev.txt
copy_proc /proc/net/arp proc_net_arp.txt
copy_proc /proc/net/route proc_net_route.txt
copy_proc /proc/net/wireless proc_net_wireless.txt
copy_proc /proc/net/tcp proc_net_tcp.txt
copy_proc /proc/net/tcp6 proc_net_tcp6.txt
copy_proc /proc/net/udp proc_net_udp.txt
copy_proc /proc/net/udp6 proc_net_udp6.txt
copy_proc /proc/net/unix proc_net_unix.txt
has ifconfig && run_to ifconfig_a.txt ifconfig -a
if has ip; then
    run_to ip_addr.txt ip addr
    run_to ip_link.txt ip link
    run_to ip_route.txt ip route
    run_to ip_neigh.txt ip neigh
fi
has netstat && run_to netstat_anp.txt netstat -anp
has ss && run_to ss_lntup.txt ss -lntup

copy_proc /proc/sysvipc/shm proc_sysvipc_shm.txt
copy_proc /proc/sysvipc/msg proc_sysvipc_msg.txt
copy_proc /proc/sysvipc/sem proc_sysvipc_sem.txt
for d in /dev/shm /tmp /run /var/run; do
    [ -e "$d" ] || continue
    safe="$(echo "$d" | tr '/' '_')"
    ls -laR "$d" >"$OUT/list${safe}.txt" 2>&1 || true
done

ls -la /dev >"$OUT/dev_listing.txt" 2>&1 || true
has lsmod && run_to lsmod.txt lsmod
run_to dmesg.txt dmesg

mkdir -p "$OUT/sys_class_net"
for n in /sys/class/net/*; do
    [ -e "$n" ] || continue
    ifname="${n##*/}"
    d="$OUT/sys_class_net/$ifname"; mkdir -p "$d"
    for f in address operstate carrier mtu speed type; do
        [ -r "$n/$f" ] && cat "$n/$f" >"$d/$f" 2>/dev/null || true
    done
    readlink "$n/device" >"$d/device_link.txt" 2>/dev/null || true
done

mkdir -p "$OUT/usb"
for u in /sys/bus/usb/devices/*; do
    [ -d "$u" ] || continue
    id="${u##*/}"; d="$OUT/usb/$id"; mkdir -p "$d"
    for f in idVendor idProduct manufacturer product serial bDeviceClass bInterfaceClass bInterfaceSubClass bInterfaceProtocol; do
        [ -r "$u/$f" ] && cat "$u/$f" >"$d/$f" 2>/dev/null || true
    done
    readlink "$u/driver" >"$d/driver_link.txt" 2>/dev/null || true
done

: >"$OUT/high_value_files.tsv"
for f in \
    /customer/minieye/adas/adas \
    /bootconfig/bin/cardv \
    /customer/minieye/config/adas.flag \
    /customer/minieye/config/calib.flag \
    /customer/minieye/config/produce.flag \
    /config/cgi_config.bin \
    /config/net_config.bin
 do
    [ -e "$f" ] || continue
    size="$(wc -c <"$f" 2>/dev/null || echo '?')"
    hash=""
    if has sha256sum; then hash="$(sha256sum "$f" 2>/dev/null | awk '{print $1}')"; fi
    printf '%s\t%s\t%s\n' "$f" "$size" "$hash" >>"$OUT/high_value_files.tsv"
 done

{
    echo '# socket lines containing 26012 (ADAS ScreenService) or 8080 (cardv WebSocket candidate)'
    grep -E '26012|8080' "$OUT/netstat_anp.txt" 2>/dev/null || true
    echo '# raw /proc net entries: 26012=0x659C, 8080=0x1F90'
    grep -Ei ':(659C|1F90) ' "$OUT"/proc_net_tcp*.txt "$OUT"/proc_net_udp*.txt 2>/dev/null || true
} >"$OUT/ports_of_interest.txt"

{
    echo "label=$LABEL"
    echo "timestamp=$TS"
    echo "output=$OUT"
    echo "collector=read-only"
    echo "expected_screenservice_port=26012"
    echo "candidate_cardv_ws_port=8080"
} >"$OUT/MANIFEST.txt"

if has tar; then
    BUNDLE="${OUT}.tar.gz"
    tar -czf "$BUNDLE" -C "$(dirname "$OUT")" "$(basename "$OUT")" 2>/dev/null || true
    [ -f "$BUNDLE" ] && log "bundle: $BUNDLE"
fi

log "done"
echo "$OUT"
