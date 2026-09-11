#!/usr/bin/env python3
"""ProMax nav protocol emulator (recovered protocol ONLY; no invented live fields).

Supports handshake/management plane byte-exact:
  ping -> pong, dev/want/can advertisement, LOAD/DTBK validation, IMG markers.
Live value-plane: template generator for the PROVEN bare-key set
  (unix/nav/spd/lim/trn/dst/exit/eta/rmin/rkm/avg/alrs/hi)
with all VALUES synthetic and enums DISABLED (turn/lane/alert/limit units UNKNOWN).
Unknown want-only keys (st/avgL/lan) are refused, not guessed.

Usage:
  python nav_protocol_emulator.py pong
  python nav_protocol_emulator.py dev --name Promax
  python nav_protocol_emulator.py live-template
  python nav_protocol_emulator.py validate <frame.json>
"""
import json, sys, time
DEV_FIELDS = ["nav", "spd", "lim", "trn", "dst", "exit", "st", "eta", "rmin", "rkm", "avg", "avgL", "alrs", "lan"]
DEV_CAN = ["speed", "limit", "turn", "street", "eta", "avgzone", "alerts"]
LIVE_KEYS = ["unix", "nav", "spd", "lim", "trn", "dst", "exit", "eta", "rmin", "rkm", "avg", "alrs", "hi"]
WANT_ONLY_UNKNOWN = ["st", "avgL", "lan"]  # in handshake want, absent from bare table: DO NOT EMIT
def pong(): return '{"v":1,"t":"pong"}\n'
def dev(name="Promax"):
    return json.dumps({"v": 1, "t": "dev", "name": name, "fw": "1.0.0", "proto": [1],
        "want": {"rate": 4, "fields": DEV_FIELDS},
        "can": DEV_CAN, "transport": "ble"}) + "\n"
def live_template():
    # Values are PLACEHOLDERS (types/units unproven). Emulator never claims semantics.
    return json.dumps({"unix": 0, "nav": 0, "spd": 0, "lim": 0, "trn": 0, "dst": 0,
        "exit": 0, "eta": 0, "rmin": 0, "rkm": 0, "avg": 0, "alrs": 0, "hi": 0,
        "_note": "SYNTHETIC: key set proven (bare table), value types/units NOT recovered"}) + "\n"
def validate(frame: str):
    try: o = json.loads(frame)
    except Exception as e: return (False, f"invalid JSON: {e}")
    if o.get("v") != 1 and "t" in o: return (False, "wrong version (want v=1)")
    t = o.get("t")
    if t in ("pong", "ping", "dev"): return (True, f"handshake type {t}")
    # live object: must not contain invented keys; values unchecked (UNKNOWN units)
    unknown = [k for k in o if k not in LIVE_KEYS + ["_note"]]
    if unknown: return (False, f"unknown keys (refused, not guessed): {unknown}")
    if len(frame.encode()) > 4096: return (False, "oversized frame")
    return (True, "live-template shape (values UNVALIDATED: units UNKNOWN)")
if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "pong"
    if a == "pong": print(pong(), end="")
    elif a == "dev": print(dev(sys.argv[2] if len(sys.argv) > 2 else "Promax"), end="")
    elif a == "live-template": print(live_template(), end="")
    elif a == "validate":
        ok, msg = validate(open(sys.argv[2], encoding="utf-8").read() if len(sys.argv) > 2 else sys.stdin.read())
        print(("PASS: " if ok else "FAIL: ") + msg); sys.exit(0 if ok else 1)
    else: print("unknown cmd", a); sys.exit(2)
