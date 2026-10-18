#!/usr/bin/env python3
"""Synthetic Candidate-E gates: oneed layout, mutation, verify and allowlist.

Host-only: no firmware bytes, no private database, no card or device access.
Exercises tools/fw/build_candidates.py (--oneed-cust layout math),
tools/fw/mutate_oneed.py, tools/fw/verify_b_manifest.py kind=oneed and
tools/fw/candidate_diff.py --oneed-* authorization.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / "tools" / "fw"
sys.path.insert(0, str(FW))

from build_candidates import compute_b_layout  # noqa: E402

TAIL_HEX = "31323334353637380a232046696c6520506172746974696f"
TAIL = bytes.fromhex(TAIL_HEX)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wav(payload: bytes) -> bytes:
    data = payload * 8
    fmt = struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16)
    chunks = (b"fmt " + struct.pack("<I", len(fmt)) + fmt
              + b"data" + struct.pack("<I", len(data)) + data)
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def script_text() -> str:
    return (
        "# File Partition: cis.es\n"
        "fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x100 0x1000\n"
        "# File Partition: miservice.es\n"
        "fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x80 0x1800\n"
        "ubi write 0x21000000 miservice 0x80\n"
        "# File Partition: customer.es\n"
        "fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x200 0x2000\n"
        "ubi write 0x21000000 customer 0x200\n"
        "# File Partition: misc.es\n"
        "fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x100 0x4000\n"
        "# File Partition: oneed_cust.es\n"
        "ubi create oneed_cust 0x1000\n"
        "fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x200 0x5000\n"
        "ubi write 0x21000000 oneed_cust 0x200\n"
        "# <- this is end of script symbol"
    )


def base_contract() -> dict:
    return {
        "loads": [
            {"section": "cis.es", "load_index": 0, "offset": 0x1000,
             "size": 0x100, "end": 0x1100, "sha256": "11" * 32},
            {"section": "miservice.es", "load_index": 0, "offset": 0x1800,
             "size": 0x80, "end": 0x1880, "sha256": "33" * 32},
            {"section": "customer.es", "load_index": 0, "offset": 0x2000,
             "size": 0x200, "end": 0x2200, "sha256": "22" * 32},
            {"section": "misc.es", "load_index": 0, "offset": 0x4000,
             "size": 0x100, "end": 0x4100, "sha256": "44" * 32},
            {"section": "oneed_cust.es", "load_index": 0, "offset": 0x5000,
             "size": 0x200, "end": 0x5200, "sha256": "55" * 32},
        ],
        "tail_unknown": {"hex": TAIL_HEX, "offset": 0x5200, "len": len(TAIL)},
        "upgrade_script_text": script_text(),
        "outer_members": [
            {"name": "SigmastarUpgradeSD_SSC8838G.bin", "sha256": "aa" * 32},
            {"name": "sysVer.txt", "sha256": "bb" * 32},
            {"name": "minieye_firmware.md5", "sha256": "cc" * 32},
            {"name": "adas_upgrade.sh", "sha256": "dd" * 32},
        ],
        "outer_order": ["SigmastarUpgradeSD_SSC8838G.bin", "sysVer.txt",
                        "minieye_firmware.md5", "adas_upgrade.sh"],
        "inner_sha256": "ee" * 32,
        "source_tar_sha256": "ff" * 32,
    }


class LayoutTest(unittest.TestCase):
    def test_oneed_layout_math(self):
        contract = base_contract()
        inner = b"\xaa" * 0x5400
        new_customer = b"C" * 0x300
        new_oneed = b"O" * 0x180
        layout = compute_b_layout(contract, inner, new_customer, new_oneed)
        loads = {r["section"]: r for r in layout["loads"]}
        self.assertEqual(loads["customer.es"]["size"], 0x300)
        self.assertEqual(loads["customer.es"]["offset"], 0x2000)
        self.assertEqual(loads["miservice.es"]["offset"], 0x1800)
        self.assertEqual(loads["misc.es"]["offset"], 0x4100)
        self.assertEqual(loads["oneed_cust.es"]["offset"], 0x5100)
        self.assertEqual(loads["oneed_cust.es"]["size"], 0x180)
        self.assertEqual(layout["tail_offset"], 0x5100 + 0x180)
        self.assertEqual(layout["total_size"], 0x5280 + len(TAIL))
        self.assertEqual(layout["delta"], 0x100)
        self.assertEqual(layout["oneed_delta"], 0x180 - 0x200)
        script = layout["script_text"]
        self.assertIn("fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x180 0x5100", script)
        self.assertIn("ubi write 0x21000000 oneed_cust 0x180", script)
        self.assertIn("ubi write 0x21000000 customer 0x300", script)
        self.assertIn("fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x80 0x1800", script)
        self.assertIn("ubi create oneed_cust 0x1000", script)

    def test_oneed_must_be_final(self):
        contract = base_contract()
        # Extend misc so oneed no longer ends last: replacing oneed must fail.
        for row in contract["loads"]:
            if row["section"] == "misc.es":
                row.update(size=0x1400, end=0x5400)
        with self.assertRaises(SystemExit):
            compute_b_layout(contract, b"\xaa" * 0x5600, b"C" * 0x300, b"O" * 0x180)


class MutationTest(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(os.environ["LOCALAPPDATA"]) / "Temp/opencode" if os.name == "nt" else None
        self.tmp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self):
        root = self.root
        tree = root / "tree"
        (tree / "audio").mkdir(parents=True)
        (tree / "other").mkdir()
        files = {
            "/audio/A.wav": wav(b"aaaa"),
            "/audio/B.wav": wav(b"bbbb"),
            "/other.txt": b"other",
        }
        entries = [
            {"path": "/", "type": "dir", "mode": 0o775, "uid": 1001, "gid": 1001},
            {"path": "/audio", "type": "dir", "mode": 0o775, "uid": 1001, "gid": 1001},
            {"path": "/other", "type": "dir", "mode": 0o775, "uid": 1001, "gid": 1001},
        ]
        for path, data in files.items():
            target = tree / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            entries.append({"path": path, "type": "reg", "mode": 0o664,
                            "uid": 1001, "gid": 1001, "size": len(data),
                            "sha256": digest(data), "mtime": 1691062660})
        stock = root / "stock.json"
        stock.write_text(json.dumps({"entries": entries}), encoding="utf-8")
        new_a = wav(b"AAAA") + b"tail"
        donor = root / "donor.wav"
        donor.write_bytes(new_a)
        specs = root / "specs.json"
        specs.write_text(json.dumps([{"path": "/audio/A.wav",
                                      "file": str(donor)}]), encoding="utf-8")
        return {"root": root, "tree": tree, "stock": stock, "new_a": new_a,
                "donor": donor, "specs": specs, "mut": root / "mut.json",
                "entries": entries}

    def run_tool(self, tool, args):
        return subprocess.run([sys.executable, str(FW / tool)] + args,
                              capture_output=True, text=True, timeout=60)

    def test_mutation_and_verify_round_trip(self):
        f = self.fixture()
        r = self.run_tool("mutate_oneed.py", [
            "--tree", str(f["tree"]), "--manifest", str(f["stock"]),
            "--audio-replacements", str(f["specs"]),
            "--out-manifest", str(f["mut"]), "--expect-count", "1"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        mut = json.loads(f["mut"].read_text(encoding="utf-8"))
        self.assertEqual(mut["kind"], "oneed")
        self.assertEqual(set(mut["replaced"]), {"/audio/A.wav"})
        self.assertEqual(mut["replaced"]["/audio/A.wav"]["new_sha256"], digest(f["new_a"]))
        self.assertEqual((f["tree"] / "audio/A.wav").read_bytes(), f["new_a"])

        # Simulated rebuilt image manifest: exactly the recorded swap, same
        # metadata; mtime may refresh only for replaced files.
        actual = []
        for e in f["entries"]:
            row = dict(e)
            if row["path"] == "/audio/A.wav":
                row["size"] = len(f["new_a"])
                row["sha256"] = digest(f["new_a"])
                row["mtime"] = 1799999999
            actual.append(row)
        actual_path = f["root"] / "actual.json"
        actual_path.write_text(json.dumps({"entries": actual}), encoding="utf-8")
        rep = f["root"] / "verify.json"
        r = self.run_tool("verify_b_manifest.py", [
            "--stock", str(f["stock"]), "--mut", str(f["mut"]),
            "--actual", str(actual_path), "--out", str(rep)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        doc = json.loads(rep.read_text(encoding="utf-8"))
        self.assertEqual(doc["verdict"], "OK")
        self.assertEqual(doc["kind"], "oneed")
        self.assertIsNone(doc["hook"])

        # Negative: an unauthorized file changed in the rebuilt image.
        tampered = [dict(x) for x in actual]
        for x in tampered:
            if x["path"] == "/other.txt":
                x["sha256"] = "00" * 32
        bad_path = f["root"] / "bad_actual.json"
        bad_path.write_text(json.dumps({"entries": tampered}), encoding="utf-8")
        r = self.run_tool("verify_b_manifest.py", [
            "--stock", str(f["stock"]), "--mut", str(f["mut"]),
            "--actual", str(bad_path)])
        self.assertNotEqual(r.returncode, 0)

    def test_mutation_refuses_identical_and_bad_paths(self):
        f = self.fixture()
        same = f["root"] / "same.wav"
        same.write_bytes((f["tree"] / "audio/A.wav").read_bytes())
        specs = f["root"] / "same_specs.json"
        specs.write_text(json.dumps([{"path": "/audio/A.wav", "file": str(same)}]),
                         encoding="utf-8")
        r = self.run_tool("mutate_oneed.py", [
            "--tree", str(f["tree"]), "--manifest", str(f["stock"]),
            "--audio-replacements", str(specs),
            "--out-manifest", str(f["root"] / "m1.json")])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("identical", r.stdout + r.stderr)

        outside = f["root"] / "outside.json"
        outside.write_text(json.dumps([{"path": "/etc/passwd", "file": str(f["donor"])}]),
                           encoding="utf-8")
        r = self.run_tool("mutate_oneed.py", [
            "--tree", str(f["tree"]), "--manifest", str(f["stock"]),
            "--audio-replacements", str(outside),
            "--out-manifest", str(f["root"] / "m2.json")])
        self.assertNotEqual(r.returncode, 0)

        r = self.run_tool("mutate_oneed.py", [
            "--tree", str(f["tree"]), "--manifest", str(f["stock"]),
            "--audio-replacements", str(f["specs"]),
            "--out-manifest", str(f["root"] / "m3.json"), "--expect-count", "2"])
        self.assertNotEqual(r.returncode, 0)


class DiffTest(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(os.environ["LOCALAPPDATA"]) / "Temp/opencode" if os.name == "nt" else None
        self.tmp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def build(self):
        contract = base_contract()
        layout = compute_b_layout(contract, b"\xaa" * 0x5400,
                                  b"C" * 0x300, b"O" * 0x180)
        base = contract
        cand = json.loads(json.dumps(contract))
        for row in cand["loads"]:
            if row["section"] == "customer.es":
                row.update(size=0x300, end=0x2300, sha256="66" * 32)
            elif row["section"] == "oneed_cust.es":
                row.update(offset=0x5100, size=0x180, end=0x5280, sha256="77" * 32)
            elif row["section"] == "misc.es":
                row.update(offset=0x4100, end=0x4200)
        cand["upgrade_script_text"] = layout["script_text"]
        cand["inner_sha256"] = "12" * 32
        for m in cand["outer_members"]:
            if m["name"] == "SigmastarUpgradeSD_SSC8838G.bin":
                m["sha256"] = "13" * 32
            elif m["name"] == "minieye_firmware.md5":
                m["sha256"] = "14" * 32
        deep = {"verdict": "VALID", "checks": [
            {"check": "protected.cardv", "result": "PASS"},
            {"check": "protected.adas", "result": "PASS"}]}
        new_a = wav(b"AAAA") + b"x"
        mut = {"kind": "oneed", "added": [], "modified": [],
               "replaced": {"/audio/A.wav": {"old_sha256": "aa" * 32, "old_size": 1,
                                             "new_sha256": digest(new_a),
                                             "new_size": len(new_a)}}}
        verify = {"kind": "oneed", "verdict": "OK", "violations": [],
                  "added": [], "hook": None, "checked": 4}
        pins = {"swaps": [{"path": "/audio/A.wav", "vi_sha256": digest(new_a),
                           "vi_size": len(new_a)}], "stock_entries": 4}
        files = {}
        for key, doc in (("base.json", base), ("cand.json", cand), ("deep.json", deep),
                         ("mut.json", mut), ("verify.json", verify), ("pins.json", pins)):
            p = self.root / key
            p.write_text(json.dumps(doc), encoding="utf-8")
            files[key] = p
        return files

    def run_diff(self, files, with_oneed=True):
        out = self.root / ("diff_oneed.json" if with_oneed else "diff_plain.json")
        args = [sys.executable, str(FW / "candidate_diff.py"),
                "--base", str(files["base.json"]), "--cand", str(files["cand.json"]),
                "--deep-report", str(files["deep.json"]), "--out", str(out)]
        if with_oneed:
            args += ["--oneed-mut", str(files["mut.json"]),
                     "--oneed-pins", str(files["pins.json"]),
                     "--oneed-verify", str(files["verify.json"])]
        r = subprocess.run(args, capture_output=True, text=True, timeout=60)
        doc = json.loads(out.read_text(encoding="utf-8"))
        return r, doc

    def test_authorized_oneed_is_allowlisted(self):
        files = self.build()
        r, doc = self.run_diff(files, with_oneed=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(doc["verdict"], "ALLOWLIST-OK", doc)
        self.assertTrue(doc["oneed_authorized"])

    def test_unauthorized_oneed_blocks(self):
        files = self.build()
        r, doc = self.run_diff(files, with_oneed=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(doc["verdict"], "BLOCK")
        self.assertTrue(any("oneed" in b for b in doc["blocks"]), doc["blocks"])

    def test_pin_mismatch_blocks(self):
        files = self.build()
        pins = json.loads(files["pins.json"].read_text(encoding="utf-8"))
        pins["swaps"][0]["vi_sha256"] = "ab" * 32
        files["pins.json"].write_text(json.dumps(pins), encoding="utf-8")
        r, doc = self.run_diff(files, with_oneed=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(any("pin mismatch" in b for b in doc["blocks"]), doc["blocks"])

    def test_verify_not_ok_blocks(self):
        files = self.build()
        verify = json.loads(files["verify.json"].read_text(encoding="utf-8"))
        verify["verdict"] = "BLOCK"
        files["verify.json"].write_text(json.dumps(verify), encoding="utf-8")
        r, doc = self.run_diff(files, with_oneed=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(any("verify verdict" in b for b in doc["blocks"]), doc["blocks"])


if __name__ == "__main__":
    unittest.main()
