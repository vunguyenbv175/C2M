#!/usr/bin/env python3
"""Strict firmware-evidence verifier (review R1-new). FAIL-CLOSED: any missing
artifact, SHA mismatch, extraction failure, generator failure, or evidence
drift returns nonzero. No `|| echo` swallowing — by design.

Chain (all inputs explicit):
  TARs -> carve -> rootfs gunzip+cpio (cardv SHA check) -> UBIFS inventories
  -> adas full extraction w/ SHA check (LZO via system lib or local helper)
  -> adas strings -> regenerate schema/cardv/symdiff JSONs to --out-dir
  -> diff vs --canonical-dir (repo docs/reverse/)

Usage:
  python3 tools/ci/verify_evidence.py --en-tar ... --vi-tar ... \
      --workdir build/evid_verify --out-dir build/evid_out \
      --canonical-dir docs/reverse
"""
from __future__ import annotations
import argparse
import difflib
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "fw"))

EXPECTED_TAR = {
    "en": "3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c",
    "vi": "f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa",
}
EXPECTED_CARDV = {
    "en": "344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c",
    "vi": "56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23",
}
EXPECTED_ADAS = {
    "en": "0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043",
    "vi": "997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1",
}
INNER = "SigmastarUpgradeSD_SSC8838G.bin"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str) -> int:
    print(f"EVIDENCE-FAIL: {msg}")
    return 1


