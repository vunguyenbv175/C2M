#!/bin/sh
# Pinned BSD WPA2 client, no replacement of stock AP/hostapd, no radio test.
# Private release binaries only. libnl is statically linked; libc stays stock.
set -eu
out=
sysroot=
while [ "$#" -gt 0 ]; do
    case "$1" in --out) out=$2; shift 2 ;; --sysroot) sysroot=$2; shift 2 ;;
        *) echo 'usage: build_supplicant.sh --out DIR --sysroot DIR' >&2; exit 2 ;; esac
done
[ -n "$out" ] && [ -d "$sysroot/lib" ] || exit 2
root=$(pwd)
mkdir -p "$out" work/d3-upstream
out=$(cd "$out" && pwd)
sysroot=$(cd "$sysroot" && pwd)
work="$root/work/d3-upstream"
fetch() {
    curl --fail --location --proto '=https' --tlsv1.2 --retry 2 --max-time 120 \
        "$2" -o "$work/$1"
    printf '%s  %s\n' "$3" "$work/$1" | sha256sum -c -
}
fetch wpa_supplicant-2.12.tar.gz https://w1.fi/releases/wpa_supplicant-2.12.tar.gz \
    08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6
fetch libnl-3.11.0.tar.gz https://github.com/thom311/libnl/releases/download/libnl3_11_0/libnl-3.11.0.tar.gz \
    2a56e1edefa3e68a7c00879496736fdbf62fc94ed3232c0baba127ecfa76874d
# Dedicated directory only; do not overwrite any user source/worktree.
tar -C "$work" -xf "$work/libnl-3.11.0.tar.gz"
tar -C "$work" -xf "$work/wpa_supplicant-2.12.tar.gz"
cat > "$work/compat_prefix.h" <<EOF
#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include "$root/fw/d3/compat.h"
EOF
flags="-Os -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -fno-stack-protector -fno-pie -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -include $work/compat_prefix.h"
(
    cd "$work/libnl-3.11.0"
    CC=arm-linux-gnueabihf-gcc AR=arm-linux-gnueabihf-ar RANLIB=arm-linux-gnueabihf-ranlib \
        CFLAGS="$flags" ./configure --host=arm-linux-gnueabihf --prefix="$work/nl" \
        --enable-static --disable-shared --disable-cli --disable-pthreads
    make -j2
    make install
)
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -c fw/device_minimal/start.S -o "$work/start.o"
cat > "$work/pkg-config-static" <<'EOF'
#!/bin/sh
exec pkg-config --static "$@"
EOF
chmod +x "$work/pkg-config-static"
cat > "$work/wpa_supplicant-2.12/wpa_supplicant/.config" <<'EOF'
CONFIG_DRIVER_NL80211=y
CONFIG_LIBNL32=y
CONFIG_CTRL_IFACE=y
CONFIG_CTRL_IFACE_UNIX=y
CONFIG_TLS=internal
CONFIG_INTERNAL_LIBTOMMATH=y
CONFIG_INTERNAL_LIBTOMMATH_FAST=y
CONFIG_NO_EAP=y
CONFIG_NO_WPA_PASSPHRASE=y
CONFIG_NO_CONFIG_WRITE=y
CONFIG_NO_STDOUT_DEBUG=y
CONFIG_NO_TKIP=y
CONFIG_NO_WEP=y
CONFIG_BACKEND=file
EOF
(
    cd "$work/wpa_supplicant-2.12/wpa_supplicant"
    PKG_CONFIG_LIBDIR="$work/nl/lib/pkgconfig" PKG_CONFIG_PATH= \
        make -j2 wpa_supplicant CC=arm-linux-gnueabihf-gcc \
        PKG_CONFIG="$work/pkg-config-static" EXTRA_CFLAGS="$flags" \
        LDFLAGS="-nostartfiles -no-pie $work/start.o -L$work/nl/lib -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 -Wl,-z,noexecstack"
)
cp "$work/wpa_supplicant-2.12/wpa_supplicant/wpa_supplicant" "$out/wpa_supplicant"
chmod 755 "$out/wpa_supplicant"
python3 fw/device_minimal/check_elf.py "$out/wpa_supplicant" --allow-dynamic
timeout 20 qemu-arm-static -L "$sysroot" "$out/wpa_supplicant" -v
# Ship attribution/licenses with private deliverable (not exposed web content).
cp "$work/wpa_supplicant-2.12/COPYING" "$out/wpa_supplicant.COPYING"
cat > "$out/supplicant_SOURCE.json" <<'EOF'
{"wpa_supplicant":{"version":"2.12","url":"https://w1.fi/releases/wpa_supplicant-2.12.tar.gz","sha256":"08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6","license":"BSD-3-Clause"},"libnl":{"version":"3.11.0","url":"https://github.com/thom311/libnl/releases/download/libnl3_11_0/libnl-3.11.0.tar.gz","sha256":"2a56e1edefa3e68a7c00879496736fdbf62fc94ed3232c0baba127ecfa76874d","license":"LGPL-2.1","link":"static; preserve exact corresponding source/build recipe in vault"},"radio_tested":false}
EOF
sha256sum "$out/wpa_supplicant" > "$out/supplicant.sha256"
