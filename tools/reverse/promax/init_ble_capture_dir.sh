#!/usr/bin/env bash
# Create a ProMax BLE capture evidence directory (SAFE: mkdir + templates only).
# Usage: bash init_ble_capture_dir.sh [PROMAX_BLE_CAPTURE_YYYYMMDD]
set -euo pipefail
ROOT="${1:-PROMAX_BLE_CAPTURE_$(date +%Y%m%d)}"
for d in 00_manifest 01_phone 02_hci 03_gatt 04_event_log 05_packets 06_correlation 07_protocol 08_summary; do
  mkdir -p "$ROOT/$d"
done
cat > "$ROOT/00_manifest/MANIFEST.txt" <<'EOF'
PROMAX BLE capture session manifest (fill in on capture day)
date:
operator:
phone model / Android version:
ProMax model / fw shown on screen:
app used for nav (name/version):
session id:
EOF
cat > "$ROOT/04_event_log/event_log.csv" <<'EOF'
iso_time,event,speed,limit,turn,distance,promax_display,notes
,,,,,,
EOF
for f in "$ROOT/01_phone/PHONE_INFO.txt" "$ROOT/02_hci/SOURCE.txt" "$ROOT/03_gatt/DISCOVERY.txt" "$ROOT/05_packets/NOTES.txt" "$ROOT/06_correlation/NOTES.txt" "$ROOT/07_protocol/FRAMING.txt" "$ROOT/08_summary/VERDICT.txt"; do
  [ -e "$f" ] || : > "$f"
done
cat > "$ROOT/README.txt" <<'EOF'
Layout: 00_manifest 01_phone 02_hci 03_gatt 04_event_log 05_packets 06_correlation 07_protocol 08_summary.
Rule: raw captures + manual log are evidence; derived tables are analysis. Never replay.
See docs/research/PROMAX_BLE_CAPTURE_RUNBOOK_V1.md
EOF
echo "created $ROOT"
