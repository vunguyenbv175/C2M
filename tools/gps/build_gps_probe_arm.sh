#!/bin/sh
# RAM-only ARM build for tools/gps/c2m_gps_probe.c + fw/d3/gps_snapshot.c.
# Exact fw/d4/build.sh + fw/d3/build.sh compat pattern: generated wrappers
# with ALL system headers before compat.h, ARMv7-A hard-float VFPv3-D16,
# time32/off32, old startup, glibc<=2.30 ELF gate, QEMU pure tests.
# No production GPS/D4 edits; wrappers are generated in $out.
# Fail-closed: no pipes hiding exit; every capture is redirect-or-fail.
# Saves logs, versions, hashes. Run from repo root.
# Usage: sh tools/gps/build_gps_probe_arm.sh --out DIR --sysroot STOCK_ROOTFS
set -eu
out=
sysroot=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift 2 ;;
        --sysroot) sysroot=$2; shift 2 ;;
        *) echo 'usage: build_gps_probe_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2 ;;
    esac
done
[ -n "$out" ] || { echo 'usage: build_gps_probe_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -n "$sysroot" ] || { echo 'usage: build_gps_probe_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -d "$sysroot/lib" ] || { echo 'sysroot lacks lib directory' >&2; exit 2; }
[ -f tools/gps/c2m_gps_probe.c ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/d3/gps_snapshot.c ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/d3/gps_snapshot.h ] || { echo 'run from repo root' >&2; exit 2; }
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
python3 - "$out/objects/probe_compat.c" "$out/objects/snapshot_compat.c" <<'PY'
from pathlib import Path
import sys
probe_dst = Path(sys.argv[1])
snapshot_dst = Path(sys.argv[2])
headers = '''#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <float.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include "compat.h"
'''
for src, dst in (('tools/gps/c2m_gps_probe.c', probe_dst),
                 ('fw/d3/gps_snapshot.c', snapshot_dst)):
    s = Path(src).read_bytes().decode('utf-8')
    s = s.replace('#define _POSIX_C_SOURCE 200809L\n', '')
    s = s.replace('#define _DEFAULT_SOURCE\n', '')
    s = s.replace('#define _GNU_SOURCE\n', '')
    dst.write_text(headers+s,encoding='utf-8')
PY
arm-linux-gnueabihf-gcc --version > "$out/objects/toolchain_version.txt" 2>&1 || { cat "$out/objects/toolchain_version.txt"; exit 1; }
cat "$out/objects/toolchain_version.txt"
arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
    -fno-stack-protector -fno-pie \
    -I "$root/fw/d3" -I "$root/tools/gps" \
    -c "$out/objects/probe_compat.c" -o "$out/objects/probe.o" \
    > "$out/objects/probe-compile.log" 2>&1 || { cat "$out/objects/probe-compile.log"; exit 1; }
cat "$out/objects/probe-compile.log"
arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
    -fno-stack-protector -fno-pie \
    -I "$root/fw/d3" -I "$root/tools/gps" \
    -c "$out/objects/snapshot_compat.c" -o "$out/objects/snapshot.o" \
    > "$out/objects/snapshot-compile.log" 2>&1 || { cat "$out/objects/snapshot-compile.log"; exit 1; }
cat "$out/objects/snapshot-compile.log"
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
    -Wl,--no-undefined -Wl,-z,noexecstack fw/device_minimal/start.S \
    "$out/objects/probe.o" "$out/objects/snapshot.o" -lm -o "$out/c2m-gps-probe" \
    > "$out/objects/probe-link.log" 2>&1 || { cat "$out/objects/probe-link.log"; exit 1; }
cat "$out/objects/probe-link.log"
python3 fw/device_minimal/check_elf.py "$out/c2m-gps-probe" --allow-dynamic \
    > "$out/objects/probe-check-elf.log" 2>&1 || { cat "$out/objects/probe-check-elf.log"; exit 1; }
cat "$out/objects/probe-check-elf.log"
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-gps-probe" --self-test \
    > "$out/gps-probe-selftest-arm.txt" 2>&1 || { cat "$out/gps-probe-selftest-arm.txt"; exit 1; }
cat "$out/gps-probe-selftest-arm.txt"
grep -q 'self_test=passed' "$out/gps-probe-selftest-arm.txt" || exit 1
grep -q 'samples_fixed=10' "$out/gps-probe-selftest-arm.txt" || exit 1
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-gps-probe" --help \
    > "$out/gps-probe-help-arm.txt" 2>&1 || { cat "$out/gps-probe-help-arm.txt"; exit 1; }
cat "$out/gps-probe-help-arm.txt"
grep -q '/tmp/car_info' "$out/gps-probe-help-arm.txt" || exit 1
arm-linux-gnueabihf-readelf -V "$out/c2m-gps-probe" > "$out/objects/c2m-gps-probe.versions.txt" 2>&1 || { cat "$out/objects/c2m-gps-probe.versions.txt"; exit 1; }
cat "$out/objects/c2m-gps-probe.versions.txt"
chmod 755 "$out/c2m-gps-probe"
sha256sum "$out/c2m-gps-probe" > "$out/gps_probe_arm_hashes.txt" || exit 1
cat "$out/gps_probe_arm_hashes.txt"
echo "gps-probe ARM RAM-only build+QEMU OK: $out/c2m-gps-probe"
