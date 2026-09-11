#!/usr/bin/env python3
"""Synthetic test for EF-A01 normalize_stock (mirrors C++ NormalizeStock)."""
from normalize_adas import normalize_stock


def main():
    snap = {
        "now_ms": 1000, "last_frame_ms": 900, "frame_id": 42,
        "libflow_connected": True, "cardv_connected": True,
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
    s = normalize_stock(snap)
    assert not s["stale"], s
    assert s["lead"] == {"long_dist": 6.5, "ttc": 1.1}, s["lead"]
    assert s["fcw"] == {"active": True, "level": 2}, s["fcw"]
    assert s["pcw"] == {"active": True}, s["pcw"]
    assert s["ldw"] == {"active": True, "level": 1}, s["ldw"]
    assert s["vehicles"][0]["headway"] == 1.2, s["vehicles"]
    # stale path
    snap2 = dict(snap, now_ms=5000)
    s2 = normalize_stock(snap2)
    assert s2["stale"] and s2["runtime_class"] == "C_InputPathSuspect", s2
    # disconnected path
    snap3 = dict(snap, libflow_connected=False)
    s3 = normalize_stock(snap3)
    assert s3["stale"] and s3["runtime_class"] == "A_ProcessAbsent", s3
    print("normalize_adas smoke: OK")


if __name__ == "__main__":
    main()
