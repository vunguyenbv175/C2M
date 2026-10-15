#!/bin/sh
# fw/debug/build_dropbear.sh — pinned Dropbear server+key + debug supervisor.
# Scope: full debug bundle build ONLY (dropbear, dropbearkey, c2m-debug,
#          debug_boot.sh + reports). No exact deploy; parent deploys to
#          /customer/c2m separately (run after D4 build).
# Target: ARMv7-A/VFPv3-D16, stock glibc 2.30 loader (/lib/ld-linux-armhf.so.3).
# Upstream: dropbear-2026.94 (bundled libtomcrypt/libtommath, no zlib).
# Pattern: fw/d3/build_supplicant.sh + fw/d3/compat.h + fw/device_minimal/start.S
#          + fw/d3/init_arrays.c (custom _start pins GLIBC_2.4, -nostartfiles).
#          Supervisor uses the fw/d4/build.sh wrapper pattern (headers before
#          compat.h, own TU, plain start.S link, --self-test gate, no serve).
# Safety: official localoptions.h disables ONLY (password/PAM, forwarding,
#          proxy/netcat) + MULTIUSER=0 (root-only same-UID; otherwise the
#          root-run -D keydir would authorize every local account).
#          No auth bypass, no default keys. getrandom (GLIBC_2.25) kept; gate
#          caps max need at 2.30, no SIMPLERANDOM override.
# Fail-closed logging: no cmd|tee pipes anywhere; every capture is
#          redirect-or-fail (>report 2>&1 || { cat report; exit 1; }) so set -e
#          sees the real status. Compiled macro proof (gcc -dM -E on
#          options.h) runs before make; QEMU -V must exit 0, -h exits are
#          asserted (dropbear 0/1, dropbearkey 1).
# Run from repo root: sh fw/debug/build_dropbear.sh --out DIR --sysroot ROOT
set -eu
out=
sysroot=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift 2 ;;
        --sysroot) sysroot=$2; shift 2 ;;
        *) echo 'usage: build_dropbear.sh --out DIR --sysroot STOCK_ROOTFS' >&2; exit 2 ;;
    esac
done
[ -n "$out" ] || { echo 'missing --out' >&2; exit 2; }
[ -n "$sysroot" ] && [ -d "$sysroot/lib" ] || { echo 'missing/invalid --sysroot' >&2; exit 2; }
[ -f fw/d3/compat.h ] || { echo 'run from repo root' >&2; exit 2; }
[ -f fw/device_minimal/start.S ] || exit 2
[ -f fw/device_minimal/check_elf.py ] || exit 2
[ -f fw/debug/supervisor.c ] || exit 2
[ -f fw/debug/supervisor.h ] || exit 2
[ -f fw/debug/debug_boot.sh ] || exit 2
command -v arm-linux-gnueabihf-gcc >/dev/null 2>&1 || { echo 'need arm-linux-gnueabihf-gcc' >&2; exit 2; }
command -v arm-linux-gnueabihf-readelf >/dev/null 2>&1 || { echo 'need arm-linux-gnueabihf-readelf' >&2; exit 2; }
command -v qemu-arm-static >/dev/null 2>&1 || { echo 'need qemu-arm-static' >&2; exit 2; }
command -v curl >/dev/null 2>&1 || exit 2
[ -f "$sysroot/lib/ld-linux-armhf.so.3" ] || { echo 'sysroot lacks /lib/ld-linux-armhf.so.3' >&2; exit 2; }

VER=2026.94
URL=https://matt.ucc.asn.au/dropbear/releases/dropbear-2026.94.tar.bz2
SHA=e098034a843699200c8c977a991fff73159735bf795d5f72ef672c41a6b1ae81

root=$(pwd)
mkdir -p "$out" "$root/work/dropbear-upstream"
out=$(cd "$out" && pwd)
sysroot=$(cd "$sysroot" && pwd)
work="$root/work/dropbear-upstream"
src="$work/dropbear-$VER"
mkdir -p "$out/reports" "$out/objects"

fetch() {
    curl --fail --location --proto '=https' --tlsv1.2 --retry 2 --max-time 120 \
        "$2" -o "$work/$1"
    printf '%s  %s\n' "$3" "$work/$1" > "$work/$1.sha256"
    sha256sum -c "$work/$1.sha256" > "$work/$1.shacheck.log" 2>&1 || { cat "$work/$1.shacheck.log"; exit 1; }
    cat "$work/$1.shacheck.log"
}
fetch dropbear-$VER.tar.bz2 "$URL" "$SHA"

