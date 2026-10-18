#!/usr/bin/env bash
#
# tools/wifi/build_rtl8821cs_lab.sh
#
# Offline, PUBLIC-SOURCE-ONLY RTL8821CS (RTL8821CS SDIO) build lab.
#
#   * fetches the pinned public driver (leavs/rtl8821cs@d0336d19) and the
#     pinned upstream Linux 4.9.227 tarball and verifies both SHA-256 pins
#     (the kernel hash is pinned from the upstream HTTPS checksum file, never
#     recomputed from the fetched tarball),
#   * reconstructs an ARMv7 + Thumb-2 kernel config from multi_v7_defconfig
#     (SMP/preempt/mod_unload/ARMv7/thumb2/p2v8) -- explicitly NOT the camera
#     ABI and NOT a reproduction of the vendor config,
#   * builds the driver twice (baseline = 1 VIF, concurrent = 2 VIF) with the
#     host distribution soft-float cross compiler (arm-linux-gnueabi-),
#   * keeps the produced .ko modules ONLY under OUTDIR/work (ephemeral runner
#     scratch) and emits only hash/symbol METADATA (no firmware, no binaries).
#
# It never touches a device, never loads a module, never writes a camera and
# never claims camera ABI compatibility. NO LOAD, EVER.
#
# Usage: bash tools/wifi/build_rtl8821cs_lab.sh OUTDIR
#
# Exit status: 0 only if every required step succeeded. Failures are recorded
# in OUTDIR/report.json and the step logs; nothing is faked.
set -uo pipefail

usage() { echo "usage: bash tools/wifi/build_rtl8821cs_lab.sh OUTDIR" >&2; }

OUT=${1:-}
[ -n "$OUT" ] || { usage; exit 2; }
case "$OUT" in -*) usage; exit 2 ;; esac

[ -f tools/wifi/rtl8821cs_lab.py ] || { echo 'run from repo root: tools/wifi/rtl8821cs_lab.py missing' >&2; exit 2; }
[ -d tools/wifi/rtl8821cs_profiles/baseline ] || { echo 'missing tools/wifi/rtl8821cs_profiles/baseline' >&2; exit 2; }
[ -d tools/wifi/rtl8821cs_profiles/concurrent ] || { echo 'missing tools/wifi/rtl8821cs_profiles/concurrent' >&2; exit 2; }

LAB_PY=$PWD/tools/wifi/rtl8821cs_lab.py
PROFILES_DIR=$PWD/tools/wifi/rtl8821cs_profiles
CROSS=arm-linux-gnueabi-
KCFLAGS_LAB="-fcommon -fno-pie"
# Keep the distribution HOSTCFLAGS defaults and add -fcommon so GCC-10+
# -fno-common does not break the bundled host tools (notably scripts/dtc).
HOSTCFLAGS_LAB="-Wall -Wmissing-prototypes -Wstrict-prototypes -O2 -fomit-frame-pointer -std=gnu89 -fcommon"

for tool in python3 make curl tar xz patch sha256sum; do
    command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 2; }
done
command -v "${CROSS}gcc" >/dev/null 2>&1 || { echo "missing cross compiler: ${CROSS}gcc" >&2; exit 2; }
command -v "${CROSS}strip" >/dev/null 2>&1 || { echo "missing ${CROSS}strip" >&2; exit 2; }

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
WORK=$OUT/work
DL=$WORK/dl
KSRC=$WORK/linux-4.9.227
STEPFILE=$OUT/steps.tsv
KLOG=$OUT/kernel-prepare.log
BLOG=$OUT/build-baseline.log
CLOG=$OUT/build-concurrent.log
: > "$STEPFILE"
: > "$KLOG"
: > "$BLOG"
: > "$CLOG"

