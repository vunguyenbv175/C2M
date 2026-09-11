#!/usr/bin/env python3
"""Road pipeline test: fixture parse -> R*Tree DB -> heading-aware query -> fusion."""
from pathlib import Path
from osm_preprocess import build_db, fuse_speed_limit, parse_osm, query

DB = Path("build/test_roads.sqlite")


def main():
    segs = parse_osm(Path("tools/road/fixtures/tiny_map.osm"))
    assert len(segs) == 4, segs  # way101->2 segs, way102->1, way103->1
    n = build_db(segs, DB, version="test-v1")
    assert n == 4, n

    # On QL1A heading NE (~45deg): top hit must be way 101, maxspeed 60
    hits = query(DB, 21.0283, 105.8347, heading=45.0)
    assert hits and hits[0]["way_id"] == 101 and hits[0]["maxspeed"] == 60, hits

    # Oneway respect: heading opposite on oneway way102 ranks it down
    hits2 = query(DB, 21.0283, 105.8397, heading=225.0)
    w102 = [h for h in hits2 if h["way_id"] == 102]
    assert w102 and w102[0]["heading_diff_deg"] > 90, hits2

    # Fusion parity with C++ FuseSpeedLimit
    assert fuse_speed_limit(60, 0.9, 50, 0.8, 50, 0.9)["source"] == "camera"
    assert fuse_speed_limit(None, 0.0, 50, 0.8, 60, 0.9)["source"] == "vietmap"
    assert fuse_speed_limit(None, 0.0, 50, 0.5, None, 0.0)["source"] == "osm"
    assert fuse_speed_limit(None, 0.0, None, 0.0, None, 0.0)["source"] == "none"

    # End-to-end: query limit -> fusion (camera empty, OSM 60)
    osm_limit = hits[0]["maxspeed"] if hits[0]["maxspeed"] > 0 else None
    fused = fuse_speed_limit(None, 0.0, osm_limit, 0.8, None, 0.0)
    assert fused == {"limit_kmh": 60, "confidence": 0.8, "source": "osm", "age_ms": 0}, fused
    print("road pipeline smoke: OK")


if __name__ == "__main__":
    main()
