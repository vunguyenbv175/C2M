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
#     (SMP/preempt/mod_unload/ARMv7/thumb2/p2v8) plus the INFERRED iteration-2
#     debug/lock/stackprotector/ipv6 deltas (DEBUG_KERNEL+DEBUG_SPINLOCK+
#     DEBUG_MUTEXES on, DEBUG_LOCK_ALLOC/PROVE_LOCKING off, stackprotector
#     REGULAR, IPV6 off) -- explicitly NOT the camera ABI and NOT a
#     reproduction of the vendor config,
#   * builds the driver twice (baseline = 1 VIF, concurrent = 2 VIF) with the
#     host distribution soft-float cross compiler (arm-linux-gnueabi-),
#   * compiles a single external-kbuild object (probe.o, compile-only, never
#     linked into a module) to record sizeof(spinlock_t)/sizeof(raw_spinlock_t)/
#     sizeof(struct mutex) and offsetof(owner/magic) under that config, and
#     scans the pinned arch/arm sources for the __memzero export,
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
# Target modules must not retain SHN_COMMON: Linux 4.9 rejects it.
# Host dtc compatibility is handled separately in HOSTCFLAGS below.
KCFLAGS_LAB="-fno-common -fno-pie"
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
LPLOG=$OUT/layout-probe.log
PROBEDIR=$WORK/layout-probe
: > "$STEPFILE"
: > "$KLOG"
: > "$BLOG"
: > "$CLOG"
: > "$LPLOG"

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
    -m CFG80211 -e CFG80211_WEXT -e PROC_FS
    -m MMC
    -d MODVERSIONS
    # Iteration-2 hypothesis (INFERRED, not a camera config): debug locks on,
    # lockdep/prove-locking explicitly off, stackprotector regular, IPv6 off.
    -e DEBUG_KERNEL -e DEBUG_SPINLOCK -e DEBUG_MUTEXES
    -d DEBUG_LOCK_ALLOC -d PROVE_LOCKING
    -e CC_STACKPROTECTOR_REGULAR -d CC_STACKPROTECTOR_STRONG -d CC_STACKPROTECTOR_NONE
    -d IPV6
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

# The iteration-2 choices are forced through scripts/config; olddefconfig can
# silently revert anything whose dependency is unmet. Report that honestly
# (as a warning step) instead of pretending the probe config held.
if python3 "$LAB_PY" config-sticky "$KSRC/.config" >>"$KLOG" 2>&1; then
    record_step kernel-config-sticky ok choices_stuck
else
    record_step kernel-config-sticky warn choices_changed_by_olddefconfig
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
# Compile-only struct-layout probe (iteration-2 hypothesis)
#
# Builds a single external-kbuild object (probe.o) against the reconstructed
# config. Only the object is requested, so kbuild links no module and runs no
# modpost / MODULE_LICENSE check. The object stays in ephemeral WORK; only JSON
# metadata (symbol sizes = sizeof/offsetof, undefined set, arch source hashes)
# is retained. Failures are recorded honestly and never faked.
# --------------------------------------------------------------------------
mkdir -p "$PROBEDIR"
cat > "$PROBEDIR/probe.c" <<'PROBE_C'
/*
 * Generated by tools/wifi/build_rtl8821cs_lab.sh. COMPILE-ONLY layout probe:
 * kbuild is asked for probe.o only, so no .ko is linked, no modpost runs and
 * no MODULE_LICENSE is required. Never a loadable or loadable-adjacent thing.
 *
 * Each global char array's symbol size encodes the value of the sizeof() or
 * offsetof() it is named for (array element is char).
 */
#include <linux/kernel.h>
#include <linux/spinlock.h>
#include <linux/mutex.h>
#include <linux/string.h>

char c2m_probe_sizeof_spinlock[sizeof(spinlock_t)];
char c2m_probe_sizeof_raw_spinlock[sizeof(raw_spinlock_t)];
char c2m_probe_sizeof_mutex[sizeof(struct mutex)];

#if defined(CONFIG_DEBUG_MUTEXES) || defined(CONFIG_MUTEX_SPIN_ON_OWNER)
char c2m_probe_offsetof_mutex_owner[offsetof(struct mutex, owner)];
#endif
#ifdef CONFIG_DEBUG_MUTEXES
char c2m_probe_offsetof_mutex_magic[offsetof(struct mutex, magic)];
#endif

/* Constant-zero versus variable-fill memset: record the emitted symbols
 * without changing the upstream ARM header. */
void c2m_probe_memset_const_zero(void *dst)
{
	memset(dst, 0, 64);
}

void c2m_probe_memset_var(void *dst, int value, unsigned long len)
{
	memset(dst, value, len);
}
PROBE_C
cat > "$PROBEDIR/Makefile" <<'PROBE_MK'
# Generated by tools/wifi/build_rtl8821cs_lab.sh. Request only probe.o.
obj-m += probe.o
PROBE_MK

# Track a failed probe build, but keep going so the run still reports.
if run_step layout-probe-build "$LPLOG" 300 \
        make -C "$KSRC" ARCH=arm CROSS_COMPILE="$CROSS" \
        KCFLAGS="$KCFLAGS_LAB" HOSTCFLAGS="$HOSTCFLAGS_LAB" \
        M="$PROBEDIR" probe.o; then
    :
