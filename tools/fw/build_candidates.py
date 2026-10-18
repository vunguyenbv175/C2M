#!/usr/bin/env python3
"""P4: one-command offline candidate builder (local, needs the original base TAR).

  python3 tools/fw/build_candidates.py --en-tar <EN.tar> --workdir build/candidates [--customer-b <B-customer.es>]
  python3 tools/fw/build_candidates.py --base-tar <VI.tar> --base-profile vi --contract <private VI contract> --workdir build/work/candidates_vi [--customer-b <D5-customer.es>]

Base profiles (--base-profile {en,vi}, default en):
  - en: EN golden base (default; --contract defaults to the EN contract).
  - vi: FULL VI base. The caller must pass --contract pointing at a
    VI-derived private contract (package_contract.py output kept in
    build/work PRIVATE, never docs/, because it embeds vendor
    upgrade_script_text and raw tail bytes). The builder slices every
    non-customer payload verbatim from the base TAR inner image, so a VI
    run preserves the full unmodified VI core (kernel/rootfs/uboot/...);
    EN core is never mixed into a VI build.

Always builds Candidate A (byte-identical repack of the base TAR) via the
proven exact repack path and validates it --deep (with --base-profile).

Builds Candidate B (currently named EN_ENHANCE_IDLE.tar; for vi runs the
workflow may rename it, e.g. D5) ONLY when --customer-b is given (a
rebuilt customer.es produced on Linux by tools/fw/rebuild_customer.sh
--mode mutated, fail-closed there). B assembly:
  1. new layout: same offsets up to customer.es; misc/oneed shifted by the
     customer delta; script fatload/ubi-write numerics regenerated;
  2. assemble_inner layout mode; 3. fresh MD5 file; 4. tar_assemble package
     mode; 5. package_contract re-derivation (B contract);
  6. validate_firmware --deep on B (with --base-profile);
  7. candidate_diff vs base contract.

--oneed-cust <image> (optional, Candidate E; requires --customer-b)
additionally replaces the FINAL oneed_cust.es payload with a rebuilt Linux
image (e.g. the checked VI system-audio swap). oneed_cust.es sits after
customer.es: its offset shifts by the customer delta (like misc), its size
may shrink, the script fatload and 'ubi write oneed_cust' numerics are
regenerated, and the UNKNOWN tail moves to the new final payload end.
candidate_diff accepts the change only with --oneed-mut/--oneed-pins/
--oneed-verify (exact authorized wav swaps).

Only customer.es + oneed_cust.es (+ derived offsets/script/MD5) may differ —
candidate_diff enforces it (it requires protected.cardv/protected.adas PASS
in the deep report, which is meaningful per-profile because --base-profile
is forwarded to both validations). No vendor binaries are written outside
--workdir (gitignored).

Without --customer-b the script prints the BLOCKED next step and exits 2
(distinct from failure=1: A still built and valid).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FW = ROOT / "tools" / "fw"
INNER = "SigmastarUpgradeSD_SSC8838G.bin"

FATLOAD_RE = re.compile(
    r"(fatload\s+mmc\s+\d+\s+0x[0-9a-fA-F]+\s+\$\(SdUpgradeImage\)\s+)"
    r"(0x[0-9a-fA-F]+|\d+)(\s+)(0x[0-9a-fA-F]+|\d+)", re.I)
UBIWRITE_RE = re.compile(
    r"(ubi\s+write\s+0x[0-9a-fA-F]+\s+(\w+)\s+)(0x[0-9a-fA-F]+|\d+)", re.I)


def run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"--- {what} stdout ---\n{r.stdout[-2000:]}")
        print(f"--- {what} stderr ---\n{r.stderr[-2000:]}")
        raise SystemExit(f"{what} failed rc={r.returncode}")


def compute_b_layout(contract: dict, inner: bytes, new_customer: bytes,
                     new_oneed: bytes | None = None) -> dict:
    loads = contract["loads"]
    old_c = next(r for r in loads if r["section"] == "customer.es")
    delta = len(new_customer) - old_c["size"]
    if delta <= -(old_c["size"]):
        raise SystemExit("B layout: absurd customer delta")
    if new_oneed is not None:
        last = max(loads, key=lambda r: r["end"])
        if last["section"] != "oneed_cust.es":
            raise SystemExit("B layout: oneed_cust.es is not the final payload")
    # new offsets: stable before customer, shifted after
    after = False
    new_loads = []
    blobs: dict[str, bytes] = {}
    for r in loads:
        off = r["offset"]
        if r["section"] == "customer.es":
            after = True
            new_loads.append({**r, "offset": off, "size": len(new_customer),
                              "end": off + len(new_customer)})
            blobs["customer.es"] = new_customer
        else:
            if after:
                off = off + delta
            if r["section"] == "oneed_cust.es" and new_oneed is not None:
                new_loads.append({**r, "offset": off, "size": len(new_oneed),
                                  "end": off + len(new_oneed)})
            else:
                new_loads.append({**r, "offset": off, "end": off + r["size"]})
            key = f'{r["section"]}#{r["load_index"]}'
            if key not in blobs:
                blobs[key] = inner[r["offset"]:r["end"]]
    # regenerate script numerics (fatload lines in script order == loads order)
    script = contract["upgrade_script_text"]
    it = iter(new_loads)
    def _fat(m: re.Match) -> str:
        r = next(it)
        return f"{m.group(1)}{hex(r['size'])}{m.group(3)}{hex(r['offset'])}"
    new_script, n1 = FATLOAD_RE.subn(_fat, script)
    try:
        next(it)
        raise SystemExit("B layout: load/script fatload count mismatch")
    except StopIteration:
        pass
    cust_hex = hex(len(new_customer))
    oneed_hex = None if new_oneed is None else hex(len(new_oneed))
    def _ubi(m: re.Match) -> str:
        if m.group(2) == "customer":
            return f"{m.group(1)}{cust_hex}"
        if oneed_hex is not None and m.group(2) == "oneed_cust":
            return f"{m.group(1)}{oneed_hex}"
        return m.group(0)
    new_script, n2 = UBIWRITE_RE.subn(_ubi, new_script)
    if n1 != len(loads) or n2 != 3:
        raise SystemExit(f"B layout: expected {len(loads)} fatload + 3 ubi-write, got {n1}+{n2}")
    if not new_script.endswith("symbol"):
        raise SystemExit("B layout: script end marker disturbed")
    new_script += "\n"
    first_off = min(r["offset"] for r in new_loads)
    if len(new_script) >= first_off:
        raise SystemExit("B layout: regenerated script overruns first payload")
    last_end = max(r["end"] for r in new_loads)
    tail = contract["tail_unknown"]
    return {"script_text": new_script, "loads": new_loads,
            "tail_hex": tail["hex"], "tail_offset": last_end,
            "total_size": last_end + tail["len"], "delta": delta,
            "oneed_delta": (None if new_oneed is None else
                            len(new_oneed) - next(r["size"] for r in loads
                                                  if r["section"] == "oneed_cust.es"))}


def main() -> int:
    ap = argparse.ArgumentParser()
    base_src = ap.add_mutually_exclusive_group(required=True)
    base_src.add_argument("--en-tar", type=Path, default=None,
                          help="base EN TAR (compatible alias of --base-tar for en runs)")
    base_src.add_argument("--base-tar", type=Path, default=None,
                          help="base TAR for the selected --base-profile "
                          "(mutually exclusive with --en-tar)")
    ap.add_argument("--base-profile", choices=("en", "vi"), default="en",
                    help="base firmware profile (default: en). 'vi' builds "
                    "a FULL VI-base candidate; pass --contract pointing at "
                    "a VI-derived private contract in build/work (never "
                    "docs/). No custom protected-hash overrides exist.")
    ap.add_argument("--workdir", type=Path, default=Path("build/candidates"))
    ap.add_argument("--customer-b", type=Path, default=None)
    ap.add_argument("--oneed-cust", type=Path, default=None,
                    help="rebuilt oneed_cust.es replacing the FINAL payload "
                         "(Candidate E; requires --customer-b)")
    ap.add_argument("--oneed-mut", type=Path, default=None,
                    help="mutate_oneed.py manifest (forwarded to candidate_diff)")
    ap.add_argument("--oneed-pins", type=Path, default=None,
                    help="pinned swap list JSON (forwarded to candidate_diff)")
    ap.add_argument("--oneed-verify", type=Path, default=None,
                    help="verify report JSON (forwarded to candidate_diff)")
    ap.add_argument("--contract", type=Path,
                    default=Path("docs/firmware/EN_PACKAGE_CONTRACT.json"))
    args = ap.parse_args()
    if args.oneed_cust is not None and args.customer_b is None:
        ap.error("--oneed-cust requires --customer-b (build both together)")
    if any(v is not None for v in (args.oneed_mut, args.oneed_pins, args.oneed_verify)):
        if not all(v is not None for v in (args.oneed_mut, args.oneed_pins, args.oneed_verify)):
            ap.error("--oneed-mut/--oneed-pins/--oneed-verify must be given together")
        if args.oneed_cust is None:
            ap.error("oneed diff authorization without --oneed-cust")
    base_tar: Path = args.base_tar if args.base_tar is not None else args.en_tar
    if args.base_profile == "vi":
        from validate_firmware import VI_TAR_SHA256
        contract_path = (ROOT / args.contract).resolve()
        if not any(contract_path.is_relative_to(ROOT / name) for name in ("build", "work")):
            ap.error("VI contract must stay in private build/work")
        if hashlib.sha256(base_tar.read_bytes()).hexdigest() != VI_TAR_SHA256:
            ap.error("VI base TAR independent SHA256 pin mismatch")
    py = sys.executable
    wd = args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    contract = json.loads((ROOT / args.contract).read_text(encoding="utf-8"))

    # ---- Candidate A (always) ----
    run([py, "tools/fw/repack_firmware.py", "--tar", str(base_tar),
         "--base-profile", args.base_profile, "--contract", str(args.contract),
         "--out", str(wd / "EN_REPACK_GOLDEN.tar"),
         "--report", str(wd / "repack_A.json")], "repack-A")
    run([py, "tools/fw/validate_firmware.py", "--tar", str(wd / "EN_REPACK_GOLDEN.tar"),
         "--contract", str(args.contract),
         "--report-json", str(wd / "validate_A_deep.json"),
         "--report-md", str(wd / "validate_A_deep.md"),
         "--deep", "--base-profile", args.base_profile], "validate-A")
    print("CANDIDATE-A: OK (byte-identical golden, VALID --deep)")

    if args.customer_b is None:
        print("CANDIDATE-B: BLOCKED — no --customer-b image. Next step on Linux:\n"
              "  bash tools/fw/rebuild_customer.sh --mode mutated ...\n"
              "then re-run this script with --customer-b <image>.")
        return 2

    # ---- Candidate B ----
    # Every non-customer payload is sliced verbatim from the BASE inner
    # image, so a vi run keeps the full unmodified VI core (never EN core).
    with tarfile.open(base_tar, "r") as tf:
        inner = tf.extractfile(INNER).read()
        sysver = tf.extractfile("sysVer.txt").read()
        adas_up = tf.extractfile("adas_upgrade.sh").read()
    new_customer = args.customer_b.read_bytes()
    new_oneed = args.oneed_cust.read_bytes() if args.oneed_cust is not None else None
    layout = compute_b_layout(contract, inner, new_customer, new_oneed)

    payload_dir = wd / "b_payloads"
    payload_dir.mkdir(exist_ok=True)
    spec_payloads = []
    seen: dict[str, int] = {}
    for r in layout["loads"]:
        if r["section"] == "customer.es":
            blob = new_customer
        elif r["section"] == "oneed_cust.es" and new_oneed is not None:
            blob = new_oneed
        else:
            key = f'{r["section"]}#{r["load_index"]}'
            n = seen.get(r["section"], 0)
            seen[r["section"]] = n + 1
            # slice from ORIGINAL inner at ORIGINAL offsets
            orig = next(x for x in contract["loads"]
                        if x["section"] == r["section"] and x["load_index"] == r["load_index"])
            blob = inner[orig["offset"]:orig["end"]]
        fname = f'{r["section"]}.{r["load_index"]}.bin'
        (payload_dir / fname).write_bytes(blob)
        spec_payloads.append({"section": r["section"], "load_index": r["load_index"],
                              "offset": r["offset"], "size": len(blob), "file": fname})
    (wd / "b_layout.json").write_text(json.dumps(
        {"script_text": layout["script_text"], "payloads": spec_payloads,
         "tail_hex": layout["tail_hex"], "tail_offset": layout["tail_offset"],
         "total_size": layout["total_size"]}, indent=2), encoding="utf-8")
    run([py, "tools/fw/assemble_inner.py", "--mode", "layout",
         "--layout-json", str(wd / "b_layout.json"), "--payload-dir", str(payload_dir),
         "--out", str(wd / "inner_B.bin"), "--report", str(wd / "inner_B.json")],
        "assemble-inner-B")
    inner_b = (wd / "inner_B.bin").read_bytes()
    md5_b = hashlib.md5(inner_b).hexdigest() + "  SigmastarUpgradeSD_SSC8838G.bin\n"
    (wd / "minieye_firmware_B.md5").write_text(md5_b, encoding="utf-8")
    (wd / "sysVer_B.txt").write_bytes(sysver)
    (wd / "adas_upgrade_B.sh").write_bytes(adas_up)
    (wd / "inner_B_for_tar.bin").write_bytes(inner_b)
    members = [{"name": INNER, "file": str(wd / "inner_B_for_tar.bin")},
               {"name": "sysVer.txt", "file": str(wd / "sysVer_B.txt")},
               {"name": "minieye_firmware.md5", "file": str(wd / "minieye_firmware_B.md5")},
               {"name": "adas_upgrade.sh", "file": str(wd / "adas_upgrade_B.sh")}]
    (wd / "b_members.json").write_text(json.dumps(members, indent=2), encoding="utf-8")
    run([py, "tools/fw/tar_assemble.py", "--mode", "package", "--tar", str(base_tar),
         "--contract", str(args.contract), "--members-json", str(wd / "b_members.json"),
         "--out", str(wd / "EN_ENHANCE_IDLE.tar"), "--report", str(wd / "tar_B.json")],
        "tar-B")
    run([py, "tools/fw/package_contract.py", "--tar", str(wd / "EN_ENHANCE_IDLE.tar"),
         "--out-json", str(wd / "EN_PACKAGE_CONTRACT_B.json"),
         "--out-md", str(wd / "EN_PACKAGE_CONTRACT_B.md")], "contract-B")
    run([py, "tools/fw/validate_firmware.py", "--tar", str(wd / "EN_ENHANCE_IDLE.tar"),
         "--contract", str(wd / "EN_PACKAGE_CONTRACT_B.json"),
         "--report-json", str(wd / "validate_B_deep.json"),
         "--report-md", str(wd / "validate_B_deep.md"),
         "--deep", "--base-profile", args.base_profile], "validate-B")
    diff_cmd = [py, "tools/fw/candidate_diff.py", "--base", str(args.contract),
                "--cand", str(wd / "EN_PACKAGE_CONTRACT_B.json"),
                "--deep-report", str(wd / "validate_B_deep.json"),
                "--out", str(wd / "candidate_B_diff.json")]
    if args.oneed_mut is not None:
        diff_cmd += ["--oneed-mut", str(args.oneed_mut),
                     "--oneed-pins", str(args.oneed_pins),
                     "--oneed-verify", str(args.oneed_verify)]
    r = subprocess.run(
        diff_cmd,
        cwd=ROOT, capture_output=True, text=True)
    print(r.stdout[-3000:])
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise SystemExit("candidate-diff BLOCKED the build (see above)")
    print("CANDIDATE-B: OK (allowlist diff proven; see candidate_B_diff.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
