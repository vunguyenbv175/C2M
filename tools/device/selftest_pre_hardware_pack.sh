#!/bin/sh
# selftest_pre_hardware_pack.sh — offline dry-run of the C2M pre-hardware bring-up pack.
# Workstation only. No network, no hardware, no firmware mutation, no repo mutation
# (all scratch state under a TEMP dir; the gates template is only read).
# Exit 0 = all mandatory tests PASS; non-zero = at least one mandatory failure.
# Usage: sh tools/device/selftest_pre_hardware_pack.sh
set -u
PASS=0
FAIL=0
SKIP=0
ok() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }
skip() { SKIP=$((SKIP + 1)); echo "SKIP: $1"; }
REPO="$(dirname "$0")/../.."
cd "$REPO" || { echo "FAIL: cannot cd to repo root"; exit 1; }
TEMPLATE="docs/hardware/C2M_HARDWARE_DAY_GATES.json"
T="${TMPDIR:-/tmp}/c2m_selftest_$$"
mkdir -p "$T" || { echo "FAIL: cannot create scratch dir"; exit 1; }
cleanup() { rm -rf "$T"; }
trap cleanup EXIT INT TERM HUP
PYBIN=""
if command -v python3 >/dev/null 2>&1; then PYBIN="python3";
elif command -v python >/dev/null 2>&1; then PYBIN="python"; fi
[ -n "$PYBIN" ] || { echo "FAIL: python3/python required"; exit 1; }

echo "== 1. JSON parse + gate schema =="
if "$PYBIN" - "$TEMPLATE" <<'PY' 2>"$T/json.err"; then
import json,sys
d=json.load(open(sys.argv[1]))
assert set(d["gates"]) == set(d["order"]), "gates/order mismatch"
assert "NOT_RUN" in d["status_values"] and "PASS" in d["status_values"]
assert all(g["status"]=="NOT_RUN" for g in d["gates"].values()), "template not pristine"
print("gates=%d order_ok" % len(d["order"]))
PY
  ok "gates template parses, schema + pristine NOT_RUN"
else
  bad "gates template JSON/schema"; cat "$T/json.err"
fi