# --------------------------------------------------------------------------
# Failure bookkeeping and finalization
# --------------------------------------------------------------------------
record_step() {
    local name=$1 status=$2 detail=${3:-}
    detail=${detail//$'\t'/ }
    printf '%s\t%s\t%s\n' "$name" "$status" "$detail" >> "$STEPFILE"
}

finalize() {
    rc=$?
    trap - EXIT
    if [ ! -f "$OUT/report.json" ]; then
        python3 "$LAB_PY" report --out "$OUT" --exit-code "$rc" >>"$OUT/finalize.log" 2>&1 \
            || printf '{"status":"failed","load_safety":"NOT_ESTABLISHED","note":"report generation failed"}\n' > "$OUT/report.json"
    fi
    echo "rtl8821cs-lab: report -> $OUT/report.json (exit=$rc)"
    exit "$rc"
}
trap finalize EXIT

START_EPOCH=${C2M_LAB_START_EPOCH:-$(date +%s)}
DEADLINE=$(( START_EPOCH + ${C2M_LAB_TIMEOUT_SECONDS:-1800} ))
remaining() { echo $(( DEADLINE - $(date +%s) )); }

run_step() {
    local name=$1 log=$2 tmo=$3
    shift 3
    local rem
    rem=$(remaining)
    if [ "$rem" -le 5 ]; then
        record_step "$name" fail "global_deadline"
        return 124
    fi
    [ "$tmo" -gt "$rem" ] && tmo=$rem
    local rc
    if timeout "$tmo" "$@" >>"$log" 2>&1; then
        record_step "$name" ok ok
        return 0
    else
        rc=$?
        record_step "$name" fail "exit=$rc"
        return "$rc"
    fi
}

# --------------------------------------------------------------------------
# Pins and toolchain record
# --------------------------------------------------------------------------
ENVDUMP=$(python3 "$LAB_PY" env 2>>"$KLOG") || { echo 'pin loader failed' >&2; exit 2; }
eval "$ENVDUMP"
for required in C2M_KERNEL_URL C2M_KERNEL_SHA256 C2M_KERNEL_DIR C2M_DRIVER_URL \
                C2M_DRIVER_ARCHIVE_SHA256 C2M_DRIVER_DIR C2M_DRIVER_VERSION C2M_DRIVER_COMMIT; do
    [ -n "${!required:-}" ] || { echo "pin loader missing $required" >&2; exit 2; }
done
python3 "$LAB_PY" manifest > "$OUT/pins.json" 2>>"$KLOG" || true

{
    echo "# RTL8821CS offline lab toolchain -- ACTUAL host distribution compiler."
    echo "# This is NOT the vendor gcc-9.1.0 (sigmastar) toolchain and is not claimed to be."
    echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "uname=$(uname -srm 2>/dev/null || echo unknown)"
    echo "target_kernel=${C2M_KERNEL_VERSION:-4.9.227}"
    echo "cross_compile=${CROSS}"
    echo "expected_vendor_toolchain=gcc-9.1.0 (sigmastar) -- NOT available / NOT used"
    echo "toolchain_is_vendor_match=false"
    echo "--- ${CROSS}gcc --version"
    "${CROSS}gcc" --version 2>&1 | head -n 1 || true
    echo "--- ${CROSS}as --version"
    "${CROSS}as" --version 2>&1 | head -n 1 || true
    echo "--- ${CROSS}ld --version"
    "${CROSS}ld" --version 2>&1 | head -n 1 || true
    echo "--- make --version"
    make --version 2>&1 | head -n 1 || true
    echo "--- python3 --version"
    python3 --version 2>&1 || true
    echo "--- host cc --version"
    cc --version 2>&1 | head -n 1 || true
    echo "--- shasum pins"
    echo "kernel_sha256=$C2M_KERNEL_SHA256"
    echo "driver_archive_sha256=$C2M_DRIVER_ARCHIVE_SHA256"
    echo "driver_commit=$C2M_DRIVER_COMMIT"
} > "$OUT/toolchain.txt" 2>&1

# --------------------------------------------------------------------------
# Downloads (strict pin verification)
# --------------------------------------------------------------------------
download_verify() {
    # name url dest expected
    local name=$1 url=$2 dest=$3 expected=$4
    mkdir -p "$(dirname "$dest")"
    if [ ! -f "$dest" ]; then
        if ! curl --fail --location --silent --show-error --retry 3 --retry-delay 3 \
                  --connect-timeout 30 --max-time 600 -o "$dest" "$url" >>"$KLOG" 2>&1; then
            record_step "$name" fail "download_failed"
            return 1
        fi
    fi
    if python3 "$LAB_PY" verify-file "$dest" "$expected" > "$OUT/$name.verify.json" 2>>"$KLOG"; then
        record_step "$name" ok sha256_verified
        return 0
    fi
    record_step "$name" fail sha256_mismatch
    return 1
}

mkdir -p "$WORK" "$DL"

if ! download_verify kernel-download "$C2M_KERNEL_URL" "$DL/linux-4.9.227.tar.xz" "$C2M_KERNEL_SHA256"; then
    echo "kernel download/verify failed (see $OUT/kernel-prepare.log)" >&2
    exit 1
fi
if ! run_step kernel-extract "$KLOG" 300 tar -C "$WORK" -xf "$DL/linux-4.9.227.tar.xz"; then
    echo "kernel extraction failed" >&2
    exit 1
fi
[ -d "$KSRC" ] || { record_step kernel-extract fail missing_dir; echo "kernel dir $KSRC missing" >&2; exit 1; }

if ! download_verify driver-download "$C2M_DRIVER_URL" "$DL/rtl8821cs.tar.gz" "$C2M_DRIVER_ARCHIVE_SHA256"; then
    echo "driver download/verify failed (see $OUT/kernel-prepare.log)" >&2
    exit 1
fi
if ! run_step driver-extract "$KLOG" 300 tar -C "$WORK" -xf "$DL/rtl8821cs.tar.gz"; then
    echo "driver extraction failed" >&2
    exit 1
fi
DRVSRC=$WORK/$C2M_DRIVER_DIR
[ -d "$DRVSRC" ] || { record_step driver-extract fail missing_dir; echo "driver dir $DRVSRC missing" >&2; exit 1; }

if python3 "$LAB_PY" check-driver "$DRVSRC" > "$OUT/driver-verify.json" 2>>"$KLOG"; then
    record_step driver-verify ok file_hashes_match
else
    record_step driver-verify fail file_hash_mismatch
    echo "driver content hashes do not match the pin" >&2
    exit 1
fi

# --------------------------------------------------------------------------
# Kernel configuration + header preparation
# --------------------------------------------------------------------------
if ! run_step kernel-defconfig "$KLOG" 300 \
        make -C "$KSRC" ARCH=arm CROSS_COMPILE="$CROSS" multi_v7_defconfig; then
    echo "multi_v7_defconfig failed" >&2
    exit 1
fi

CONFIG_ARGS=(
    --file .config
    -e MODULES -e MODULE_UNLOAD -e MODULE_FORCE_UNLOAD
    -e SMP -d PREEMPT_NONE -d PREEMPT_VOLUNTARY -e PREEMPT
    -e THUMB2_KERNEL -e CPU_V7 -e ARM_PATCH_PHYS_VIRT -e AEABI
    -m CFG80211 -e CFG80211_WEXT -e WIRELESS_EXT
    -m MMC
    -d MODVERSIONS
    -d CC_STACKPROTECTOR_STRONG -d CC_STACKPROTECTOR_REGULAR
    -d GCC_PLUGINS
    -d MODULE_SIG -d MODULE_SIG_ALL -d MODULE_SIG_FORCE
    -d SYSTEM_TRUSTED_KEYRING -d SYSTEM_BLACKLIST_KEYRING
    -d LOCALVERSION_AUTO
    --set-str LOCALVERSION ""
)
cfg_rem=$(remaining); [ "$cfg_rem" -gt 120 ] && cfg_rem=120
if ( cd "$KSRC" && timeout "$cfg_rem" scripts/config "${CONFIG_ARGS[@]}" ) >>"$KLOG" 2>&1; then
    record_step kernel-config ok flags_applied
else
    record_step kernel-config fail scripts_config_failed
    exit 1
fi

if ! run_step kernel-olddefconfig "$KLOG" 300 \
        make -C "$KSRC" ARCH=arm CROSS_COMPILE="$CROSS" olddefconfig; then
    echo "olddefconfig failed" >&2
    exit 1
fi

if ! run_step kernel-prepare "$KLOG" 900 \
        make -C "$KSRC" ARCH=arm CROSS_COMPILE="$CROSS" \
        KCFLAGS="$KCFLAGS_LAB" HOSTCFLAGS="$HOSTCFLAGS_LAB" prepare; then
    echo "kernel prepare failed" >&2
    exit 1
fi
if ! run_step kernel-modules-prepare "$KLOG" 900 \
        make -C "$KSRC" ARCH=arm CROSS_COMPILE="$CROSS" \
        KCFLAGS="$KCFLAGS_LAB" HOSTCFLAGS="$HOSTCFLAGS_LAB" modules_prepare; then
    echo "kernel modules_prepare failed" >&2
    exit 1
fi

# Record the reconstructed config state (vermagic flags + expectations).
if python3 "$LAB_PY" config-state "$KSRC/.config" --out "$OUT/kernel-config.json" >"$KLOG.config" 2>&1; then
    record_step kernel-config-state ok config_state_written
else
    record_step kernel-config-state fail vermagic_required_missing
fi

# Generated-header presence check (module build needs these).
missing_headers=
for header in include/generated/autoconf.h include/config/auto.conf \
              include/generated/utsrelease.h include/generated/bounds.h; do
    [ -f "$KSRC/$header" ] || missing_headers="$missing_headers $header"
done
if [ -n "$missing_headers" ]; then
    record_step kernel-headers fail "missing:$missing_headers"
    echo "generated headers missing:$missing_headers" >&2
    exit 1
fi
record_step kernel-headers ok all_present

kernel_warns=$(grep -c -i 'warning:' "$KLOG" 2>/dev/null || true)
record_step kernel-warnings ok "count=${kernel_warns:-0}"

# --------------------------------------------------------------------------
# Per-profile builds (patch + external module build + metadata)
# --------------------------------------------------------------------------
build_profile() {
    local profile=$1
    local patch=$PROFILES_DIR/$profile/Makefile.patch
    local drv=$WORK/driver-$profile
    local log=$OUT/build-$profile.log
    : > "$log"

    if [ ! -f "$patch" ]; then
        record_step "patch-$profile" fail patch_missing
        return 1
    fi
    rm -rf "$drv"
    if ! cp -a "$DRVSRC" "$drv" >>"$log" 2>&1; then
        record_step "copy-$profile" fail copy_failed
        return 1
    fi
    if ! patch --batch --forward -p1 -d "$drv" -i "$patch" >>"$log" 2>&1; then
        record_step "patch-$profile" fail patch_failed
        return 1
    fi
    record_step "patch-$profile" ok applied

    if ! run_step "build-$profile" "$log" 900 \
            make -C "$drv" ARCH=arm CROSS_COMPILE="$CROSS" KSRC="$KSRC" \
            KCFLAGS="$KCFLAGS_LAB" HOSTCFLAGS="$HOSTCFLAGS_LAB" \
            CONFIG_P2P=n CONFIG_WIFI_MONITOR=n CONFIG_RTW_ANDROID=0 \
            MODULE_NAME=8821cs modules; then
        return 1
    fi

    # Surface compiler warnings in the report rather than hiding them.
    local warns
    warns=$(grep -c -i 'warning:' "$log" 2>/dev/null || true)
    record_step "warnings-$profile" ok "count=${warns:-0}"

    local ko=$drv/8821cs.ko
    if [ ! -f "$ko" ]; then
        record_step "ko-$profile" fail ko_missing
        return 1
    fi
    if python3 "$LAB_PY" module-metadata --ko "$ko" --profile "$profile" \
            --out "$OUT/$profile.metadata.json" >>"$log" 2>&1; then
        record_step "ko-$profile" ok metadata_written
        return 0
    fi
    record_step "ko-$profile" fail metadata_failed
    return 1
}

build_profile baseline || true
build_profile concurrent || true

# Plugin build order is baseline first; the concurrency profile is research.
echo "rtl8821cs-lab: modules were built only under $WORK (ephemeral); only metadata is retained." >>"$KLOG"

# --------------------------------------------------------------------------
# Final report
# --------------------------------------------------------------------------
FAILED=0
if grep -q $'\tfail\t' "$STEPFILE" 2>/dev/null; then
    FAILED=1
fi
python3 "$LAB_PY" report --out "$OUT" --exit-code "$FAILED" || true
if [ "$FAILED" -ne 0 ]; then
    echo "rtl8821cs-lab: one or more steps failed; see $OUT/report.json and the logs" >&2
    exit 1
fi
echo "rtl8821cs-lab: all steps succeeded"
exit 0
