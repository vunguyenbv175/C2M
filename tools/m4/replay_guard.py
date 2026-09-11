#!/usr/bin/env python3
"""EF-A02 L2 replay guard. Only harmless info-class messages may be replayed.

ALLOW (L2 harmless): DispBrightSet, StorageStatus, DisplayMode/ScreenModeSet, ClientConn
DENY (needs L3+proof): vehicleWarning, vehicleMeasure, pedestrians, laneWarningRes,
  AdasStatus, GPSSpeed/GPSLevel (semantic), RecordVoice
"""
from __future__ import annotations

ALLOW_UUIDS = {"DispBrightSet", "StorageStatus", "ScreenModeSet", "ClientConn"}
DENY_UUIDS = {"AdasStatus", "HeavyCalibStatus", "GPSLevel", "GPSSpeed", "RecordVoice"}
DENY_KEYS = {"vehicleWarning", "vehicleMeasure", "pedestrians", "laneWarningRes"}


def classify_json_uuid(uuid: str) -> str:
    if uuid in ALLOW_UUIDS:
        return "ALLOW-L2"
    return "DENY"


def classify_inner_key(key: str) -> str:
    if key in DENY_UUIDS or key in DENY_KEYS:
        return "DENY"
    return "DENY"  # default-deny for unknown semantic keys


def guard_replay(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    ok, blocked = [], []
    for c in candidates:
        uuid = c.get("uuid", "")
        key = c.get("key", "")
        verdict = classify_json_uuid(uuid) if uuid else classify_inner_key(key)
        (ok if verdict == "ALLOW-L2" else blocked).append(c)
    return ok, blocked


if __name__ == "__main__":
    demo = [{"uuid": "DispBrightSet"}, {"uuid": "AdasStatus"}, {"key": "vehicleWarning"}]
    print(guard_replay(demo))
