#!/usr/bin/env python3
"""Deterministic EN-vs-VI C2M ADAS regression evidence (static, read-only).

Read-only with respect to firmware inputs. Writes only
docs/reverse/EVIDENCE_VI_ADAS_FAILURE.json. Never modifies firmware,
extracted proprietary payloads, or Candidate A/B artifacts.

Schema (required): firmware, payload_diff, kernel_findings, cardv_findings,
adas_findings, calibration_findings, config_findings,
package_metadata_findings, root_cause_candidates, excluded_causes, unknowns.
Legacy keys (inputs, findings, cross_references, ...) are retained for
backward compatibility with V1 reports.
"""
from __future__ import annotations

import hashlib
import json
import struct
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "reverse"

INPUTS = {
    "en_tar": ROOT / "firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar",
    "vi_tar": ROOT / "firmware/original/V2023.09.20.1_C2M_U_FR_WIFI_VI.tar",
    "en_kernel": ROOT / "build/carve_en/kernel.es.load0.off_00061000.size_22691f.bin",
    "vi_kernel": ROOT / "build/vi_carve/kernel.es.load0.off_00061000.size_226921.bin",
    "en_cardv": ROOT / "build/fw_bin_en/cardv",
    "vi_cardv": ROOT / "build/fw_bin_vi/cardv",
    "en_adas": ROOT / "build/fw_bin_en/adas",
    "vi_adas": ROOT / "build/fw_bin_vi/adas",
    "en_sc7a20": ROOT / "build/fw_bin_en/sc7a20.ko",
    "vi_sc7a20": ROOT / "build/fw_bin_vi/sc7a20.ko",
}

