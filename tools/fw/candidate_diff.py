#!/usr/bin/env python3
"""Prove a Candidate-B package differs from EN golden ONLY where authorized.

Compares --base (EN_PACKAGE_CONTRACT.json) vs --cand (B contract re-derived
by package_contract.py from the B TAR) plus the --deep validation report of
the B TAR. Verdict ALLOWLIST-OK / BLOCK (nonzero exit on BLOCK).

Authorized differences (everything else must be identical):
  outer: SigmastarUpgradeSD_SSC8838G.bin + minieye_firmware.md5 bytes
         (new inner + new MD5); sysVer.txt + adas_upgrade.sh identical.
  inner: customer.es payload bytes (new UBIFS) + its size; misc/oneed_cust
         OFFSETS may shift by exactly the customer delta (their SHAs must be
         identical); all other payload SHAs identical; UNKNOWN tail identical.
  script: numeric args of fatload/ubi-write lines for customer.es, misc.es,
         oneed_cust.es only (sizes/offsets consistent with the new layout).
  protected (from --deep-report): cardv + adas SHAs unchanged vs golden.

Usage:
  python3 tools/fw/candidate_diff.py --base EN.json --cand B.json \\
      --deep-report validate_b_deep.json --out diff_report.json
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

FATLOAD_RE = re.compile(
    r"fatload\s+mmc\s+\d+\s+0x[0-9a-fA-F]+\s+\$\(SdUpgradeImage\)\s+"
    r"(0x[0-9a-fA-F]+|\d+)\s+(0x[0-9a-fA-F]+|\d+)", re.I)
UBIWRITE_RE = re.compile(r"ubi\s+write\s+0x[0-9a-fA-F]+\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)", re.I)


def loads_by_section(contract: dict) -> dict:
    out: dict = {}
    for r in contract["loads"]:
        out.setdefault(r["section"], []).append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--cand", type=Path, required=True)
    ap.add_argument("--deep-report", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    base = json.loads(args.base.read_text(encoding="utf-8"))
    cand = json.loads(args.cand.read_text(encoding="utf-8"))
    deep = json.loads(args.deep_report.read_text(encoding="utf-8"))
    blocks: list[str] = []
    notes: list[str] = []

    def block(msg: str):
        blocks.append(msg)

    # outer members
    bm = {m["name"]: m for m in base["outer_members"]}
    cm = {m["name"]: m for m in cand["outer_members"]}
    if set(bm) != set(cm) or base["outer_order"] != cand["outer_order"]:
        block(f"outer member set/order changed: {cand['outer_order']}")
    for n in ("sysVer.txt", "adas_upgrade.sh"):
        if bm[n]["sha256"] != cm[n]["sha256"]:
            block(f"outer {n} changed (protected)")
    if bm["minieye_firmware.md5"]["sha256"] == cm["minieye_firmware.md5"]["sha256"]:
        block("md5 file unchanged while inner changed (stale MD5)")
    if cand["inner_sha256"] == base["inner_sha256"]:
        block("inner image unchanged (nothing to differentiate B)")

    # payloads
    bl, cl = loads_by_section(base), loads_by_section(cand)
    if set(bl) != set(cl):
        block(f"load section set changed: {sorted(set(bl) ^ set(cl))}")
    delta = None
    for sec in sorted(set(bl) & set(cl)):
        for b, c in zip(sorted(bl[sec], key=lambda r: r["load_index"]),
                        sorted(cl[sec], key=lambda r: r["load_index"])):
            if sec == "customer.es":
                if b["sha256"] == c["sha256"]:
                    block("customer.es unchanged (expected the B mutation)")
                if b["offset"] != c["offset"]:
                    block("customer.es offset moved (must stay for stable layout)")
                if delta is None:
                    delta = c["size"] - b["size"]
                notes.append(f"customer.es size {b['size']} -> {c['size']} (delta {c['size'] - b['size']})")
            else:
                if b["sha256"] != c["sha256"]:
                    block(f"{sec}#{b['load_index']} payload bytes changed (protected)")
                if b["size"] != c["size"]:
                    block(f"{sec}#{b['load_index']} size changed")
    if delta is None:
        block("could not establish customer delta")
        delta = 0
    for sec in ("misc.es", "oneed_cust.es"):
        for b, c in zip(sorted(bl.get(sec, []), key=lambda r: r["load_index"]),
                        sorted(cl.get(sec, []), key=lambda r: r["load_index"])):
            want = b["offset"] + (delta if delta else 0)
            # sections BEFORE customer keep offsets; misc/oneed are AFTER
            if sec in ("misc.es", "oneed_cust.es") and c["offset"] != want:
                block(f"{sec} offset {hex(c['offset'])} != base {hex(b['offset'])} + delta {hex(delta)}")
    for sec in ("cis.es", "ipl.es", "ipl_cust.es", "uboot.es", "kernel.es",
                "rootfs.es", "miservice.es"):
        for b, c in zip(sorted(bl.get(sec, []), key=lambda r: r["load_index"]),
                        sorted(cl.get(sec, []), key=lambda r: r["load_index"])):
            if b["offset"] != c["offset"]:
                block(f"{sec} offset moved (must be stable before customer)")

    # UNKNOWN tail identical
    if base["tail_unknown"]["hex"] != cand["tail_unknown"]["hex"]:
        block("UNKNOWN tail changed (must be preserved verbatim)")

    # script numerics confined to customer/misc/oneed lines
    bf = [(int(m.group(1), 0), int(m.group(2), 0)) for m in FATLOAD_RE.finditer(base["upgrade_script_text"])]
    cf = [(int(m.group(1), 0), int(m.group(2), 0)) for m in FATLOAD_RE.finditer(cand["upgrade_script_text"])]
    if len(bf) != len(cf):
        block(f"fatload line count {len(bf)} -> {len(cf)}")
    else:
        changed = [i for i, (x, y) in enumerate(zip(bf, cf)) if x != y]
        # fatload index order follows script section order; customer=idx of
        # customer.es load, misc/oneed after it. Derive from loads order:
        order = []
        for r in base["loads"]:
            order.append(r["section"])
        allow = {i for i, s in enumerate(order) if s in ("customer.es", "misc.es", "oneed_cust.es")}
        bad = [i for i in changed if i not in allow]
        if bad:
            block(f"fatload numerics changed outside customer/misc/oneed: lines {bad}")
        notes.append(f"fatload lines changed: {changed} (allow {sorted(allow)})")
    bw = {m.group(1): int(m.group(2), 0) for m in UBIWRITE_RE.finditer(base["upgrade_script_text"])}
    cw = {m.group(1): int(m.group(2), 0) for m in UBIWRITE_RE.finditer(cand["upgrade_script_text"])}
    if set(bw) != set(cw):
        block(f"ubi write volumes changed: {sorted(set(bw) ^ set(cw))}")
    for vol in set(bw) & set(cw):
        if vol == "customer" and bw[vol] == cw[vol]:
            block("ubi write customer size not updated")
        if vol != "customer" and bw[vol] != cw[vol]:
            block(f"ubi write {vol} size changed")

    # protected deep hashes from the B validation report
    prot = {r["check"]: r for r in deep.get("checks", [])}
    for key, want in (("protected.cardv", None), ("protected.adas", None)):
        row = prot.get(key)
        if row is None or row.get("result") != "PASS":
            block(f"B deep report missing PASS for {key}")
    if deep.get("verdict") not in ("VALID", "INCOMPLETE_EVIDENCE"):
        block(f"B deep validation verdict is {deep.get('verdict')}")

    verdict = "BLOCK" if blocks else "ALLOWLIST-OK"
    doc = {"verdict": verdict, "blocks": blocks, "notes": notes,
           "customer_delta": delta,
           "base_inner": base["inner_sha256"], "cand_inner": cand["inner_sha256"]}
    args.out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps(doc, indent=2))
    return 0 if verdict == "ALLOWLIST-OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
