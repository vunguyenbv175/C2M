#!/usr/bin/env python3
"""Carve SigmaStar C2M upgrade payloads from a vendor .tar or raw upgrade .bin.

The upgrade image begins with an ASCII U-Boot script. Each '# File Partition:'
section may contain one or more `fatload ... <size> <offset>` commands. This
script records those commands and extracts the referenced byte ranges without
making assumptions about payload type.
"""
from __future__ import annotations
import argparse, hashlib, json, re, tarfile
from pathlib import Path

INNER = "SigmastarUpgradeSD_SSC8838G.bin"
SECTION_RE = re.compile(r"^# File Partition:\s*(\S+)\s*$", re.M)
FATLOAD_RE = re.compile(
    r"fatload\s+mmc\s+\d+\s+0x[0-9a-fA-F]+\s+\$\(SdUpgradeImage\)\s+"
    r"(0x[0-9a-fA-F]+|\d+)\s+(0x[0-9a-fA-F]+|\d+)", re.I
)
END_MARKER = b"% <- this is end of script symbol"

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_upgrade(path: Path) -> tuple[bytes, dict]:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    meta = {"source": str(path), "source_sha256": h.hexdigest()}
    if tarfile.is_tarfile(path):
        with tarfile.open(path, "r:*") as tf:
            try:
                member = tf.getmember(INNER)
            except KeyError as exc:
                raise SystemExit(f"{path}: missing {INNER}") from exc
            f = tf.extractfile(member)
            if f is None:
                raise SystemExit(f"{path}: cannot read {INNER}")
            data = f.read()
            meta.update({"container": "tar", "inner_name": INNER, "inner_size": len(data), "inner_sha256": sha256_bytes(data)})
            return data, meta
    data = path.read_bytes()
    meta.update({"container": "raw", "inner_name": path.name, "inner_size": len(data), "inner_sha256": sha256_bytes(data)})
    return data, meta

def parse_script(data: bytes) -> tuple[str, int]:
    idx = data.find(END_MARKER)
    cap = min(len(data), 0x20000) if idx < 0 else idx + len(END_MARKER)
    return data[:cap].decode("latin-1", "replace"), cap

def safe_name(section: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", section)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path, help="vendor TAR or SigmastarUpgradeSD_SSC8838G.bin")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--no-carve", action="store_true", help="only write manifest/script")
    args = ap.parse_args()

    data, meta = read_upgrade(args.image)
    script, script_end = parse_script(data)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "upgrade_script.txt").write_text(script, encoding="utf-8")

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
            valid = 0 <= offset <= stop <= len(data)
            row = {
                "section": section,
                "load_index": j,
                "offset": offset,
                "offset_hex": hex(offset),
                "size": size,
                "size_hex": hex(size),
                "end": stop,
                "end_hex": hex(stop),
                "within_image": valid,
            }
            if valid:
                payload = data[offset:stop]
                row["sha256"] = sha256_bytes(payload)
                out_name = f"{safe_name(section)}.load{j}.off_{offset:08x}.size_{size:x}.bin"
                row["file"] = out_name
                if not args.no_carve:
                    (args.output / out_name).write_bytes(payload)
            loads.append(row)

    manifest = {**meta, "script_end": script_end, "loads": loads}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
