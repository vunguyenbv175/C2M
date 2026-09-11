#!/bin/sh
# c2m_hw_day.sh — hardware-day ORCHESTRATOR (never an automatic flashing tool).
# May: show next step, verify required files, run read-only captures, hash outputs, record manual PASS/FAIL.
# Must NOT: flash automatically, edit stock configs, kill services, run IPU inference, inject M4.
# Usage: sh tools/device/c2m_hw_day.sh [status|next|record <gate> <PASS|FAIL|PARTIAL|UNKNOWN|BLOCKED> [note]]
set -u
GATES="docs/hardware/C2M_HARDWARE_DAY_GATES.json"
ROOT_GLOB="C2M_HW_*"
# python3 on Linux runners, python on Windows/Git-Bash dev boxes.
PYBIN=""
if command -v python3 >/dev/null 2>&1; then PYBIN="python3";
elif command -v python >/dev/null 2>&1; then PYBIN="python"; fi
cmd="${1:-status}"
record_gate() {
  gate="$1"; val="$2"; note="${3:-}"
  case "$val" in PASS|FAIL|PARTIAL|UNKNOWN|BLOCKED|NOT_RUN) ;; *) echo "bad value: $val" >&2; exit 2;; esac
  if [ -z "$PYBIN" ]; then echo "python3/python required to record gates" >&2; exit 3; fi
  "$PYBIN" - "$GATES" "$gate" "$val" "$note" <<'PY'
import json,sys,datetime
p,gate,val,note=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
d=json.load(open(p))
assert gate in d["gates"], f"unknown gate {gate}"
d["gates"][gate]["status"]=val
d["gates"][gate]["timestamp"]=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
if note: d["gates"][gate]["notes"]=note
json.dump(d,open(p,"w"),indent=2)
print(f"{gate}={val}")
PY
}
show_status() {
  echo "== hardware-day gates =="
  if [ -n "$PYBIN" ]; then
    "$PYBIN" - "$GATES" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
for k in d["order"]:
  g=d["gates"][k]
  print(f"{k:20s} {g['status']:8s} {g['evidence_path']}")
PY
  else cat "$GATES"; fi
  echo "== evidence roots =="
  ls -d $ROOT_GLOB 2>/dev/null || echo "(none yet; run init_hardware_day_dir.sh)"
  echo "DANGEROUS/manual steps are printed by the master runbook, never auto-run here."
}
show_next() {
  if [ -n "$PYBIN" ]; then
    "$PYBIN" - "$GATES" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
nxt=[k for k in d["order"] if d["gates"][k]["status"] in ("NOT_RUN","UNKNOWN")]
print("next gate:", nxt[0] if nxt else "(all decided — see summary)")
PY
  fi
  echo "See docs/hardware/C2M_HARDWARE_DAY_MASTER_RUNBOOK.md step table for the exact manual command."
}
case "$cmd" in
  status) show_status;;
  next) show_next;;
  record) shift; record_gate "${1:-}" "${2:-}" "${3:-}";;
  *) echo "usage: $0 [status|next|record <gate> <value> [note]]" >&2; exit 2;;
esac
