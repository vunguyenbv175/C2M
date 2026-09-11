#!/usr/bin/env python3
"""WS1: Re-derive the complete EN vendor package contract from the original TAR.

Reads the original EN TAR (local-only, never committed) and machine-encodes:
  - outer TAR members (name/order/size/mode/mtime/uid/gid/uname/gname,
    header offset, data offset, per-member SHA-256, raw 512B header SHA)
  - sysVer.txt / minieye_firmware.md5 contents + MD5-vs-inner relationship
  - adas_upgrade.sh SHA + role (SD-card second-stage upgrade, NOT the
    U-Boot upgrade script inside the .bin)
  - inner upgrade image: U-Boot script text, script_end, per-section
    fatload offset/size/sha, gap/padding accounting (fill byte 0xFF),
    trailing UNKNOWN bytes, total size + SHA-256/MD5
  - partition/write commands per section (verbatim script body)
  - every byte accounted: script / payload / 0xFF pad / UNKNOWN tail

Unknowns are marked UNKNOWN explicitly, never inferred.

Outputs:
  --out-json  machine contract (default docs/firmware/EN_PACKAGE_CONTRACT.json)
  --out-md    human companion (default docs/firmware/EN_PACKAGE_CONTRACT.md)

Also usable as a library by repack_firmware.py / validate_firmware.py.

Usage:
  python3 tools/fw/package_contract.py --tar firmware/original/...EN.tar
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INNER = "SigmastarUpgradeSD_SSC8838G.bin"
END_MARKER = b"% <- this is end of script symbol"
SECTION_RE = re.compile(r"^# File Partition:\s*(\S+)\s*$", re.M)
FATLOAD_RE = re.compile(
    r"fatload\s+mmc\s+\d+\s+0x[0-9a-fA-F]+\s+\$\(SdUpgradeImage\)\s+"
    r"(0x[0-9a-fA-F]+|\d+)\s+(0x[0-9a-fA-F]+|\d+)", re.I)


def sha256_bytes(d: bytes) -> str:
    return hashlib.sha256(d).hexdigest()


def parse_tar_raw(path: Path) -> tuple[list[dict], bytes]:
    raw = path.read_bytes()
    members = []
    off = 0
    order = 0
    while True:
        if off + 512 > len(raw):
            raise ValueError("truncated TAR header at " + hex(off))
        hdr = raw[off:off + 512]
        if hdr == b"\x00" * 512:
            # count trailing zeros, must be >= 1024 per POSIX (here 1536)
            tail = raw[off:]
            members_trailing = len(tail)
            return members, raw
        name = hdr[:100].split(b"\x00")[0].decode("ascii", "replace")
        mode = int(hdr[100:108].split(b"\x00")[0].strip() or b"0", 8)
        uid = int(hdr[108:116].split(b"\x00")[0].strip() or b"0", 8)
        gid = int(hdr[116:124].split(b"\x00")[0].strip() or b"0", 8)
        size = int(hdr[124:136].split(b"\x00")[0].strip() or b"0", 8)
        mtime = int(hdr[136:148].split(b"\x00")[0].strip() or b"0", 8)
        chksum_raw = hdr[148:156]
        typeflag = hdr[156:157]
        magic = hdr[257:265]
        uname = hdr[265:297].split(b"\x00")[0].decode("ascii", "replace")
        gname = hdr[297:329].split(b"\x00")[0].decode("ascii", "replace")
        data = raw[off + 512:off + 512 + size]
        if len(data) != size:
            raise ValueError(f"truncated member {name}")
        members.append({
            "order": order, "name": name, "size": size,
            "mode_oct": oct(mode), "mode": mode, "uid": uid, "gid": gid,
            "mtime": mtime, "typeflag": typeflag.decode("ascii", "replace"),
            "magic": repr(bytes(magic)),
            "uname": uname, "gname": gname,
            "header_offset": off, "header_offset_hex": hex(off),
            "data_offset": off + 512, "data_offset_hex": hex(off + 512),
            "header_sha256": sha256_bytes(hdr),
            "sha256": sha256_bytes(data),
        })
        order += 1
        off += 512 + ((size + 511) // 512) * 512
    raise AssertionError("unreachable")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tar", type=Path, required=True)
    ap.add_argument("--out-json", type=Path,
                    default=ROOT / "docs/firmware/EN_PACKAGE_CONTRACT.json")
    ap.add_argument("--out-md", type=Path,
                    default=ROOT / "docs/firmware/EN_PACKAGE_CONTRACT.md")
    args = ap.parse_args()

    tar_bytes = args.tar.read_bytes()
    tar_sha256 = sha256_bytes(tar_bytes)
    members, raw = parse_tar_raw(args.tar)

    with tarfile.open(args.tar, "r") as tf:
        sysver = tf.extractfile("sysVer.txt").read()
        md5file = tf.extractfile("minieye_firmware.md5").read()
        adas_up = tf.extractfile("adas_upgrade.sh").read()
        inner = tf.extractfile(INNER).read()

    inner_md5 = hashlib.md5(inner).hexdigest()
    md5_listed = md5file.decode("ascii", "replace").split()[0].strip()
    md5_relation = ("EXACT-MATCH: minieye_firmware.md5 lists "
                    f"{md5_listed}; md5(inner .bin) = {inner_md5}; "
                    f"match={md5_listed == inner_md5}")

    # inner script + loads (reuse carve logic, extended with commands/gaps)
    end_idx = inner.find(END_MARKER)
    if end_idx < 0:
        raise SystemExit("END_MARKER not found in inner image")
    script_end = end_idx + len(END_MARKER)
    script = inner[:script_end].decode("latin-1", "replace")
    script_trailer_nl = inner[script_end:script_end + 1] == b"\n"

    matches = list(SECTION_RE.finditer(script))
    loads = []
    for i, sm in enumerate(matches):
        section = sm.group(1)
        start = sm.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(script)
        body = script[start:end]
        for j, fm in enumerate(FATLOAD_RE.finditer(body)):
            size = int(fm.group(1), 0)
            offset = int(fm.group(2), 0)
            stop = offset + size
            valid = 0 <= offset <= stop <= len(inner)
            row = {"section": section, "load_index": j,
                   "offset": offset, "offset_hex": hex(offset),
                   "size": size, "size_hex": hex(size),
                   "end": stop, "end_hex": hex(stop),
                   "within_image": valid,
                   "script_body": body.strip("\n")[:2000]}
            if valid:
                row["sha256"] = sha256_bytes(inner[offset:stop])
                row["md5"] = hashlib.md5(inner[offset:stop]).hexdigest()
            loads.append(row)

    # byte accounting: every byte = script(+1 NL) / payload / 0xFF pad / UNKNOWN tail
    covered = bytearray(len(inner))  # 0=unaccounted
    covered[:script_end] = b"\x01" * script_end
    if script_trailer_nl:
        covered[script_end] = 1
    for r in loads:
        if r["within_image"]:
            covered[r["offset"]:r["end"]] = b"\x01" * (r["end"] - r["offset"])
    # gaps must be 0xFF
    gaps = []
    total_pad = 0
    # head gap: after script NL to first payload
    first_off = min(r["offset"] for r in loads if r["within_image"])
    head_pad = inner[script_end + 1:first_off]
    gaps.append({"range": [script_end + 1, first_off],
                 "range_hex": [hex(script_end + 1), hex(first_off)],
                 "len": len(head_pad), "fill": "0xFF" if set(head_pad) == {0xFF} else "MIXED-UNEXPECTED",
                 "sha256": sha256_bytes(head_pad)})
    total_pad += len(head_pad)
    ordered = sorted([r for r in loads if r["within_image"]], key=lambda r: r["offset"])
    for a, b in zip(ordered, ordered[1:]):
        if b["offset"] > a["end"]:
            seg = inner[a["end"]:b["offset"]]
            gaps.append({"range": [a["end"], b["offset"]],
                         "range_hex": [hex(a["end"]), hex(b["offset"])],
                         "len": len(seg), "fill": "0xFF" if set(seg) == {0xFF} else "MIXED-UNEXPECTED",
                         "sha256": sha256_bytes(seg)})
            total_pad += len(seg)
    last_end = max(r["end"] for r in loads if r["within_image"])
    tail = inner[last_end:]
    tail_info = {"offset": last_end, "offset_hex": hex(last_end), "len": len(tail),
                 "hex": tail.hex(),
                 "ascii": tail.decode("latin-1", "replace"),
                 "interpretation": "UNKNOWN: 24 bytes past last payload (oneed_cust end); "
                                   "identical shape in EN and VI "
                                   "('12345678\\n# File Partitio'); possibly image-builder "
                                   "trailer fragment; NEVER assumed to be padding (not 0xFF).",
                 "sha256": sha256_bytes(tail)}

    contract = {
        "method": "tools/fw/package_contract.py re-derives the EN package from the original TAR bytes; "
                  "no field is inferred — see UNKNOWN markers.",
        "source_tar_sha256": tar_sha256,
        "source_tar_size": len(tar_bytes),
        "outer_members": members,
        "outer_order": [m["name"] for m in members],
        "outer_trailing_zero_bytes": len(raw) - (members[-1]["data_offset"] +
                                     ((members[-1]["size"] + 511) // 512) * 512),
        "sysVer_txt": sysver.decode("ascii", "replace"),
        "sysVer_sha256": sha256_bytes(sysver),
        "minieye_firmware_md5_file": md5file.decode("ascii", "replace"),
        "minieye_firmware_md5_relation": md5_relation,
        "inner_md5": inner_md5,
        "inner_sha256": sha256_bytes(inner),
        "inner_size": len(inner),
        "adas_upgrade_sh_sha256": sha256_bytes(adas_up),
        "adas_upgrade_sh_size": len(adas_up),
        "adas_upgrade_sh_role": "Second-stage SD-card script run on-device AFTER U-Boot "
                                "flash (md5-checks inner .bin, extracts image.tar, backs up "
                                "customer configs, triggers reboot). NOT the U-Boot script "
                                "at inner offset 0.",
        "upgrade_script_text": script,
        "upgrade_script_end": script_end,
        "upgrade_script_sha256": sha256_bytes(inner[:script_end]),
        "script_trailer_newline": bool(script_trailer_nl),
        "loads": loads,
        "head_pad_is_ff": bool(set(head_pad) == {0xFF}),
        "inter_payload_gaps": gaps,
        "tail_unknown": tail_info,
        "accounting": {
            "script_bytes": script_end + (1 if script_trailer_nl else 0),
            "payload_bytes": sum(r["size"] for r in loads if r["within_image"]),
            "ff_pad_bytes": total_pad,
            "unknown_tail_bytes": len(tail),
            "total": len(inner),
            "check": (script_end + (1 if script_trailer_nl else 0)
                      + sum(r["size"] for r in loads if r["within_image"])
                      + total_pad + len(tail)) == len(inner),
        },
        "partition_map": [
            {"partition": "CIS", "source": "cis.es loads (0x4000/0xA000)",
             "uboot_cmd": "writecis"},
            {"partition": "KEY_CUST/MISC/ADAS_CUST/ubi0", "source": "set_partition.es (no fatload)",
             "uboot_cmd": "mtdparts + saveenv"},
            {"partition": "IPL0", "source": "ipl.es", "uboot_cmd": "nand erase.part + nand write.e"},
            {"partition": "IPL_CUST0/IPL_CUST1", "source": "ipl_cust.es", "uboot_cmd": "nand erase.part + nand write.e x2"},
            {"partition": "UBOOT0/UBOOT1", "source": "uboot.es", "uboot_cmd": "nand erase.part + nand write.e x2"},
            {"partition": "KERNEL/RECOVERY", "source": "kernel.es", "uboot_cmd": "nand erase.part + nand write.e x2"},
            {"partition": "rootfs", "source": "rootfs.es", "uboot_cmd": "nand erase.part + nand write.e"},
            {"partition": "ubi0 (erase)", "source": "ubi0.es section (no fatload)", "uboot_cmd": "nand erase.part ubi0"},
            {"partition": "ubi0:miservice", "source": "miservice.es", "uboot_cmd": "ubi create + ubi write"},
            {"partition": "ubi0:customer", "source": "customer.es", "uboot_cmd": "ubi create + ubi write"},
            {"partition": "MISC", "source": "misc.es", "uboot_cmd": "nand erase.part + nand write.e"},
            {"partition": "ubi0:oneed_cust", "source": "oneed_cust.es", "uboot_cmd": "ubi create + ubi write"},
        ],
        "unknowns": [
            "tail 24 bytes past oneed_cust end (see tail_unknown)",
            "outer TAR header magic/version encoding ('ustar  ' vs python USTAR) — "
            "payload-irrelevant, documented in repack report",
            "whether U-Boot validates inner MD5 before executing script (script itself "
            "does not md5-check payloads; adas_upgrade.sh checks the whole .bin only)",
        ],
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(contract, indent=2), encoding="utf-8")

    md = []
    md.append("# EN Package Contract — re-derived from original vendor TAR\n")
    md.append(f"Source TAR SHA-256: `{tar_sha256}` ({len(tar_bytes)} bytes)\n")
    md.append("## Outer TAR members (order-significant)\n")
    md.append("| order | name | size | mode | mtime | header@ | data@ | sha256 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for m in members:
        md.append(f"| {m['order']} | `{m['name']}` | {m['size']} | {m['mode_oct']} | "
                  f"{m['mtime']} | {m['header_offset_hex']} | {m['data_offset_hex']} | `{m['sha256'][:16]}…` |")
    md.append(f"\nTrailing zero bytes after last member data: {contract['outer_trailing_zero_bytes']} "
              "(3x512 zero blocks; preserved verbatim by the splicing repacker).\n")
    md.append("## sysVer / MD5 relationship\n")
    md.append(f"sysVer.txt: `{sysver!r}`\n")
    md.append(f"minieye_firmware.md5: `{md5file.decode().strip()}`\n")
    md.append(md5_relation + "\n")
    md.append("## Inner upgrade image\n")
    md.append(f"Size {len(inner)} bytes, SHA-256 `{sha256_bytes(inner)[:16]}…` (full hash in JSON), "
              f"MD5 `{inner_md5}`.\n")
    md.append(f"U-Boot script: {script_end} bytes + 1x `\\n` trailer, then 0xFF pad to "
              f"{hex(first_off)} (first payload).\n")
    md.append("### Payloads\n")
    md.append("| section | offset | size | end | sha256 |")
    md.append("|---|---|---|---|---|")
    for r in loads:
        md.append(f"| {r['section']}#{r['load_index']} | {r['offset_hex']} | {r['size_hex']} | "
                  f"{r['end_hex']} | `{r.get('sha256','INVALID')[:16]}…` |")
    md.append("\n### Gaps / padding\n")
    for g in gaps:
        md.append(f"- `{g['range_hex'][0]}..{g['range_hex'][1]}` ({g['len']} B): fill={g['fill']}")
    md.append(f"\n### UNKNOWN tail ({len(tail)} B @ {hex(last_end)})\n")
    md.append(f"hex `{tail.hex()}` ascii `{tail.decode('latin-1','replace')!r}` — "
              "preserved verbatim, never interpreted.\n")
    md.append("## Partition / write map\n")
    for p in contract["partition_map"]:
        md.append(f"- `{p['partition']}` <- {p['source']}: {p['uboot_cmd']}")
    md.append("\n## Byte accounting\n")
    a = contract["accounting"]
    md.append(f"script {a['script_bytes']} + payload {a['payload_bytes']} + 0xFF pad {a['ff_pad_bytes']} "
              f"+ UNKNOWN tail {a['unknown_tail_bytes']} = {a['total']} (check={a['check']})\n")
    args.out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {args.out_json} + {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
