#!/bin/sh
# init_hardware_day_dir.sh — SAFE_WRITE_OUTPUT_ONLY (workstation only).
# Creates C2M_HW_<YYYYMMDD>/ evidence tree + manifest. Never touches device.
# Usage: sh tools/device/init_hardware_day_dir.sh [YYYYMMDD]
set -u
DATE="${1:-$(date +%Y%m%d 2>/dev/null || echo unknown_date)}"
ROOT="C2M_HW_${DATE}"
mkdir -p "$ROOT/00_manifest" "$ROOT/01_recovery" "$ROOT/02_candidate_A" "$ROOT/03_candidate_B" \
  "$ROOT/04_en_runtime" "$ROOT/05_vi_runtime" "$ROOT/06_adas_compare" "$ROOT/07_m4" \
  "$ROOT/08_ipu_baseline" "$ROOT/09_media_topology" "$ROOT/10_ipu_safe" \
  "$ROOT/11_ipu_coexist" "$ROOT/12_summary" || exit 1
{
  echo "root=$ROOT"
  echo "created=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
  echo "purpose=pre-hardware bring-up evidence (read-only captures + manual gates)"
  echo "order=0-recovery,1-A-flash,2-A-pass,3-B-flash,4-B-pass,5-EN,6-VI,7-class-A-H,8-M4-L0L1,10-IPU,11-SCL,12-SAFE,13-COEXIST"
  echo "gates=docs/hardware/C2M_HARDWARE_DAY_GATES.json"
} >"$ROOT/00_manifest/MANIFEST.txt"
cp docs/hardware/C2M_HARDWARE_DAY_GATES.json "$ROOT/00_manifest/GATES.start.json" 2>/dev/null || true
echo "$ROOT"
