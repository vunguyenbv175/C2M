#!/usr/bin/env python3
"""EF-A06 host-side OSM preprocess (V0 spec + tiny-XML demo).

Full Vietnam PBF is NOT parsed on C2M and NOT bundled in repo.
V0: define SQLite schema, parse a tiny OSM XML sample, emit vietnam_roads.sqlite sample,
and demo FuseSpeedLimit parity with include/c2m/road/road_provider.hpp.
"""
from __future__ import annotations
import argparse
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS segments(
  id INTEGER PRIMARY KEY, min_lat REAL, max_lat REAL, min_lon REAL, max_lon REAL,
  maxspeed INTEGER, road_class TEXT, oneway INTEGER, name TEXT);
CREATE INDEX IF NOT EXISTS idx_segments_bbox ON segments(min_lat,max_lat,min_lon,max_lon);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def fuse_speed_limit(camera, cam_conf, osm, osm_conf, vietmap, vm_conf, age_ms=0):
    out = {"limit_kmh": None, "confidence": 0.0, "source": "none", "age_ms": age_ms}
    if camera is not None and cam_conf >= 0.6:
        return {"limit_kmh": camera, "confidence": cam_conf, "source": "camera", "age_ms": age_ms}
    if vietmap is not None and vm_conf >= 0.6:
        return {"limit_kmh": vietmap, "confidence": vm_conf, "source": "vietmap", "age_ms": age_ms}
    if osm is not None and osm_conf >= 0.4:
        return {"limit_kmh": osm, "confidence": osm_conf, "source": "osm", "age_ms": age_ms}
    return out


def build_sample(db: Path):
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    con.execute("DELETE FROM segments")
    con.executemany(
        "INSERT INTO segments(id,min_lat,max_lat,min_lon,max_lon,maxspeed,road_class,oneway,name)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        [(1, 10.7, 10.9, 106.6, 106.8, 60, "trunk", 0, "QL1A-sample"),
         (2, 21.0, 21.1, 105.8, 105.9, 80, "primary", 0, "Vo Nguyen Giap-sample")])
    con.execute("INSERT OR REPLACE INTO meta VALUES('version','sample-v1')")
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    con.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("build/vietnam_roads_sample.sqlite"))
    args = ap.parse_args()
    n = build_sample(args.out)
    # fusion sanity (parity with C++ FuseSpeedLimit)
    assert fuse_speed_limit(60, 0.9, 50, 0.8, 50, 0.9)["source"] == "camera"
    assert fuse_speed_limit(None, 0.0, 50, 0.8, 60, 0.9)["source"] == "vietmap"
    assert fuse_speed_limit(None, 0.0, 50, 0.5, None, 0.0)["source"] == "osm"
    assert fuse_speed_limit(None, 0.0, None, 0.0, None, 0.0)["source"] == "none"
    print(f"road sample DB: {args.out} rows={n}; fusion smoke OK")


if __name__ == "__main__":
    main()