# Only the generated extracted dir below is removed; user sources and
# worktrees are never touched (work/dropbear-upstream holds fetch+build only).
rm -rf "$src"
tar -C "$work" -xf "$work/dropbear-$VER.tar.bz2"

# Compile prefix: libc headers BEFORE compat header (proven supplicant order).
cat > "$work/compat_prefix.h" <<EOF
#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include "$root/fw/d3/compat.h"
EOF
flags="-Os -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard -fno-stack-protector -fno-pie -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -include $work/compat_prefix.h"

# Custom _start (GLIBC_2.4 pin) + init-array trampoline for static archives.
python3 - "$work/start.S" <<'PY'
from pathlib import Path
import sys
s = Path('fw/device_minimal/start.S').read_text()
s = s.replace('mov a4, #0\n    push {a4}', 'mov a4, #0\n    push {a4}\n    ldr a4, =c2m_init_arrays')
Path(sys.argv[1]).write_text(s)
PY
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -c "$work/start.S" -o "$work/start.o"
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -c fw/d3/init_arrays.c -o "$work/init_arrays.o"

# Official feature selection only. Pubkey stays on (needs -D). Root-only
# same-UID server: MULTIUSER=0 so -D <run dir> cannot authorize other
# accounts (pre-auth runs as root and could read the root-only keydir).
# DROP_PRIVS follows MULTIUSER (0). No bypass.
cat > "$src/localoptions.h" <<'EOF'
#ifndef DROPBEAR_LOCALOPTIONS_H
#define DROPBEAR_LOCALOPTIONS_H
#undef DROPBEAR_SVR_PASSWORD_AUTH
#define DROPBEAR_SVR_PASSWORD_AUTH 0
#undef DROPBEAR_SVR_PAM_AUTH
#define DROPBEAR_SVR_PAM_AUTH 0
#undef DROPBEAR_SVR_SHADOW_AUTH
#define DROPBEAR_SVR_SHADOW_AUTH 0
#undef DROPBEAR_CLI_PASSWORD_AUTH
#define DROPBEAR_CLI_PASSWORD_AUTH 0
#undef DROPBEAR_SVR_AGENTFWD
#define DROPBEAR_SVR_AGENTFWD 0
#undef DROPBEAR_CLI_AGENTFWD
#define DROPBEAR_CLI_AGENTFWD 0
#undef DROPBEAR_X11FWD
#define DROPBEAR_X11FWD 0
#undef DROPBEAR_SVR_LOCALTCPFWD
#define DROPBEAR_SVR_LOCALTCPFWD 0
#undef DROPBEAR_SVR_REMOTETCPFWD
#define DROPBEAR_SVR_REMOTETCPFWD 0
#undef DROPBEAR_CLI_LOCALTCPFWD
#define DROPBEAR_CLI_LOCALTCPFWD 0
#undef DROPBEAR_CLI_REMOTETCPFWD
#define DROPBEAR_CLI_REMOTETCPFWD 0
#undef DROPBEAR_SVR_LOCALSTREAMFWD
#define DROPBEAR_SVR_LOCALSTREAMFWD 0
#undef DROPBEAR_SVR_REMOTESTREAMFWD
#define DROPBEAR_SVR_REMOTESTREAMFWD 0
#undef DROPBEAR_CLI_PROXYCMD
#define DROPBEAR_CLI_PROXYCMD 0
#undef DROPBEAR_CLI_NETCAT
#define DROPBEAR_CLI_NETCAT 0
#undef DROPBEAR_SFTPSERVER
#define DROPBEAR_SFTPSERVER 0
#undef DROPBEAR_CLI_COMPRESSION
#define DROPBEAR_CLI_COMPRESSION 0
#undef DROPBEAR_ED25519
#define DROPBEAR_ED25519 1
#undef DROPBEAR_ECDSA
#define DROPBEAR_ECDSA 1
#undef DROPBEAR_ECDH
#define DROPBEAR_ECDH 1
#undef DROPBEAR_CURVE25519
#define DROPBEAR_CURVE25519 1
#undef DROPBEAR_CHACHA20POLY1305
#define DROPBEAR_CHACHA20POLY1305 1
#undef DROPBEAR_AES128
#define DROPBEAR_AES128 1
#undef DROPBEAR_AES256
#define DROPBEAR_AES256 1
#undef DROPBEAR_SHA2_256_HMAC
#define DROPBEAR_SHA2_256_HMAC 1
#undef DROPBEAR_DH_GROUP14_SHA256
#define DROPBEAR_DH_GROUP14_SHA256 1
#undef DROPBEAR_SVR_PUBKEY_AUTH
#define DROPBEAR_SVR_PUBKEY_AUTH 1
#undef DROPBEAR_SVR_MULTIUSER
#define DROPBEAR_SVR_MULTIUSER 0
#endif
EOF

