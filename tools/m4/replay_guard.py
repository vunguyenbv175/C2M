#!/usr/bin/env python3
"""EF-A02 L2 replay guard — projection of tools/m4/m4_policy.json (review F2).

Only harmless info-class messages may be planned/replayed at L2.
L3 semantic injection is BLOCKED (Gate F): no encoder exists yet.
"""
from __future__ import annotations
import json
from pathlib import Path

_POLICY = json.loads((Path(__file__).resolve().parent / "m4_policy.json").read_text())
ALLOW_UUIDS = set(_POLICY["allow_l2_json_uuids"])


def classify_json_uuid(uuid: str) -> str:
    return "ALLOW-L2" if uuid in ALLOW_UUIDS else "DENY"


def classify_inner_key(key: str) -> str:
    return "DENY"  # default-deny: all semantic keys need L3 proof


def guard_replay(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    ok, blocked = [], []
    for c in candidates:
        uuid = c.get("uuid", "")
        key = c.get("key", "")
        verdict = classify_json_uuid(uuid) if uuid else classify_inner_key(key)
        (ok if verdict == "ALLOW-L2" else blocked).append(c)
    return ok, blocked


if __name__ == "__main__":
    demo = [{"uuid": "DispBrightSet"}, {"uuid": "GPSSpeed"},
            {"uuid": "AdasStatus"}, {"key": "vehicleWarning"}]
    print(guard_replay(demo))
