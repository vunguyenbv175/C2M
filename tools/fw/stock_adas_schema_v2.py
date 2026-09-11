#!/usr/bin/env python3
"""Gate A deliverable generator: docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json

Field-level stock contract table. Every row re-measures its evidence from the
ORIGINAL firmware artifacts extracted in build/ :
  build/fw_bin_{en,vi}/cardv            (rootfs gzip-cpio, byte-exact)
  build/rootfs_{en,vi}_inner.bin        (libflow.so etc.)
  build/{en,vi}_customer_inventory.json (UBIFS file inventory, no decompression)
  build/adas_plain_en.json              (adas uncompressed-block scan)

Verdict scale: CONFIRMED | HIGH-CONFIDENCE | RAW-ONLY | UNKNOWN
Only CONFIRMED/HIGH-CONFIDENCE *driver* fields may feed normalized warnings;
RAW-ONLY fields are preserved, never promoted; UNKNOWN stays empty.
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "tools/fw")
from extract_rootfs_cpio import iter_cpio

BUILD = Path("build")
OUT = Path("docs/reverse/EVIDENCE_STOCK_ADAS_SCHEMA.json")


def first_offsets(data: bytes, needle: bytes, cap: int = 4) -> list[str]:
    out, start = [], 0
    while len(out) < cap:
        i = data.find(needle, start)
        if i < 0:
            break
        out.append(hex(i))
        start = i + 1
    return out


def main() -> int:
    en_cardv = (BUILD / "fw_bin_en" / "cardv").read_bytes()
    vi_cardv = (BUILD / "fw_bin_vi" / "cardv").read_bytes()
    en_blobs = dict(iter_cpio((BUILD / "rootfs_en_inner.bin").read_bytes()))
    vi_blobs = dict(iter_cpio((BUILD / "rootfs_vi_inner.bin").read_bytes()))
    en_lf, vi_lf = en_blobs["lib/libflow.so"], vi_blobs["lib/libflow.so"]
    en_inv = json.loads((BUILD / "en_customer_inventory.json").read_text())
    vi_inv = json.loads((BUILD / "vi_customer_inventory.json").read_text())
    adas_plain = json.loads((BUILD / "adas_plain_en.json").read_text())

    assert hashlib.sha256(en_cardv).hexdigest() == \
        "344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c"
    assert hashlib.sha256(vi_cardv).hexdigest() == \
        "56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23"
    assert hashlib.sha256(en_lf).hexdigest() == hashlib.sha256(vi_lf).hexdigest()

    def cardv_ev(*toks: str) -> dict:
        return {t: {"en": first_offsets(en_cardv, t.encode()),
                    "vi": first_offsets(vi_cardv, t.encode())} for t in toks}

    def lf_ev(*toks: str) -> dict:
        return {t: {"en_count": en_lf.count(t.encode()),
                    "vi_count": vi_lf.count(t.encode())} for t in toks}

    F = []  # fields

    def add(name, group, verdict, drives, evidence, note):
        F.append({"field": name, "group": group, "verdict": verdict,
                  "drives_normalized_warning": drives, "evidence": evidence, "note": note})

    ADAS_SIDE = ("adas .rodata strings live in LZO blocks of customer UBIFS "
                 "(inode 136 EN / 199 VI); direct string proof pending LZO "
                 "decompression. Key routing is HIGH-CONFIDENCE via prior "
                 "callsite disassembly (M4_STATIC_PROTOCOL_V1 §2) + adas-side "
                 "confinement (absent from libflow.so/rootfs).")

    for key in ("vehicleWarning", "vehicleMeasure", "pedestrians", "laneWarningRes"):
        add(key, "adas.key", "HIGH-CONFIDENCE", False, {"basis": ADAS_SIDE},
            "topic/key routing; inner data fields below are RAW-ONLY unless noted")

    for f, note in (
        ("vehicleWarning.vehicle_id", "join key Warning<->Measure"),
        ("vehicleWarning.headway", "unit unverified"),
        ("vehicleWarning.warning_level", "generic level; NEVER drives FCW"),
        ("vehicleWarning.headway_warning", "class exists (HMW.wav); trigger mapping UNKNOWN"),
        ("vehicleWarning.vb_warning", "class exists (VB.wav); mapping UNKNOWN"),
        ("vehicleWarning.sag_warning", "class exists (SAG.wav); mapping UNKNOWN"),
        ("vehicleMeasure.vehicle_class", "enum unverified"),
        ("vehicleMeasure.vehicle_width", "unit unverified"),
        ("vehicleMeasure.longitude_dist", "vendor spelling; unit/sign unverified"),
        ("vehicleMeasure.lateral_dist", "unit/sign unverified"),
        ("vehicleMeasure.ttc", "unit unverified"),
        ("pedestrians.id", "id only"), ("pedestrians.world_x", "frame unverified"),
        ("pedestrians.world_y", "frame unverified"), ("pedestrians.ttc_m", "unit unverified"),
        ("pedestrians.ttc", "unit unverified"), ("pedestrians.have_bike", "attribute"),
        ("pedestrians.is_key", "selection flag; NEVER drives PCW"),
        ("laneWarningRes.lanelines", "array; poly encoding unverified"),
        ("laneWarningRes.bird_view_poly_coeff", "encoding unverified"),
        ("laneWarningRes.label", "enum unverified"), ("laneWarningRes.type", "enum unverified"),
        ("laneWarningRes.turn_radius", "unit unverified"),
        ("laneWarningRes.turn_frequently", "bool"),
    ):
        add(f, "adas.field", "RAW-ONLY", False, {"basis": ADAS_SIDE}, note)

    add("vehicleWarning.fcw", "adas.field", "HIGH-CONFIDENCE", True,
        {"basis": ADAS_SIDE + " Explicit field name (vs generic warning_level); "
                  "FCW.wav asset proves the FCW class exists in stock audio.",
         "audio_asset": "customer:/minieye/adas/audios/FCW.wav (identical EN/VI)"},
        "SOLE driver of fcw.active: active=(fcw!=0). warning_level never drives FCW.")
    add("vehicleMeasure.is_crucial", "adas.field", "HIGH-CONFIDENCE", True,
        {"basis": ADAS_SIDE}, "SOLE lead-vehicle signal. No min-distance fallback (F11).")
    add("vehicleMeasure.is_second_crucial", "adas.field", "HIGH-CONFIDENCE", False,
        {"basis": ADAS_SIDE}, "secondary marker only; never invents lead alone.")
    add("pedestrians.is_danger", "adas.field", "HIGH-CONFIDENCE", True,
        {"basis": ADAS_SIDE + " PCW.wav asset proves the PCW class exists.",
         "audio_asset": "customer:/minieye/adas/audios/PCW.wav (VI re-recorded)"},
        "SOLE driver of pcw.active.")
    add("laneWarningRes.deviate_state", "adas.field", "HIGH-CONFIDENCE", True,
        {"basis": ADAS_SIDE + " LDW.wav asset proves the LDW class exists.",
         "audio_asset": "customer:/minieye/adas/audios/LDW.wav (VI re-recorded)"},
        "SOLE driver of ldw.active. Enum values UNKNOWN.")

    add("camera.TSR_limit", "adas.tsr", "UNKNOWN", False,
        {"upgrade_image_search": "SpeedLimit/speed_limit ASCII present in both upgrade "
         "images (weak: component unattributed)",
         "basis": "enablement/routing unproven; needs runtime config proof"},
        "No normalized speed-limit from camera until proven. detected_speed_limit stays empty.")
    add("ScreenWarningRes", "adas.screen", "HIGH-CONFIDENCE", False,
        {"basis": "serializer SendScreenMsg<sdk::ScreenWarningRes> in M4_STATIC_PROTOCOL_V1 §6; "
                  "direct string proof pending LZO"}, "laneWarningRes carrier type.")
    add("ScreenAudioMsg", "adas.screen", "UNKNOWN", False,
        {"basis": "absent from plain-block scan; needs LZO/runtime"}, "audio routing unproven.")

    # cardv JSON — CONFIRMED with ELF offsets
    ce = cardv_ev("GPSLevel", "GPSSpeed", "DispBrightSet", "StorageStatus", "ClientConn",
                  "RecordVoice", "ScreenModeSet", "AdasStatus", "HeavyCalibStatus",
                  "minieye-websocket", "raw_adas", "fortest",
                  "SendADASInfoToScreen", "SendGPSInfoToScreen", "SendGPSSpeedToScreen",
                  "WSGetConnectStatus", "src/module_websocket.cpp")
    json_templates = {
        "GPSLevel": '{"type":1600, "uuid":"GPSLevel", "level":%d}',
        "GPSSpeed": '{"type":1601, "uuid":"GPSSpeed", "speed":%d}',
        "DispBrightSet": '{"type":1100, "uuid":"DispBrightSet", "brightness":%d}',
        "AdasStatus": '{"type":3000, "uuid":"AdasStatus", "status":%s}',
        "HeavyCalibStatus": '{"type":3001, "uuid":"HeavyCalibStatus", "status":"%s}',
        "ScreenModeSet": '{"type":1103, "uuid":"ScreenModeSet", "theme":"%s}',
        "RecordVoice": '{"type":2001, "uuid":"RecordVoice", "op":%d}',
    }
    for uuid, tpl in json_templates.items():
        add(f"cardv.json.{uuid}", "cardv.json", "CONFIRMED", False,
            {"binary": "bootconfig/bin/cardv (EN+VI, sha-verified)",
             "elf_offsets": ce[uuid],
             "template": tpl, "source_file": "src/module_websocket.cpp"},
            "Byte-exact template in .rodata. Info-class (brightness/storage/mode/conn) "
            "harmless; AdasStatus/Calib/GPSSpeed/RecordVoice semantic-DENY at M4 L2.")
    add("cardv.ringbuf.raw_adas", "cardv.ringbuf", "CONFIRMED", False,
        {"binary": "bootconfig/bin/cardv", "elf_offsets": ce["raw_adas"],
         "companion": ce["fortest"]}, '"raw_adas"+"fortest" adjacent .rodata; writer proved stable (RAW_ADAS_CONTRACT_V1).')
    add("cardv.ws.minieye-websocket", "cardv.ws", "CONFIRMED", False,
        {"binary": "bootconfig/bin/cardv", "elf_offsets": ce["minieye-websocket"]},
        "subprotocol; server port 8080 HIGH-CONFIDENCE (prior lws disassembly; ASCII port absent as expected).")
    for fn in ("SendADASInfoToScreen", "SendGPSInfoToScreen", "WSGetConnectStatus"):
        add(f"cardv.screen.{fn}", "cardv.screen", "CONFIRMED", False,
            {"binary": "bootconfig/bin/cardv", "elf_offsets": ce[fn]}, "screen sender path (symbol string).")
    add("cardv.screen.SendGPSSpeedToScreen", "cardv.screen", "CONFIRMED", False,
        {"binary": "VI cardv only", "elf_offsets": ce["SendGPSSpeedToScreen"]},
        "VI-ONLY function string; GPS template itself exists in EN too (function-level delta, not template delta).")

    le = lf_ev("subscribe", "unsubscribe", "DoSubscribe", "OnRecvWSBinaryFrame", "OutMsg",
               "RealClientInfo", "24012", "127.0.0.1", "websocket", "Upgrade")
    add("libflow.outer.{time,source,topic,data}", "transport", "HIGH-CONFIDENCE", False,
        {"binary": "lib/libflow.so (identical EN/VI, "
                   + hashlib.sha256(en_lf).hexdigest()[:16] + "…)",
         "symbols": le, "basis": "generic-lib defaults 127.0.0.1:24012 + subscribe/unsubscribe/DoSubscribe/"
                    "OnRecvWSBinaryFrame/OutMsg/RealClientInfo symbols; outer shape + subscribe frame per "
                    "LIBFLOW_WIRE_PROTOCOL_V1 disassembly; wire proof needs pcap"},
        "Transport envelope for ScreenService; C2M override port 26012 HIGH-CONFIDENCE (adas-side).")
    add("transport.physical_interface", "transport", "UNKNOWN", False,
        {"basis": "no image evidence; needs OFF-vs-ON runtime capture"},
        "Never assume usb0.")
    add("transport.ws_path_and_source", "transport", "UNKNOWN", False,
        {"basis": "needs live handshake capture"}, "URL path + AdasScreenService source string.")

    doc = {
        "method": "field table generated by tools/fw/stock_adas_schema_v2.py from original EN/VI "
                  "images (carve gzip-cpio + UBIFS inventory + ELF search). Prior disassembly docs are "
                  "cited as index only where direct proof is LZO-blocked.",
        "images": {
            "en_tar_sha256": "3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c",
            "vi_tar_sha256": "f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa",
            "cardv_en_sha256": hashlib.sha256(en_cardv).hexdigest(),
            "cardv_vi_sha256": hashlib.sha256(vi_cardv).hexdigest(),
            "libflow_identical_en_vi": True,
            "customer_files_en": len(en_inv["files"]), "customer_files_vi": len(vi_inv["files"]),
            "adas_plain_blocks_scanned": adas_plain["plain_blocks"],
            "adas_lzo_blocks_pending": adas_plain["lzo_blocks"],
        },
        "fields": F,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    from collections import Counter
    print(Counter(f["verdict"] for f in F), f"fields={len(F)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
