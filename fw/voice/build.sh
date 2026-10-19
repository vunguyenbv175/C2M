#!/bin/sh
# Candidate F boot voice helper build.
#
# Builds c2m-light from fw/voice/light.c against the stock rootfs ABI and
# links dlopen/dlsym from the stock glibc-2.30 libdl (never the host 2.34+
# merged libc symbol).  The binary is read-only: it only queries the stock
# ISP AE exposure API and never writes device state.
#
# Outputs in --out:
#   c2m-light       ELF32 ARM read-only ambient light reader
#   boot_voice.sh   detached one-shot boot hook (copied verbatim)
#   objects/        private compiler intermediates (kept out of deploy dirs)
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
[ -f "$sysroot/lib/libdl-2.30.so" ] || {
    echo 'missing stock libdl-2.30.so in sysroot' >&2
    exit 2
}

mkdir -p "$out/objects"
root=$(pwd)

arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
    -fno-stack-protector -fno-pie \
    -c "$root/fw/voice/light.c" -o "$out/objects/light.o"

arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
    -Wl,--no-undefined -Wl,-z,noexecstack \
    -Wl,-rpath-link,"$sysroot/lib" -L "$sysroot/lib" \
    "$root/fw/device_minimal/start.S" "$out/objects/light.o" \
    "$sysroot/lib/libdl-2.30.so" -o "$out/c2m-light"

python3 fw/device_minimal/check_elf.py "$out/c2m-light" --allow-dynamic
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-light" --self-test
arm-linux-gnueabihf-readelf -V "$out/c2m-light" > "$out/objects/c2m-light.versions.txt"

cp fw/voice/boot_voice.sh "$out/boot_voice.sh"
chmod 755 "$out/c2m-light" "$out/boot_voice.sh"
sha256sum "$out/c2m-light" "$out/boot_voice.sh" > "$out/c2m_voice_hashes.txt"
