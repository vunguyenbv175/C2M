#!/usr/bin/env python3
"""EF-A06 host OSM pipeline (review F10 fix): real OSM XML parse -> SQLite R*Tree
-> heading-aware nearest-segment query -> FuseSpeedLimit demo.

  python3 tools/road/osm_preprocess.py --in tools/road/fixtures/tiny_map.osm \
      --out build/vietnam_roads_sample.sqlite
  python3 tools/road/test_road.py

Vietnam-scale strategy (host-only, never on C2M): same script against a
vietnam.osm.pbf-derived XML/chunk (osmium not required for the fixture path);
target V1 DB < 100MB (motorways/trunks/primaries first). DB files are NOT
committed to the repo.
"""
from __future__ import annotations
import argparse
import math
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS segments(
  id INTEGER PRIMARY KEY, way_id INTEGER, min_lat REAL, max_lat REAL,
  min_lon REAL, max_lon REAL, maxspeed INTEGER, road_class TEXT,
  oneway INTEGER, name TEXT, heading_deg REAL);
CREATE VIRTUAL TABLE IF NOT EXISTS seg_rtree USING rtree(
  id, min_lat, max_lat, min_lon, max_lon);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def heading_deg(lat1, lon1, lat2, lon2) -> float:
    dy = lat2 - lat1
    dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return (math.degrees(math.atan2(dx, dy)) + 360) % 360


def parse_osm(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    nodes = {n.get("id"): (float(n.get("lat")), float(n.get("lon"))) for n in root.findall("node")}
    segs = []
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        refs = [nd.get("ref") for nd in way.findall("nd")]
        pts = [nodes[r] for r in refs if r in nodes]
        for i in range(len(pts) - 1):
            (a1, o1), (a2, o2) = pts[i], pts[i + 1]
            try:
                ms = int(str(tags.get("maxspeed", "-1")).split()[0])
            except ValueError:
                ms = -1
            segs.append({
                "way_id": int(way.get("id")), "seg": i,
                "min_lat": min(a1, a2), "max_lat": max(a1, a2),
                "min_lon": min(o1, o2), "max_lon": max(o1, o2),
                "maxspeed": ms, "road_class": tags.get("highway", ""),
                "oneway": 1 if tags.get("oneway") == "yes" else 0,
                "name": tags.get("name", ""),
                "heading_deg": heading_deg(a1, o1, a2, o2)})
    return segs


def build_db(segs: list[dict], db: Path, version: str = "fixture-v1") -> int:
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    for k, s in enumerate(segs):
        con.execute(
            "INSERT INTO segments(id,way_id,min_lat,max_lat,min_lon,max_lon,maxspeed,"
            "road_class,oneway,name,heading_deg) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (k, s["way_id"], s["min_lat"], s["max_lat"], s["min_lon"], s["max_lon"],
             s["maxspeed"], s["road_class"], s["oneway"], s["name"], s["heading_deg"]))
        con.execute("INSERT INTO seg_rtree VALUES(?,?,?,?,?)",
                    (k, s["min_lat"], s["max_lat"], s["min_lon"], s["max_lon"]))
    con.execute("INSERT INTO meta VALUES('version',?)", (version,))
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    con.close()
    return n


def query(db: Path, lat: float, lon: float, heading: float, radius_deg: float = 0.005) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT s.* FROM segments s JOIN seg_rtree r ON s.id = r.id
           WHERE r.min_lat <= ? AND r.max_lat >= ? AND r.min_lon <= ? AND r.max_lon >= ?""",
        (lat + radius_deg, lat - radius_deg, lon + radius_deg, lon - radius_deg)).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        dh = abs((d["heading_deg"] - heading + 180) % 360 - 180)
        dh = min(dh, abs((d["heading_deg"] + 180 - heading + 180) % 360 - 180)) if d["oneway"] == 0 else dh
        d["heading_diff_deg"] = dh
        out.append(d)
    out.sort(key=lambda d: d["heading_diff_deg"])
    return out


def fuse_speed_limit(camera, cam_conf, osm, osm_conf, vietmap, vm_conf, age_ms=0):
    if camera is not None and cam_conf >= 0.6:
        return {"limit_kmh": camera, "confidence": cam_conf, "source": "camera", "age_ms": age_ms}
    if vietmap is not None and vm_conf >= 0.6:
        return {"limit_kmh": vietmap, "confidence": vm_conf, "source": "vietmap", "age_ms": age_ms}
    if osm is not None and osm_conf >= 0.4:
        return {"limit_kmh": osm, "confidence": osm_conf, "source": "osm", "age_ms": age_ms}
    return {"limit_kmh": None, "confidence": 0.0, "source": "none", "age_ms": age_ms}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=Path("tools/road/fixtures/tiny_map.osm"))
    ap.add_argument("--out", type=Path, default=Path("build/vietnam_roads_sample.sqlite"))
    args = ap.parse_args()
    segs = parse_osm(args.inp)
    n = build_db(segs, args.out)
    print(f"parsed {len(segs)} segments -> {args.out} rows={n}")


if __name__ == "__main__":
    main()
