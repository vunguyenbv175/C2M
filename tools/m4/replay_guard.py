#!/usr/bin/env python3
"""EF-A02 L2 replay guard — projection of tools/m4/m4_policy.json (review F2).

Only harmless info-class messages may be planned/replayed at L2.
L3 semantic injection is BLOCKED (Gate F): no encoder exists yet.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

_POLICY = json.loads((Path(__file__).resolve().parent / "m4_policy.json").read_text())
ALLOW_UUIDS = set(_POLICY["allow_l2_json_uuids"])

# Harmless-template key shapes (mirrors M4Adapter::ShapeOk, C++).
SHAPES = {
    "DispBrightSet": {"type", "uuid", "brightness"},
    "StorageStatus": {"type", "uuid", "status"},
    "ScreenModeSet": {"type", "uuid", "theme"},
    "ClientConn": {"type", "uuid", "connected"},
}
KEY_RE = re.compile(r'"([A-Za-z_]+)"\s*:')
DENIED_SUBSTRINGS = (
    "vehicleWarning vehicleMeasure pedestrians laneWarningRes AdasStatus "
    "HeavyCalibStatus GPSSpeed GPSLevel RecordVoice warning_level warn crucial "
    "danger deviat fcw ttc dist headway lane ped bike frame_id is_key speed"
).split()


def classify_json_uuid(uuid: str) -> str:
    return "ALLOW-L2" if uuid in ALLOW_UUIDS else "DENY"


def payload_shape_ok(uuid: str, payload: str) -> bool:
    """Key-shape allowlist + denied-substring sweep (parity with C++ boundary)."""
    want = SHAPES.get(uuid)
    if want is None:
        return False
    try:
        obj = json.loads(payload)
    except Exception:
        return False
    if not isinstance(obj, dict):
        return False
    if set(obj) - want:
        return False
    for d in DENIED_SUBSTRINGS:
        if d in payload:
            return False
    return True


def classify_inner_key(key: str) -> str:
    return "DENY"  # default-deny: all semantic keys need L3 proof


def guard_replay(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    ok, blocked = [], []
    for c in candidates:
        uuid = c.get("uuid", "")
        key = c.get("key", "")
        if uuid:
            verdict = classify_json_uuid(uuid)
            if verdict == "ALLOW-L2" and "payload" in c:
                verdict = "ALLOW-L2" if payload_shape_ok(uuid, c["payload"]) else "DENY"
        else:
            verdict = classify_inner_key(key)
        (ok if verdict == "ALLOW-L2" else blocked).append(c)
    return ok, blocked


if __name__ == "__main__":
    demo = [{"uuid": "DispBrightSet"}, {"uuid": "GPSSpeed"},
            {"uuid": "AdasStatus"}, {"key": "vehicleWarning"},
            {"uuid": "DispBrightSet",
             "payload": '{"uuid":"DispBrightSet","brightness":7,"fcw":1}'}]
    print(guard_replay(demo))
