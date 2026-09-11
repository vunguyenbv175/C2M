#!/usr/bin/env python3
"""Correlate a ProMax BLE packet table with a manual event log (READ-ONLY).

Inputs:
  packets.json   from parse_promax_ble_capture.py (--out table)
  events.csv     wall-clock event log: iso_time,event[,speed,limit,turn,distance,promax_display,notes]
                 (template: 04_event_log/event_log.csv)
  --pre S --post S     cluster window around each event (defaults 5 / 10)
  --offset-s F         add F seconds to packet timestamps (clock-domain correction)

Output (--out corr.json, plus human summary unless --quiet):
  per event: packet cluster, per-handle counts/dirs/lengths,
  consecutive-payload diffs per handle (first differing offset),
  per-handle session cadence (median inter-arrival),
  candidate field changes with repeat_count.

CORRELATION ONLY. Confidence is capped at CANDIDATE -- PROVEN requires a
human to confirm repeated controlled changes (see ANALYSIS_PLAN doc).
No semantic labels are invented. Deterministic, stdlib only.
"""
import sys
import os
import json
import csv
import datetime

CONF_CAP = "CANDIDATE"  # tool never emits PROVEN


def parse_iso(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return None


def pkt_time(r, offset):
    t = parse_iso(r.get("ts_iso") or "")
    if t is None:
        try:
            t = datetime.datetime.fromtimestamp(float(r.get("frame.time_epoch", "")))
        except Exception:
            return None
    return t + datetime.timedelta(seconds=offset)


def diff_bytes(a, b):
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n if len(a) != len(b) else -1


def main():
    a = sys.argv[1:]
    if len(a) < 2 or "-h" in a or "--help" in a:
        print(__doc__)
        return 0
    pkt_path, evt_path = a[0], a[1]
    pre, post, offset, out = 5.0, 10.0, 0.0, None
    i = 2
    while i < len(a):
        if a[i] == "--pre":
            pre = float(a[i + 1])
            i += 2
        elif a[i] == "--post":
            post = float(a[i + 1])
            i += 2
        elif a[i] == "--offset-s":
            offset = float(a[i + 1])
            i += 2
        elif a[i] == "--out":
            out = a[i + 1]
            i += 2
        else:
            i += 1
    rows = json.load(open(pkt_path))["rows"]
    for r in rows:
        r["_t"] = pkt_time(r, offset)
    rows = [r for r in rows if r["_t"] is not None]
    rows.sort(key=lambda r: r["_t"])
    events = list(csv.DictReader(open(evt_path, newline="")))
    # session cadence per handle
    last, gaps = {}, {}
    for r in rows:
        h = r.get("handle") or "(no-handle)"
        if h in last:
            gaps.setdefault(h, []).append((r["_t"] - last[h]).total_seconds())
        last[h] = r["_t"]
    cadence = {}
    for h, g in gaps.items():
        g.sort()
        cadence[h] = {"n": len(g) + 1, "median_gap_s": g[len(g) // 2]}
    clusters = []
    for e in events:
        t = parse_iso(e.get("iso_time"))
        if t is None:
            continue
        lo, hi = t - datetime.timedelta(seconds=pre), t + datetime.timedelta(seconds=post)
        cl = [r for r in rows if lo <= r["_t"] <= hi]
        per_handle = {}
        for r in cl:
            h = r.get("handle") or "(no-handle)"
            d = per_handle.setdefault(h, {"count": 0, "dirs": {}, "lengths": [],
                                          "uuid": r.get("uuid", "")})
            d["count"] += 1
            d["dirs"][r["direction"]] = d["dirs"].get(r["direction"], 0) + 1
            d["lengths"].append(len(r.get("payload_hex", "")) // 2)
        # consecutive diffs inside cluster per handle
        diffs = []
        by_h = {}
        for r in cl:
            by_h.setdefault(r.get("handle") or "(no-handle)", []).append(r)
        for h, lst in by_h.items():
            for x, y in zip(lst, lst[1:]):
                try:
                    ba, bb = bytes.fromhex(x.get("payload_hex", "")), bytes.fromhex(y.get("payload_hex", ""))
                except ValueError:
                    continue
                at = diff_bytes(ba, bb)
                if at >= 0:
                    diffs.append({"handle": h, "offset": at,
                                  "old": ba[at:at + 8].hex() if at < len(ba) else "-",
                                  "new": bb[at:at + 8].hex() if at < len(bb) else "-",
                                  "direction": y["direction"]})
        clusters.append({"event": e.get("event", ""), "iso_time": e.get("iso_time", ""),
                         "packets": len(cl), "per_handle": per_handle, "diffs": diffs,
                         "note": e.get("notes", "")})
    # repeatability across events: same (handle, offset) differing more than once
    seen = {}
    for c in clusters:
        for d in c["diffs"]:
            k = (d["handle"], d["offset"])
            seen.setdefault(k, []).append(c["event"])
    candidates = [{"handle": h, "offset": o, "events": sorted(set(v)),
                   "repeat_count": len(set(v)),
                   "confidence": CONF_CAP if len(set(v)) > 1 else "LOW"}
                  for (h, o), v in sorted(seen.items())]
    doc = {"packets_used": len(rows), "events": len(clusters),
           "cadence_per_handle": cadence, "clusters": clusters,
           "candidate_changes": candidates,
           "rule": "tool caps at CANDIDATE; PROVEN needs human confirmation"}
    if out:
        d = os.path.dirname(out)
        if d:
            os.makedirs(d, exist_ok=True)
        json.dump(doc, open(out, "w"), indent=1, default=str)
    if "--quiet" not in a:
        print("packets=%d events=%d" % (len(rows), len(clusters)))
        for h, c in sorted(cadence.items()):
            print("  handle %-12s n=%-4d median_gap=%.2fs" % (h, c["n"], c["median_gap_s"]))
        for cd in candidates:
            print("  %s off=%s repeats=%d %s events=%s" % (
                cd["handle"], cd["offset"], cd["repeat_count"],
                cd["confidence"], "|".join(cd["events"][:4])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
