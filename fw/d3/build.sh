#!/bin/sh
# ARMv7-A/VFPv3-D16 exact EN loader ABI. No new runtime libraries.
set -eu
out=
sysroot=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift 2 ;;
        --sysroot) sysroot=$2; shift 2 ;;
        *) echo 'usage: build.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2 ;;
    esac
done
[ -n "$out" ] && [ -d "$sysroot/lib" ] || exit 2
mkdir -p "$out" "$out/objects"
root=$(pwd)
for pair in web:c2m-web wifi_control:c2m-wifi; do
    src=${pair%%:*}
    exe=${pair#*:}
    # Put compatibility header AFTER libc headers, BEFORE function definitions.
    python3 - "$src" "$out" <<'PY'
from pathlib import Path
import sys
name,out=sys.argv[1:]
p=Path('fw/d3')/(name+'.c')
s=p.read_bytes().decode('utf-8')
# Wrapper has already set these before headers. Avoid macro redefinition
# diagnostics (the source uses empty defines; -Werror is intentionally on).
s=s.replace('#define _POSIX_C_SOURCE 200809L\n', '').replace('#define _DEFAULT_SOURCE\n', '')
# The dedicated marker precedes the source; -imacros is unsafe because it
# would rewrite stat declarations. Force a preprocessing wrapper instead.
headers='''#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <net/if.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "compat.h"
'''
Path(out,'objects',name+'_compat.c').write_text(headers+s,encoding='utf-8')
PY
    arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
        -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
        -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
        -fno-stack-protector -fno-pie -I "$root/fw/d3" \
        -c "$out/objects/${src}_compat.c" -o "$out/objects/$src.o"
    arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
        -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
        -Wl,--no-undefined -Wl,-z,noexecstack \
        fw/device_minimal/start.S "$out/objects/$src.o" -o "$out/$exe"
    python3 fw/device_minimal/check_elf.py "$out/$exe" --allow-dynamic
    timeout 30 qemu-arm-static -L "$sysroot" "$out/$exe" --self-test
    arm-linux-gnueabihf-readelf -V "$out/$exe" > "$out/objects/$exe.versions.txt"
done
cp fw/d3/boot.sh fw/d3/connectivity_probe.sh "$out/"
chmod 755 "$out/boot.sh" "$out/connectivity_probe.sh" "$out/c2m-web" "$out/c2m-wifi"
# Explicit deploy list excludes build objects and every incidental source.
sha256sum "$out/boot.sh" "$out/connectivity_probe.sh" "$out/c2m-web" "$out/c2m-wifi" \
    > "$out/d3_hashes.txt"
