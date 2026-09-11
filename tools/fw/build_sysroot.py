#!/usr/bin/env python3
"""P0: derive the EN stock-userspace ABI manifest (sysroot evidence).

Extracts from the LOCAL golden firmware (never committed):
  - dynamic loader + core libc set from the rootfs cpio (names + SHAs);
  - each stock ELF's NEEDED/GLIBC-max evidence is produced by
    fw/device_minimal/check_elf.py --allow-dynamic (see TARGET_ABI.md);
  - verifies the firmware contains NO crt objects or libc headers, which is
    exactly why the stock-ABI dynamic link is performed with the runner
    cross toolchain + glibc_compat.h pins (check_elf.py proves the result)
    instead of a literal --sysroot link.

Outputs docs/firmware/SYSROOT_MANIFEST.json (hashes/metadata only).

Usage:
  python3 tools/fw/build_sysroot.py --tar <EN.tar> [-o docs/firmware/SYSROOT_MANIFEST.json]
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "fw"))
from extract_rootfs_cpio import iter_cpio_full  # noqa: E402

INNER = "SigmastarUpgradeSD_SSC8838G.bin"
WANT_LIBS = ("lib/ld-linux-armhf.so.3", "lib/libc.so.6", "lib/libm.so.6",
             "lib/libgcc_s.so.1", "lib/libpthread.so.0")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tar", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path,
                    default=ROOT / "docs" / "firmware" / "SYSROOT_MANIFEST.json")
    args = ap.parse_args()

    with tarfile.open(args.tar, "r") as tf:
        members = tf.getmembers()
        rootfs_es = None
        for m in members:
            blob = tf.extractfile(m).read()
            if m.name == INNER:
                inner = blob
        # locate rootfs.es via carve manifest logic (reuse offsets from contract?)
        from carve_upgrade import read_upgrade
        data, _meta = read_upgrade(args.tar)
    import re
    script = data[:data.find(b"% <- this is end of script symbol")].decode("latin-1")
    m = re.search(r"fatload\s+mmc\s+\d+\s+0x[0-9a-fA-F]+\s+\$\(SdUpgradeImage\)\s+"
                  r"(0x[0-9a-fA-F]+|\d+)\s+(0x[0-9a-fA-F]+|\d+)", script.split("rootfs.es")[1])
    size, off = int(m.group(1), 0), int(m.group(2), 0)
    rootfs_inner = gzip.decompress(data[off:off + size])
    cpio = {n: (m, b) for n, m, b in iter_cpio_full(rootfs_inner)}

    libs = {}
    for name in WANT_LIBS:
        if name in cpio:
            mode, blob = cpio[name]
            if (mode >> 12) == 0o12:
                target = blob.split(b"\0")[0].decode("ascii", "replace")
                # resolve one level (lib/*.so -> versioned file in same dir)
                tname = "lib/" + target
                if tname in cpio:
                    _m, tb = cpio[tname]
                    libs[name] = {"symlink_to": target,
                                  "target_size": len(tb),
                                  "target_sha256": hashlib.sha256(tb).hexdigest()}
                else:
                    libs[name] = {"symlink_to": target, "target_missing": True}
            else:
                libs[name] = {"size": len(blob),
                              "sha256": hashlib.sha256(blob).hexdigest()}
        else:
            libs[name] = {"missing": True}
    # absence proof: no crt objects / libc headers anywhere in rootfs
    crt = [n for n, (_m, _b) in cpio.items()
           if "/crt" in n or n.endswith(("crt1.o", "crti.o", "crtn.o"))
           or n.startswith("usr/include")]
    doc = {"method": "tools/fw/build_sysroot.py from the original EN TAR (local-only)",
           "loader": "lib/ld-linux-armhf.so.3",
           "glibc_baseline": "2.30 (stock cardv max need GLIBC_2.29, see TARGET_ABI.md)",
           "libs": libs,
           "crt_or_headers_in_firmware": crt,
           "conclusion": ("crt/headers ABSENT from firmware: a literal --sysroot link "
                          "against stock objects is impossible; the stock-ABI dynamic "
                          "binary is therefore built with the runner cross toolchain + "
                          "glibc_compat.h version pins, and check_elf.py --allow-dynamic "
                          "proves interp/NEEDED/GLIBC<=2.30 per build. "
                          if not crt else
                          "UNEXPECTED: crt/headers present — revisit sysroot strategy. ")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps(doc, indent=2)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
