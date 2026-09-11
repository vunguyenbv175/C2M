#!/bin/bash
# P1/P2 driver: UBIFS customer rebuild on Linux (fail-closed).
#   --mode noop     extract tree -> mkfs.ubifs -> manifest-compare vs stock (GATE)
#   --mode mutated  same, but compare vs stock+mutation via verify_b_manifest.py
# Requires: python3, mkfs.ubifs (mtd-utils), root (for uid/gid fidelity via chown).
# Records exact tool versions/hashes in the report. Any unexplained diff FAILS.
set -euo pipefail
MODE=""; TREE=""; GEO=""; STOCK_MANIFEST=""; OUT=""; REPORT=""
MUT_MANIFEST=""; TREE_REPORT=""
while [ $# -gt 0 ]; do case "$1" in
  --mode) MODE="$2"; shift 2;;
  --tree) TREE="$2"; shift 2;;
  --geometry) GEO="$2"; shift 2;;
  --stock-manifest) STOCK_MANIFEST="$2"; shift 2;;
  --mut-manifest) MUT_MANIFEST="$2"; shift 2;;
  --tree-report) TREE_REPORT="$2"; shift 2;;
  --out) OUT="$2"; shift 2;;
  --report) REPORT="$2"; shift 2;;
  *) echo "unknown arg $1"; exit 2;;
esac; done
[ -n "$MODE" ] && [ -n "$TREE" ] && [ -n "$GEO" ] && [ -n "$STOCK_MANIFEST" ] && [ -n "$OUT" ] && [ -n "$REPORT" ] \
  || { echo "missing required args"; exit 2; }
[ "$MODE" = "noop" ] || [ "$MODE" = "mutated" ] || { echo "bad --mode"; exit 2; }
command -v mkfs.ubifs >/dev/null || { echo "REBUILD-FAIL: mkfs.ubifs not found (apt install mtd-utils)"; exit 1; }
command -v python3 >/dev/null || { echo "REBUILD-FAIL: python3 missing"; exit 1; }
[ "$(id -u)" = "0" ] || { echo "REBUILD-FAIL: must run as root (uid/gid fidelity needs chown 1001)"; exit 1; }
if [ -n "$TREE_REPORT" ]; then
  FB=$(python3 -c "import json;print(len(json.load(open('$TREE_REPORT')).get('symlink_fallbacks',[])))")
  [ "$FB" = "0" ] || { echo "REBUILD-FAIL: tree has $FB symlink fallbacks (extract on Linux)"; exit 1; }
fi
# uid/gid fidelity: stock image is uniformly 1001:1001 (manifest-proven).
chown -R 1001:1001 "$TREE"
MIN_IO=$(python3 -c "import json;print(json.load(open('$GEO'))['min_io_size'])")
LEB_SZ=$(python3 -c "import json;print(json.load(open('$GEO'))['leb_size'])")
MAX_LEB=$(python3 -c "import json;print(json.load(open('$GEO'))['max_leb_cnt'])")
COMPR=$(python3 -c "import json;print(json.load(open('$GEO'))['default_compr_name'])")
MKFS_VER=$(mkfs.ubifs -h 2>&1 | head -3 | tr '\n' '|')
MKFS_BIN=$(command -v mkfs.ubifs)
MKFS_SHA=$(sha256sum "$MKFS_BIN" | awk '{print $1}')
echo "tool: $MKFS_BIN sha=$MKFS_SHA info=$MKFS_VER"
echo "geometry: min_io=$MIN_IO leb=$LEB_SZ maxleb=$MAX_LEB compr=$COMPR"
mkfs.ubifs -m "$MIN_IO" -e "$LEB_SZ" -c "$MAX_LEB" -x "$COMPR" -r "$TREE" -o "$OUT"
OUT_SHA=$(sha256sum "$OUT" | awk '{print $1}')
OUT_SIZE=$(stat -c%s "$OUT")
ACTUAL_MANIFEST="${REPORT%.json}.actual_manifest.json"
python3 tools/fw/ubifs_manifest.py "$OUT" -o "$ACTUAL_MANIFEST"
if [ "$MODE" = "noop" ]; then
  python3 tools/fw/ubifs_manifest.py --compare "$STOCK_MANIFEST" "$ACTUAL_MANIFEST" | tee "${REPORT%.json}.compare.txt"
else
  [ -n "$MUT_MANIFEST" ] || { echo "mutated mode needs --mut-manifest"; exit 2; }
  python3 tools/fw/verify_b_manifest.py --stock "$STOCK_MANIFEST" --mut "$MUT_MANIFEST" \
    --actual "$ACTUAL_MANIFEST" --out "${REPORT%.json}.bmanifest.json" | tee "${REPORT%.json}.compare.txt"
fi
python3 - "$REPORT" "$OUT" "$OUT_SHA" "$OUT_SIZE" "$MKFS_BIN" "$MKFS_SHA" "$MKFS_VER" <<'EOF'
import json,sys
_, rep, out, sha, size, tool, tsha, tver = sys.argv
json.dump({"mode": "REBUILD-REPORT", "image": out, "sha256": sha, "size": int(size),
           "tool": tool, "tool_sha256": tsha, "tool_version_info": tver,
           "verdict": "REBUILD-OK"}, open(rep, "w"), indent=2)
EOF
echo "REBUILD-OK: $OUT sha=$OUT_SHA size=$OUT_SIZE"