# Configure: probe --help, use only proven options. Force bundled libtom,
# no zlib, no harden (would inject PIE/stack-protector/FORTIFY >2.30).
(
    cd "$src"
    ./configure --help > "$out/reports/configure-help.txt" 2>&1
    cfg="--host=arm-linux-gnueabihf --disable-harden --disable-zlib --enable-bundled-libtom"
    for o in syslog shadow lastlog utmp utmpx wtmp wtmpx loginfunc pututline pututxline openpty; do
        if grep -q -- "--disable-$o" "$out/reports/configure-help.txt"; then
            cfg="$cfg --disable-$o"
        fi
    done
    grep -q -- "--enable-bundled-libtom" "$out/reports/configure-help.txt" || { echo 'bundled-libtom option missing' >&2; exit 1; }
    printf '%s\n' "$cfg" > "$out/reports/configure-opts.txt"
    # No host crypt: password auth is compiled out, do not detect/link -lcrypt.
    # shellcheck disable=SC2086
    ac_cv_func_crypt=no ac_cv_lib_crypt_crypt=no \
        CC=arm-linux-gnueabihf-gcc AR=arm-linux-gnueabihf-ar RANLIB=arm-linux-gnueabihf-ranlib \
        CFLAGS="$flags" LTM_CFLAGS="$flags -O2 -funroll-loops -fomit-frame-pointer" \
        ./configure $cfg > "$out/reports/configure.log" 2>&1 || { cat "$out/reports/configure.log"; exit 1; }
    cat "$out/reports/configure.log"
    # LTM_CFLAGS propagation: bundled libtommath Makefile must carry arch/prefix.
    grep -q "armv7-a" libtommath/Makefile || { echo 'LTM_CFLAGS did not propagate' >&2; exit 1; }
    grep -q "compat_prefix" libtommath/Makefile || { echo 'LTM compat prefix missing' >&2; exit 1; }
    # Modern random path record: getrandom (GLIBC_2.25) is within the 2.30 cap.
    # NOTE: config.h holds only configure probes; Dropbear option values live
    # in the preprocessor output below, never in config.h.
    grep -i -E "getrandom|explicit_bzero|memset_s" config.h > "$out/reports/config-random.txt" 2>&1 || true
    cat "$out/reports/config-random.txt"
)

