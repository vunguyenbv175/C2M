#!/usr/bin/env python3
"""EF-A01 Python mirror of NormalizeStock (Gate B hardened).

Sole warning drivers per STOCK_ADAS_SCHEMA_V2: fcw field, is_danger,
deviate_state, is_crucial. Transport never implies process state.
Mirrors include/c2m/adas/stock_adas_provider.hpp exactly.
"""
from __future__ import annotations
from typing import Any


def _num(row: dict, key: str, dflt: float = 0.0) -> float:
    try:
        v = row.get(key, dflt)
        return float(v) if isinstance(v, (int, float)) else dflt
    except Exception:
        return dflt


def normalize_stock(snapshot: dict, now_ms: int | None = None, stale_after_ms: int = 500) -> dict:
    # R1: caller time drives age. Defaults to ingest time only for back-compat.
    if now_ms is None:
        now_ms = int(snapshot.get("now_ms", 0))
    last_frame_ms = int(snapshot.get("last_frame_ms", 0))
    libflow = bool(snapshot.get("libflow_reachable", snapshot.get("libflow_connected", False)))
    sub = bool(snapshot.get("subscription_active", libflow))
    cardv_conn = bool(snapshot.get("cardv_reachable", snapshot.get("cardv_connected", False)))
    frame_seen = bool(snapshot.get("frame_seen", snapshot.get("libflow_connected", False)))
    process = snapshot.get("process", "Unknown")  # Unknown|Present|Absent (collector only)
    nums: dict[str, list[dict]] = snapshot.get("nums", {})
    cardv: dict[str, str] = snapshot.get("cardv", {})
    age_ms = max(0, now_ms - last_frame_ms) if frame_seen else 0
    stale = (not frame_seen) or (age_ms > stale_after_ms)

    warn_rows = nums.get("vehicleWarning", [])
    warn = warn_rows[0] if warn_rows else {}
    warn_id = int(_num(warn, "vehicle_id", -1))
    headway = _num(warn, "headway", 0.0)
    warning_level = int(_num(warn, "warning_level", 0))
    fcw_raw = int(_num(warn, "fcw", 0))
    raw = {"vehicle_warning": dict(warn), "warning_level": warning_level,
           "headway_warning": int(_num(warn, "headway_warning", 0)),
           "vb_warning": int(_num(warn, "vb_warning", 0)),
           "sag_warning": int(_num(warn, "sag_warning", 0)),
           "key_pedestrian_count": 0, "deviate_state": 0}

    vehicles: list[dict[str, Any]] = []
    for r in nums.get("vehicleMeasure", []):
        v = {
            "id": int(_num(r, "vehicle_id", -1)),
            "vehicle_class": int(_num(r, "vehicle_class", -1)),
            "width": _num(r, "vehicle_width", 0.0),
            "long_dist": _num(r, "longitude_dist", 0.0),
            "lat_dist": _num(r, "lateral_dist", 0.0),
            "ttc": _num(r, "ttc", 0.0),
            "is_crucial": bool(_num(r, "is_crucial", 0.0)),
            "is_second_crucial": bool(_num(r, "is_second_crucial", 0.0)),
            "headway": 0.0,
        }
        if v["id"] == warn_id:
            v["headway"] = headway
        vehicles.append(v)

    lead: dict[str, Any] | None = None
    # R2: is_crucial is the SOLE lead signal; second_crucial is metadata only.
    second_crucial_count = 0
    for v in vehicles:
        if v["is_crucial"]:
            lead = {"long_dist": v["long_dist"], "ttc": v["ttc"], "reason": "crucial"}
            break
    for v in vehicles:
        if v["is_second_crucial"]:
            second_crucial_count += 1
    raw["second_crucial_count"] = second_crucial_count

    pedestrians: list[dict[str, Any]] = []
    pcw = False
    for r in nums.get("pedestrians", []):
        p = {
            "id": int(_num(r, "id", -1)),
            "world_x": _num(r, "world_x", 0.0),
            "world_y": _num(r, "world_y", 0.0),
            "is_key": bool(_num(r, "is_key", 0.0)),
            "is_danger": bool(_num(r, "is_danger", 0.0)),
            "ttc_m": _num(r, "ttc_m", 0.0),
            "ttc": _num(r, "ttc", 0.0),
            "have_bike": bool(_num(r, "have_bike", 0.0)),
        }
        if p["is_key"]:
            raw["key_pedestrian_count"] += 1
        if p["is_danger"]:
            pcw = True
        pedestrians.append(p)

    lane_rows = nums.get("laneWarningRes", [])
    lane = {"deviate_state": 0, "turn_radius": 0.0, "turn_frequently": False}
    if lane_rows:
        lane = {
            "deviate_state": int(_num(lane_rows[0], "deviate_state", 0)),
            "turn_radius": _num(lane_rows[0], "turn_radius", 0.0),
            "turn_frequently": bool(_num(lane_rows[0], "turn_frequently", 0.0)),
        }
    raw["deviate_state"] = lane["deviate_state"]

    if process == "Absent":
        runtime_class = "A_ProcessAbsent"
    elif not frame_seen:
        runtime_class = "Unknown"
    elif stale:
        runtime_class = "C_InputPathSuspect"
    else:
        runtime_class = "Ok"

    return {
        "timestamp_ms": now_ms,
        "frame_id": int(snapshot.get("frame_id", 0)),
        "stale": stale,
        "age_ms": age_ms,
        "runtime_class": runtime_class,
        "process": process,
        "libflow_reachable": libflow,
        "subscription_active": sub,
        "cardv_reachable": cardv_conn,
        "vehicles": vehicles,
        "lead": lead,
        "fcw": {"active": bool(fcw_raw), "level": fcw_raw, "evidence": "HighConfidence" if fcw_raw else "Unknown"},
        "pcw": {"active": pcw, "evidence": "HighConfidence" if pcw else "Unknown"},
        "ldw": {"active": lane["deviate_state"] != 0, "level": lane["deviate_state"],
                "evidence": "HighConfidence" if lane["deviate_state"] else "Unknown"},
        "lane": lane,
        "pedestrians": pedestrians,
        "raw": raw,
        "cardv_status": {
            "adas_status": cardv.get("AdasStatus", "UNKNOWN"),
            "calib_status": cardv.get("HeavyCalibStatus", "UNKNOWN"),
            "stale": "AdasStatus" not in cardv,
        },
    }
