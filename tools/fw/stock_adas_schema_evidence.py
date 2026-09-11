#!/usr/bin/env python3
"""Gate A — firmware-grounded stock ADAS schema evidence (V2 review F0).

Searches the two ORIGINAL vendor upgrade images (EN golden + VI donor) for every
safety-critical string normalized by StockADASProvider, without trusting prior
reports. Pure Python, no binutils needed.

Method:
  - read_upgrade() from carve_upgrade.py (handles .tar or raw .bin)
  - byte-exact search for each schema token in the full upgrade image
  - record count + first offsets + EN/VI presence
  - classify per docs/reviews/..._V2.md Gate A:
      CONFIRMED(companion) : distinctive token present in BOTH images
      RAW-ONLY             : field bytes present but semantics unproven -> preserve raw
      UNKNOWN              : meaning/unit/enum/transport not provable by string presence

Outputs:
  docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json
  (markdown companion: docs/reverse/STOCK_ADAS_SCHEMA_V2.md references this JSON)

Usage:
  python3 tools/fw/stock_adas_schema_evidence.py -o docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from carve_upgrade import read_upgrade

EN_DEFAULT = Path("firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar")
VI_DEFAULT = Path("firmware/original/V2023.09.20.1_C2M_U_FR_WIFI_VI.tar")

# token -> (group, classification_if_present_in_both, note)
TOKENS: dict[str, tuple[str, str, str]] = {
    # libflow topics / inner keys (distinctive)
    "vehicleWarning": ("adas.topic-key", "CONFIRMED", "inner key for topic vehicle"),
    "vehicleMeasure": ("adas.topic-key", "CONFIRMED", "inner key for topic vehicle"),
    "pedestrians": ("adas.topic-key", "CONFIRMED", "inner key for topic ped"),
    "laneWarningRes": ("adas.topic-key", "CONFIRMED", "inner key for topic lane"),
    "AdasScreenService": ("adas.service", "CONFIRMED", "ScreenService name"),
    "screen_export_addr": ("adas.service", "CONFIRMED", "flag name"),
    "screen_export_port": ("adas.service", "CONFIRMED", "flag name"),
    "26012": ("adas.service", "CONFIRMED", "default port digits; weak alone, strong with neighbours"),
    "minieye-websocket": ("cardv.ws", "CONFIRMED", "cardv subprotocol"),
    "raw_adas": ("cardv.ringbuf", "CONFIRMED", "ringbuf endpoint"),
    "fortest": ("cardv.ringbuf", "CONFIRMED", "ringbuf companion string"),
    # vehicleWarning detail fields -> RAW-ONLY semantics
    "warning_level": ("adas.vehicleWarning", "RAW-ONLY", "generic level; must NOT drive FCW alone"),
    "headway_warning": ("adas.vehicleWarning", "RAW-ONLY", "headway class; keep raw"),
    "vb_warning": ("adas.vehicleWarning", "RAW-ONLY", "unknown VB class; keep raw"),
    "sag_warning": ("adas.vehicleWarning", "RAW-ONLY", "unknown SAG class; keep raw"),
    "headway": ("adas.vehicleWarning", "RAW-ONLY", "float; unit unverified"),
    "fcw": ("adas.vehicleWarning", "RAW-ONLY", "explicit FCW field; only proven FCW driver"),
    # vehicleMeasure detail fields
    "vehicle_class": ("adas.vehicleMeasure", "RAW-ONLY", "enum unverified"),
    "vehicle_width": ("adas.vehicleMeasure", "RAW-ONLY", "unit unverified"),
    "longitude_dist": ("adas.vehicleMeasure", "RAW-ONLY", "vendor spelling; unit/sign unverified"),
    "lateral_dist": ("adas.vehicleMeasure", "RAW-ONLY", "unit/sign unverified"),
    "is_crucial": ("adas.vehicleMeasure", "RAW-ONLY", "stock lead marker; only trusted lead signal"),
    "is_second_crucial": ("adas.vehicleMeasure", "RAW-ONLY", "secondary marker"),
    # ped detail fields
    "world_x": ("adas.ped", "RAW-ONLY", "coords frame unverified"),
    "world_y": ("adas.ped", "RAW-ONLY", "coords frame unverified"),
    "is_key": ("adas.ped", "RAW-ONLY", "selection flag; must NOT drive PCW"),
    "is_danger": ("adas.ped", "RAW-ONLY", "danger flag; sole PCW driver pending runtime proof"),
    "ttc_m": ("adas.ped", "RAW-ONLY", "unit unverified"),
    "have_bike": ("adas.ped", "RAW-ONLY", "attribute flag"),
    "pedWarning": ("adas.ped", "RAW-ONLY", "separate warning path; do not conflate"),
    "pcw_on": ("adas.ped", "RAW-ONLY", "explicit PCW-related token if present"),
    "ped_on": ("adas.ped", "RAW-ONLY", "explicit ped token if present"),
    # lane detail fields
    "lanelines": ("adas.lane", "RAW-ONLY", "array"),
    "ldw_info": ("adas.lane", "RAW-ONLY", "wrapper"),
    "deviate_state": ("adas.lane", "RAW-ONLY", "enum unverified; sole LDW driver pending proof"),
    "turn_radius": ("adas.lane", "RAW-ONLY", "unit unverified"),
    "turn_frequently": ("adas.lane", "RAW-ONLY", "bool"),
    "bird_view_poly_coeff": ("adas.lane", "RAW-ONLY", "encoding unverified"),
    "ScreenWarningRes": ("adas.lane", "RAW-ONLY", "serializer type name"),
    # TSR / audio / screen routing
    "ScreenAudioMsg": ("adas.screen-audio", "RAW-ONLY", "audio routing; presence only"),
    "SpeedLimit": ("adas.tsr", "RAW-ONLY", "TSR-related; enablement NOT proven by presence"),
    "speed_limit": ("adas.tsr", "RAW-ONLY", "TSR-related variant"),
    "SpeedLimitReporter": ("adas.tsr", "RAW-ONLY", "reporter symbol if present"),
    "traffic_light": ("adas.tsr", "RAW-ONLY", "TL-related"),
    # cardv JSON uuids
    "GPSLevel": ("cardv.json", "CONFIRMED", "uuid template"),
    "GPSSpeed": ("cardv.json", "CONFIRMED", "VI-added uuid; EN presence not required"),
    "DispBrightSet": ("cardv.json", "CONFIRMED", "harmless L2 class"),
    "StorageStatus": ("cardv.json", "CONFIRMED", "harmless L2 class"),
    "ClientConn": ("cardv.json", "CONFIRMED", "harmless L2 class"),
    "ScreenModeSet": ("cardv.json", "CONFIRMED", "harmless L2 class"),
    "AdasStatus": ("cardv.json", "CONFIRMED", "status; semantic DENY at L2"),
    "HeavyCalibStatus": ("cardv.json", "CONFIRMED", "status"),
    "RecordVoice": ("cardv.json", "CONFIRMED", "audio; DENY at L2"),
    "SendGPSSpeedToScreen": ("cardv.screen", "CONFIRMED", "VI-only symbol; GPS refactor marker"),
    "SendGPSInfoToScreen": ("cardv.screen", "CONFIRMED", "screen sender"),
    "SendADASInfoToScreen": ("cardv.screen", "CONFIRMED", "screen sender"),
    # transport markers
    "sdk_use_msgpack": ("transport", "CONFIRMED", "msgpack mode flag"),
    "Upgrade: websocket": ("transport", "RAW-ONLY", "may appear as 'Upgrade' + 'websocket' separately"),
}

MAX_OFFSETS = 8


def find_all(data: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        i = data.find(needle, start)
        if i < 0:
            return out
        out.append(i)
        start = i + 1
        if len(out) > 65536:
            return out


def scan_image(path: Path) -> tuple[bytes, dict]:
    data, meta = read_upgrade(path)
    return data, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", type=Path, default=EN_DEFAULT)
    ap.add_argument("--vi", type=Path, default=VI_DEFAULT)
    ap.add_argument("-o", "--output", type=Path,
                    default=Path("docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json"))
    args = ap.parse_args()

    en_data, en_meta = scan_image(args.en)
    vi_data, vi_meta = scan_image(args.vi)

    rows: list[dict] = []
    for token, (group, cls, note) in TOKENS.items():
        nb = token.encode()
        en_offs = find_all(en_data, nb)
        vi_offs = find_all(vi_data, nb)
        en_present = bool(en_offs)
        vi_present = bool(vi_offs)
        if en_present and vi_present:
            verdict = cls
        elif en_present or vi_present:
            verdict = cls + "-SINGLE-IMAGE"
        else:
            verdict = "ABSENT"
        rows.append({
            "token": token,
            "group": group,
            "note": note,
            "classification": verdict,
            "en": {"present": en_present, "count": len(en_offs),
                   "first_offsets_hex": [hex(o) for o in en_offs[:MAX_OFFSETS]]},
            "vi": {"present": vi_present, "count": len(vi_offs),
                   "first_offsets_hex": [hex(o) for o in vi_offs[:MAX_OFFSETS]]},
        })

    doc = {
        "method": "byte-exact search over full upgrade images (tar->SigmastarUpgradeSD bin); "
                  "offsets are upgrade-image offsets, not runtime addresses. "
                  "String presence proves the token ships in stock firmware; it does NOT prove "
                  "units/enums/routing/enablement. See STOCK_ADAS_SCHEMA_V2.md for semantic verdicts.",
        "en": {"source": en_meta["source"], "source_sha256": en_meta["source_sha256"],
               "inner_sha256": en_meta.get("inner_sha256"), "inner_size": en_meta.get("inner_size")},
        "vi": {"source": vi_meta["source"], "source_sha256": vi_meta["source_sha256"],
               "inner_sha256": vi_meta.get("inner_sha256"), "inner_size": vi_meta.get("inner_size")},
        "tokens": rows,
        "semantic_unknowns": [
            "unit/sign of longitude_dist/lateral_dist/ttc/headway/world_x/world_y/turn_radius",
            "enum meanings of warning_level/vehicle_class/label/type/deviate_state",
            "VB/SAG warning classes",
            "is_key vs is_danger PCW semantics (pending runtime event correlation)",
            "TSR enablement and speed-limit output routing",
            "ScreenWarningRes vs ScreenAudioMsg routing",
            "physical M4 transport interface",
            "libflow WebSocket URL path and AdasScreenService source string",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    n_both = sum(1 for r in rows if r["en"]["present"] and r["vi"]["present"])
    n_single = sum(1 for r in rows if r["en"]["present"] ^ r["vi"]["present"])
    n_absent = sum(1 for r in rows if not r["en"]["present"] and not r["vi"]["present"])
    print(f"tokens={len(rows)} both={n_both} single={n_single} absent={n_absent}")
    for r in rows:
        flag = "OK " if r["en"]["present"] and r["vi"]["present"] else ("ONE" if r["en"]["present"] or r["vi"]["present"] else "---")
        print(f"{flag} {r['token']:22s} ENx{r['en']['count']:<6d} VIx{r['vi']['count']:<6d} {r['classification']}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
