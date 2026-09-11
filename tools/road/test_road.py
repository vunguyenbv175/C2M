#!/usr/bin/env python3
"""Road pipeline test: fixture parse -> R*Tree DB -> geometric query -> fusion."""
from pathlib import Path
from osm_preprocess import build_db, fuse_speed_limit, parse_maxspeed, parse_osm, query

DB = Path("build/test_roads.sqlite")


def main():
    segs = parse_osm(Path("tools/road/fixtures/tiny_map.osm"))
    assert len(segs) == 5, segs  # way101->2 segs, way102/103/104->1 each
    n = build_db(segs, DB, version="test-v1")
    assert n == 5, n

    # On QL1A heading NE (~43deg segment): top hit must be way 101, maxspeed 60.
    hits = query(DB, 21.0283, 105.8347, heading=45.0)
    assert hits and hits[0]["way_id"] == 101 and hits[0]["maxspeed"] == 60, hits

    # R8: closest segment must win over best-heading farther segment.
    # Point sits ON way101 (dist~0, heading diff ~17deg) while parallel way104
    # (~100m away) matches the 60deg query heading better.
    hits = query(DB, 21.0283, 105.8347, heading=60.0)
    w101 = [h for h in hits if h["way_id"] == 101]
    w104 = [h for h in hits if h["way_id"] == 104]
    assert w101 and w104, hits
    assert w101[0]["distance_m"] < 5.0, w101[0]
    assert w104[0]["distance_m"] > 50.0, w104[0]
    assert hits[0]["way_id"] == 101, [(h["way_id"], round(h["score"], 1)) for h in hits]

    # Oneway respect: heading opposite on oneway way102 is a violation.
    hits2 = query(DB, 21.0283, 105.8397, heading=225.0)
    w102 = [h for h in hits2 if h["way_id"] == 102]
    assert w102 and w102[0]["oneway_violation"] is True, hits2

    # maxspeed formats are explicit, never silently picked.
    assert parse_maxspeed("60") == (60, "ok")
    assert parse_maxspeed("60 km/h") == (60, "ok")
    assert parse_maxspeed("37 mph")[0] == 60 and parse_maxspeed("37 mph")[1] == "mph-converted"
    assert parse_maxspeed("signals") == (None, "non-numeric")
    assert parse_maxspeed("60 @ (Mo-Fr 08:00-18:00)") == (None, "conditional")
    assert parse_maxspeed("60;80") == (None, "ambiguous-multi")
    assert parse_maxspeed(None) == (None, "missing")

    # Fusion parity with C++ FuseSpeedLimit
    assert fuse_speed_limit(60, 0.9, 50, 0.8, 50, 0.9)["source"] == "camera"
    assert fuse_speed_limit(None, 0.0, 50, 0.8, 60, 0.9)["source"] == "vietmap"
    assert fuse_speed_limit(None, 0.0, 50, 0.5, None, 0.0)["source"] == "osm"
    assert fuse_speed_limit(None, 0.0, None, 0.0, None, 0.0)["source"] == "none"

    # End-to-end: query limit -> fusion (camera empty, OSM 60)
    hits = query(DB, 21.0283, 105.8347, heading=45.0)
    osm_limit = hits[0]["maxspeed"] if hits[0]["maxspeed"] > 0 else None
    fused = fuse_speed_limit(None, 0.0, osm_limit, 0.8, None, 0.0)
    assert fused == {"limit_kmh": 60, "confidence": 0.8, "source": "osm", "age_ms": 0}, fused
    print("road pipeline smoke: OK")


if __name__ == "__main__":
    main()
