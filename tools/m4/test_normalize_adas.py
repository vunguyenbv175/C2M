#!/usr/bin/env python3
"""Gate B tests for normalize_stock: sole drivers + negative cases + honest health."""
from normalize_adas import normalize_stock

BASE = {
    "now_ms": 1000, "last_frame_ms": 900, "frame_id": 42,
    "libflow_reachable": True, "subscription_active": True,
    "cardv_reachable": True, "frame_seen": True,
    "nums": {
        "vehicleWarning": [{"vehicle_id": 3, "headway": 1.2, "warning_level": 2,
                            "fcw": 1, "headway_warning": 0, "vb_warning": 0, "sag_warning": 0}],
        "vehicleMeasure": [
            {"vehicle_class": 1, "vehicle_id": 3, "vehicle_width": 1.8,
             "longitude_dist": 6.5, "lateral_dist": 0.4, "ttc": 1.1,
             "is_crucial": 1, "is_second_crucial": 0},
            {"vehicle_class": 0, "vehicle_id": 4, "vehicle_width": 1.7,
             "longitude_dist": 25.0, "lateral_dist": -1.2, "ttc": 4.0,
             "is_crucial": 0, "is_second_crucial": 0},
        ],
        "pedestrians": [{"id": 7, "world_x": 1.2, "world_y": 8.0, "is_key": 0,
                         "is_danger": 1, "ttc_m": 1.4, "ttc": 1.4, "have_bike": 0}],
        "laneWarningRes": [{"deviate_state": 1, "turn_radius": 300.0, "turn_frequently": 0}],
    },
    "cardv": {"AdasStatus": "ON", "HeavyCalibStatus": "CALIB_OK"},
}


def main():
    s = normalize_stock(BASE)
    assert not s["stale"] and s["runtime_class"] == "Ok", s
    assert s["lead"] == {"long_dist": 6.5, "ttc": 1.1, "reason": "crucial"}, s["lead"]
    assert s["fcw"]["active"] is True and s["raw"]["warning_level"] == 2, s

    # NEGATIVE: warning_level without fcw must NOT become FCW
    snap = {**BASE, "nums": {**BASE["nums"], "vehicleWarning": [
        {"vehicle_id": -1, "headway": 0.9, "warning_level": 5, "fcw": 0,
         "headway_warning": 1, "vb_warning": 0, "sag_warning": 0}]}}
    s2 = normalize_stock(snap)
    assert s2["fcw"]["active"] is False, s2["fcw"]
    assert s2["raw"]["warning_level"] == 5 and s2["raw"]["headway_warning"] == 1, s2["raw"]

    # NEGATIVE: key-only pedestrian must NOT become PCW
    snap = {**BASE, "nums": {**BASE["nums"], "pedestrians": [
        {"id": 9, "world_x": 0.5, "world_y": 6.0, "is_key": 1,
         "is_danger": 0, "ttc_m": 2.0, "ttc": 2.0, "have_bike": 0}]}}
    s3 = normalize_stock(snap)
    assert s3["pcw"]["active"] is False, s3["pcw"]
    assert s3["raw"]["key_pedestrian_count"] == 1, s3["raw"]

    # NEGATIVE: no crucial markers -> NO lead (no invented fallback)
    snap = {**BASE, "nums": {**BASE["nums"], "vehicleMeasure": [
        {"vehicle_class": 0, "vehicle_id": 4, "vehicle_width": 1.7,
         "longitude_dist": 25.0, "lateral_dist": -1.2, "ttc": 4.0,
         "is_crucial": 0, "is_second_crucial": 0}]}}
    s4 = normalize_stock(snap)
    assert s4["lead"] is None, s4["lead"]

    # second_crucial still yields lead with reason
    snap = {**BASE, "nums": {**BASE["nums"], "vehicleMeasure": [
        {"vehicle_class": 0, "vehicle_id": 4, "vehicle_width": 1.7,
         "longitude_dist": 25.0, "lateral_dist": -1.2, "ttc": 4.0,
         "is_crucial": 0, "is_second_crucial": 1}]}}
    s5 = normalize_stock(snap)
    assert s5["lead"]["reason"] == "second_crucial", s5["lead"]

    # HONEST HEALTH: no frames -> Unknown (never A_ProcessAbsent from socket)
    s6 = normalize_stock({**BASE, "frame_seen": False, "libflow_reachable": False})
    assert s6["stale"] and s6["runtime_class"] == "Unknown", s6
    # A_ProcessAbsent only with explicit collector proof
    s7 = normalize_stock({**BASE, "frame_seen": False, "libflow_reachable": False, "process": "Absent"})
    assert s7["runtime_class"] == "A_ProcessAbsent", s7
    # stale frames -> C_InputPathSuspect
    s8 = normalize_stock({**BASE, "now_ms": 5000})
    assert s8["stale"] and s8["runtime_class"] == "C_InputPathSuspect", s8
    print("normalize_adas Gate B smoke: OK")


if __name__ == "__main__":
    main()