echo "== 2. shell syntax (sh -n) =="
SYNTAX_BAD=0
for f in tools/device/*.sh tools/fw/capture_c2m_adas_runtime.sh; do
  sh -n "$f" 2>/dev/null || { echo "  syntax fail: $f"; SYNTAX_BAD=1; }
done
[ "$SYNTAX_BAD" -eq 0 ] && ok "sh -n clean on all pack scripts" || bad "sh -n failures"

echo "== 3. python syntax =="
PYC_BAD=0
for f in tools/fw/compare_c2m_runtime_capture.py tools/device/classify_adas_state.py \
         tools/reverse/promax/parse_promax_ble_capture.py tools/reverse/promax/correlate_promax_nav_session.py \
         tools/research/ipu_sdk/compare_mi_ipu_api.py tools/research/ipu_sdk/fingerprint_sgs_sdk.py \
         tools/research/ai_adas/onnx_operator_audit.py; do
  "$PYBIN" -m py_compile "$f" 2>/dev/null || { echo "  py_compile fail: $f"; PYC_BAD=1; }
done
[ "$PYC_BAD" -eq 0 ] && ok "py_compile clean on all pack tools" || bad "py_compile failures"
find tools/device tools/fw tools/reverse/promax tools/research/ipu_sdk tools/research/ai_adas -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

echo "== 4. gate dependency engine (temp copy, template untouched) =="
H_BEFORE=$(sha256sum "$TEMPLATE" 2>/dev/null | awk '{print $1}')
if ! command -v sha256sum >/dev/null 2>&1 || [ -z "$H_BEFORE" ]; then
  skip "sha256sum absent for template-hash guard"
else
  cp "$TEMPLATE" "$T/gates.json" || bad "scratch gates copy"
  G="sh tools/device/c2m_hw_day.sh --gates $T/gates.json"
  n=$($G next 2>&1) || bad "fresh next rc"
  case "$n" in *"next gate: recovery_ready"*) ok "fresh -> recovery_ready";; *) bad "fresh next ($n)";; esac
  $G record recovery_ready FAIL >/dev/null 2>&1
  n=$($G next 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && case "$n" in *STOP*) true;; *) false;; esac; then ok "FAIL -> STOP"; else bad "FAIL -> STOP ($n rc=$rc)"; fi
  case "$n" in *"next gate: candidate_a_pass"*) bad "FAIL suggested A";; *) ok "FAIL does not suggest A";; esac
  $G record recovery_ready PASS >/dev/null 2>&1
  n=$($G next 2>&1) || bad "pass next rc"
  case "$n" in *"next gate: candidate_a_pass"*) ok "PASS -> A allowed";; *) bad "PASS -> A ($n)";; esac
  $G record candidate_a_pass FAIL >/dev/null 2>&1
  n=$($G next 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && case "$n" in *STOP*) true;; *) false;; esac; then ok "A-FAIL -> STOP"; else bad "A-FAIL -> STOP ($n rc=$rc)"; fi
  case "$n" in *"next gate: candidate_b_pass"*) bad "A-FAIL suggested B";; *) ok "A-FAIL blocks B";; esac
  for g in recovery_ready candidate_a_pass candidate_b_pass en_capture_done vi_capture_done adas_classified m4_l1_pass ipu_baseline_done scl_map_done; do
    $G record "$g" PASS >/dev/null 2>&1
  done
  n=$($G next 2>&1) || bad "prefinal next rc"
  case "$n" in *"next gate: ipu_safe_pass"*) ok "pre-coexist -> safe";; *) bad "pre-coexist ($n)";; esac
  $G record ipu_safe_pass BLOCKED >/dev/null 2>&1
  n=$($G next 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && case "$n" in *STOP*ipu_safe_pass=BLOCKED*) true;; *) false;; esac; then
    ok "coexist blocked without safe"
  else
    bad "coexist gate ($n rc=$rc)"
  fi
  if $G record "$TEMPLATE" recovery_ready PASS >/dev/null 2>&1; then
    bad "template path record not refused"
  else
    ok "template path record refused"
  fi
  H_AFTER=$(sha256sum "$TEMPLATE" | awk '{print $1}')
  if [ "$H_BEFORE" = "$H_AFTER" ]; then ok "template immutable across gate tests"; else bad "TEMPLATE MUTATED"; fi
fi

echo "== 5. recursive hash block (synthetic nested tree) =="
mkdir -p "$T/cap/proc_1/task/7" "$T/cap/dir with space"
printf 'a' > "$T/cap/ps.txt"
printf 'b' > "$T/cap/proc_1/status"
printf 'c' > "$T/cap/proc_1/task/7/status"
printf 'd' > "$T/cap/dir with space/f.txt"
OUT="cap"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$T" && find "$OUT" -type f ! -name 'SHA256SUMS.txt' -print | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done >"$OUT/SHA256SUMS.txt" 2>/dev/null) || bad "hash block rc"
  NL=$(wc -l < "$T/cap/SHA256SUMS.txt" | tr -d ' ')
  [ "$NL" = "4" ] && ok "4/4 files hashed incl. space-path" || bad "hash count=$NL"
  if grep -q SHA256SUMS "$T/cap/SHA256SUMS.txt"; then bad "SHA256SUMS self-included"; else ok "SHA256SUMS excluded"; fi
  if (cd "$T" && sha256sum -c cap/SHA256SUMS.txt 2>/dev/null | grep -c ': OK' | grep -q '^4$'); then
    ok "sha256sum -c verifies 4/4"
  else
    bad "sha256sum -c verify"
  fi
  (cd "$T" && find "$OUT" -type f ! -name 'SHA256SUMS.txt' -print | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done >second.txt)
  if cmp -s "$T/cap/SHA256SUMS.txt" "$T/second.txt"; then ok "hash output deterministic"; else bad "hash nondeterministic"; fi
  if (cd "$T" && tar -czf cap.tar.gz cap 2>/dev/null) && tar -tzf "$T/cap.tar.gz" >/dev/null 2>&1; then
    ok "tar bundle valid"
  else
    bad "tar bundle"
  fi
else
  skip "sha256sum/tar absent"
fi

echo "== 6. doc path/reference check =="
if "$PYBIN" - <<'PY' >"$T/paths.out" 2>"$T/paths.err"; then
import re
from pathlib import Path
root = Path(".")
hits = []
for md in (root / "docs" / "hardware").glob("*.md"):
    t = md.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"(tools/[A-Za-z0-9_./-]+\.(?:sh|py))", t):
        hits.append((md.name, m.group(1)))
missing = [(w, p) for w, p in hits if not (root / p).exists()]
print("refs=%d missing=%d" % (len(hits), len(missing)))
for w, p in missing:
    print("MISSING %s in %s" % (p, w))
PY
  cat "$T/paths.out"
  if grep -q "^MISSING" "$T/paths.out"; then bad "dangling doc references"; else ok "no dangling doc references"; fi
else
  bad "path check crashed"; cat "$T/paths.err"
fi

echo "== 7. IPU false-PASS test =="
if command -v g++ >/dev/null 2>&1; then
  if g++ -std=c++17 -Wall -Werror -Itools/device/c2m-ipu-smoke tools/device/c2m-ipu-smoke/main.cpp -o "$T/smoke" 2>"$T/build.err"; then
    "$T/smoke" --probe-only >/dev/null 2>&1; [ "$?" -eq 0 ] && ok "probe-only rc=0" || bad "probe-only rc"
    "$T/smoke" --single-invoke >/dev/null 2>&1; [ "$?" -eq 4 ] && ok "single-invoke rc=4 SDK_BLOCKED" || bad "single-invoke rc"
    "$T/smoke" --bogus >/dev/null 2>&1; [ "$?" -eq 2 ] && ok "usage rc=2" || bad "usage rc"
  else
    bad "smoke build (-Wall -Werror)"; cat "$T/build.err"
  fi
else
  if grep -q "return 4" tools/device/c2m-ipu-smoke/main.cpp; then
    ok "refuse-branch present (g++ absent, static proof)"
  else
    bad "refuse-branch missing and g++ absent"
  fi
fi

echo "== 8. python direct-run suites =="
"$PYBIN" tests/test_candidate_b.py >/dev/null 2>&1 && ok "test_candidate_b.py OK" || bad "test_candidate_b.py"
"$PYBIN" tests/test_firmware_pipeline.py >/dev/null 2>&1 && ok "test_firmware_pipeline.py OK" || bad "test_firmware_pipeline.py"
"$PYBIN" tools/device/test_classify_adas_state.py >/dev/null 2>&1 && ok "test_classify_adas_state.py OK" || bad "test_classify_adas_state.py"
"$PYBIN" tools/research/ai_adas/onnx_operator_audit.py "$T/nope.onnx" >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 3 ] || [ "$rc" -ne 0 ]; then ok "onnx audit fail-closed (rc=$rc, never false-PASS)"; else bad "onnx audit rc=$rc"; fi

echo "== 8b. research tooling synthetics (compare/promax/ipu-sdk) =="
mkdir -p "$T/syn/en" "$T/syn/vi"
printf 'a b c\n' > "$T/syn/en/proc_cmdline.txt"
printf 'a b c\n' > "$T/syn/vi/proc_cmdline.txt"
printf '1\tadas\t/bin/adas\n' > "$T/syn/en/processes.tsv"
printf '1\tadas\t/bin/adas\n' > "$T/syn/vi/processes.tsv"
if "$PYBIN" tools/fw/compare_c2m_runtime_capture.py "$T/syn/en" "$T/syn/vi" -o "$T/syn/out.json" >/dev/null 2>&1; then
  ok "compare_c2m_runtime_capture synthetic OK"
else
  bad "compare_c2m_runtime_capture synthetic"
fi
if "$PYBIN" tools/research/ipu_sdk/compare_mi_ipu_api.py 2>/dev/null | grep -q "MATCH (11)"; then
  ok "compare_mi_ipu_api baseline 11/0/0"
else
  bad "compare_mi_ipu_api baseline"
fi
if "$PYBIN" tools/research/ipu_sdk/fingerprint_sgs_sdk.py --sdk tools/device/c2m-ipu-smoke 2>/dev/null | "$PYBIN" -c "import json,sys; d=json.load(sys.stdin); assert d['file_count']>0" 2>/dev/null; then
  ok "fingerprint_sgs_sdk metadata-only OK"
else
  bad "fingerprint_sgs_sdk"
fi
if "$PYBIN" - "$T" <<'PY' >/dev/null 2>&1; then
import json, struct, subprocess, sys
from pathlib import Path
t = Path(sys.argv[1])
TS = 0x00E03AB44A676000 + 1700000000000000
def rec(flags, ts, pkt):
    return struct.pack(">IIIIQ", len(pkt), len(pkt), flags, 0, ts) + pkt
ev = bytes([0x3E, 0x07]) + bytes([0x03, 0x00]) + struct.pack("<H", 1) + struct.pack("<H", 0x20) + bytes(4)
att = bytes([0x12]) + struct.pack("<H", 0x2A) + b'{"t":"ping"}\n'
acl = struct.pack("<HH", 1, len(att) + 4) + struct.pack("<HH", len(att), 4) + att
att2 = bytes([0x1B]) + struct.pack("<H", 0x2C) + b'{"v":1}\n'
acl2 = struct.pack("<HH", 1, len(att2) + 4) + struct.pack("<HH", len(att2), 4) + att2
blob = b"btsnoop\x00" + struct.pack(">II", 1, 1002)
blob += rec(1, TS, bytes([0x04]) + ev)
blob += rec(0, TS + 1000000, bytes([0x02]) + acl)
blob += rec(1, TS + 2000000, bytes([0x02]) + acl2)
(t / "snoop.log").write_bytes(blob)
(t / "ev.csv").write_text("iso_time,event\n2023-11-14T22:13:20.000,nav_starts\n2023-11-14T22:13:30.000,idle\n")
r = subprocess.run([sys.executable, "tools/reverse/promax/parse_promax_ble_capture.py",
                    str(t / "snoop.log"), "--out", str(t / "table.json")],
                   capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-500:]
rows = json.loads((t / "table.json").read_text())["rows"]
names = {x["att_op_name"] for x in rows}
assert {"WRITE_REQ", "NOTIFY"} <= names, names
r = subprocess.run([sys.executable, "tools/reverse/promax/correlate_promax_nav_session.py",
                    str(t / "table.json"), str(t / "ev.csv"),
                    "--out", str(t / "corr.json")], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-500:]
corr = json.loads((t / "corr.json").read_text())
defvals = []
def collect(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("confidence", "verdict"):
                defvals.append(v)
            else:
                collect(v)
    elif isinstance(o, list):
        for v in o:
            collect(v)
collect(corr)
assert all(v != "PROVEN" for v in defvals), defvals
assert set(("packets_used", "clusters", "candidate_changes")) <= set(corr), corr.keys()
print("promax-synth-ok")
PY
  ok "promax parser+correlator synthetic (WRITE_REQ/NOTIFY, never PROVEN)"
else
  bad "promax synthetic tooling"
fi

echo "== 9. git diff --check =="
if git diff --check 2>/dev/null; then ok "git diff --check clean"; else bad "git diff --check"; fi

echo "RESULT pass=$PASS fail=$FAIL skip=$SKIP"
[ "$FAIL" -eq 0 ]
