#!/bin/sh
# RAM-only ARM build for M4 passive usb0 observer (fw/m4_sniff/m4_usb_observe.c).
# Receive-only AF_PACKET attach; never transmits, never writes files.
# Exact fw/d4/build_shadow_arm.sh compat pattern: generated wrapper with ALL
# system headers before compat.h, ARMv7-A hard-float VFPv3-D16, time32/off32,
# old startup, glibc<=2.30 ELF gate, QEMU pure tests. No TEST macros.
# Fail-closed: no pipes hiding exit; every capture is redirect-or-fail.
# Saves logs, versions, hashes. Run from repo root.
# Usage: sh fw/m4_sniff/build_arm.sh --out DIR --sysroot STOCK_ROOTFS
set -eu
out=
sysroot=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift 2 ;;
        --sysroot) sysroot=$2; shift 2 ;;
        *) echo 'usage: build_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2 ;;
    esac
done
[ -n "$out" ] || { echo 'usage: build_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -n "$sysroot" ] || { echo 'usage: build_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -d "$sysroot/lib" ] || { echo 'sysroot lacks lib directory' >&2; exit 2; }
[ -f fw/m4_sniff/m4_usb_observe.c ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/d3/compat.h ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/device_minimal/start.S ] || exit 2
[ -f fw/device_minimal/check_elf.py ] || exit 2
command -v arm-linux-gnueabihf-gcc >/dev/null 2>&1 || { echo 'need arm-linux-gnueabihf-gcc' >&2; exit 2; }
command -v arm-linux-gnueabihf-readelf >/dev/null 2>&1 || { echo 'need arm-linux-gnueabihf-readelf' >&2; exit 2; }
command -v qemu-arm-static >/dev/null 2>&1 || { echo 'need qemu-arm-static' >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo 'need python3' >&2; exit 2; }
[ -f "$sysroot/lib/ld-linux-armhf.so.3" ] || { echo 'sysroot lacks /lib/ld-linux-armhf.so.3' >&2; exit 2; }
root=$(pwd)
mkdir -p "$out" "$out/objects"
out=$(cd "$out" && pwd)
sysroot=$(cd "$sysroot" && pwd)
mkdir -p "$out/objects"
python3 - "$out/objects" <<'PY'
from pathlib import Path
import sys
out = Path(sys.argv[1])
headers = '''#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <netpacket/packet.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include "compat.h"
'''
src = Path('fw/m4_sniff/m4_usb_observe.c').read_bytes().decode('utf-8')
src = src.replace('#define _POSIX_C_SOURCE 200809L\n', '')
src = src.replace('#define _DEFAULT_SOURCE\n', '')
src = src.replace('#define _GNU_SOURCE\n', '')
(out / 'm4_usb_observe_compat.c').write_text(headers+src,encoding='utf-8')
PY
arm-linux-gnueabihf-gcc --version > "$out/objects/toolchain_version.txt" 2>&1 || { cat "$out/objects/toolchain_version.txt"; exit 1; }
cat "$out/objects/toolchain_version.txt"
arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
    -fno-stack-protector -fno-pie \
    -I "$root/fw/d3" \
    -c "$out/objects/m4_usb_observe_compat.c" -o "$out/objects/m4_usb_observe.o" \
    > "$out/objects/observe-compile.log" 2>&1 || { cat "$out/objects/observe-compile.log"; exit 1; }
cat "$out/objects/observe-compile.log"
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
    -Wl,--no-undefined -Wl,-z,noexecstack fw/device_minimal/start.S \
    "$out/objects/m4_usb_observe.o" -o "$out/c2m-m4-sniff" \
    > "$out/objects/sniff-link.log" 2>&1 || { cat "$out/objects/sniff-link.log"; exit 1; }
cat "$out/objects/sniff-link.log"
python3 fw/device_minimal/check_elf.py "$out/c2m-m4-sniff" --allow-dynamic \
    > "$out/objects/sniff-check-elf.log" 2>&1 || { cat "$out/objects/sniff-check-elf.log"; exit 1; }
cat "$out/objects/sniff-check-elf.log"
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-m4-sniff" --self-test \
    > "$out/sniff-selftest-arm.txt" 2>&1 || { cat "$out/sniff-selftest-arm.txt"; exit 1; }
cat "$out/sniff-selftest-arm.txt"
grep -q 'M4 USB observe self-test: OK' "$out/sniff-selftest-arm.txt" || exit 1
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-m4-sniff" --help \
    > "$out/sniff-help-arm.txt" 2>&1 || { cat "$out/sniff-help-arm.txt"; exit 1; }
cat "$out/sniff-help-arm.txt"
grep -q -- '--observe' "$out/sniff-help-arm.txt" || exit 1
grep -q 'usb0' "$out/sniff-help-arm.txt" || exit 1
grep -q 'observer simulation' "$out/sniff-help-arm.txt" || exit 1
grep -q 'never transmits' "$out/sniff-help-arm.txt" || exit 1
if grep -q 'c2m_d4_status' "$out/c2m-m4-sniff"; then echo 'sniffer must not reference status path' >&2; exit 1; fi
for flag in --serve --db --gps-file --status-file; do
    if grep -q -- "$flag" "$out/c2m-m4-sniff"; then echo 'sniffer must not contain writer/fixture CLI' >&2; exit 1; fi
done
for token in 'send(' 'sendto(' 'sendmsg(' 'connect(' 'ioctl' 'setsockopt' 'system(' 'popen(' 'fopen(' 'O_CREAT'; do
    if grep -q -F -- "$token" "$out/c2m-m4-sniff"; then echo "sniffer must not contain transmit/file token: $token" >&2; exit 1; fi
done
arm-linux-gnueabihf-readelf -V "$out/c2m-m4-sniff" > "$out/objects/c2m-m4-sniff.versions.txt" 2>&1 || { cat "$out/objects/c2m-m4-sniff.versions.txt"; exit 1; }
cat "$out/objects/c2m-m4-sniff.versions.txt"
chmod 755 "$out/c2m-m4-sniff"
sha256sum "$out/c2m-m4-sniff" > "$out/m4_sniff_arm_hashes.txt" || exit 1
cat "$out/m4_sniff_arm_hashes.txt"
echo "m4-sniff ARM RAM-only build+QEMU OK: $out/c2m-m4-sniff"