def run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"--- {what} stdout ---\n{r.stdout[-2000:]}")
        print(f"--- {what} stderr ---\n{r.stderr[-2000:]}")
        raise RuntimeError(f"{what} failed rc={r.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--en-tar", type=Path, required=True)
    ap.add_argument("--vi-tar", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--canonical-dir", type=Path, required=True)
    args = ap.parse_args()

    for tag, tar, exp in (("en", args.en_tar, EXPECTED_TAR["en"]),
                          ("vi", args.vi_tar, EXPECTED_TAR["vi"])):
        if not tar.is_file():
            return fail(f"missing {tag} TAR: {tar}")
        got = sha256_file(tar)
        if got != exp:
            return fail(f"{tag} TAR SHA mismatch: got {got} want {exp}")

    wd, out = args.workdir, args.out_dir
    wd.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    try:
        from carve_upgrade import read_upgrade
        from extract_rootfs_cpio import iter_cpio
        from ubifs_extract_file import extract as ubifs_extract
        from ubifs_ls import main as _  # noqa: F401  (import check only)
    except Exception as e:
        return fail(f"tool import failed: {e}")

    carved = {}
    for tag, tar in (("en", args.en_tar), ("vi", args.vi_tar)):
        data, meta = read_upgrade(tar)
        blob = wd / f"upgrade_{tag}.bin"
        blob.write_bytes(data)
        # locate rootfs + customer payloads via carve manifest
        run([sys.executable, "tools/fw/carve_upgrade.py", str(tar), "-o", str(wd / f"carve_{tag}")],
            f"carve-{tag}")
        man = json.loads((wd / f"carve_{tag}" / "manifest.json").read_text())
        carved[tag] = {r["section"]: wd / f"carve_{tag}" / r["file"] for r in man["loads"] if "file" in r}

    # rootfs -> cardv + inners, with SHA gate
    inners = {}
    for tag in ("en", "vi"):
        rootfs = carved[tag].get("rootfs.es")
        if rootfs is None or not rootfs.is_file():
            return fail(f"{tag}: rootfs.es not carved")
        try:
            inner = gzip.decompress(rootfs.read_bytes())
        except Exception as e:
            return fail(f"{tag}: rootfs gunzip failed: {e}")
        inners[tag] = wd / f"rootfs_{tag}_inner.bin"
        inners[tag].write_bytes(inner)
        blobs = dict(iter_cpio(inner))
        for name in ("bootconfig/bin/cardv",):
            p = wd / f"cardv_{tag}"
            p.write_bytes(blobs[name])
            if sha256_file(p) != EXPECTED_CARDV[tag]:
                return fail(f"{tag}: cardv SHA mismatch")

    # customer inventories
    inv = {}
    for tag in ("en", "vi"):
        cust = carved[tag].get("customer.es")
        if cust is None or not cust.is_file():
            return fail(f"{tag}: customer.es not carved")
        run([sys.executable, "tools/fw/ubifs_ls.py", str(cust), "-o", str(wd / f"inv_{tag}.json")],
            f"inventory-{tag}")
        inv[tag] = wd / f"inv_{tag}.json"

    # adas full extraction w/ SHA gate (LZO via system lib or local helper)
    adas = {}
    for tag in ("en", "vi"):
        cust = carved[tag]["customer.es"]
        target = wd / f"adas_{tag}"
        try:
            blob, _rep = ubifs_extract(cust, "/minieye/adas/adas")
        except Exception as e:
            return fail(f"{tag}: adas UBIFS extraction failed: {e}")
        target.write_bytes(blob)
        if sha256_file(target) != EXPECTED_ADAS[tag]:
            return fail(f"{tag}: adas SHA mismatch")
        adas[tag] = target

    # regenerate evidence into out-dir (explicit paths; never writes repo)
    try:
        run([sys.executable, "tools/fw/adas_string_evidence.py",
             "--en", str(adas["en"]), "--vi", str(adas["vi"]),
             "-o", str(out / "EVIDENCE_ADAS_STRINGS.json")], "adas-strings")
        run([sys.executable, "tools/fw/cardv_contract_evidence.py",
             "--en", str(wd / "cardv_en"), "--vi", str(wd / "cardv_vi"),
             "-o", str(out / "EVIDENCE_CARDV_CONTRACT.json")], "cardv-contract")
        run([sys.executable, "tools/fw/cardv_symdiff.py",
             "--en", str(wd / "cardv_en"), "--vi", str(wd / "cardv_vi"),
             "-o", str(out / "EVIDENCE_CARDV_SYMDIFF.json")], "cardv-symdiff")
    except RuntimeError as e:
        return fail(str(e))

    # NOTE: stock_adas_schema_v2 needs inventory/plain scans in its build-dir
    # layout; regenerate it via a staged build-dir mirror.
    staged = wd / "staged_build"
    (staged / "fw_bin_en").mkdir(parents=True, exist_ok=True)
    (staged / "fw_bin_vi").mkdir(parents=True, exist_ok=True)
    (staged / "fw_bin_en" / "cardv").write_bytes((wd / "cardv_en").read_bytes())
    (staged / "fw_bin_vi" / "cardv").write_bytes((wd / "cardv_vi").read_bytes())
    (staged / "rootfs_en_inner.bin").write_bytes(inners["en"].read_bytes())
    (staged / "rootfs_vi_inner.bin").write_bytes(inners["vi"].read_bytes())
    (staged / "en_customer_inventory.json").write_text(inv["en"].read_text())
    (staged / "vi_customer_inventory.json").write_text(inv["vi"].read_text())
    try:
        run([sys.executable, "tools/fw/adas_plainblock_evidence.py",
             str(carved["en"]["customer.es"]), "--tag", "EN",
             "-o", str(staged / "adas_plain_en.json")], "adas-plainblocks")
        run([sys.executable, "tools/fw/stock_adas_schema_v2.py",
             "--build-dir", str(staged),
             "--adas-strings", str(out / "EVIDENCE_ADAS_STRINGS.json"),
             "-o", str(out / "EVIDENCE_STOCK_ADAS_SCHEMA.json")], "schema-regen")
    except RuntimeError as e:
        return fail(str(e))

    # diff vs canonical (images/tar-hash lines excluded? No — must match exactly)
    drifted = False
    for name in ("EVIDENCE_ADAS_STRINGS.json", "EVIDENCE_CARDV_CONTRACT.json",
                 "EVIDENCE_CARDV_SYMDIFF.json", "EVIDENCE_STOCK_ADAS_SCHEMA.json"):
        canon = args.canonical_dir / name
        if not canon.is_file():
            print(f"EVIDENCE-FAIL: canonical missing: {canon}")
            drifted = True
            continue
        a = canon.read_text(encoding="utf-8").splitlines()
        b = (out / name).read_text(encoding="utf-8").splitlines()
        # volatile fields that legitimately differ per run: method paths
        def norm(lines):
            return [ln for ln in lines if '"image":' not in ln and '"source":' not in ln
                    and "staged_build" not in ln and "carve_" not in ln and "evid_" not in ln]
        diff = list(difflib.unified_diff(norm(a), norm(b), lineterm=""))
        if diff:
            print(f"EVIDENCE-DRIFT: {name} ({len(diff)} lines)")
            print("\n".join(diff[:40]))
            drifted = True
    if drifted:
        return fail("evidence drift vs canonical — review required")
    print("EVIDENCE-OK: all artifacts verified, no drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
