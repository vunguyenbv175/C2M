#!/bin/sh
# D4 dedicated GPS/offline-area advisory; no stock audio/IPC/UART output.
# Exact stock ARM32 time32/off32/glibc ABI, independently gated after link.
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
mkdir -p "$out/objects"
root=$(pwd)
for src in fw/d4/main.c fw/d4/advisory.c fw/d3/gps_snapshot.c fw/warner/db.c fw/warner/warner.c; do
    name=$(basename "$src" .c)
    python3 - "$src" "$out/objects/${name}_compat.c" <<'PY'
from pathlib import Path
import sys
source,destination = map(Path, sys.argv[1:])
s = source.read_bytes().decode('utf-8')
s = s.replace('#define _POSIX_C_SOURCE 200809L\n', '').replace('#define _DEFAULT_SOURCE\n', '')
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
destination.write_text(headers+s,encoding='utf-8')
PY
    arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
        -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
        -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
        -fno-stack-protector -fno-pie \
        -I "$root/fw/d4" -I "$root/fw/d3" -I "$root/fw/warner" \
        -c "$out/objects/${name}_compat.c" -o "$out/objects/$name.o"
done
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
    -Wl,--no-undefined -Wl,-z,noexecstack fw/device_minimal/start.S \
    "$out/objects/main.o" "$out/objects/advisory.o" "$out/objects/gps_snapshot.o" \
    "$out/objects/db.o" "$out/objects/warner.o" -lm -o "$out/c2m-signs"
python3 fw/device_minimal/check_elf.py "$out/c2m-signs" --allow-dynamic
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-signs" --self-test
arm-linux-gnueabihf-readelf -V "$out/c2m-signs" > "$out/objects/c2m-signs.versions.txt"
cp fw/d4/d4_boot.sh "$out/d4_boot.sh"
chmod 755 "$out/c2m-signs" "$out/d4_boot.sh"
sha256sum "$out/c2m-signs" "$out/d4_boot.sh" > "$out/d4_hashes.txt"