# Compiled macro proof BEFORE make: preprocess options.h with the real build
# flags. This pulls config.h, localoptions.h (-DLOCALOPTIONS_H_EXISTS) and the
# post-default computed values, so it proves what the compiler will see.
# Records a sanitized DROPBEAR_* snapshot plus pass/fail helpers.
(
    cd "$src"
    make default_options_guard.h > "$out/reports/guard.log" 2>&1 || { cat "$out/reports/guard.log"; exit 1; }
    cat "$out/reports/guard.log"
    printf '#include "options.h"\n' > "$work/macro_probe.c"
    # shellcheck disable=SC2086
    arm-linux-gnueabihf-gcc -dM -E -DLOCALOPTIONS_H_EXISTS -I. -Isrc $flags \
        -x c "$work/macro_probe.c" > "$out/reports/dropbear-macros-full.txt" 2>"$out/reports/dropbear-macros-err.txt" \
        || { cat "$out/reports/dropbear-macros-err.txt"; exit 1; }
    grep "^#define DROPBEAR_" "$out/reports/dropbear-macros-full.txt" > "$out/reports/dropbear-macros.txt" \
        || { echo 'no DROPBEAR macros in preprocessor output' >&2; exit 1; }
    cat "$out/reports/dropbear-macros.txt"
    assert_macro() {
        if ! grep -q "^#define $1 $2$" "$out/reports/dropbear-macros.txt"; then
            echo "macro proof FAIL: $1 != $2" >&2
            exit 1
        fi
    }
    reject_macro() {
        if grep -q "^#define $1 $2$" "$out/reports/dropbear-macros.txt"; then
            echo "macro proof FAIL: forbidden $1 == $2 present" >&2
            exit 1
        fi
    }
    assert_macro DROPBEAR_SVR_PASSWORD_AUTH 0
    assert_macro DROPBEAR_SVR_PAM_AUTH 0
    assert_macro DROPBEAR_SVR_MULTIUSER 0
    assert_macro DROPBEAR_SVR_AGENTFWD 0
    assert_macro DROPBEAR_CLI_AGENTFWD 0
    assert_macro DROPBEAR_X11FWD 0
    assert_macro DROPBEAR_SVR_LOCALTCPFWD 0
    assert_macro DROPBEAR_SVR_REMOTETCPFWD 0
    assert_macro DROPBEAR_CLI_LOCALTCPFWD 0
    assert_macro DROPBEAR_CLI_REMOTETCPFWD 0
    assert_macro DROPBEAR_SVR_LOCALSTREAMFWD 0
    assert_macro DROPBEAR_SVR_REMOTESTREAMFWD 0
    assert_macro DROPBEAR_CLI_PROXYCMD 0
    assert_macro DROPBEAR_CLI_NETCAT 0
    assert_macro DROPBEAR_SFTPSERVER 0
    assert_macro DROPBEAR_SVR_PUBKEY_AUTH 1
    assert_macro DROPBEAR_ED25519 1
    assert_macro DROPBEAR_CHACHA20POLY1305 1
    reject_macro DROPBEAR_SVR_PASSWORD_AUTH 1
    reject_macro DROPBEAR_SVR_PAM_AUTH 1
    reject_macro DROPBEAR_SVR_MULTIUSER 1
    echo 'macro proof: OK (password/pam/multiuser/forwarding off, pubkey on)'
)

# Build server+key only. LDFLAGS pins custom start, stock loader, no-exec-stack.
(
    cd "$src"
    # shellcheck disable=SC2086
    make -j2 PROGRAMS='dropbear dropbearkey' CC=arm-linux-gnueabihf-gcc \
        AR=arm-linux-gnueabihf-ar RANLIB=arm-linux-gnueabihf-ranlib \
        CFLAGS="$flags" \
        LDFLAGS="-nostartfiles -no-pie $work/start.o $work/init_arrays.o -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 -Wl,-z,noexecstack" \
        > "$out/reports/build.log" 2>&1 || { cat "$out/reports/build.log"; exit 1; }
    cat "$out/reports/build.log"
    [ -f dropbear ] || { echo 'make did not produce dropbear' >&2; exit 1; }
    [ -f dropbearkey ] || { echo 'make did not produce dropbearkey' >&2; exit 1; }
    # CFLAGS propagation: every cross compile line must carry the compat prefix.
    grep -q "arm-linux-gnueabihf-gcc" "$out/reports/build.log" || { echo 'no compile lines in build log' >&2; exit 1; }
    awk '/arm-linux-gnueabihf-gcc/ && / -c( |$)/ && !/compat_prefix/ { print "missing prefix: " $0; bad=1 } END { exit (bad ? 1 : 0) }' \
        "$out/reports/build.log" > "$out/reports/prefix-check.txt" 2>&1 \
        || { cat "$out/reports/prefix-check.txt"; exit 1; }
    cat "$out/reports/prefix-check.txt"
)

cp "$src/dropbear" "$out/dropbear"
cp "$src/dropbearkey" "$out/dropbearkey"
chmod 755 "$out/dropbear" "$out/dropbearkey"

# ELF gates: dynamic, /lib/ld-linux-armhf.so.3, NEEDED in {libc,libm,libgcc}, max GLIBC 2.30.
# No cmd|tee pipes: each capture is redirect-or-fail so set -e sees the status.
arm-linux-gnueabihf-readelf -W --dyn-syms "$out/dropbear" > "$out/reports/dropbear-dynsyms.txt" 2>&1 \
    || { cat "$out/reports/dropbear-dynsyms.txt"; exit 1; }
grep GLIBC_ "$out/reports/dropbear-dynsyms.txt" > "$out/reports/dropbear-glibc-unsorted.txt" \
    || { echo 'no GLIBC refs in dropbear (unexpected for a dynamic binary)' >&2; exit 1; }
