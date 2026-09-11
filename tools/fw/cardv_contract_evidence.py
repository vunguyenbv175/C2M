#!/usr/bin/env python3
"""Gate A cardv evidence: byte-level proof of JSON/ringbuf/GPS contracts in the two
stock cardv ELFs extracted from the original EN/VI rootfs images.

Checks:
  - SHA-256 identity vs docs/reverse/CARDV_RAW_ADAS_CONTRACT_V1.md
  - JSON uuid templates + minieye-websocket subprotocol + port digits
  - raw_adas/fortest ringbuf endpoint strings
  - GPS/NMEA + SendGPS* screen symbols/strings
Outputs JSON evidence; prints table.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

EXPECTED = {
    "en": "344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c",
    "vi": "56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23",
}

TOKENS = [
    "minieye-websocket", "raw_adas", "fortest",
    "GPSLevel", "GPSSpeed", "DispBrightSet", "StorageStatus", "ClientConn",
    "RecordVoice", "ScreenModeSet", "AdasStatus", "HeavyCalibStatus",
    "WSGetConnectStatus", "SendADASInfoToScreen", "SendGPSInfoToScreen",
    "SendGPSSpeedToScreen", "SendBacklightLevelInfoToScreen",
    "SendDisplayModeToScreen", "SendStorageInfoToScreen",
    "SendWifiStatusToScreen", "SendAudioRecordStatusToScreen",
    "GetADASStatus", "GetADASCalibStatus",
    "adas_minieye_send_frame_task", "CRingBuf", "RequestWriteFrame", "CommitWrite",
    "nmea_parse", "nmea_pack_type", "nmea_BDGSV2info_na", "nmea_satinfo",
    "GsensorSetSensitivity", "GsensorSetPowerOnByInt",
    "26012", "8080",
]


def find_all(data: bytes, needle: bytes, cap: int = 12) -> list[int]:
    out: list[int] = []
    start = 0
    while len(out) < cap:
        i = data.find(needle, start)
        if i < 0:
            break
        out.append(i)
        start = i + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", type=Path, default=Path("build/fw_bin_en/cardv"))
    ap.add_argument("--vi", type=Path, default=Path("build/fw_bin_vi/cardv"))
    ap.add_argument("-o", "--output", type=Path,
                    default=Path("docs/reverse/EVIDENCE_CARDV_CONTRACT.json"))
    args = ap.parse_args()

    en = args.en.read_bytes()
    vi = args.vi.read_bytes()
    en_sha = hashlib.sha256(en).hexdigest()
    vi_sha = hashlib.sha256(vi).hexdigest()
    print(f"EN cardv: size={len(en)} sha256={en_sha} match_doc={en_sha == EXPECTED['en']}")
    print(f"VI cardv: size={len(vi)} sha256={vi_sha} match_doc={vi_sha == EXPECTED['vi']}")

    rows = []
    for tok in TOKENS:
        eo = find_all(en, tok.encode())
        vo = find_all(vi, tok.encode())
        rows.append({"token": tok, "en_count": len(eo),
                     "en_offsets_hex": [hex(o) for o in eo],
                     "vi_count": len(vo), "vi_offsets_hex": [hex(o) for o in vo],
                     "verdict": "BOTH" if eo and vo else ("EN-ONLY" if eo else ("VI-ONLY" if vo else "ABSENT"))})
        print(f"{rows[-1]['verdict']:8s} ENx{len(eo):<3d} VIx{len(vo):<3d} {tok}")

    doc = {"method": "byte-exact search in cardv ELFs extracted from original EN/VI rootfs "
                     "(gzip-cpio) images; offsets are ELF file offsets.",
           "en": {"size": len(en), "sha256": en_sha, "matches_contract_doc": en_sha == EXPECTED["en"]},
           "vi": {"size": len(vi), "sha256": vi_sha, "matches_contract_doc": vi_sha == EXPECTED["vi"]},
           "tokens": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
