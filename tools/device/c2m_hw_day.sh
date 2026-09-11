#!/bin/sh
# c2m_hw_day.sh — hardware-day ORCHESTRATOR (fail-closed; never an automatic flashing tool).
# May: show next step, verify required files, run read-only captures, hash outputs, record manual PASS/FAIL.
# Must NOT: flash automatically, edit stock configs, kill services, run IPU inference, inject M4.
# Gate state lives in the ACTIVE hardware-day copy — never the tracked template:
#   --gates <path>                          (explicit; record refuses template + GATES.start.json)
#   $C2M_HW_ROOT/00_manifest/GATES.current.json   (env)
#   C2M_HW_*/00_manifest/GATES.current.json       (auto-detect; must resolve to exactly one)
# With no active copy, status/next read the immutable template read-only; record/stop refuse.
# Fatal day stop: `stop <reason>` writes 00_manifest/STOP_DAY; status/next then report STOP (exit 1)
# and block every later stage until the sentinel file is explicitly removed by the operator.
# Usage: sh tools/device/c2m_hw_day.sh [--gates <path>] [status|next|record <gate> <PASS|FAIL|PARTIAL|UNKNOWN|BLOCKED|NOT_RUN> [note]|stop <reason>]
# Exit: 0 = next gate suggested / all decided-green / status shown / record|stop stored.
#       1 = STOP/BLOCKED (do not proceed) or corrupt gate state.
#       2/3 = usage error / python missing.
set -u
TEMPLATE="docs/hardware/C2M_HARDWARE_DAY_GATES.json"
ROOT_GLOB="C2M_HW_*"
# python3 on Linux runners, python on Windows/Git-Bash dev boxes.
PYBIN=""
if command -v python3 >/dev/null 2>&1; then PYBIN="python3";
elif command -v python >/dev/null 2>&1; then PYBIN="python"; fi
GATES_ARG=""
if [ "${1:-}" = "--gates" ]; then GATES_ARG="${2:-}"; shift 2; fi
ACTIVE_MODE=0
if [ -n "$GATES_ARG" ]; then
  GATES="$GATES_ARG"; ACTIVE_MODE=1
  [ -f "$GATES" ] || { echo "gates file not found: $GATES" >&2; exit 2; }
elif [ -n "${C2M_HW_ROOT:-}" ]; then
  GATES="$C2M_HW_ROOT/00_manifest/GATES.current.json"; ACTIVE_MODE=1
  [ -f "$GATES" ] || { echo "no active gates copy under C2M_HW_ROOT=$C2M_HW_ROOT (run init_hardware_day_dir.sh)" >&2; exit 2; }
else
  n=0; found=""
  for f in C2M_HW_*/00_manifest/GATES.current.json; do
    [ -f "$f" ] || continue
    n=$((n + 1)); found="$f"
  done
  if [ "$n" -eq 1 ]; then GATES="$found"; ACTIVE_MODE=1;
  elif [ "$n" -gt 1 ]; then echo "multiple active day copies; set C2M_HW_ROOT or pass --gates <path>" >&2; exit 2;
  else GATES="$TEMPLATE"; ACTIVE_MODE=0; fi
fi
[ -f "$GATES" ] || { echo "gates file not found: $GATES" >&2; exit 2; }
# Day root + fatal-stop sentinel (active copies only; template has no sentinel).
DAYROOT=""; STOPFILE=""
if [ "$ACTIVE_MODE" -eq 1 ]; then
  DAYROOT="$(dirname "$(dirname "$GATES")")"
  STOPFILE="$DAYROOT/00_manifest/STOP_DAY"
fi
stop_day() {
  reason="${1:-}"
  [ "$ACTIVE_MODE" -eq 1 ] || { echo "refusing: no active hardware-day copy (run init_hardware_day_dir.sh first)" >&2; exit 2; }
  [ -n "$reason" ] || { echo "usage: $0 stop <reason>" >&2; exit 2; }
  if [ -z "$PYBIN" ]; then echo "python3/python required to record stop" >&2; exit 3; fi
  "$PYBIN" - "$STOPFILE" "$reason" <<'PY'
import sys,datetime
p,reason=sys.argv[1],sys.argv[2]
ts=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
open(p,"w").write(f"STOP_DAY\ntimestamp={ts}\nreason={reason}\n")
print(f"STOP recorded: {reason}")
PY
}
check_stop() {
  # Echoes sentinel reason and returns 0 when the day is stopped (caller exits 1).
  if [ -n "$STOPFILE" ] && [ -f "$STOPFILE" ]; then
    echo "STOP: hardware day halted ($(cat "$STOPFILE" | tr '\n' ' '))"
    echo "All later stages BLOCKED until the operator resolves the cause and removes: $STOPFILE"
    return 0
  fi
  return 1
}
record_gate() {
  gate="$1"; val="$2"; note="${3:-}"
  case "$val" in PASS|FAIL|PARTIAL|UNKNOWN|BLOCKED|NOT_RUN) ;; *) echo "bad value: $val" >&2; exit 2;; esac
  if [ "$ACTIVE_MODE" -eq 0 ]; then
    echo "refusing: $TEMPLATE is the immutable template (run init_hardware_day_dir.sh, then record into C2M_HW_<date>/00_manifest/GATES.current.json)" >&2; exit 2
  fi
  case "$GATES" in */GATES.start.json)
    echo "refusing: GATES.start.json is the immutable initial state (record into GATES.current.json)" >&2; exit 2;; esac
  if [ -z "$PYBIN" ]; then echo "python3/python required to record gates" >&2; exit 3; fi
  "$PYBIN" - "$GATES" "$gate" "$val" "$note" <<'PY'
