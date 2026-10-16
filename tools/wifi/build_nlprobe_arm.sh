#!/bin/sh
# RAM-only ARM build for tools/wifi/c2m_nlprobe.c (diagnostic only).
# Exact fw/d4/build.sh + fw/d3/build.sh compat pattern: generated wrapper
# with ALL system headers before compat.h, ARMv7-A hard-float VFPv3-D16,
# time32/off32, old startup, glibc<=2.30 ELF gate, QEMU pure tests.
# No production GPS/D4 or nlprobe C edits; wrapper is generated in $out.
# Fail-closed: no pipes hiding exit; every capture is redirect-or-fail.
# Saves logs, versions, hashes. Run from repo root.
# Usage: sh tools/wifi/build_nlprobe_arm.sh --out DIR --sysroot STOCK_ROOTFS
set -eu
out=
sysroot=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift 2 ;;
        --sysroot) sysroot=$2; shift 2 ;;
        *) echo 'usage: build_nlprobe_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2 ;;
    esac
done
[ -n "$out" ] || { echo 'usage: build_nlprobe_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -n "$sysroot" ] || { echo 'usage: build_nlprobe_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -d "$sysroot/lib" ] || { echo 'sysroot lacks lib directory' >&2; exit 2; }
[ -f tools/wifi/c2m_nlprobe.c ] || { echo 'run from repo root' >&2; exit 2; }
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
python3 - "$out/objects/nlprobe_compat.c" <<'PY'
from pathlib import Path
import sys
destination = Path(sys.argv[1])
s = Path('tools/wifi/c2m_nlprobe.c').read_bytes().decode('utf-8')
s = s.replace('#define _POSIX_C_SOURCE 200809L\n', '')
s = s.replace('#define _DEFAULT_SOURCE\n', '')
s = s.replace('#define _GNU_SOURCE\n', '')
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
#include <net/if.h>
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
#ifdef __linux__
#include <linux/netlink.h>
#include <linux/genetlink.h>
#include <linux/nl80211.h>
#endif
#include "compat.h"
'''
destination.write_text(headers+s,encoding='utf-8')
PY
arm-linux-gnueabihf-gcc --version > "$out/objects/toolchain_version.txt" 2>&1 || { cat "$out/objects/toolchain_version.txt"; exit 1; }
cat "$out/objects/toolchain_version.txt"
arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
    -fno-stack-protector -fno-pie \
    -I "$root/fw/d3" \
    -c "$out/objects/nlprobe_compat.c" -o "$out/objects/nlprobe.o" \
    > "$out/objects/nlprobe-compile.log" 2>&1 || { cat "$out/objects/nlprobe-compile.log"; exit 1; }
cat "$out/objects/nlprobe-compile.log"
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
    -Wl,--no-undefined -Wl,-z,noexecstack fw/device_minimal/start.S \
    "$out/objects/nlprobe.o" -o "$out/c2m-nlprobe" \
    > "$out/objects/nlprobe-link.log" 2>&1 || { cat "$out/objects/nlprobe-link.log"; exit 1; }
cat "$out/objects/nlprobe-link.log"
python3 fw/device_minimal/check_elf.py "$out/c2m-nlprobe" --allow-dynamic \
    > "$out/objects/nlprobe-check-elf.log" 2>&1 || { cat "$out/objects/nlprobe-check-elf.log"; exit 1; }
cat "$out/objects/nlprobe-check-elf.log"
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-nlprobe" --self-test \
    > "$out/nlprobe-selftest-arm.txt" 2>&1 || { cat "$out/nlprobe-selftest-arm.txt"; exit 1; }
cat "$out/nlprobe-selftest-arm.txt"
grep -q 'self_test=passed' "$out/nlprobe-selftest-arm.txt" || exit 1
grep -q 'linux_live_validated=no' "$out/nlprobe-selftest-arm.txt" || exit 1
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-nlprobe" --help \
    > "$out/nlprobe-help-arm.txt" 2>&1 || { cat "$out/nlprobe-help-arm.txt"; exit 1; }
cat "$out/nlprobe-help-arm.txt"
grep -q 'wlan0' "$out/nlprobe-help-arm.txt" || exit 1
arm-linux-gnueabihf-readelf -V "$out/c2m-nlprobe" > "$out/objects/c2m-nlprobe.versions.txt" 2>&1 || { cat "$out/objects/c2m-nlprobe.versions.txt"; exit 1; }
cat "$out/objects/c2m-nlprobe.versions.txt"
chmod 755 "$out/c2m-nlprobe"
sha256sum "$out/c2m-nlprobe" > "$out/nlprobe_arm_hashes.txt" || exit 1
cat "$out/nlprobe_arm_hashes.txt"
echo "nlprobe ARM RAM-only build+QEMU OK: $out/c2m-nlprobe"
