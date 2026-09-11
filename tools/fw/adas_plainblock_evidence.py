#!/usr/bin/env python3
"""Gate A adas evidence WITHOUT LZO: scan the *uncompressed* UBIFS data blocks of
the stock adas inode for ScreenService/libflow/TSR tokens.

For each token: which 4KB blocks contain it (block index + ELF-relative approx).
Caveat: tokens spanning block boundaries or inside LZO blocks are missed; absence
here is NOT proof of absence from adas. Presence is strong proof the token ships
inside the stock adas file.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ubifs_extract_file import latest_data_blocks, latest_dentries, latest_inodes, path_index, scan_nodes

TOKENS = [
    "vehicleWarning", "vehicleMeasure", "pedestrians", "laneWarningRes",
    "vehicle", "ped", "lane", "frame_id",
    "AdasScreenService", "ScreenService", "screen_export",
    "LibflowServer", "libflow", "subscribe", "unsubscribe",
    "vehicle_id", "headway", "warning_level", "fcw", "headway_warning",
    "vb_warning", "sag_warning", "vehicle_class", "vehicle_width",
    "longitude_dist", "lateral_dist", "ttc", "is_crucial", "is_second_crucial",
    "world_x", "world_y", "is_key", "is_danger", "ttc_m", "have_bike",
    "lanelines", "ldw_info", "deviate_state", "turn_radius", "turn_frequently",
    "bird_view_poly_coeff", "ScreenWarningRes", "ScreenAudioMsg",
    "VehicleRun", "ReadVehicle", "ReadPed", "LaneRun",
    "C1VehicleWarning", "C1VehicleMeasureRes", "C1PedRes", "ScreenWarningRes",
    "SpeedLimit", "speed_limit", "TSR", "traffic", "model_root_dir",
    "switch_file", "adas_de.flag", "FLAGS_m0", "sdk_use_msgpack", "msgpack",
    "26012", "24012",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--target", default="/minieye/adas/adas")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--tag", default="EN")
    args = ap.parse_args()

    image = args.image.read_bytes()
    nodes = scan_nodes(image)
    entries = path_index(latest_dentries(nodes))
    ino = int(entries[args.target]["target"])
    meta = latest_inodes(nodes)[ino]
    blocks = latest_data_blocks(nodes, ino)
    plain = {b: r["payload"] for b, r in sorted(blocks.items()) if int(r["compression"]) == 0}
    lzo_blocks = sum(1 for r in blocks.values() if int(r["compression"]) == 1)
    print(f"{args.tag} adas inode={ino} size={meta['size']} blocks={len(blocks)} "
          f"plain={len(plain)} lzo={lzo_blocks}")

    rows = []
    for tok in TOKENS:
        nb = tok.encode()
        hits = [b for b, p in plain.items() if nb in p]
        # count occurrences within plain blocks
        total = sum(plain[b].count(nb) for b in hits)
        rows.append({"token": tok, "plain_block_hits": hits[:24],
                     "plain_block_count": len(hits), "plain_occurrences": total,
                     "verdict": "PRESENT-IN-PLAIN-BLOCKS" if hits else "NOT-IN-PLAIN-BLOCKS"})
        print(f"{'HIT ' if hits else 'miss'} {tok:22s} blocks={len(hits):<4d} occ={total:<4d} {hits[:8]}")

    doc = {"tag": args.tag, "target": args.target, "inode": ino, "size": meta["size"],
           "total_blocks": len(blocks), "plain_blocks": len(plain), "lzo_blocks": lzo_blocks,
           "caveat": "misses tokens hidden in LZO blocks or split across block edges; "
                     "hits prove the token ships in stock adas; misses prove nothing",
           "tokens": rows}
    if args.output:
        args.output.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