fi

# Even when the object is absent this writes layout-probe.json containing the
# arch/arm source scan (armksyms.c AND memzero.S) and an honest object status.
if python3 "$LAB_PY" layout-probe --obj "$PROBEDIR/probe.o" --ksrc "$KSRC" \
        --out "$OUT/layout-probe.json" >>"$LPLOG" 2>&1; then
    record_step layout-probe ok json_written
else
    record_step layout-probe fail probe_object_missing_or_unparseable
fi

# --------------------------------------------------------------------------
# Iteration-5 codegen probe: which target flag choices control the __memzero
# libcall emission for constant-zero memset in the pinned host toolchain.
# Direct cross-gcc compile of a tiny standalone snippet; no kernel headers.
# The per-variant flag set is recorded next to the objects (single source).
# --------------------------------------------------------------------------
MZDIR=$WORK/memzero-probe
MZLOG=$OUT/memzero-probe.log
MZFLAGS=$MZDIR/flags.tsv
mkdir -p "$MZDIR"
: > "$MZLOG"
: > "$MZFLAGS"
cat > "$MZDIR/snippet.c" <<'MZ_SNIPPET'
/* Generated by tools/wifi/build_rtl8821cs_lab.sh. Compile-only codegen probe. */
extern void *memset(void *dst, int value, unsigned long len);
void c2m_mz_zero_const(void *dst) { memset(dst, 0, 64); }
void c2m_mz_fill_prop(void *dst, int value) { memset(dst, value, 64); }
void c2m_mz_fill_var(void *dst, int value, unsigned long len) { memset(dst, value, len); }
MZ_SNIPPET
"${CROSS}gcc" --version 2>>"$MZLOG" | head -n 1 > "$MZDIR/toolchain.txt" || true
mz_variant() {
    local name=$1
    shift
    printf '%s\t%s\n' "$name" "$*" >> "$MZFLAGS"
    if "${CROSS}gcc" -c "$@" "$MZDIR/snippet.c" -o "$MZDIR/$name.o" >>"$MZLOG" 2>&1; then
        record_step "memzero-probe-$name" ok compiled
    else
        record_step "memzero-probe-$name" fail compile_failed
    fi
}
MZ_BASE="-O2 -march=armv7-a -mthumb -fno-common -fno-pie"
mz_variant default $MZ_BASE
mz_variant fno_builtin $MZ_BASE -fno-builtin
mz_variant fno_builtin_memset $MZ_BASE -fno-builtin-memset
mz_variant os -Os -march=armv7-a -mthumb -fno-common -fno-pie
mz_variant arm -O2 -march=armv7-a -marm -fno-common -fno-pie
if python3 "$LAB_PY" memzero-probe --dir "$MZDIR" --out "$OUT/memzero-probe.json" >>"$MZLOG" 2>&1; then
    record_step memzero-probe ok json_written
else
    record_step memzero-probe fail probe_parse_failed
fi

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
    else
        record_step "ko-$profile" fail metadata_failed
        return 1
    fi

    # Bounded allocated/COMMON object accounting (metadata only, no raw bytes).
    # A kbuild .cmd is public source and is read as TEXT ONLY, never executed.
    local ko_cmd= storage_ok=0 memzero_ok=0
    # Use a C translation-unit command, not the final linker command.
    for cand in "$drv/os_dep/.osdep_service.o.cmd" "$drv/os_dep/linux/.os_intfs.o.cmd"; do
        if [ -f "$cand" ]; then ko_cmd=$cand; break; fi
    done
    if [ -n "$ko_cmd" ]; then
        python3 "$LAB_PY" module-storage --ko "$ko" --profile "$profile" \
            --cmd "$ko_cmd" --out "$OUT/$profile.storage.json" >>"$log" 2>&1 || storage_ok=$?
    else
        python3 "$LAB_PY" module-storage --ko "$ko" --profile "$profile" \
            --out "$OUT/$profile.storage.json" >>"$log" 2>&1 || storage_ok=$?
    fi
    if [ "$storage_ok" -eq 0 ]; then
        record_step "storage-$profile" ok storage_written
    else
        record_step "storage-$profile" fail "storage_failed_exit=$storage_ok"
    fi

    # Iteration-5: exact object-level __memzero/memset attribution. Every
    # regular *.o under the ephemeral driver tree is parsed in place; only
    # symbol-name metadata is retained, never object bytes.
    python3 "$LAB_PY" memzero-scan --objects-dir "$drv" --profile "$profile" \
        --out "$OUT/$profile.memzero-attribution.json" >>"$log" 2>&1 || memzero_ok=$?
    if [ "$memzero_ok" -eq 0 ]; then
        record_step "memzero-$profile" ok attribution_written
    else
        record_step "memzero-$profile" fail "memzero_scan_exit=$memzero_ok"
    fi
    if [ "$storage_ok" -eq 0 ] && [ "$memzero_ok" -eq 0 ]; then
        return 0
    fi
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
