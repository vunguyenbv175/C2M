#!/bin/sh
# Host-only build + self-test for tools/wifi/c2m_nlprobe.c.
# No firmware, no sysroot, no camera, no Wi-Fi device access.
# Usage: sh tools/wifi/build_nlprobe.sh --out DIR
set -eu
out=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --out) out=$2; shift 2 ;;
        *) echo 'usage: build_nlprobe.sh --out DIR' >&2; exit 2 ;;
    esac
done
[ -n "$out" ] || { echo 'usage: build_nlprobe.sh --out DIR' >&2; exit 2; }
mkdir -p "$out"
CC=${CC:-cc}
if ! command -v "$CC" >/dev/null 2>&1; then
    if command -v gcc >/dev/null 2>&1; then CC=gcc;
    elif command -v clang >/dev/null 2>&1; then CC=clang;
    else echo 'c2m-nlprobe: no C compiler (cc/gcc/clang)' >&2; exit 1; fi
fi
"$CC" -std=c99 -O2 -Wall -Wextra -Werror \
    tools/wifi/c2m_nlprobe.c -o "$out/c2m-nlprobe"
"$out/c2m-nlprobe" --help >/dev/null
"$out/c2m-nlprobe" --self-test | tee "$out/nlprobe-selftest.txt"
grep -q 'self_test=passed' "$out/nlprobe-selftest.txt"
if command -v python3 >/dev/null 2>&1; then
    python3 tools/wifi/test_c2m_nlprobe.py
fi
echo "host build+self-test OK: $out/c2m-nlprobe"
