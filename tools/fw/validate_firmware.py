#!/usr/bin/env python3
"""WS3: Independent firmware validator (separate from the builder).

Validates a candidate EN package against the package contract. Produces a
human-readable (.md) and machine-readable (.json) report with verdict:

  VALID | INVALID | INCOMPLETE_EVIDENCE

Rules:
  - UNKNOWN is never converted into PASS. Anything unaccounted -> INVALID
    (corruption) or INCOMPLETE_EVIDENCE (missing evidence, e.g. --deep
    extraction unavailable).
  - All mandatory checks propagate nonzero exit (no fake-green): INVALID and
    INCOMPLETE_EVIDENCE both return nonzero; only VALID returns 0.

Checks (package layer, no trust in builder internals):
  outer member set/order/sizes/shas | sysVer | package MD5 vs md5(inner) |
  upgrade-script marker + script SHA | per-section offsets/sizes/bounds/shas |
  gap fill 0xFF | UNKNOWN tail exact match | byte accounting |
  adas_upgrade.sh SHA | protected-component hashes (--deep only)

Protected EN components (--deep): cardv + adas SHA-256 re-extracted from the
candidate's own rootfs/customer payloads (read-only UBIFS/cpio path).
Without --deep these rows are INCOMPLETE (validator says so explicitly).

Usage:
  python3 tools/fw/validate_firmware.py --tar build/EN_REPACK_GOLDEN.tar \\
      --contract docs/firmware/EN_PACKAGE_CONTRACT.json \\
      --report-json build/validate_report.json --report-md build/validate_report.md [--deep]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INNER = "SigmastarUpgradeSD_SSC8838G.bin"
END_MARKER = b"% <- this is end of script symbol"

# Golden protected-component hashes (EN baseline, independently verified).
PROTECTED = {
    "cardv_sha256": "344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c",
    "adas_sha256": "0dcc69828078e4e243b17ca9508d15ca6b47a3c2f6ec59d6c20bc5b5e9c94043",
}


def sha256_bytes(d: bytes) -> str:
    return hashlib.sha256(d).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tar", type=Path, required=True)
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--report-json", type=Path, required=True)
    ap.add_argument("--report-md", type=Path, required=True)
    ap.add_argument("--deep", action="store_true",
                    help="also re-extract cardv/adas from candidate payloads")
    args = ap.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    rows: list[dict] = []

    def check(name: str, ok: bool, detail: str, evidence: str = ""):
        rows.append({"check": name, "result": "PASS" if ok else "FAIL",
                     "detail": detail, "evidence": evidence})

    deep_incomplete: list[str] = []
    try:
        tf = tarfile.open(args.tar, "r")
        members = tf.getmembers()
        names = [m.name for m in members]
        blobs = {m.name: tf.extractfile(m).read() for m in members}
    except Exception as e:
        check("tar.readable", False, f"cannot read TAR: {e}")
        return _finish(args, rows, "INVALID", deep_incomplete)

    check("outer.member_set_order", names == contract["outer_order"],
          f"got {names}; want {contract['outer_order']}")
    for exp in contract["outer_members"]:
        got = blobs.get(exp["name"])
        if got is None:
            check(f"outer.member.{exp['name']}", False, "MISSING member")
        else:
            check(f"outer.member.{exp['name']}",
                  len(got) == exp["size"] and sha256_bytes(got) == exp["sha256"],
                  f"size {len(got)} vs {exp['size']}; sha {sha256_bytes(got)[:16]}… vs {exp['sha256'][:16]}…")

    inner = blobs.get(INNER)
    if inner is None:
        check("inner.present", False, "missing inner upgrade image")
        return _finish(args, rows, "INVALID", deep_incomplete)

    # sysVer
    sysver = blobs.get("sysVer.txt", b"").decode("ascii", "replace")
    check("sysVer", sysver == contract["sysVer_txt"],
          f"got {sysver!r}; want {contract['sysVer_txt']!r}")
    # package MD5
    md5file = blobs.get("minieye_firmware.md5", b"").decode("ascii", "replace")
    listed = (md5file.split() or [""])[0]
    actual_md5 = hashlib.md5(inner).hexdigest()
    check("package.md5", listed == actual_md5,
          f"listed {listed}; md5(inner) {actual_md5}")
    # adas_upgrade.sh
    check("adas_upgrade_sh",
          sha256_bytes(blobs.get("adas_upgrade.sh", b"")) == contract["adas_upgrade_sh_sha256"],
          "second-stage SD script hash")
    # script marker + sha
    script_end = contract["upgrade_script_end"]
    check("script.end_marker", inner.find(END_MARKER) + len(END_MARKER) == script_end,
          f"marker end at {inner.find(END_MARKER)}; want script_end {script_end}")
    check("script.sha", sha256_bytes(inner[:script_end]) == contract["upgrade_script_sha256"],
          "U-Boot script bytes hash")
    # payloads
    for r in contract["loads"]:
        off, end = r["offset"], r["end"]
        if not (0 <= off <= end <= len(inner)):
            check(f"payload.{r['section']}#{r['load_index']}.bounds", False,
                  f"offset {hex(off)} size {hex(r['size'])} outside image {hex(len(inner))}")
            continue
        chunk = inner[off:end]
        check(f"payload.{r['section']}#{r['load_index']}.sha",
              sha256_bytes(chunk) == r["sha256"],
              f"{r['offset_hex']} + {r['size_hex']}")
    # gaps 0xFF
    for g in contract["inter_payload_gaps"]:
        a, b = g["range"]
        seg = inner[a:b]
        check(f"gap.{hex(a)}..{hex(b)}.ff", set(seg) == {0xFF} if seg else True,
              f"{len(seg)} bytes fill={'0xFF' if (not seg or set(seg) == {0xFF}) else 'MIXED'}")
    # tail exact
    tail = contract["tail_unknown"]
    tseg = inner[tail["offset"]:tail["offset"] + tail["len"]]
    check("tail.unknown_exact", tseg.hex() == tail["hex"],
          f"UNKNOWN tail must match verbatim ({tail['len']} B)")
    # accounting
    a = contract["accounting"]
    check("accounting.total", len(inner) == a["total"] and a["check"],
          f"inner {len(inner)} vs contract total {a['total']}")

    # deep protected components
    if args.deep:
        try:
            sys.path.insert(0, str(ROOT / "tools" / "fw"))
            import gzip
            from extract_rootfs_cpio import iter_cpio
            from ubifs_extract_file import extract as ubifs_extract
            import tempfile
            # locate rootfs/customer payloads via contract offsets
            by_section = {}
            for r in contract["loads"]:
                by_section.setdefault(r["section"], r)
            rootfs_blob = inner[by_section["rootfs.es"]["offset"]:by_section["rootfs.es"]["end"]]
            cust_blob = inner[by_section["customer.es"]["offset"]:by_section["customer.es"]["end"]]
            rootfs_inner = gzip.decompress(rootfs_blob)
            cpio = dict(iter_cpio(rootfs_inner))
            cardv = cpio.get("bootconfig/bin/cardv")
            if cardv is None:
                check("protected.cardv", False, "cardv not found in candidate rootfs cpio")
            else:
                check("protected.cardv", sha256_bytes(cardv) == PROTECTED["cardv_sha256"],
                      f"cardv sha {sha256_bytes(cardv)[:16]}… vs golden {PROTECTED['cardv_sha256'][:16]}…")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".customer.es") as f:
                f.write(cust_blob)
                tmp = Path(f.name)
            try:
                adas, _ = ubifs_extract(tmp, "/minieye/adas/adas")
            finally:
                tmp.unlink(missing_ok=True)
            check("protected.adas", sha256_bytes(adas) == PROTECTED["adas_sha256"],
                  f"adas sha {sha256_bytes(adas)[:16]}… vs golden {PROTECTED['adas_sha256'][:16]}…")
        except Exception as e:
            deep_incomplete.append(f"deep extraction failed: {e}")
            check("protected.deep", False, f"INCOMPLETE: {e}")
    else:
        deep_incomplete.append("protected cardv/adas not re-extracted (no --deep)")

    fails = [r for r in rows if r["result"] == "FAIL"]
    if fails:
        verdict = "INVALID"
    elif deep_incomplete:
        verdict = "INCOMPLETE_EVIDENCE"
    else:
        verdict = "VALID"
    # NOTE: package-layer-only validation without --deep is INCOMPLETE by design
    # (protected hashes unverified). Callers wanting a strict VALID must pass --deep.
    return _finish(args, rows, verdict, deep_incomplete)


def _finish(args, rows, verdict: str, incomplete_notes: list[str]) -> int:
    doc = {"target": str(args.tar), "contract": str(args.contract),
           "verdict": verdict, "checks": rows,
           "incomplete_notes": incomplete_notes,
           "protected_golden": PROTECTED}
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    md = [f"# Firmware validation report — `{verdict}`\n",
          f"Target: `{args.tar}`\nContract: `{args.contract}`\n",
          "| check | result | detail |", "|---|---|---|"]
    for r in rows:
        md.append(f"| {r['check']} | {r['result']} | {r['detail']} |")
    if incomplete_notes:
        md.append("\n## Incomplete evidence\n")
        md += [f"- {n}" for n in incomplete_notes]
    md.append(f"\nVerdict: **{verdict}** (UNKNOWN never counts as PASS)\n")
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:8]), f"\n... verdict={verdict} ({len(rows)} checks)")
    return 0 if verdict == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
