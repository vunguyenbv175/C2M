#!/usr/bin/env python3
"""EF-A01 Python mirror of include/c2m/adas/stock_adas_provider.hpp::NormalizeStock.

Converts already-decoded stock inner payloads into a normalized AdasState dict.
Used by host-sim, Web V0, and synthetic tests. No sockets here.
"""
from __future__ import annotations
from typing import Any


def _num(row: dict, key: str, dflt: float = 0.0) -> float:
    try:
        v = row.get(key, dflt)
        return float(v) if isinstance(v, (int, float)) else dflt
    except Exception:
        return dflt


def normalize_stock(snapshot: dict, stale_after_ms: int = 500) -> dict:
    now_ms = int(snapshot.get("now_ms", 0))
    last_frame_ms = int(snapshot.get("last_frame_ms", 0))
    libflow = bool(snapshot.get("libflow_connected", False))
    cardv_conn = bool(snapshot.get("cardv_connected", False))
    nums: dict[str, list[dict]] = snapshot.get("nums", {})
    cardv: dict[str, str] = snapshot.get("cardv", {})
    age_ms = max(0, now_ms - last_frame_ms)
    stale = (not libflow) or (age_ms > stale_after_ms)

    warn_rows = nums.get("vehicleWarning", [])
    warn = warn_rows[0] if warn_rows else {}
    warn_id = int(_num(warn, "vehicle_id", -1))
    headway = _num(warn, "headway", 0.0)
    warning_level = int(_num(warn, "warning_level", 0))
    fcw_raw = int(_num(warn, "fcw", 0))

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

    lead = None
    for v in vehicles:
        if v["is_crucial"]:
            lead = v
            break
    if lead is None:
        for v in vehicles:
            if v["is_second_crucial"]:
                lead = v
                break
    if lead is None and vehicles:
        lead = min(vehicles, key=lambda x: x["long_dist"])

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
        if p["is_danger"] or p["is_key"]:
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
    ldw = lane["deviate_state"] != 0

    if not libflow:
        runtime_class = "A_ProcessAbsent"
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
        "vehicles": vehicles,
        "lead": {"long_dist": lead["long_dist"], "ttc": lead["ttc"]} if lead else None,
        "fcw": {"active": bool(fcw_raw or warning_level), "level": warning_level},
        "pcw": {"active": pcw},
        "ldw": {"active": ldw, "level": lane["deviate_state"]},
        "lane": lane,
        "pedestrians": pedestrians,
        "cardv_status": {
            "adas_status": cardv.get("AdasStatus", "UNKNOWN"),
            "calib_status": cardv.get("HeavyCalibStatus", "UNKNOWN"),
            "stale": "AdasStatus" not in cardv,
        },
    }