import json,sys,datetime
p,gate,val,note=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
d=json.load(open(p))
assert gate in d["gates"], f"unknown gate {gate}"
assert val in d["status_values"], f"bad value {val}"
d["gates"][gate]["status"]=val
d["gates"][gate]["timestamp"]=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
if note: d["gates"][gate]["notes"]=note
json.dump(d,open(p,"w"),indent=2)
print(f"{gate}={val} ({p})")
PY
}
show_status() {
  if [ "$ACTIVE_MODE" -eq 1 ]; then echo "== gates copy (ACTIVE): $GATES ==";
  else echo "== gates (TEMPLATE read-only — record refused until a hardware-day dir is initialized) =="; fi
  if [ -n "$PYBIN" ]; then
    "$PYBIN" - "$GATES" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
bad=[k for k in d["order"] if d["gates"][k]["status"] not in d["status_values"]]
for k in d["order"]:
  g=d["gates"][k]
  print(f"{k:20s} {g['status']:8s} {g['evidence_path']}")
if bad:
  print(f"CORRUPT gate state (unknown values): {' '.join(bad)}")
  sys.exit(1)
PY
  else cat "$GATES"; fi
  if [ -n "$STOPFILE" ] && [ -f "$STOPFILE" ]; then
    echo "== DAY STOPPED =="; cat "$STOPFILE"
  fi
  echo "== evidence roots =="
  ls -d $ROOT_GLOB 2>/dev/null || echo "(none yet; run init_hardware_day_dir.sh)"
  echo "DANGEROUS/manual steps are printed by the master runbook, never auto-run here."
}
show_next() {
  # Fail-closed: STOP_DAY sentinel, corrupt state, or any unsatisfied blocking
  # prerequisite (FAIL/PARTIAL/UNKNOWN/NOT_RUN, or BLOCKED except the documented
  # VI-capture skip) blocks the next gate. Chain enforced at minimum:
  #   recovery -> A -> B -> EN -> VI -> A-H/classify,  and  SAFE -> COEXIST.
  if check_stop; then exit 1; fi
  if [ -z "$PYBIN" ]; then echo "python3/python required for next-gate evaluation" >&2; exit 3; fi
  "$PYBIN" - "$GATES" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
order=d["order"]; g=d["gates"]; allowed=set(d["status_values"])
corrupt=[k for k in order if g[k]["status"] not in allowed]
if corrupt:
  print(f"STOP: corrupt gate state (unknown values): {' '.join(corrupt)}")
  sys.exit(1)
PREREQ={
  "recovery_ready": [],
  "candidate_a_pass": ["recovery_ready"],
  "candidate_b_pass": ["candidate_a_pass"],
  "en_capture_done": ["candidate_b_pass"],
  "vi_capture_done": ["en_capture_done"],
  "adas_classified": ["en_capture_done", "vi_capture_done"],
  "m4_l1_pass": ["adas_classified"],
  "ipu_baseline_done": ["adas_classified"],
  "scl_map_done": ["ipu_baseline_done"],
  "ipu_safe_pass": ["ipu_baseline_done", "scl_map_done"],
  "ipu_coexist_pass": ["ipu_safe_pass"],
}
# Documented exception only: runbook step 6 permits SKIP VI (record BLOCKED) when
# no recovery path exists; classification may then proceed EN-only. Every other
# prerequisite must be PASS; FAIL/PARTIAL/UNKNOWN/NOT_RUN (or BLOCKED elsewhere) blocks.
SOFT_BLOCK_OK={("adas_classified", "vi_capture_done")}
def satisfied(dep, want_for):
  s=g[dep]["status"]
  if s=="PASS": return True
  if s=="BLOCKED" and (want_for,dep) in SOFT_BLOCK_OK: return True
  return False
for k in order:
  s=g[k]["status"]
  if s in ("PASS","FAIL","PARTIAL","BLOCKED"):
    continue  # decided; downstream prereq checks enforce the consequences
  if s not in ("NOT_RUN","UNKNOWN"):
    print(f"STOP: corrupt gate state ({k}={s})")
    sys.exit(1)
  bad=[p for p in PREREQ.get(k,[]) if not satisfied(p,k)]
  if bad:
    detail=", ".join(f"{p}={g[p]['status']}" for p in bad)
    print(f"STOP: {k} BLOCKED by {detail} (resolve before proceeding)")
    sys.exit(1)
  print(f"next gate: {k} ({g[k]['evidence_path']})")
  sys.exit(0)
fails=[k for k in order if g[k]["status"]=="FAIL"]
if fails:
  print(f"all gates decided but FAIL present: {' '.join(fails)} (do not proceed)")
  sys.exit(1)
print("(all decided — see summary)")
PY
}
cmd="${1:-status}"
case "$cmd" in
  status) show_status;;
  next) show_next;;
  record) shift; record_gate "${1:-}" "${2:-}" "${3:-}";;
  stop) shift; stop_day "${1:-}";;
  *) echo "usage: $0 [--gates <path>] [status|next|record <gate> <value> [note]|stop <reason>]" >&2; exit 2;;
esac
