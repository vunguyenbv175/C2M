#!/usr/bin/env python3
"""P1 evidence: direct string/ELF search over the LZO-extracted stock adas ELFs.

Requires: build/fw_bin_{en,vi}/adas (see UBIFS Extraction doc for LZO route).
Outputs: docs/reverse/EVIDENCE_ADAS_STRINGS.json
Checks: SHA-256 vs canonical expected hashes before scanning.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

EXPECTED = {
    "en": "0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043",
    "vi": "997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1",
}

TOKENS = [
    # ScreenService / libflow routing
    "AdasScreenService", "ScreenService", "screen_export_addr", "screen_export_port",
    "LibflowServer", "libflow", "subscribe", "unsubscribe", "26012",
    "vehicle", "ped", "lane", "frame_id",
    "vehicleWarning", "vehicleMeasure", "pedestrians", "laneWarningRes",
    # vehicleWarning fields
    "vehicle_id", "headway", "warning_level", "fcw", "headway_warning",
    "vb_warning", "sag_warning",
    # vehicleMeasure fields
    "vehicle_class", "vehicle_width", "longitude_dist", "lateral_dist",
    "ttc", "is_crucial", "is_second_crucial",
    # ped fields
    "world_x", "world_y", "is_key", "is_danger", "ttc_m", "have_bike",
    "pedWarning", "ped_on", "pcw_on",
    # lane fields
    "lanelines", "ldw_info", "deviate_state", "turn_radius", "turn_frequently",
    "bird_view_poly_coeff", "ScreenWarningRes", "ScreenAudioMsg",
    # producer/consumer symbols (DEBUG_MEMORY §4.4/§13 + M4 doc)
    "VehicleRun", "ReadVehicle", "ReadPed", "LaneRun",
    "C1VehicleWarning", "C1VehicleMeasureRes", "C1PedRes",
    "TsrProcess", "ReadTsr", "TsrMsg", "TsrRes", "TsrTraceRes", "TsrWarning",
    "SpeedLimitReport", "SpeedLimitReporter", "SetTsrResult",
    # package/config
    "model_root_dir", "switch_file", "adas_de.flag", "FLAGS_m0", "sdk_use_msgpack",
    "raw_adas", "fortest",
]


def find_all(data: bytes, needle: bytes, cap: int = 10) -> list[int]:
    out, start = [], 0
    while len(out) < cap:
        i = data.find(needle, start)
        if i < 0:
            break
        out.append(i)
        start = i + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", type=Path, default=Path("build/fw_bin_en/adas"))
    ap.add_argument("--vi", type=Path, default=Path("build/fw_bin_vi/adas"))
    ap.add_argument("-o", "--output", type=Path,
                    default=Path("docs/reverse/EVIDENCE_ADAS_STRINGS.json"))
    args = ap.parse_args()
    en, vi = args.en.read_bytes(), args.vi.read_bytes()
    en_sha, vi_sha = hashlib.sha256(en).hexdigest(), hashlib.sha256(vi).hexdigest()
    assert en_sha == EXPECTED["en"], f"EN hash mismatch {en_sha}"
    assert vi_sha == EXPECTED["vi"], f"VI hash mismatch {vi_sha}"
    print(f"EN adas {len(en)} {en_sha[:16]}.. OK")
    print(f"VI adas {len(vi)} {vi_sha[:16]}.. OK")

    rows = []
    for tok in TOKENS:
        eo = find_all(en, tok.encode())
        vo = find_all(vi, tok.encode())
        rows.append({"token": tok, "en_count": en.count(tok.encode()),
                     "en_offsets_hex": [hex(o) for o in eo],
                     "vi_count": vi.count(tok.encode()),
                     "vi_offsets_hex": [hex(o) for o in vo],
                     "verdict": "BOTH" if eo and vo else ("EN-ONLY" if eo else ("VI-ONLY" if vo else "ABSENT"))})
    both = sum(1 for r in rows if r["verdict"] == "BOTH")
    print(f"tokens={len(rows)} both={both}")
    for r in rows:
        print(f"{r['verdict']:8s} ENx{r['en_count']:<4d} VIx{r['vi_count']:<4d} {r['token']}")
    args.output.write_text(json.dumps(
        {"method": "byte-exact search in LZO-extracted adas ELFs (hash-verified); offsets are ELF file offsets.",
         "en": {"size": len(en), "sha256": en_sha}, "vi": {"size": len(vi), "sha256": vi_sha},
         "tokens": rows}, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
