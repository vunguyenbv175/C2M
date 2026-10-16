#!/bin/sh
# RAM-only ARM build for M4 ADB standard authorization request (fw/m4_adb/m4_adb_authorize.c).
# Authorization-request only: fixed native USB 1-1 (vid 2207 pid 0013),
# interface 2 class ff subclass 42 protocol 01, bulk OUT ep 04 / IN ep 85.
# Sends one CNXN as two bulk-OUT transfers (24-byte header + 7-byte
# payload, 31 total, standard AOSP split) then one AUTH public-key as two
# bulk-OUT transfers (24-byte header + 711-byte public-key payload, 735
# total, 766 combined), reads at most four bulk-IN replies; never sends
# AUTH signature, private key, shell, OPEN, reset, config, or write payloads
# and never opens a shell. Stdin is exactly 711 PUBLIC-key bytes only.
# Exact fw/m4_adb/build_arm.sh compat pattern: generated wrapper with ALL
# system headers before compat.h, ARMv7-A hard-float VFPv3-D16, time32/off32,
# old startup, glibc<=2.30 ELF gate, QEMU pure tests. No TEST macros.
# Fail-closed: no pipes hiding exit; every capture is redirect-or-fail.
# Saves logs, versions, hashes. Run from repo root.
# Usage: sh fw/m4_adb/build_authorize_arm.sh --out DIR --sysroot STOCK_ROOTFS
set -eu
out=
sysroot=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift 2 ;;
        --sysroot) sysroot=$2; shift 2 ;;
        *) echo 'usage: build_authorize_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2 ;;
    esac
done
[ -n "$out" ] || { echo 'usage: build_authorize_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -n "$sysroot" ] || { echo 'usage: build_authorize_arm.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2; }
[ -d "$sysroot/lib" ] || { echo 'sysroot lacks lib directory' >&2; exit 2; }
[ -f fw/m4_adb/m4_adb_authorize.c ] || { echo 'run from repo root' >&2; exit 2; }
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
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <linux/usb/ch9.h>
#include <linux/usbdevice_fs.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include "compat.h"
'''
src = Path('fw/m4_adb/m4_adb_authorize.c').read_bytes().decode('utf-8')
src = src.replace('#define _POSIX_C_SOURCE 200809L\n', '')
src = src.replace('#define _DEFAULT_SOURCE\n', '')
src = src.replace('#define _GNU_SOURCE\n', '')
(out / 'm4_adb_authorize_compat.c').write_text(headers+src,encoding='utf-8')
PY
arm-linux-gnueabihf-gcc --version > "$out/objects/toolchain_version.txt" 2>&1 || { cat "$out/objects/toolchain_version.txt"; exit 1; }
cat "$out/objects/toolchain_version.txt"
arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
    -fno-stack-protector -fno-pie \
    -I "$root/fw/d3" \
    -c "$out/objects/m4_adb_authorize_compat.c" -o "$out/objects/m4_adb_authorize.o" \
    > "$out/objects/authorize-compile.log" 2>&1 || { cat "$out/objects/authorize-compile.log"; exit 1; }
cat "$out/objects/authorize-compile.log"
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
    -Wl,--no-undefined -Wl,-z,noexecstack fw/device_minimal/start.S \
    "$out/objects/m4_adb_authorize.o" -o "$out/c2m-m4-authorize" \
    > "$out/objects/authorize-link.log" 2>&1 || { cat "$out/objects/authorize-link.log"; exit 1; }
cat "$out/objects/authorize-link.log"
python3 fw/device_minimal/check_elf.py "$out/c2m-m4-authorize" --allow-dynamic \
    > "$out/objects/authorize-check-elf.log" 2>&1 || { cat "$out/objects/authorize-check-elf.log"; exit 1; }
cat "$out/objects/authorize-check-elf.log"
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-m4-authorize" --self-test \
    > "$out/authorize-selftest-arm.txt" 2>&1 || { cat "$out/authorize-selftest-arm.txt"; exit 1; }
cat "$out/authorize-selftest-arm.txt"
grep -q 'M4 ADB authorize self-test: OK' "$out/authorize-selftest-arm.txt" || exit 1
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-m4-authorize" --help \
    > "$out/authorize-help-arm.txt" 2>&1 || { cat "$out/authorize-help-arm.txt"; exit 1; }
cat "$out/authorize-help-arm.txt"
grep -q -- '--request-authorization' "$out/authorize-help-arm.txt" || exit 1
grep -q 'standard authorization request' "$out/authorize-help-arm.txt" || exit 1
grep -q 'one public key' "$out/authorize-help-arm.txt" || exit 1
grep -q 'no shell' "$out/authorize-help-arm.txt" || exit 1
if grep -q 'c2m_d4_status' "$out/c2m-m4-authorize"; then echo 'authorize must not reference status path' >&2; exit 1; fi
for flag in --serve --db --gps-file --status-file --observe; do
    if grep -q -- "$flag" "$out/c2m-m4-authorize"; then echo 'authorize must not contain writer/fixture CLI' >&2; exit 1; fi
done
for token in 'socket(' 'bind(' 'connect(' 'send(' 'sendto(' 'sendmsg(' 'recv(' 'recvfrom(' 'system(' 'popen(' 'fopen(' 'execve(' 'O_CREAT'; do
    if grep -q -F -- "$token" "$out/c2m-m4-authorize"; then echo "authorize must not contain socket/exec/file token: $token" >&2; exit 1; fi
done
for token in 'SHELL' 'A_OPEN' 'USBDEVFS_RESET' 'USBDEVFS_DISCONNECT' 'USBDEVFS_CLEAR_HALT' 'USBDEVFS_SETCONFIGURATION' 'O_TRUNC'; do
    if grep -q -F -- "$token" "$out/c2m-m4-authorize"; then echo "authorize must not contain forbidden token: $token" >&2; exit 1; fi
done
for token in '--request-authorization' 'CNXN' 'AUTH' 'M4 ADB authorize self-test: OK' 'standard authorization request' 'one public key' 'no shell'; do
    if ! grep -q -F -- "$token" "$out/c2m-m4-authorize"; then echo "authorize missing contract: $token" >&2; exit 1; fi
done
arm-linux-gnueabihf-readelf -V "$out/c2m-m4-authorize" > "$out/objects/c2m-m4-authorize.versions.txt" 2>&1 || { cat "$out/objects/c2m-m4-authorize.versions.txt"; exit 1; }
cat "$out/objects/c2m-m4-authorize.versions.txt"
chmod 755 "$out/c2m-m4-authorize"
sha256sum "$out/c2m-m4-authorize" > "$out/m4_authorize_arm_hashes.txt" || exit 1
cat "$out/m4_authorize_arm_hashes.txt"
echo "m4-authorize ARM RAM-only build+QEMU OK: $out/c2m-m4-authorize"
