#!/usr/bin/env python3
"""Extract only stock EN loader/shared libraries for private RAM-debug QEMU.

Input is the already independently pinned EN updater TAR. No firmware package
is produced, and none of these vendor bytes belong in public CI artifacts.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
from pathlib import Path, PurePosixPath
import stat

from extract_rootfs_cpio import iter_cpio_full

PINS = {
    "ld-2.30.so": "dd2f57c2363db9abce352fcaf07b943e59fbd5dcca898bb39a2709350fbadb4c",
    "libc-2.30.so": "3b2cc951503e0bc40e45ebc6e8f39b92b937ab7a3b7c009377708d2473756657",
    "libm-2.30.so": "8025a30fd4b7b118ebd35fc1b71e9898473136dc83edaa24358f57ba69d04084",
    "libgcc_s.so.1": "5def4c502c9fe114903eef41dfdbd5b2b6b7abf89015dac444dbafde4de441f0",
}
LINKS = {"ld-linux-armhf.so.3": "ld-2.30.so", "libc.so.6": "libc-2.30.so",
         "libm.so.6": "libm-2.30.so"}
ALLOW = set(PINS) | set(LINKS)


def extract(inner: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("sysroot output must not exist")
    entries = {}
    for name, mode, blob in iter_cpio_full(gzip.decompress(inner.read_bytes())):
        name = name.removeprefix("./")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("unsafe archive path")
        if not name.startswith("lib/"):
            continue
        if len(path.parts) != 2 or path.name not in ALLOW:
            # Only four required runtime files and their exact links; never
            # extract vendor programs, ADAS libraries, license/config bytes.
            continue
        if name in entries:
            raise ValueError("duplicate library entry")
        if stat.S_ISREG(mode) or stat.S_ISLNK(mode):
            entries[name] = (mode, blob)
    for name, digest in PINS.items():
        entry = entries.get("lib/" + name)
        if not entry or not stat.S_ISREG(entry[0]):
            raise ValueError("stock runtime pin missing")
        if hashlib.sha256(entry[1]).hexdigest() != digest:
            raise ValueError("stock runtime pin mismatch")
    for name, expected in LINKS.items():
        entry = entries.get("lib/" + name)
        if not entry or not stat.S_ISLNK(entry[0]):
            raise ValueError("stock runtime symlink missing")
        if entry[1].rstrip(b"\0").decode("ascii") != expected:
            raise ValueError("stock runtime symlink pin mismatch")
    # Validate every link before writing anything. Stock links are local basenames.
    for mode, blob in entries.values():
        if stat.S_ISLNK(mode):
            target = blob.rstrip(b"\0").decode("ascii")
            if "/" in target or target in ("", ".", ".."):
                raise ValueError("nonlocal library symlink rejected")
            destination = entries.get("lib/" + target)
            if not destination or not stat.S_ISREG(destination[0]):
                raise ValueError("library symlink target is not a regular entry")
    (out / "lib").mkdir(parents=True)
    for name, (mode, blob) in entries.items():
        path = out / name
        if stat.S_ISREG(mode):
            path.write_bytes(blob)
            path.chmod(stat.S_IMODE(mode))
    for name, (mode, blob) in entries.items():
        if stat.S_ISLNK(mode):
            (out / name).symlink_to(blob.rstrip(b"\0").decode("ascii"))
    return {"verdict": "PINNED-STOCK-LIBRARIES-ONLY", "entries": len(entries),
            "runtime_sha256": PINS, "vendor_bytes_public": False}


def main() -> int:
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inner", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    print(json.dumps(extract(args.inner, args.out), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
