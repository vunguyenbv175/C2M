#!/bin/sh
# run_c2m_runtime_capture.sh — READ_ONLY wrapper (device side).
# Usage: sh tools/device/run_c2m_runtime_capture.sh en|vi
# Verifies label, creates timestamped output, runs existing read-only collector,
# writes MANIFEST, hashes files, tars if tar exists. Never modifies config,
# never restarts/kills services, never remounts, never decodes secrets.
set -u
usage() { echo "usage: $0 en|vi" >&2; exit 2; }
LABEL="${1:-}"
[ "$LABEL" = "en" ] || [ "$LABEL" = "vi" ] || usage
BASE="${C2M_CAPTURE_BASE:-/mnt/mmc}"
TS="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo unknown_time)"
SCRIPT_DIR="$(dirname "$0")"
COLLECTOR="$SCRIPT_DIR/../../tools/fw/capture_c2m_adas_runtime.sh"
# Allow invocation from repo root (tools/device/...) or absolute path.
[ -f "$COLLECTOR" ] || COLLECTOR="tools/fw/capture_c2m_adas_runtime.sh"
if [ ! -f "$COLLECTOR" ]; then echo "collector not found: $COLLECTOR" >&2; exit 3; fi
OUT="$(sh "$COLLECTOR" "$LABEL" 2>&1 | tail -n 1)"
# Collector prints OUT dir on last line; fall back to glob if unexpected.
if [ ! -d "$OUT" ]; then
  OUT="$(ls -dt "${BASE}/capture_${LABEL}_"* 2>/dev/null | head -n 1)"
fi
[ -n "$OUT" ] && [ -d "$OUT" ] || { echo "capture failed (no output dir)" >&2; exit 4; }
{
  echo "wrapper=run_c2m_runtime_capture.sh"
  echo "label=$LABEL"
  echo "timestamp=$TS"
  echo "output=$OUT"
  echo "policy=read-only-no-config-write-no-restart-no-kill-no-remount-no-secret-decode"
} >>"$OUT/MANIFEST.txt"
if command -v sha256sum >/dev/null 2>&1; then
  # Deterministic recursive manifest over ALL regular files (incl. nested proc_*),
  # excluding the checksum file itself while it is being generated.
  (cd "$(dirname "$OUT")" && find "$(basename "$OUT")" -type f ! -name 'SHA256SUMS.txt' -print | LC_ALL=C sort | xargs sha256sum >"$(basename "$OUT")/SHA256SUMS.txt" 2>/dev/null) || true
  (cd "$(dirname "$OUT")" && find "$(basename "$OUT")" -type f -print | LC_ALL=C sort >"$(basename "$OUT")/FILELIST.txt" 2>/dev/null) || true
fi
if command -v tar >/dev/null 2>&1; then
  tar -czf "${OUT}.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")" 2>/dev/null || true
  [ -f "${OUT}.tar.gz" ] && echo "bundle: ${OUT}.tar.gz"
fi
echo "$OUT"