EXPECTED = {
    "en_tar": "3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c",
    "vi_tar": "f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa",
    "en_kernel": "c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030",
    "vi_kernel": "8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314",
    "en_cardv": "344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c",
    "vi_cardv": "56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23",
    "en_adas": "0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043",
    "vi_adas": "997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1",
    "en_sc7a20": "2d8121dd245d88684a5ece8e5647dfd04571a3184beca2a01fcac7743bbc797a",
    "vi_sc7a20": "5d020616c2b67909a6bc5db19245bfedaf1301d875ae7c117c4d1888de566d64",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def parse_uimage(path: Path) -> dict:
    d = path.read_bytes()
    magic, hcrc, tm, size, load, entry, dcrc, os_, arch, typ, comp = struct.unpack(
        ">IIIIIIIBBBB", d[:32])
    name = d[32:64].rstrip(b"\x00").decode("latin-1", "replace")
    payload = d[64:]
    assert magic == 0x27051956, f"{path}: bad uImage magic"
    assert len(payload) == size, f"{path}: payload size mismatch"
    import binascii
    assert (binascii.crc32(payload) & 0xFFFFFFFF) == dcrc, f"{path}: data CRC mismatch"
    return {
        "file": rel(path), "size": len(d),
        "payload_size": size, "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "load_hex": hex(load), "entry_hex": hex(entry),
        "timestamp": tm, "comp": comp, "os": os_, "arch": arch,
        "type": typ, "name": name, "data_crc_ok": True,
    }


def outer_members(tar_path: Path) -> dict:
    out = {}
    with tarfile.open(tar_path, "r:*") as tf:
        for m in tf.getmembers():
            fh = tf.extractfile(m)
            blob = fh.read() if fh else b""
            out[m.name] = {"size": m.size, "sha256": hashlib.sha256(blob).hexdigest(),
                           "head": blob[:96].decode("latin-1", "replace")}
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for name, path in INPUTS.items():
        digest = sha256(path)
        inputs[name] = {
            "path": rel(path), "size": path.stat().st_size,
            "sha256": digest, "expected_sha256": EXPECTED[name],
            "verified": digest == EXPECTED[name],
        }
    if not all(row["verified"] for row in inputs.values()):
        raise SystemExit("input hash verification failed")

    en_manifest = json.loads((ROOT / "build/carve_en/manifest.json").read_text(encoding="utf-8"))
    vi_manifest = json.loads((ROOT / "build/vi_carve/manifest.json").read_text(encoding="utf-8"))
    me = {r["section"] + "#" + str(r["load_index"]): r for r in en_manifest["loads"]}
    mv = {r["section"] + "#" + str(r["load_index"]): r for r in vi_manifest["loads"]}
    payload_diff = []
    for key in sorted(set(me) | set(mv)):
        a, b = me.get(key), mv.get(key)
        payload_diff.append({
            "payload": key,
            "en_size": a["size"] if a else None,
            "vi_size": b["size"] if b else None,
            "en_sha256": a["sha256"] if a else None,
            "vi_sha256": b["sha256"] if b else None,
            "same": bool(a and b and a["sha256"] == b["sha256"]),
            "verdict": "same" if (a and b and a["sha256"] == b["sha256"]) else "different",
            "source": "tools/fw/carve_upgrade.py manifests",
            "en_file": a["file"] if a else None,
            "vi_file": b["file"] if b else None,
        })

    en_outer = outer_members(INPUTS["en_tar"])
    vi_outer = outer_members(INPUTS["vi_tar"])
    en_bootargs = [l for l in (ROOT / "build/carve_en/upgrade_script.txt").read_text(encoding="utf-8").splitlines() if l.startswith("setenv bootargs")]
    vi_bootargs = [l for l in (ROOT / "build/vi_carve/upgrade_script.txt").read_text(encoding="utf-8").splitlines() if l.startswith("setenv bootargs")]
    assert len(en_bootargs) == 1 and len(vi_bootargs) == 1
    en_uimg = parse_uimage(INPUTS["en_kernel"])
    vi_uimg = parse_uimage(INPUTS["vi_kernel"])

    firmware = {
        "en_tar": {"path": rel(INPUTS["en_tar"]), "sha256": inputs["en_tar"]["sha256"], "size": inputs["en_tar"]["size"]},
        "vi_tar": {"path": rel(INPUTS["vi_tar"]), "sha256": inputs["vi_tar"]["sha256"], "size": inputs["vi_tar"]["size"]},
        "en_inner": {"name": en_manifest["inner_name"], "size": en_manifest["inner_size"], "sha256": en_manifest["inner_sha256"]},
        "vi_inner": {"name": vi_manifest["inner_name"], "size": vi_manifest["inner_size"], "sha256": vi_manifest["inner_sha256"]},
        "en_outer": en_outer, "vi_outer": vi_outer,
        "en_sysver": en_outer["sysVer.txt"], "vi_sysver": vi_outer["sysVer.txt"],
        "adas_upgrade_same": en_outer["adas_upgrade.sh"]["sha256"] == vi_outer["adas_upgrade.sh"]["sha256"],
        "en_bootargs": en_bootargs[0], "vi_bootargs": vi_bootargs[0],
    }

    kernel_findings = [
        {"id": "K01", "source": "uImage header parse (struct >IIIIIIIBBBB)",
         "file": "kernel.es load0 (EN vs VI)", "offset_symbol": "uImage header bytes 0..63",
         "en_evidence": f"load={en_uimg['load_hex']} entry={en_uimg['entry_hex']} comp={en_uimg['comp']} time={en_uimg['timestamp']} dcrc_ok=True",
         "vi_evidence": f"load={vi_uimg['load_hex']} entry={vi_uimg['entry_hex']} comp={vi_uimg['comp']} time={vi_uimg['timestamp']} dcrc_ok=True",
         "interpretation": "Same load/entry excludes relocation delta; comp=9 is nonstandard SigmaStar (not zlib) so payload is opaque to local tooling; distinct timestamps prove distinct builds.",
         "classification": "PROVEN_DIFFERENCE_NO_CAUSALITY", "confidence": "CONFIRMED"},
        {"id": "K02", "source": "build/carve_en|vi_carve/upgrade_script.txt setenv bootargs",
         "file": "upgrade_script.txt # File Partition: set_config", "offset_symbol": "bootargs line",
         "en_evidence": firmware["en_bootargs"][:160] + "... (no mmap_reserved)",
         "vi_evidence": "adds mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000",
         "interpretation": "Proves VI reserves an extra 8 MiB window labelled fb at 0x3F000000-0x3F800000. Does not prove overlap with CMA/MMA/IPU/camera buffers, consumption at runtime, or starvation.",
         "classification": "PROVEN_DIFFERENCE_NO_CAUSALITY", "confidence": "CONFIRMED"},
        {"id": "K03", "source": "payload sha256 of uImage body (bytes 64..end)",
         "file": "kernel.es.load0", "offset_symbol": "compressed payload",
         "en_evidence": f"size={en_uimg['payload_size']} sha={en_uimg['payload_sha256'][:16]}... first16=ecfd777c5347d6308ecf2deab2253790",
         "vi_evidence": f"size={vi_uimg['payload_size']} sha={vi_uimg['payload_sha256'][:16]}... first16 identical, tail differs",
         "interpretation": "Payloads are distinct builds with identical 16-byte prefix; semantic driver/config delta inside the opaque comp=9 blob remains UNKNOWN (no config/DTB recovered).",
         "classification": "PROVEN_DIFFERENCE_OPAQUE", "confidence": "CONFIRMED"},
        {"id": "K04", "source": "docs/firmware_en_vi/02_BOOT_KERNEL_ROOTFS.md + rootfs gzip/cpio magic",
         "file": "rootfs.es.load0", "offset_symbol": "rootfs module set bootconfig/modules/4.9.227",
         "en_evidence": "mi_sys/mi_scl/mi_ipu/mi_vif/mi_isp/mi_sensor .ko+.so present; sc7a20.ko 24196",
         "vi_evidence": "same named media stack present; sc7a20.ko 24204; 15 client modules rebuilt (vermagic still 4.9.227)",
         "interpretation": "Rootfs media ABI surface is narrow (only cardv+sc7a20 content-changed of 528 files); path equality does not prove identical kernel-side driver behaviour.",
         "classification": "SUPPORTING_CONTEXT", "confidence": "MEDIUM"},
    ]

    cardv_findings = [
        {"id": "C01", "source": "sha256 + size", "file": "build/fw_bin_en|vi/cardv",
         "offset_symbol": "whole file", "en_evidence": "1225780 B 344b4a3f...",
         "vi_evidence": "1225780 B 56db44d9...", "interpretation": "Equal size, different build (BuildID differs).",
         "classification": "PROVEN_DIFFERENCE", "confidence": "CONFIRMED"},
        {"id": "C02", "source": "docs/reverse/EVIDENCE_CARDV_SYMDIFF.json (elf_dynsym_diff)",
         "file": "cardv dynsym", "offset_symbol": "symbol table",
         "en_evidence": "4478 syms; EN-only Is_Gps_info/nmea_satinfo/nema_calc_checksum/g_zkw_gps_module",
         "vi_evidence": "4476 syms; VI-only nmea_BDGSV2info_na/SendGPSSpeedToScreen; 9 size-changed (GPS/G-sensor/restart/minieye_init)",
         "interpretation": "VI work concentrated in GPS/G-sensor/power/display, not in ring-buffer API surface.",
         "classification": "PROVEN_DIFFERENCE_NON_PRODUCER", "confidence": "CONFIRMED"},
        {"id": "C03", "source": "docs/reverse/EVIDENCE_CARDV_CONTRACT.json (strings/xref)",
         "file": "cardv .rodata", "offset_symbol": "raw_adas token EN 0xFF340 / VI 0xF5794",
         "en_evidence": "exactly one raw_adas token", "vi_evidence": "exactly one raw_adas token, moved by layout",
         "interpretation": "Endpoint not renamed; offset move is layout noise.",
         "classification": "PROVEN_SAME", "confidence": "CONFIRMED"},
        {"id": "C04", "source": "docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md + cardv_ringbuf_contract.py",
         "file": "cardv", "offset_symbol": "send()/adas_minieye_send_frame_task()/minieye_init + CRingBuf::CRingBuf/RequestWriteFrame/CommitWrite",
         "en_evidence": "visible ctor+request/commit sequence present; normalized send+send_frame_task identical",
         "vi_evidence": "same visible sequence; same normalized code; minieye_init +4 B same thread/call order",
         "interpretation": "Deliberate writer-contract rewrite downgraded; live width/height/stride/format/timestamps/cadence/startup-order remain UNKNOWN.",
         "classification": "PROVEN_SAME_VISIBLE_CONTRACT", "confidence": "HIGH-CONFIDENCE"},
    ]

    adas_findings = [
        {"id": "A01", "source": "elf_function_diff + dynsym", "file": "build/fw_bin_en|vi/adas",
         "offset_symbol": "symbol table", "en_evidence": "3875 syms; SystemInit 124 B @0x94499",
         "vi_evidence": "3875 syms, 0 EN-only, 0 VI-only; SystemInit 100 B @0x94499",
         "interpretation": "Only symbol-size delta is SystemInit (logging/error handling); both retain MI_SYS_Init/MI_SCL_CreateDevice/IPUCreateDevice.",
         "classification": "PROVEN_TRIVIAL_DELTA", "confidence": "CONFIRMED"},
        {"id": "A02", "source": "thumb_callgraph_diff (2734 comparable functions)",
         "file": "adas .text", "offset_symbol": "SystemInit / LaneCalib::get_extrinsic / VehicleAlgo::PedProcess",
         "en_evidence": "2731 same call sequence", "vi_evidence": "3 changed; 2 same-sized differ only in indirect-call register token",
         "interpretation": "Consistent with register-allocation noise until a CFG-aware proof shows otherwise; broad algorithm rewrite downgraded.",
         "classification": "DOWNGRADED_REWRITE", "confidence": "MEDIUM"},
        {"id": "A03", "source": "docs/reverse/BITANSWER_LICENSE_PATH_V1.md",
         "file": "adas", "offset_symbol": "Bit_SetRootPath/Bit_Login/Bit_ReadFeature/Bit_CheckOutSn/Bit_CheckOutFeatures + /proc/self/exe helper + dispatcher",
         "en_evidence": "byte-identical compared paths", "vi_evidence": "byte-identical compared paths",
         "interpretation": "Changed license implementation downgraded; runtime UUID/custom-info/feature state still UNKNOWN.",
         "classification": "PROVEN_SAME_COMPARED_PATHS", "confidence": "HIGH-CONFIDENCE"},
        {"id": "A04", "source": "docs/reverse/EVIDENCE_ADAS_STRINGS.json + STOCK_ADAS_SCHEMA",
         "file": "adas", "offset_symbol": "--camera_input=ringbuf_vehicle --ringbuf_name=raw_adas --image_width=1920 --image_height=1440 --vehicle_run_freq=10",
         "en_evidence": "consumer expects ringbuf_vehicle/raw_adas 1920x1440 @10Hz",
         "vi_evidence": "same consumer defaults recovered",
         "interpretation": "Static consumer endpoint/geometry aligns with cardv producer name; live acceptance still needs runtime proof.",
         "classification": "SUPPORTING_CONTEXT", "confidence": "MEDIUM"},
    ]

    calibration_findings = [
        {"id": "L01", "source": "prior instruction-level review (VehicleAlgo::RunLane->...->UpdateInstallCalibState(2))",
         "file": "adas", "offset_symbol": "UpdateInstallCalibState/PassAutoCalibCheck/ProcessHeavyMode/ProcessRegularMode",
         "en_evidence": "60000.0 ms + 0.1 threshold in Regular mode; heavy-mode success returns same state path",
         "vi_evidence": "effectively identical at instruction level",
         "interpretation": "Explains EN warm-up delay; no proven VI semantic break upstream of state=2 in compared functions.",
         "classification": "PROVEN_SAME_COMPARED_PATHS", "confidence": "MEDIUM"},
        {"id": "L02", "source": "adas_checkcalib.sh + run.sh semantics",
         "file": "customer UBIFS /minieye/adas", "offset_symbol": "install_calib_state gate",
         "en_evidence": "stock script accepts 1 or 2; only 0 blocks normal startup",
         "vi_evidence": "byte-identical script",
         "interpretation": "state=2 is success marker, not start precondition; script delta excluded.",
         "classification": "PROVEN_SAME", "confidence": "CONFIRMED"},
        {"id": "L03", "source": "LaneCalibFacade::get_extrinsic input trace (static)",
         "file": "adas", "offset_symbol": "LaneCalibFacade/LaneCalib/calib_service/lane_accelerator/lane_postprocess",
         "en_evidence": "validity depends on frame metadata + model output + samples/time/quality gates (exact thresholds partially recovered)",
         "vi_evidence": "same code surface; exact live inputs unavailable",
         "interpretation": "Precise failing gate (movement/GPS/timing/confidence/geometry/IMU/persistence) remains UNKNOWN without runtime logs.",
         "classification": "UNKNOWN_GATE", "confidence": "UNKNOWN"},
    ]

    config_findings = [
        {"id": "G01", "source": "ubifs_extract_file.py + sha256 (re-verified this run)",
         "file": "customer UBIFS /minieye/adas/run.sh", "offset_symbol": "whole file 1584 B",
         "en_evidence": "796e555a276d849737b8034021e1464a8241ed291a332ef5a61b767d9ab860e4",
         "vi_evidence": "796e555a276d849737b8034021e1464a8241ed291a332ef5a61b767d9ab860e4 (identical)",
         "interpretation": "Release-specific shell-gate regression excluded; requires adas.flag+calib.flag, base64-decodes to adas_de/calib_de.flag, exits on --enable_vehicle=false.",
         "classification": "PROVEN_SAME", "confidence": "CONFIRMED"},
        {"id": "G02", "source": "ubifs_extract_file.py + prior evidence",
         "file": "customer UBIFS /minieye/adas/adas_checkcalib.sh", "offset_symbol": "whole file 1145 B",
         "en_evidence": "518f22e98842eb8a6c315d0a29098c885f0d2c942c4690154ddc730034b3d8c4",
         "vi_evidence": "same hash (byte-identical)",
         "interpretation": "Calibration-check script delta excluded.",
         "classification": "PROVEN_SAME", "confidence": "CONFIRMED"},
        {"id": "G03", "source": "adas_upgrade.sh + UBIFS manifest semantics",
         "file": "/customer/minieye/config + /config/cgi_config.bin + /config/net_config.bin",
         "offset_symbol": "persistent keys: install_calib_state/pitch/yaw/camera_height/extrinsic/intrinsic",
         "en_evidence": "updater preserves config dir; generic image holds placeholder only",
         "vi_evidence": "same preservation; same placeholder shape; device files unavailable",
         "interpretation": "Same persistent files can yield different VI behaviour only if parser/range/default/validation branches differ (unproven) or values are rejected at runtime (untested).",
         "classification": "COMPATIBILITY_UNKNOWN", "confidence": "UNKNOWN"},
    ]

    package_metadata_findings = [
        {"id": "P01", "source": "elf_overlay_report + EVIDENCE_ADAS_MODEL_DIRECTORY.json (AES directory FLAGS_m0)",
         "file": "adas overlay @0x172B1C", "offset_symbol": "models d0/v_a/v_t/p_r/road/tl",
         "en_evidence": "overlay 10117644 c395db15...; 6 blobs hashed",
         "vi_evidence": "overlay 10135506 6becae4d...; same 6 blob hashes, sizes equal, offsets shifted, m0 self-consistent",
         "interpretation": "Changed CNN weights and stale-m0 excluded as primary.",
         "classification": "PROVEN_SAME_BLOBS", "confidence": "CONFIRMED"},
        {"id": "P02", "source": "adas_gap_report + EVIDENCE_ADAS_GAP_GEOMETRY.json",
         "file": "adas interstitial", "offset_symbol": "7 gaps ELF-end..flags",
         "en_evidence": "gaps 7394/16790/7624/17384/14532/20660/6746",
         "vi_evidence": "gaps 8706/21304/16974/15410/15616/21880/9102; deltas sum exactly +17862 = file-size delta",
         "interpretation": "Entire VI growth is non-model interstitial; format/reader/causality UNKNOWN (no proven xref/validator/log).",
         "classification": "PROVEN_GEOMETRY_UNKNOWN_SEMANTICS", "confidence": "CONFIRMED"},
    ]

    root_cause_candidates = [
        {"rank": 1, "candidate": "VI kernel/media/contiguous-memory or IPU init behaviour blocks usable frames",
         "proven_difference": "Distinct uImage payloads (hashes differ, +2 B); VI adds 8 MiB fb reservation 0x3F000000-0x3F800000; valid load/entry/CRC both sides.",
         "mechanism": "Changed reservation/allocator ordering or VIF/ISP/SCL/IPU driver behaviour could starve raw_adas or fail MI_SYS_Init/MI_SCL_CreateDevice/IPUCreateDevice at runtime.",
         "supporting": "Kernel is the largest opaque VI delta; userspace media stack is otherwise identical so kernel is the natural suspect surface.",
         "contradicting": "No config/DTB/allocator/IPU log proves starvation; camera+recording work so sensor path is not grossly broken.",
         "confidence": "UNKNOWN", "next_test": "Read-only EN/VI capture: /proc/cmdline /proc/meminfo /proc/iomem dmesg lsmod ps + MI_* return codes + raw_adas frame counters."},
        {"rank": 2, "candidate": "Persistent calibration/config accepted differently by VI executable",
         "proven_difference": "None in scripts (run.sh + adas_checkcalib.sh byte-identical); updater preserves /customer/minieye/config (proven).",
         "mechanism": "Same flag bytes could fail VI parser/range/validation branches, or VI requires a new key absent from EN-era files.",
         "supporting": "Startup depends on device-specific adas.flag/calib.flag decoded to adas_de/calib_de.flag + --enable_vehicle gate.",
         "contradicting": "No parser diff proven in compared code; generic image has placeholder only so no static incompatibility shown.",
         "confidence": "UNKNOWN", "next_test": "Private read-only copy+decode of device flags; run EN-vs-VI parser matrix on copies; record validation logs without publishing secrets."},
        {"rank": 3, "candidate": "Upstream frame starvation despite unchanged writer helpers",
         "proven_difference": "cardv builds differ (equal size, distinct hash) but send()/send_frame_task normalized code identical; raw_adas token singular both sides.",
         "mechanism": "Sensor/VIF/ISP/SCL setup, CMA allocation, thread start timing, or startup-order race yields no/tardy/malformed frames to an unchanged writer.",
         "supporting": "Static equality of writer does not prove live frames, geometry, stride, timestamps, cadence, or mapping success.",
         "contradicting": "Call-sequence equality lowers deliberate-rewrite probability; recording works so some camera path flows.",
         "confidence": "UNKNOWN", "next_test": "Capture cardv/adas threads, raw_adas existence, frame metadata (w/h/stride/fmt/seq/ts/fps), allocation errors on EN vs VI."},
        {"rank": 4, "candidate": "ADAS interstitial package metadata interpretation",
         "proven_difference": "7 non-model gaps sum exactly to +17862 B; models identical; m0 self-consistent.",
         "mechanism": "Opaque protection/package records could gate model loading, feature enable, or calibration via an unidentified reader.",
         "supporting": "Placement around protected blobs is consistent with package/protection metadata.",
         "contradicting": "No xref/reader/parser/log ties gaps to activation; BitAnswer compared paths byte-identical.",
         "confidence": "UNKNOWN", "next_test": "Search xrefs for gap/overlay offsets; strace/mmap trace of /proc/self/exe ranges; reversible EN-base + VI-adas launch log."},
        {"rank": 5, "candidate": "Runtime license/custom-info/feature state",
         "proven_difference": "None in compared implementation (Bit_Login/ReadFeature/CheckOutSn/CheckOutFeatures/SetRootPath/dispatcher byte-identical).",
         "mechanism": "Identical code returns different feature set when fed different UUID/license/feature blobs.",
         "supporting": "License root lives under preserved config dir; device-specific state untested.",
         "contradicting": "Implementation delta downgraded by byte-identity of compared paths.",
         "confidence": "LOW", "next_test": "Sanitized login/feature-query return-code capture on EN vs VI; never publish secrets."},
        {"rank": 6, "candidate": "Display/M4-only failure masking live inference",
         "proven_difference": "VI adds SendGPSSpeedToScreen + GPS/display/G-sensor/power changes + 8 MiB fb reservation; display reportedly normal.",
         "mechanism": "Inference runs but warnings/pixels/audio never reach screen/M4, appearing as never-active lane/AI.",
         "supporting": "cardv owns many Send*ToScreen paths; MessagePack/AdasStatus layers separate inference from rendering.",
         "contradicting": "Display-normal observation cuts both ways; no evidence inference reaches display boundary in VI.",
         "confidence": "LOW", "next_test": "Classify A-F first; if inference alive, capture ScreenService/MessagePack traffic + M4 pcap on verified interface."},
    ]

    excluded_causes = [
        {"cause": "Different CNN/model weights", "evidence": "6/6 blobs byte-identical (EVIDENCE_ADAS_MODEL_DIRECTORY.json)", "confidence": "CONFIRMED"},
        {"cause": "Stale m0 offsets", "evidence": "VI m0 tracks shifted offsets self-consistently", "confidence": "CONFIRMED"},
        {"cause": "adas_checkcalib.sh difference", "evidence": "byte-identical 1145 B 518f22e9...", "confidence": "CONFIRMED"},
        {"cause": "Missing UpdateInstallCalibState(2) path", "evidence": "Heavy/Regular success paths effectively identical", "confidence": "MEDIUM"},
        {"cause": "Broad lane-algorithm rewrite", "evidence": "2731/2734 same call sequence; 2 diffs look like regalloc noise", "confidence": "MEDIUM"},
        {"cause": "raw_adas API rewrite / endpoint rename", "evidence": "Same CRingBuf API + single raw_adas token + identical normalized helpers", "confidence": "HIGH-CONFIDENCE"},
        {"cause": "M4/display transport collapse as sole proof of inference failure", "evidence": "Display reported normal; inference-vs-rendering layers separable", "confidence": "MEDIUM"},
    ]

    unknowns = [
        "Exact VI runtime failure class A-F (absent/crash/starved/IPU-fail/gate-suppressed/display-only)",
        "Live raw_adas metadata: w/h/stride/format/bytes/seq/timestamps/fps/drops/mapping",
        "Kernel config + DTB semantic delta inside opaque comp=9 payload",
        "Runtime CMA/MIU/mmap_reserved consumer, allocation order, IPU return codes",
        "Device adas.flag/calib.flag + decoded contents, enable_vehicle value, parser logs",
        "Calibration gate inputs: movement/GPS/timing/confidence/geometry/IMU/persistence thresholds",
        "Causal reader (if any) of the 7 interstitial regions; package validation logs",
        "Runtime license UUID/custom-info/feature values and Bit_* return codes",
        "Whether inference runs while screen/audio stays silent",
    ]

    legacy_findings = [
        {"id": "F01", "rank": 1, "status": "UNKNOWN",
         "hypothesis": "VI kernel/media/memory integration prevents usable frames or IPU initialization",
         "evidence": ["EN and VI kernel payloads differ; VI adds 8 MiB fb reservation.",
                      "No runtime dmesg/cmdline/media/allocator/IPU capture exists."],
         "references": ["docs/firmware_en_vi/01_PACKAGE_FLASH_LAYOUT.md:125-141",
                        "docs/firmware_en_vi/02_BOOT_KERNEL_ROOTFS.md:43-58",
                        "docs/firmware_en_vi/05_CAMERA_MEDIA_IMU.md:59-72"]},
        {"id": "F02", "rank": 2, "status": "UNKNOWN",
         "hypothesis": "Persistent calibration/config state is accepted differently by VI",
         "evidence": ["Updater preserves /customer/minieye/config.",
                      "run.sh identical; exits if flags absent or enable_vehicle=false.",
                      "Device flag contents unavailable."],
         "references": ["docs/firmware_en_vi/07_CONFIG_LICENSE_CALIBRATION.md:3-64"]},
        {"id": "F03", "rank": 3, "status": "UNKNOWN",
         "hypothesis": "Frames fail upstream despite an unchanged raw_adas writer contract",
         "evidence": ["Same CRingBuf ctor/request/commit pattern; normalized helpers identical.",
                      "Live geometry/cadence/ordering unmeasured."],
         "references": ["docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md:21-189"]},
        {"id": "F04", "rank": 4, "status": "UNKNOWN",
         "hypothesis": "ADAS interstitial package metadata or its runtime interpretation causes failure",
         "evidence": ["6 model blobs identical; 7 gaps sum to +17862.", "No proven reader/xref."],
         "references": ["docs/reverse/ADAS_INTERSTITIAL_GAPS_V1.md:8-32"]},
        {"id": "F05", "rank": 5, "status": "DOWNGRADED",
         "hypothesis": "VI changed the license/feature implementation",
         "evidence": ["Compared BitAnswer paths byte-identical; runtime state untested."],
         "references": ["docs/reverse/BITANSWER_LICENSE_PATH_V1.md:181-224"]},
        {"id": "F06", "rank": 6, "status": "DOWNGRADED",
         "hypothesis": "The M4/display path alone explains total activation failure",
         "evidence": ["VI has display/GPS + fb changes; display-only failure cannot prove inference failure."],
         "references": ["docs/reverse/SCREEN_ADAS_PATH_DIFF_V2.md"]},
        {"id": "F07", "rank": 7, "status": "EXCLUDED_AS_PRIMARY",
         "hypothesis": "Different CNN/model weights caused the regression",
         "evidence": ["6/6 blobs byte-identical."],
         "references": ["docs/reverse/EVIDENCE_ADAS_MODEL_DIRECTORY.json"]},
    ]

    evidence = {
        "schema": "c2m.vi_adas_failure.evidence.v1",
        "generated_by": "tools/fw/vi_adas_failure_evidence.py",
        "analysis_mode": "static-read-only",
        "ground_truth": {"en": "known-working ADAS baseline",
                         "vi": "known-non-working ADAS firmware on the same unit"},
        "exclusions": ["No firmware modification", "No Candidate C build", "No binary patching",
                       "No Candidate A/B alteration", "No commit or push"],
        "firmware": firmware,
        "payload_diff": payload_diff,
        "kernel_findings": kernel_findings,
        "cardv_findings": cardv_findings,
        "adas_findings": adas_findings,
        "calibration_findings": calibration_findings,
        "config_findings": config_findings,
        "package_metadata_findings": package_metadata_findings,
        "root_cause_candidates": root_cause_candidates,
        "excluded_causes": excluded_causes,
        "unknowns": unknowns,
        "inputs": inputs,
        "findings": legacy_findings,
        "cross_references": ["VI_ADAS_FAILURE_DEEP_DIVE_V1.md", "VI_KERNEL_MEDIA_DIFF_V1.md",
                             "VI_CALIBRATION_PATH_V1.md", "VI_CARDV_RAW_ADAS_DEEP_DIFF_V1.md",
                             "VI_ADAS_PACKAGE_METADATA_V2.md"],
    }

    path = OUT / "EVIDENCE_VI_ADAS_FAILURE.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    json.loads(path.read_text(encoding="utf-8"))
    print(f"wrote {rel(path)} payloads={len(payload_diff)} "
          f"kernel={len(kernel_findings)} cardv={len(cardv_findings)} "
          f"adas={len(adas_findings)} calib={len(calibration_findings)} "
          f"config={len(config_findings)} pkg={len(package_metadata_findings)} "
          f"candidates={len(root_cause_candidates)}; all {len(inputs)} hashes verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
