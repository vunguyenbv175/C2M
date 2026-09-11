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
  min_lon REAL, max_lon REAL, maxspeed INTEGER, maxspeed_reason TEXT,
  road_class TEXT, oneway INTEGER, name TEXT, heading_deg REAL,
  ax REAL, ao REAL, bx REAL, bo REAL);
CREATE VIRTUAL TABLE IF NOT EXISTS seg_rtree USING rtree(
  id, min_lat, max_lat, min_lon, max_lon);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def heading_deg(lat1, lon1, lat2, lon2) -> float:
    dy = lat2 - lat1
    dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return (math.degrees(math.atan2(dx, dy)) + 360) % 360


def parse_maxspeed(raw) -> tuple[int | None, str]:
    """Explicit maxspeed handling (R8). Never silently picks from ambiguous text."""
    if raw is None:
        return None, "missing"
    s = str(raw).strip().lower()
    if s in ("signals", "variable", "none", ""):
        return None, "non-numeric"
    if "@" in s or "(" in s:
        return None, "conditional"
    if ";" in s or "," in s:
        return None, "ambiguous-multi"
    parts = s.split()
    try:
        val = float(parts[0])
    except ValueError:
        return None, "unparsable"
    if len(parts) > 1 and parts[1].startswith("mph"):
        return round(val * 1.60934), "mph-converted"
    return round(val), "ok"


def parse_osm(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    nodes = {n.get("id"): (float(n.get("lat")), float(n.get("lon"))) for n in root.findall("node")}
    segs = []
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        refs = [nd.get("ref") for nd in way.findall("nd")]
        pts = [nodes[r] for r in refs if r in nodes]
        ms, ms_reason = parse_maxspeed(tags.get("maxspeed"))
        for i in range(len(pts) - 1):
            (a1, o1), (a2, o2) = pts[i], pts[i + 1]
            segs.append({
                "way_id": int(way.get("id")), "seg": i,
                "min_lat": min(a1, a2), "max_lat": max(a1, a2),
                "min_lon": min(o1, o2), "max_lon": max(o1, o2),
                "maxspeed": ms if ms is not None else -1,
                "maxspeed_reason": ms_reason,
                "road_class": tags.get("highway", ""),
                "oneway": 1 if tags.get("oneway") == "yes" else 0,
                "name": tags.get("name", ""),
                "ax": a1, "ao": o1, "bx": a2, "bo": o2,
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
            "maxspeed_reason,road_class,oneway,name,heading_deg,ax,ao,bx,bo)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (k, s["way_id"], s["min_lat"], s["max_lat"], s["min_lon"], s["max_lon"],
             s["maxspeed"], s["maxspeed_reason"], s["road_class"], s["oneway"],
             s["name"], s["heading_deg"], s["ax"], s["ao"], s["bx"], s["bo"]))
        con.execute("INSERT INTO seg_rtree VALUES(?,?,?,?,?)",
                    (k, s["min_lat"], s["max_lat"], s["min_lon"], s["max_lon"]))
    con.execute("INSERT INTO meta VALUES('version',?)", (version,))
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    con.close()
    return n


DEG_LAT_M = 111320.0


def point_seg_dist_m(lat, lon, ax, ao, bx, bo) -> float:
    """Equirectangular point-to-segment distance in meters."""
    mx = math.cos(math.radians((lat + ax + bx) / 3))
    px, py = lon * DEG_LAT_M * mx, lat * DEG_LAT_M
    axx, axy = ao * DEG_LAT_M * mx, ax * DEG_LAT_M
    bxx, bxy = bo * DEG_LAT_M * mx, bx * DEG_LAT_M
    dx, dy = bxx - axx, bxy - axy
    denom = dx * dx + dy * dy
    t = ((px - axx) * dx + (py - axy) * dy) / denom if denom > 0 else 0.0
    t = max(0.0, min(1.0, t))
    cx, cy = axx + t * dx, axy + t * dy
    return math.hypot(px - cx, py - cy)


def heading_diff_deg(seg_heading: float, heading: float, oneway: int) -> float:
    d = abs((seg_heading - heading + 180) % 360 - 180)
    if oneway == 0:
        d = min(d, 180 - d)
    return d


# score = geometric distance + heading penalty + oneway-violation penalty
HEADING_M_PER_DEG = 1.0
ONEWAY_VIOLATION_M = 500.0


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
        dist = point_seg_dist_m(lat, lon, d["ax"], d["ao"], d["bx"], d["bo"])
        hd = heading_diff_deg(d["heading_deg"], heading, d["oneway"])
        oneway_violation = d["oneway"] == 1 and hd > 90
        d["distance_m"] = dist
        d["heading_diff_deg"] = hd
        d["oneway_violation"] = oneway_violation
        d["score"] = dist + HEADING_M_PER_DEG * hd + (ONEWAY_VIOLATION_M if oneway_violation else 0.0)
        out.append(d)
    out.sort(key=lambda d: d["score"])
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