sort "$out/reports/dropbear-glibc-unsorted.txt" > "$out/reports/dropbear-glibc.txt" || exit 1
cat "$out/reports/dropbear-glibc.txt"
arm-linux-gnueabihf-readelf -W --dyn-syms "$out/dropbearkey" > "$out/reports/dropbearkey-dynsyms.txt" 2>&1 \
    || { cat "$out/reports/dropbearkey-dynsyms.txt"; exit 1; }
grep GLIBC_ "$out/reports/dropbearkey-dynsyms.txt" > "$out/reports/dropbearkey-glibc-unsorted.txt" \
    || { echo 'no GLIBC refs in dropbearkey (unexpected for a dynamic binary)' >&2; exit 1; }
sort "$out/reports/dropbearkey-glibc-unsorted.txt" > "$out/reports/dropbearkey-glibc.txt" || exit 1
cat "$out/reports/dropbearkey-glibc.txt"
python3 fw/device_minimal/check_elf.py "$out/dropbear" --allow-dynamic > "$out/reports/check_elf-dropbear.txt" 2>&1 \
    || { cat "$out/reports/check_elf-dropbear.txt"; exit 1; }
cat "$out/reports/check_elf-dropbear.txt"
python3 fw/device_minimal/check_elf.py "$out/dropbearkey" --allow-dynamic > "$out/reports/check_elf-dropbearkey.txt" 2>&1 \
    || { cat "$out/reports/check_elf-dropbearkey.txt"; exit 1; }
cat "$out/reports/check_elf-dropbearkey.txt"
arm-linux-gnueabihf-readelf -V "$out/dropbear" > "$out/objects/dropbear.versions.txt"
arm-linux-gnueabihf-readelf -V "$out/dropbearkey" > "$out/objects/dropbearkey.versions.txt"

# QEMU smoke on stock sysroot: version/help, -D/-l presence, keygen -y proof.
# Exit policy (rc recorded per command): -V must exit 0; -h may exit 0 or 1
# (usage printers vary); dropbearkey -h is expected to fail (exit 1).
timeout 20 qemu-arm-static -L "$sysroot" "$out/dropbear" -V > "$out/reports/dropbear-V.txt" 2>&1 \
    || { cat "$out/reports/dropbear-V.txt"; exit 1; }
cat "$out/reports/dropbear-V.txt"
grep -q "$VER" "$out/reports/dropbear-V.txt" || { echo 'version proof missing' >&2; exit 1; }
rc=0
timeout 20 qemu-arm-static -L "$sysroot" "$out/dropbear" -h > "$out/reports/dropbear-h.txt" 2>&1 || rc=$?
printf 'exit=%s\n' "$rc" > "$out/reports/dropbear-h-rc.txt"
cat "$out/reports/dropbear-h.txt"
[ "$rc" = 0 ] || [ "$rc" = 1 ] || { echo "dropbear -h unexpected exit $rc" >&2; exit 1; }
grep -q -- "-D" "$out/reports/dropbear-h.txt" || { echo 'dropbear -D support missing' >&2; exit 1; }
grep -q -- "-l" "$out/reports/dropbear-h.txt" || { echo 'dropbear -l support missing' >&2; exit 1; }
rc=0
timeout 20 qemu-arm-static -L "$sysroot" "$out/dropbearkey" -h > "$out/reports/dropbearkey-h.txt" 2>&1 || rc=$?
printf 'exit=%s\n' "$rc" > "$out/reports/dropbearkey-h-rc.txt"
cat "$out/reports/dropbearkey-h.txt"
[ "$rc" = 1 ] || { echo "dropbearkey -h expected exit 1, got $rc" >&2; exit 1; }
rm -rf "$work/smoke-keys"
mkdir -p "$work/smoke-keys"
timeout 20 qemu-arm-static -L "$sysroot" "$out/dropbearkey" -t ed25519 -f "$work/smoke-keys/host_ed25519" \
    > "$out/reports/dropbearkey-gen.txt" 2>&1 || { cat "$out/reports/dropbearkey-gen.txt"; exit 1; }
cat "$out/reports/dropbearkey-gen.txt"
timeout 20 qemu-arm-static -L "$sysroot" "$out/dropbearkey" -f "$work/smoke-keys/host_ed25519" -y \
    > "$out/reports/dropbearkey-y.txt" 2>&1 || { cat "$out/reports/dropbearkey-y.txt"; exit 1; }
