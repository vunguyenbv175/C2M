#!/usr/bin/env python3
"""Gate E: stock-compatible libflow fixtures (stand-ins for hardware captures).

Packs outer {time,source,topic,data=BIN(inner)} + inner {frame_id,time,key,data}
with msgpack, exactly like stock ScreenService/libflow. When a real pcap exists,
replace these fixtures with captured frames — the consumer path is identical.

Scenarios: fcw / lead / ped / ldw / idle
Output: build/fixtures/<scenario>_<topic>.bin  (+ manifest.json)
"""
from __future__ import annotations
import json
from pathlib import Path

import msgpack

OUT = Path("build/fixtures")


def frame(topic: str, key: str, data, frame_id: int = 42, t: int = 1000) -> bytes:
    inner = {"frame_id": frame_id, "time": t, "key": key, "data": data}
    outer = {"time": t, "source": "AdasScreenService", "topic": topic,
             "data": msgpack.packb(inner, use_bin_type=True)}
    return msgpack.packb(outer, use_bin_type=True)


VEH_WARN_FCW = {"vehicle_id": 3, "headway": 0.9, "warning_level": 0, "fcw": 2,
                "headway_warning": 0, "vb_warning": 0, "sag_warning": 0}
VEH_MEAS = [{"vehicle_class": 1, "vehicle_id": 3, "vehicle_width": 1.8,
             "longitude_dist": 6.5, "lateral_dist": 0.4, "ttc": 1.1,
             "is_crucial": True, "is_second_crucial": False}]
PED = [{"id": 7, "world_x": 1.2, "world_y": 8.0, "is_key": False,
        "is_danger": True, "ttc_m": 1.4, "ttc": 1.4, "have_bike": False}]
LANE = {"lanelines": [], "ldw_info": {"deviate_state": 1},
        "turn_radius": 250.0, "turn_frequently": False}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    plan = {
        "fcw_vehicleWarning": ("vehicle", "vehicleWarning", VEH_WARN_FCW),
        "fcw_vehicleMeasure": ("vehicle", "vehicleMeasure", VEH_MEAS),
        "ped_pedestrians": ("ped", "pedestrians", PED),
        "ldw_lane": ("lane", "laneWarningRes", LANE),
    }
    manifest = {}
    for name, (topic, key, data) in plan.items():
        blob = frame(topic, key, data)
        (OUT / f"{name}.bin").write_bytes(blob)
        manifest[name] = {"topic": topic, "key": key, "bytes": len(blob)}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"fixtures={len(plan)} -> {OUT}")


if __name__ == "__main__":
    main()
