#!/usr/bin/env python3
"""Synthetic (no-vendor) tests for the Candidate-B pipeline logic.

Covers, without any firmware:
  - ubifs manifest --compare (identical / content / mode / add / remove);
  - mutate_customer guards (wrong base, double-hook, success shape);
  - verify_b_manifest (OK + violation);
  - candidate_diff allowlist (OK + kernel-tamper + tail + deep verdict);
  - assemble_inner layout mode (round-trip + overlap rejection);
  - tar_assemble golden + package modes on a synthetic TAR.
Run: python3 tests/test_candidate_b.py
"""
from __future__ import annotations
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sh(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_py(tool: str, *argv: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, f"tools/fw/{tool}", *argv],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)[-3000:]


def manifest(entries: list[dict]) -> dict:
    return {"image": "synth", "image_bytes": 1, "node_count": 1,
            "entry_count": len(entries), "entries": entries}


def reg(path: str, data: bytes, mode: int = 0o755, mtime: int = 1691062662) -> dict:
    return {"path": path, "inode": 1, "type": "reg", "mode": mode,
            "mode_oct": oct(mode), "uid": 1001, "gid": 1001,
            "size": len(data), "mtime": mtime, "sha256": sh(data)}


def mini_contract(customer_size: int, cust_off: int, misc_off: int,
                  kernel_sha: str, tail_hex: str = "001122",
                  script_extra: str = "") -> dict:
    fat = (f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {hex(0x100)} 0x4000\n"
           f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {hex(customer_size)} {hex(cust_off)}\n"
           f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {hex(0x200)} {hex(misc_off)}\n")
    ubi = (f"ubi write 0x21000000 customer {hex(customer_size)}\n"
           f"ubi write 0x21000000 misc 0x200\n")
    script = ("# File Partition: kernel.es\n" + fat.splitlines()[0] +
              "\n# File Partition: customer.es\n" + fat.splitlines()[1] +
              "\n# File Partition: misc.es\n" + fat.splitlines()[2] +
              "\n% <- this is end of script symbol" + script_extra)
    return {
        "outer_order": ["SigmastarUpgradeSD_SSC8838G.bin", "sysVer.txt",
                        "minieye_firmware.md5", "adas_upgrade.sh"],
        "outer_members": [
            {"name": "SigmastarUpgradeSD_SSC8838G.bin", "size": 9, "sha256": sh(b"inner")},
            {"name": "sysVer.txt", "size": 3, "sha256": sh(b"sys")},
            {"name": "minieye_firmware.md5", "size": 4, "sha256": sh(b"md5x")},
            {"name": "adas_upgrade.sh", "size": 4, "sha256": sh(b"adas")},
        ],
        "inner_sha256": sh(b"inner"),
        "upgrade_script_text": script,
        "loads": [
            {"section": "kernel.es", "load_index": 0, "offset": 0x4000,
             "end": 0x4100, "size": 0x100, "sha256": kernel_sha, "within_image": True},
            {"section": "customer.es", "load_index": 0, "offset": cust_off,
             "end": cust_off + customer_size, "size": customer_size,
             "sha256": sh(b"c" * customer_size), "within_image": True},
            {"section": "misc.es", "load_index": 0, "offset": misc_off,
             "end": misc_off + 0x200, "size": 0x200,
             "sha256": sh(b"m" * 0x200), "within_image": True},
        ],
        "tail_unknown": {"offset": misc_off + 0x200, "len": 3, "hex": tail_hex},
    }


def main() -> int:
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. manifest compare
        a = manifest([reg("/f", b"hello"), reg("/g", b"world")])
        (tmp / "a.json").write_text(json.dumps(a))
        (tmp / "b.json").write_text(json.dumps(a))
        rc, _ = run_py("ubifs_manifest.py", "--compare", str(tmp / "a.json"), str(tmp / "b.json"))
        if rc != 0:
            fails.append("manifest identical not OK")
        b2 = manifest([reg("/f", b"HELLO"), reg("/g", b"world")])
        (tmp / "b2.json").write_text(json.dumps(b2))
        rc, out = run_py("ubifs_manifest.py", "--compare", str(tmp / "a.json"), str(tmp / "b2.json"))
        if rc == 0 or "CHANGED /f" not in out:
            fails.append("manifest content diff missed")
        b3 = manifest([reg("/f", b"hello", mode=0o644), reg("/g", b"world")])
        (tmp / "b3.json").write_text(json.dumps(b3))
        rc, _ = run_py("ubifs_manifest.py", "--compare", str(tmp / "a.json"), str(tmp / "b3.json"))
        if rc == 0:
            fails.append("manifest mode diff missed")
        b4 = manifest([reg("/f", b"hello")])
        (tmp / "b4.json").write_text(json.dumps(b4))
        rc, out = run_py("ubifs_manifest.py", "--compare", str(tmp / "a.json"), str(tmp / "b4.json"))
        if rc == 0 or "REMOVED /g" not in out:
            fails.append("manifest removal missed")

        # 2. mutate guards + success
        tree = tmp / "tree"
        (tree / "wifi").mkdir(parents=True)
        hook_bytes = b"#!/bin/sh\necho hi\nsleep 1\n"
        (tree / "wifi" / "rcInsDriver.sh").write_bytes(hook_bytes)
        (tmp / "idle.bin").write_bytes(b"ARMFAKE")
        stock = manifest([dict(reg("/wifi/rcInsDriver.sh", hook_bytes),
                               sha256=sh(hook_bytes),
                               size=len(hook_bytes))])
        (tmp / "stock.json").write_text(json.dumps(stock))
        rc, _ = run_py("mutate_customer.py", "--tree", str(tree),
                       "--manifest", str(tmp / "stock.json"),
                       "--idle-bin", str(tmp / "idle.bin"),
                       "--out-manifest", str(tmp / "mut.json"))
        if rc != 0:
            fails.append("mutate clean tree failed")
        else:
            mut = json.loads((tmp / "mut.json").read_text())
            hook_new = (tree / "wifi" / "rcInsDriver.sh").read_bytes()
            if not hook_new.endswith(b"/customer/c2m/c2m-idle &\n"):
                fails.append("hook line not appended")
            if not (tree / "c2m" / "c2m-idle").is_file():
                fails.append("idle binary not placed")
            # double-hook must fail
            rc, _ = run_py("mutate_customer.py", "--tree", str(tree),
                           "--manifest", str(tmp / "stock.json"),
                           "--idle-bin", str(tmp / "idle.bin"),
                           "--out-manifest", str(tmp / "mut2.json"))
            if rc == 0:
                fails.append("double-hook not rejected")
            # verify_b_manifest OK on actual
            actual = manifest([
                reg("/wifi/rcInsDriver.sh", hook_new),
                reg("/c2m/c2m-idle", b"ARMFAKE", mode=0o755),
            ])
            (tmp / "actual.json").write_text(json.dumps(actual))
            r = subprocess.run(
                [sys.executable, "tools/fw/verify_b_manifest.py", "--stock",
                 str(tmp / "stock.json"), "--mut", str(tmp / "mut.json"),
                 "--actual", str(tmp / "actual.json")],
                cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                fails.append("verify_b_manifest OK case failed: " + r.stdout[-500:])
            # violation: unexpected extra path
            actual_bad = manifest([
                reg("/wifi/rcInsDriver.sh", hook_new),
                reg("/c2m/c2m-idle", b"ARMFAKE", mode=0o755),
                reg("/evil", b"x"),
            ])
            (tmp / "actualbad.json").write_text(json.dumps(actual_bad))
            r = subprocess.run(
                [sys.executable, "tools/fw/verify_b_manifest.py", "--stock",
                 str(tmp / "stock.json"), "--mut", str(tmp / "mut.json"),
                 "--actual", str(tmp / "actualbad.json")],
                cwd=ROOT, capture_output=True, text=True)
            if r.returncode == 0:
                fails.append("verify_b_manifest extra path not BLOCKED")
        # wrong base manifest must fail
        tree2 = tmp / "tree2"
        (tree2 / "wifi").mkdir(parents=True)
        (tree2 / "wifi" / "rcInsDriver.sh").write_bytes(b"#!/bin/sh\necho EVIL\n")
        rc, _ = run_py("mutate_customer.py", "--tree", str(tree2),
                       "--manifest", str(tmp / "stock.json"),
                       "--idle-bin", str(tmp / "idle.bin"),
                       "--out-manifest", str(tmp / "mut3.json"))
        if rc == 0:
            fails.append("mutate with tampered base not rejected")

        # 3. candidate_diff allowlist
        ksha = sh(b"k" * 0x100)
        base = mini_contract(0x300, 0x5000, 0x6000, ksha)
        (tmp / "base.json").write_text(json.dumps(base))
        cand = mini_contract(0x340, 0x5000, 0x6040, ksha)  # +0x40 delta
        cand["outer_members"][0]["sha256"] = sh(b"inner2")
        cand["inner_sha256"] = sh(b"inner2")
        cand["outer_members"][2]["sha256"] = sh(b"md5y")
        cand["loads"][1]["sha256"] = sh(b"c" * 0x340)
        (tmp / "cand.json").write_text(json.dumps(cand))
        deep = {"verdict": "VALID",
                "checks": [{"check": "protected.cardv", "result": "PASS"},
                           {"check": "protected.adas", "result": "PASS"}]}
        (tmp / "deep.json").write_text(json.dumps(deep))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand.json"), "--deep-report", str(tmp / "deep.json"),
             "--out", str(tmp / "diff.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            fails.append("allowlist OK case BLOCKED: " + r.stdout[-600:] + " ERR:" + r.stderr[-600:])
        # kernel tamper -> BLOCK
        cand2 = json.loads((tmp / "cand.json").read_text())
        cand2["loads"][0]["sha256"] = sh(b"evil")
        (tmp / "cand2.json").write_text(json.dumps(cand2))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand2.json"), "--deep-report", str(tmp / "deep.json"),
             "--out", str(tmp / "diff2.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            fails.append("kernel payload tamper not BLOCKED")
        # tail change -> BLOCK
        cand3 = json.loads((tmp / "cand.json").read_text())
        cand3["tail_unknown"]["hex"] = "ffffff"
        (tmp / "cand3.json").write_text(json.dumps(cand3))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand3.json"), "--deep-report", str(tmp / "deep.json"),
             "--out", str(tmp / "diff3.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            fails.append("tail change not BLOCKED")
        # bad deep verdict -> BLOCK
        deep_bad = {"verdict": "INVALID", "checks": []}
        (tmp / "deepbad.json").write_text(json.dumps(deep_bad))
        r = subprocess.run(
            [sys.executable, "tools/fw/candidate_diff.py", "--base", str(tmp / "base.json"),
             "--cand", str(tmp / "cand.json"), "--deep-report", str(tmp / "deepbad.json"),
             "--out", str(tmp / "diff4.json")], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            fails.append("bad deep verdict not BLOCKED")

        # 4. assemble_inner layout round-trip + overlap rejection
        layout = {"script_text": "HDR\n% <- this is end of script symbol\n",
                  "payloads": [{"section": "a.es", "load_index": 0, "offset": 0x100,
                                "size": 4, "file": "p0.bin"}],
                  "tail_hex": "aa", "tail_offset": 0x104, "total_size": 0x105}
        (tmp / "layout.json").write_text(json.dumps(layout))
        (tmp / "p0.bin").write_bytes(b"DATA")
        rc, _ = run_py("assemble_inner.py", "--mode", "layout",
                       "--layout-json", str(tmp / "layout.json"),
                       "--payload-dir", str(tmp), "--out", str(tmp / "inner.bin"))
        if rc != 0:
            fails.append("assemble layout failed")
        else:
            d = (tmp / "inner.bin").read_bytes()
            if d[0x100:0x104] != b"DATA" or d[-1:] != b"\xaa" or d[0x40] != 0xFF:
                fails.append("assemble layout bytes wrong")
        bad_layout = dict(layout, payloads=[
            {"section": "a.es", "load_index": 0, "offset": 0x10, "size": 4, "file": "p0.bin"}])
        (tmp / "badlayout.json").write_text(json.dumps(bad_layout))
        rc, _ = run_py("assemble_inner.py", "--mode", "layout",
                       "--layout-json", str(tmp / "badlayout.json"),
                       "--payload-dir", str(tmp), "--out", str(tmp / "inner2.bin"))
        if rc == 0:
            fails.append("assemble overlap not rejected")

        # 5. tar_assemble on a synthetic TAR
        star = tmp / "synth.tar"
        members = [("SigmastarUpgradeSD_SSC8838G.bin", b"1" * 100),
                   ("sysVer.txt", b"sys"), ("minieye_firmware.md5", b"md5x"),
                   ("adas_upgrade.sh", b"adas")]
        with tarfile.open(star, "w", format=tarfile.USTAR_FORMAT) as t:
            for name, data in members:
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                ti.mode = 0o775 if name.endswith(".sh") else 0o664
                ti.mtime = 1691062673
                t.addfile(ti, io.BytesIO(data))
        scontract = {"outer_order": [n for n, _ in members],
                     "outer_members": [{"name": n, "size": len(d), "sha256": sh(d)}
                                       for n, d in members]}
        (tmp / "scontract.json").write_text(json.dumps(scontract))
        rc, _ = run_py("tar_assemble.py", "--mode", "golden", "--tar", str(star),
                       "--contract", str(tmp / "scontract.json"),
                       "--out", str(tmp / "repro.tar"))
        if rc != 0 or (tmp / "repro.tar").read_bytes() != star.read_bytes():
            fails.append("tar golden round-trip failed")
        (tmp / "new_inner.bin").write_bytes(b"2" * 120)
        (tmp / "sys_blob").write_bytes(b"sys")
        (tmp / "md5_blob").write_bytes(b"md5x")
        (tmp / "adas_blob").write_bytes(b"adas")
        (tmp / "members.json").write_text(json.dumps([
            {"name": "SigmastarUpgradeSD_SSC8838G.bin", "file": str(tmp / "new_inner.bin")},
            {"name": "sysVer.txt", "file": str(tmp / "sys_blob")},
            {"name": "minieye_firmware.md5", "file": str(tmp / "md5_blob")},
            {"name": "adas_upgrade.sh", "file": str(tmp / "adas_blob")},
        ]))
        rc, _ = run_py("tar_assemble.py", "--mode", "package", "--tar", str(star),
                       "--contract", str(tmp / "scontract.json"),
                       "--members-json", str(tmp / "members.json"),
                       "--out", str(tmp / "pkg.tar"))
        if rc != 0:
            fails.append("tar package mode failed")
        else:
            orig = star.read_bytes()
            new = (tmp / "pkg.tar").read_bytes()
            oh, nh = orig[:512], new[:512]
            if oh[:124] != nh[:124] or oh[136:148] != nh[136:148] or oh[156:] != nh[156:]:
                fails.append("tar package header changed outside size/chksum")
            if oh[124:136] == nh[124:136]:
                fails.append("tar package size field not updated")
            with tarfile.open(tmp / "pkg.tar", "r") as tf:
                if tf.extractfile("SigmastarUpgradeSD_SSC8838G.bin").read() != b"2" * 120:
                    fails.append("tar package member bytes wrong")

    if fails:
        print("CANDIDATE-B SYNTHETIC FAILURES:")
        for f in fails:
            print(" -", f)
        return 1
    print("candidate-b synthetic: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