cat "$out/reports/dropbearkey-y.txt"
grep -q "ssh-ed25519" "$out/reports/dropbearkey-y.txt" || { echo 'ed25519 -y proof missing' >&2; exit 1; }

# Supervisor (own TU): fw/d4/build.sh wrapper pattern. Headers BEFORE compat,
# source macro duplicates stripped (supervisor.c carries static _POSIX_...).
# Own code has no static-archive constructors: link plain start.S (d4 style),
# no init_arrays.o. Gate: check_elf + QEMU --self-test only (no serve/fixtures).
python3 - "fw/debug/supervisor.c" "$out/objects/supervisor_compat.c" <<'PY'
from pathlib import Path
import sys
source, destination = map(Path, sys.argv[1:])
s = source.read_bytes().decode('utf-8')
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
#include <net/if.h>
#include <netinet/in.h>
#include <poll.h>
#include <pwd.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#ifdef __linux__
#include <linux/wireless.h>
#endif
#include "compat.h"
'''
destination.write_text(headers+s,encoding='utf-8')
PY
arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror \
    -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 \
    -fno-stack-protector -fno-pie \
    -I "$root/fw/d3" -I "$root/fw/debug" \
    -c "$out/objects/supervisor_compat.c" -o "$out/objects/supervisor.o"
arm-linux-gnueabihf-gcc -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard \
    -nostartfiles -no-pie -Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 \
    -Wl,--no-undefined -Wl,-z,noexecstack fw/device_minimal/start.S \
    "$out/objects/supervisor.o" -o "$out/c2m-debug"
chmod 755 "$out/c2m-debug"
arm-linux-gnueabihf-readelf -W --dyn-syms "$out/c2m-debug" > "$out/reports/c2m-debug-dynsyms.txt" 2>&1 \
    || { cat "$out/reports/c2m-debug-dynsyms.txt"; exit 1; }
grep GLIBC_ "$out/reports/c2m-debug-dynsyms.txt" > "$out/reports/c2m-debug-glibc-unsorted.txt" \
    || { echo 'no GLIBC refs in c2m-debug (unexpected for a dynamic binary)' >&2; exit 1; }
sort "$out/reports/c2m-debug-glibc-unsorted.txt" > "$out/reports/c2m-debug-glibc.txt" || exit 1
cat "$out/reports/c2m-debug-glibc.txt"
python3 fw/device_minimal/check_elf.py "$out/c2m-debug" --allow-dynamic > "$out/reports/check_elf-c2m-debug.txt" 2>&1
cat "$out/reports/check_elf-c2m-debug.txt"
timeout 30 qemu-arm-static -L "$sysroot" "$out/c2m-debug" --self-test > "$out/reports/c2m-debug-selftest.txt" 2>&1
cat "$out/reports/c2m-debug-selftest.txt"
arm-linux-gnueabihf-readelf -V "$out/c2m-debug" > "$out/objects/c2m-debug.versions.txt"
cp fw/debug/debug_boot.sh "$out/debug_boot.sh"
chmod 755 "$out/debug_boot.sh"

# Provenance: objects, prefix, localoptions, licenses, source pin, hashes.
cp "$work/start.o" "$work/init_arrays.o" "$work/compat_prefix.h" "$out/objects/"
cp "$src/localoptions.h" "$out/objects/localoptions.h"
for f in LICENSE COPYING README; do
    [ -f "$src/$f" ] && cp "$src/$f" "$out/dropbear.$f"
done
[ -f "$out/dropbear.LICENSE" ] || [ -f "$out/dropbear.COPYING" ] || { echo 'license copy missing' >&2; exit 1; }
cat > "$out/dropbear_SOURCE.json" <<EOF
{"dropbear":{"version":"$VER","url":"$URL","sha256":"$SHA","license":"MIT (see dropbear.LICENSE/COPYING in out)"},"link":"dynamic stock glibc2.30; bundled libtomcrypt/libtommath static; no zlib/crypt/pam","radio_tested":false}
EOF
sha256sum "$out/dropbear" "$out/dropbearkey" > "$out/dropbear.sha256"
cat "$out/dropbear.sha256"
sha256sum "$out/c2m-debug" "$out/debug_boot.sh" > "$out/debug.sha256"
cat "$out/debug.sha256"
