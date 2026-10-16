#!/bin/sh
# RAM-only ARM build for D4 diagnostic shadow (fw/d4/main.c + advisory + GPS + DB).
# Compile-time shadow variant only: -DC2M_D4_SHADOW_OBSERVE. Production
# fw/d4/build.sh path is unchanged. Exact fw/d4/build.sh + fw/d3/build.sh
# compat pattern: generated wrappers with ALL system headers before compat.h,
# ARMv7-A hard-float VFPv3-D16, time32/off32, old startup, glibc<=2.30 ELF
# gate, QEMU pure tests. No TEST ONLY macros in this target build.
# Fail-closed: no pipes hiding exit; every capture is redirect-or-fail.
# Saves logs, versions, hashes. Run from repo root.
# Usage: sh fw/d4/build_shadow_arm.sh --out DIR --sysroot STOCK_ROOTFS
set -eu
out=
sysroot=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift 2 ;;
        --sysroot) sysroot=$2; shift 2 ;;
        *) echo 'usage: build_shadow_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2 ;;
    esac
done
[ -n "$out" ] || { echo 'usage: build_shadow_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -n "$sysroot" ] || { echo 'usage: build_shadow_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -d "$sysroot/lib" ] || { echo 'sysroot lacks lib directory' >&2; exit 2; }
[ -f fw/d4/main.c ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/d4/advisory.c ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/d3/gps_snapshot.c ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/d3/gps_snapshot.h ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/warner/db.c ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/warner/warner.c ] || { echo 'run from repo root' >&2; exit 2; }
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
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
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
sources = [
    ('fw/d4/main.c', 'main_compat.c'),
    ('fw/d4/advisory.c', 'advisory_compat.c'),
    ('fw/d3/gps_snapshot.c', 'gps_snapshot_compat.c'),
    ('fw/warner/db.c', 'db_compat.c'),
    ('fw/warner/warner.c', 'warner_compat.c'),
]
for src, dst in sources:
    s = Path(src).read_bytes().decode('utf-8')
    s = s.replace('#define _POSIX_C_SOURCE 200809L\n', '')
    s = s.replace('#define _DEFAULT_SOURCE\n', '')
    s = s.replace('#define _GNU_SOURCE\n', '')
    (out / dst).write_text(headers+s,encoding='utf-8')
PY
arm-linux-gnueabihf-gcc --version > "$out/objects/toolchain_version.txt" 2>&1 || { cat "$out/objects/toolchain_version.txt"; exit 1; }
cat "$out/objects/toolchain_version.txt"
for name in main advisory gps_snapshot db warner; do
    arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
        -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
        -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
        -fno-stack-protector -fno-pie \
        -DC2M_D4_SHADOW_OBSERVE \
        -I "$root/fw/d4" -I "$root/fw/d3" -I "$root/fw/warner" \
        -c "$out/objects/${name}_compat.c" -o "$out/objects/${name}.o" \
        > "$out/objects/${name}-compile.log" 2>&1 || { cat "$out/objects/${name}-compile.log"; exit 1; }
    cat "$out/objects/${name}-compile.log"
done
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
    -Wl,--no-undefined -Wl,-z,noexecstack fw/device_minimal/start.S \
    "$out/objects/main.o" "$out/objects/advisory.o" "$out/objects/gps_snapshot.o" \
    "$out/objects/db.o" "$out/objects/warner.o" -lm -o "$out/c2m-d4-shadow" \
    > "$out/objects/shadow-link.log" 2>&1 || { cat "$out/objects/shadow-link.log"; exit 1; }
cat "$out/objects/shadow-link.log"
python3 fw/device_minimal/check_elf.py "$out/c2m-d4-shadow" --allow-dynamic \
    > "$out/objects/shadow-check-elf.log" 2>&1 || { cat "$out/objects/shadow-check-elf.log"; exit 1; }
cat "$out/objects/shadow-check-elf.log"
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-d4-shadow" --self-test \
    > "$out/shadow-selftest-arm.txt" 2>&1 || { cat "$out/shadow-selftest-arm.txt"; exit 1; }
cat "$out/shadow-selftest-arm.txt"
grep -q 'D4 synthetic advisory self-test: OK' "$out/shadow-selftest-arm.txt" || exit 1
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-d4-shadow" --help \
    > "$out/shadow-help-arm.txt" 2>&1 || { cat "$out/shadow-help-arm.txt"; exit 1; }
cat "$out/shadow-help-arm.txt"
grep -q -- '--observe' "$out/shadow-help-arm.txt" || exit 1
grep -q '/tmp/car_info' "$out/shadow-help-arm.txt" || exit 1
grep -q '/customer/c2m/signs-d4.bin' "$out/shadow-help-arm.txt" || exit 1
grep -q 'observer simulation' "$out/shadow-help-arm.txt" || exit 1
if grep -q 'c2m_d4_status' "$out/c2m-d4-shadow"; then echo 'shadow must not reference status path' >&2; exit 1; fi
for flag in --serve --db --gps-file --status-file; do
    if grep -q -- "$flag" "$out/c2m-d4-shadow"; then echo 'shadow must not contain writer/fixture CLI' >&2; exit 1; fi
done
arm-linux-gnueabihf-readelf -V "$out/c2m-d4-shadow" > "$out/objects/c2m-d4-shadow.versions.txt" 2>&1 || { cat "$out/objects/c2m-d4-shadow.versions.txt"; exit 1; }
cat "$out/objects/c2m-d4-shadow.versions.txt"
chmod 755 "$out/c2m-d4-shadow"
sha256sum "$out/c2m-d4-shadow" > "$out/d4_shadow_arm_hashes.txt" || exit 1
cat "$out/d4_shadow_arm_hashes.txt"
echo "d4-shadow ARM RAM-only build+QEMU OK: $out/c2m-d4-shadow"
