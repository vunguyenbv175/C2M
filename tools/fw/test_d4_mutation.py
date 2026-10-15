#!/usr/bin/env python3
"""Synthetic D4 mutation gates. No private DB, firmware, card or device access."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/fw/mutate_customer.py"
RECORD = struct.Struct("<ddf16s64s")
D3_NAMES = {"boot.sh", "connectivity_probe.sh", "c2m-web", "c2m-wifi", "wpa_supplicant"}
D4_NAMES = {"c2m-signs", "d4_boot.sh", "signs-d4.bin"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_field(value: str, size: int) -> bytes:
    return (value.encode("utf-8") + b"\0").ljust(size, b"\0")


def record(lat=12.3456789, lon=107.9876543, heading=90.0,
           kind="R.420", label="Private fixture Biển") -> bytes:
    return RECORD.pack(lat, lon, heading, text_field(kind, 16), text_field(label, 64))


def database(*rows: bytes) -> bytes:
    return b"C2MSDB01" + struct.pack("<I", len(rows)) + b"".join(rows)


def arm_elf() -> bytes:
    data = bytearray(52)
    data[:6] = b"\x7fELF\x01\x01"
    data[18] = 40
    return bytes(data)


def shell_path(path: Path) -> str:
    value = path.as_posix()
    return "/" + value[0].lower() + value[2:] if len(value) > 2 and value[1] == ":" else value


class D4MutationTest(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(os.environ["LOCALAPPDATA"]) / "Temp/opencode" if os.name == "nt" else None
        self.tmp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sequence = 0

    def fixture(self, hook=b"#!/bin/sh\nfalse\nexit $?\n") -> dict:
        self.sequence += 1
        root = self.root / str(self.sequence)
        tree = root / "tree"
        (tree / "wifi").mkdir(parents=True)
        (tree / "wifi/rcInsDriver.sh").write_bytes(hook)
        stock = root / "stock.json"
        stock.write_text(json.dumps({"entries": [{"path": "/wifi/rcInsDriver.sh",
            "type": "reg", "size": len(hook), "sha256": digest(hook)}]}), encoding="utf-8")
        idle = root / "idle"
        idle.write_bytes(b"synthetic-idle")
        d3 = root / "d3"
        d3.mkdir()
        for name in D3_NAMES:
            source = b"#!/bin/sh\nexit 0\n" if name.endswith(".sh") else arm_elf()
            (d3 / name).write_bytes(source)
        d4 = root / "d4"
        d4.mkdir()
        (d4 / "c2m-signs").write_bytes(arm_elf())
        (d4 / "d4_boot.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
        db = root / "private.bin"
        data = database(record(), record(heading=0, kind="R.421"))
        db.write_bytes(data)
        return {"root": root, "tree": tree, "stock": stock, "idle": idle,
                "d3": d3, "d4": d4, "db": db, "out": root / "mutation.json"}

    def run_mutation(self, f: dict, *, omit=(), override=None, extra=()):
        options = {"--tree": str(f["tree"]), "--manifest": str(f["stock"]),
                   "--idle-bin": str(f["idle"]), "--tsr-experiment": None,
                   "--d3-services-dir": str(f["d3"]), "--d4-services-dir": str(f["d4"]),
                   "--d4-database": str(f["db"]),
                   "--d4-database-sha256": digest(f["db"].read_bytes()),
                   "--out-manifest": str(f["out"])}
        options.update(override or {})
        command = [sys.executable, str(TOOL)]
        for name, value in options.items():
            if name not in omit:
                command.append(name)
                if value is not None:
                    command.append(value)
        return subprocess.run(command + list(extra), capture_output=True, text=True, timeout=30)

    def snapshot(self, tree: Path) -> dict:
        result = {}
        for path in tree.rglob("*"):
            mode = stat.S_IMODE(path.lstat().st_mode)
            if path.is_symlink():
                entry = ("link", mode, os.readlink(path))
            elif path.is_dir():
                entry = ("dir", mode)
            else:
                entry = ("reg", mode, digest(path.read_bytes()))
            result[path.relative_to(tree).as_posix()] = entry
        return result

    def assert_blocked(self, f: dict, **kwargs):
        before = self.snapshot(f["tree"])
        report_before = f["out"].read_bytes() if f["out"].is_file() else None
        result = self.run_mutation(f, **kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(f["tree"]), before, "failed validation mutated tree")
        self.assertEqual(f["out"].read_bytes() if f["out"].is_file() else None, report_before)
        combined = result.stdout + result.stderr
        for private in ("12.3456789", "107.9876543", "Private fixture", "Biển"):
            self.assertNotIn(private, combined)
        encoded = base64.b64encode(f["db"].read_bytes()).decode()
        if encoded:
            self.assertNotIn(encoded, combined)
        return result

    def test_exact_allowlist_modes_metadata_and_hook_order(self):
        f = self.fixture()
        result = self.run_mutation(f, override={"--d4-database-sha256": digest(f["db"].read_bytes()).upper()})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        doc = json.loads(f["out"].read_text(encoding="utf-8"))
        self.assertTrue(doc["d3_services"])
        self.assertTrue(doc["d4_services"])
        self.assertTrue(doc["tsr_experiment"])
        self.assertFalse(doc["tsr_patch"])
        self.assertEqual(doc["d4_database"], {"count": 2, "sha256": digest(f["db"].read_bytes())})
        rows = {row["path"]: row for row in doc["added"]}
        expected = {"/c2m", "/c2m/c2m-idle", "/c2m/tsr_profile_boot.sh"}
        expected.update("/c2m/" + name for name in D3_NAMES | D4_NAMES)
        self.assertEqual(set(rows), expected)
        actual = {"/" + path.relative_to(f["tree"]).as_posix() for path in f["tree"].rglob("*")}
        self.assertEqual(actual, expected | {"/wifi", "/wifi/rcInsDriver.sh"})
        for name in D4_NAMES:
            row = rows["/c2m/" + name]
            mode = 0o644 if name == "signs-d4.bin" else 0o755
            data = (f["tree"] / "c2m" / name).read_bytes()
            self.assertEqual(row["mode"], mode)
            self.assertEqual(row["mode_oct"], oct(mode))
            self.assertEqual((row["uid"], row["gid"]), (1001, 1001))
            self.assertEqual((row["size"], row["sha256"]), (len(data), digest(data)))
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE((f["tree"] / "c2m" / name).stat().st_mode), mode)
        self.assertEqual((f["tree"] / "c2m/signs-d4.bin").read_bytes(), f["db"].read_bytes())
        for name in D3_NAMES:
            self.assertEqual((f["tree"] / "c2m" / name).read_bytes(), (f["d3"] / name).read_bytes())
        self.assertEqual((f["tree"] / "c2m/tsr_profile_boot.sh").read_bytes(),
                         (ROOT / "fw/tsr/tsr_profile_boot.sh").read_bytes())
        hook = (f["tree"] / "wifi/rcInsDriver.sh").read_bytes()
        self.assertNotIn(b"\r", hook)
        text = hook.decode()
        launches = ["/customer/c2m/c2m-idle >/dev/null 2>&1 &",
                    "/bin/sh /customer/c2m/boot.sh >/dev/null 2>&1 &",
                    "/bin/sh /customer/c2m/d4_boot.sh >/dev/null 2>&1 &"]
        for launch in launches:
            self.assertEqual(text.count(launch), 1)
        self.assertLess(text.index(launches[0]), text.index(launches[1]))
        self.assertLess(text.index(launches[1]), text.index(launches[2]))
        self.assertEqual(text.count("( _c2m_n=0"), 1)
        self.assertEqual(text.count("while [ $_c2m_n -lt 30 ]; do"), 1)
        self.assertIn("sleep 2\n_c2m_n=$(($_c2m_n + 1))\ndone\n", text)
        self.assertLess(text.index("tsr_profile_boot.sh"), text.index("( _c2m_n=0"))
        self.assertIn(launches[2] + " ) >/dev/null 2>&1 &\nexit $_c2m_rc\n", text)
        self.assertEqual(doc["replaced"], {})
        self.assertEqual([row["path"] for row in doc["modified"]], ["/wifi/rcInsDriver.sh"])
        self.assertNotIn("Private fixture", result.stdout)
        self.assertNotIn("12.3456789", result.stdout)
        encoded = base64.b64encode(f["db"].read_bytes()).decode()
        if encoded:
            self.assertNotIn(encoded, result.stdout)
        self.assert_blocked(f)  # no double mutation

    def test_required_options_pin_and_dependencies(self):
        for missing in ("--d4-services-dir", "--d4-database", "--d4-database-sha256",
                        "--d3-services-dir", "--tsr-experiment"):
            with self.subTest(missing=missing):
                self.assert_blocked(self.fixture(), omit={missing})
        for pin in ("", "f" * 63, "f" * 65, "g" * 64, " " + "a" * 64, "0" * 64):
            with self.subTest(pin_length=len(pin)):
                self.assert_blocked(self.fixture(), override={"--d4-database-sha256": pin})
        self.assert_blocked(self.fixture(), omit={"--tsr-experiment"}, extra=["--tsr-patch"])

    def test_exact_service_inputs_and_formats(self):
        for case in ("missing-bin", "missing-boot", "extra-file", "extra-dir", "elf64", "x86",
                     "big-endian", "short-elf", "crlf", "bad-shebang", "directory"):
            with self.subTest(case=case):
                f = self.fixture()
                binary, boot = f["d4"] / "c2m-signs", f["d4"] / "d4_boot.sh"
                if case == "missing-bin": binary.unlink()
                elif case == "missing-boot": boot.unlink()
                elif case == "extra-file": (f["d4"] / "unlisted").write_bytes(b"x")
                elif case == "extra-dir": (f["d4"] / "unlisted").mkdir()
                elif case == "crlf": boot.write_bytes(b"#!/bin/sh\r\nexit 0\r\n")
                elif case == "bad-shebang": boot.write_bytes(b"#!/bin/bash\nexit 0\n")
                elif case == "directory": binary.unlink(); binary.mkdir()
                else:
                    data = bytearray(arm_elf())
                    if case == "elf64": data[4] = 2
                    elif case == "x86": data[18] = 3
                    elif case == "big-endian": data[5] = 2
                    elif case == "short-elf": data = data[:51]
                    binary.write_bytes(data)
                self.assert_blocked(f)

    def test_database_header_count_and_size(self):
        valid = database(record())
        inputs = (b"", valid[:11], valid[:-1], valid + b"x", b"BADMAGIC" + valid[8:],
                  b"C2MSDB01" + struct.pack("<I", 0),
                  b"C2MSDB01" + struct.pack("<I", 40001),
                  b"C2MSDB01" + struct.pack(">I", 1) + record(),
                  b"x" * 4000013)
        for index, data in enumerate(inputs):
            with self.subTest(case=index):
                f = self.fixture()
                f["db"].write_bytes(data)
                self.assert_blocked(f)

    def test_database_bad_numbers_classes_and_strings(self):
        rows = [record(lat=float("nan")), record(lat=float("inf")), record(lat=-91),
                record(lon=float("nan")), record(lon=float("inf")), record(lon=181),
                record(heading=float("nan")), record(heading=float("inf")),
                record(heading=-999), record(heading=-1), record(heading=360), record(heading=361)]
        rows += [record(kind=kind) for kind in ("P.127", "P.125", "P.130", "P.131a", "W.207", "", "r.420")]
        for offset, value in ((20, b"x" * 16), (36, b"x" * 64), (35, b"x"), (99, b"x"),
                              (36, b"\xff"), (36, b"\n"), (36, b"\x7f"), (36, b"\xc2\x85")):
            row = bytearray(record())
            row[offset:offset + len(value)] = value
            rows.append(bytes(row))
        for index, row in enumerate(rows):
            with self.subTest(case=index):
                f = self.fixture()
                # The second row must also be checked, not just the first.
                f["db"].write_bytes(database(record(), row))
                self.assert_blocked(f)

    def test_database_boundaries(self):
        for rows in ((record(lat=-90, lon=-180, heading=0), record(lat=90, lon=180, heading=359.99)),
                     (record(),) * 12999):
            with self.subTest(count=len(rows)):
                f = self.fixture()
                f["db"].write_bytes(database(*rows))
                result = self.run_mutation(f)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                doc = json.loads(f["out"].read_text())
                self.assertEqual(doc["d4_database"]["count"], len(rows))
        # The source format permits 40,000 records, but the fixed D4 image
        # asset is capped at the private subset output bound (~1.3 MB).
        for count in (13000, 40000):
            f = self.fixture()
            f["db"].write_bytes(database(*(record(),) * count))
            self.assert_blocked(f)

    def test_no_foreign_asset_or_report_overwrite(self):
        for name in {"c2m-idle", "tsr_profile_boot.sh"} | D3_NAMES | D4_NAMES:
            with self.subTest(name=name):
                f = self.fixture()
                (f["tree"] / "c2m").mkdir()
                (f["tree"] / "c2m" / name).write_bytes(b"foreign sentinel")
                self.assert_blocked(f)
        f = self.fixture()
        f["out"].write_bytes(b"foreign report")
        self.assert_blocked(f)
        f = self.fixture()
        f["out"] = f["tree"] / "foreign-report.json"
        self.assert_blocked(f)
        f = self.fixture()
        (f["tree"] / "c2m").write_bytes(b"not a directory")
        self.assert_blocked(f)

    def test_all_legacy_inputs_checked_before_d4_tree_writes(self):
        for bad in ("idle", "d3", "audio", "hook"):
            with self.subTest(bad=bad):
                f = self.fixture()
                extra = []
                if bad == "idle": f["idle"].unlink()
                elif bad == "d3": (f["d3"] / "wpa_supplicant").write_bytes(b"not ELF")
                elif bad == "hook": (f["tree"] / "wifi/rcInsDriver.sh").write_bytes(b"tamper\n")
                else:
                    audio = f["root"] / "bad-audio.json"
                    audio.write_text("not json")
                    extra = ["--audio-replacements", str(audio)]
                self.assert_blocked(f, extra=extra)

    def test_late_audio_failure_does_not_partially_mutate(self):
        f = self.fixture()
        audio_dir = f["tree"] / "minieye/adas/audios"
        audio_dir.mkdir(parents=True)
        payload = b"\x01\x02" * 10
        wav = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(payload), b"WAVE",
                          b"fmt ", 16, 1, 1, 24000, 48000, 2, 16, b"data", len(payload)) + payload
        for name in ("A.wav", "B.wav"):
            (audio_dir / name).write_bytes(wav)
        md5 = ("\n".join(hashlib.md5(wav).hexdigest() + "  ./audios/" + name
                         for name in ("A.wav", "B.wav")) + "\n").encode()
        (audio_dir.parent / "md5sum.txt").write_bytes(md5)
        stock = json.loads(f["stock"].read_text())
        for relative in ("audios/A.wav", "audios/B.wav", "md5sum.txt"):
            data = (audio_dir.parent / relative).read_bytes()
            stock["entries"].append({"path": "/minieye/adas/" + relative,
                                      "type": "reg", "size": len(data), "sha256": digest(data)})
        f["stock"].write_text(json.dumps(stock))
        good, bad = f["root"] / "good.wav", f["root"] / "bad.wav"
        good.write_bytes(wav[:-2] + b"\x03\x04")
        bad.write_bytes(b"invalid wave")
        mapping = f["root"] / "audio.json"
        mapping.write_text(json.dumps([{"path": "/minieye/adas/audios/A.wav", "file": str(good)},
                                       {"path": "/minieye/adas/audios/B.wav", "file": str(bad)}]))
        self.assert_blocked(f, extra=["--audio-replacements", str(mapping)])

    def test_no_terminal_exit_is_rejected_before_writes(self):
        self.assert_blocked(self.fixture(b"#!/bin/sh\nfalse\n"))

    @unittest.skipIf(os.name == "nt", "Windows symlink privileges vary; POSIX link gate coverage")
    def test_symlink_sources_and_destinations_blocked(self):
        for target in ("binary", "boot", "database", "services", "destination", "broken", "parent", "hook"):
            with self.subTest(target=target):
                f = self.fixture()
                if target in ("binary", "boot", "database", "services"):
                    source = {"binary": f["d4"] / "c2m-signs", "boot": f["d4"] / "d4_boot.sh",
                              "database": f["db"], "services": f["d4"]}[target]
                    actual = f["root"] / "actual"
                    source.rename(actual)
                    source.symlink_to(actual, target_is_directory=target == "services")
                elif target in ("destination", "broken"):
                    (f["tree"] / "c2m").mkdir()
                    other = f["root"] / "other"
                    if target == "destination": other.write_bytes(b"foreign")
                    (f["tree"] / "c2m/signs-d4.bin").symlink_to(other)
                elif target == "parent":
                    other = f["root"] / "other"
                    other.mkdir()
                    (f["tree"] / "c2m").symlink_to(other, target_is_directory=True)
                else:
                    hook = f["tree"] / "wifi/rcInsDriver.sh"
                    actual = f["root"] / "actual-hook"
                    hook.rename(actual)
                    hook.symlink_to(actual)
                self.assert_blocked(f)

    def test_stock_exit_status_and_detached_reachable_hook(self):
        shell = shutil.which("sh")
        if not shell:
            self.skipTest("POSIX shell unavailable")
        for tail, code in ((b"exit 0\n", 0), (b"exit 7\n", 7), (b"exit $?\n", 1), (b"exit\n", 1)):
            with self.subTest(tail=tail):
                f = self.fixture(b"#!/bin/sh\nfalse\n" + tail)
                result = self.run_mutation(f)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                text = (f["tree"] / "wifi/rcInsDriver.sh").read_bytes().decode()
                expected_tail = tail.decode() if tail not in (b"exit\n", b"exit $?\n") else "exit $_c2m_rc\n"
                self.assertTrue(text.endswith(expected_tail))
                # Run only synthetic stubs, never installed ARM binaries or device paths.
                stub = f["root"] / "stub"
                stub.mkdir()
                for name in ("sleep", "grep"):
                    (stub / name).write_bytes(b"#!/bin/sh\nexit 1\n" if name == "grep" else b"#!/bin/sh\nexit 0\n")
                    os.chmod(stub / name, 0o755)
                for name in ("c2m-idle", "boot.sh", "d4_boot.sh", "tsr_profile_boot.sh"):
                    sentinel = shell_path(stub / (name + ".seen"))
                    (stub / name).write_bytes(("#!/bin/sh\nprintf seen > " + shlex.quote(sentinel) + "\n").encode())
                    os.chmod(stub / name, 0o755)
                host_hook = f["root"] / "host-hook.sh"
                host_hook.write_bytes(text.replace("/customer/c2m/", shell_path(stub) + "/").encode())
                syntax = subprocess.run([shell, "-n", shell_path(host_hook)], capture_output=True, text=True)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
                command = 'export PATH=%s:"$PATH"; exec /bin/sh %s' % (
                    shlex.quote(shell_path(stub)), shlex.quote(shell_path(host_hook)))
                start = time.monotonic()
                result = subprocess.run([shell, "-c", command], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertLess(time.monotonic() - start, 5)
                names = ("c2m-idle", "boot.sh", "d4_boot.sh", "tsr_profile_boot.sh")
                deadline = time.monotonic() + 5
                while (time.monotonic() < deadline
                       and not all((stub / (name + ".seen")).is_file() for name in names)):
                    time.sleep(0.02)
                for name in names:
                    self.assertTrue((stub / (name + ".seen")).is_file(), name)

    def test_deploy_shell_sources_are_lf(self):
        for relative in ("fw/tsr/tsr_profile_boot.sh", "fw/d3/boot.sh",
                         "fw/d3/connectivity_probe.sh", "fw/d4/d4_boot.sh"):
            data = (ROOT / relative).read_bytes()
            self.assertNotIn(b"\r", data, relative)
            self.assertTrue(data.startswith(b"#!/bin/sh\n"), relative)


if __name__ == "__main__":
    unittest.main(verbosity=2)
