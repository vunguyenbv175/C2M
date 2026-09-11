#!/bin/sh
set -eu

EN='firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar'
VI='firmware/original/V2023.09.20.1_C2M_U_FR_WIFI_VI.tar'
EN_SHA='3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c'
VI_SHA='f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa'

check_file() {
    file="$1"
    expected="$2"
    [ -f "$file" ] || { echo "MISSING: $file" >&2; return 1; }
    actual=$(sha256sum "$file" | awk '{print $1}')
    if [ "$actual" != "$expected" ]; then
        echo "HASH MISMATCH: $file" >&2
        echo " expected: $expected" >&2
        echo " actual:   $actual" >&2
        return 1
    fi
    echo "OK: $file"
}

check_file "$EN" "$EN_SHA"
check_file "$VI" "$VI_SHA"
