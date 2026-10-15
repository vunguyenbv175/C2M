#!/usr/bin/env python3
"""Synthetic debug-services mutation gates. No device, network, card or private vault."""
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
D3_NAMES = ("boot.sh", "connectivity_probe.sh", "c2m-web", "c2m-wifi", "wpa_supplicant")
DEBUG_NAMES = ("c2m-debug", "dropbear", "dropbearkey", "debug_boot.sh")
DEBUG_ALL = ("c2m-debug", "dropbear", "dropbearkey", "debug_boot.sh", "debug_owner.pub")
OWNER_COMMENT = "c2m-debug-owner"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def arm_elf() -> bytes:
    data = bytearray(52)
    data[:6] = b"\x7fELF\x01\x01"
    data[18] = 40
    return bytes(data)


def owner_pub(key32: bytes = b"\x07" * 32, comment: str = OWNER_COMMENT) -> bytes:
    blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + key32
    return ("ssh-ed25519 " + base64.b64encode(blob).decode("ascii")
            + " " + comment + "\n").encode("ascii")


def shell_path(path: Path) -> str:
    value = path.as_posix()
    return "/" + value[0].lower() + value[2:] if len(value) > 2 and value[1] == ":" else value


class DebugMutationTest(unittest.TestCase):
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
        dbg = root / "dbg"
        dbg.mkdir()
        for name in DEBUG_NAMES:
            if name.endswith(".sh"):
                (dbg / name).write_bytes(b"#!/bin/sh\nexit 0\n")
            else:
                (dbg / name).write_bytes(arm_elf())
        key = root / "owner.pub"
        key.write_bytes(owner_pub())
        return {"root": root, "tree": tree, "stock": stock, "idle": idle,
                "d3": d3, "dbg": dbg, "key": key, "out": root / "mutation.json"}

    def run_mutation(self, f: dict, *, omit=(), override=None, extra=()):
        options = {"--tree": str(f["tree"]), "--manifest": str(f["stock"]),
                   "--idle-bin": str(f["idle"]), "--tsr-experiment": None,
                   "--d3-services-dir": str(f["d3"]),
                   "--debug-services-dir": str(f["dbg"]),
                   "--debug-owner-key": str(f["key"]),
                   "--debug-owner-key-sha256": digest(f["key"].read_bytes()),
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
        return result

    def test_exact_allowlist_modes_metadata_and_hook_order(self):
        f = self.fixture()
        key_b64 = f["key"].read_bytes().decode().split(" ")[1]
        result = self.run_mutation(f)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        doc = json.loads(f["out"].read_text(encoding="utf-8"))
        self.assertTrue(doc["debug_services"])
        self.assertTrue(doc["d3_services"])
        self.assertTrue(doc["tsr_experiment"])
        self.assertFalse(doc.get("d4_services", False))
        self.assertEqual(doc["debug_owner_key_sha256"], digest(f["key"].read_bytes()))
        self.assertNotIn("debug_owner_key", [k for k in doc if k != "debug_owner_key_sha256"])
        rows = {row["path"]: row for row in doc["added"]}
        expected = {"/c2m", "/c2m/c2m-idle", "/c2m/tsr_profile_boot.sh"}
        expected.update("/c2m/" + n for n in D3_NAMES)
        expected.update("/c2m/" + n for n in DEBUG_ALL)
        self.assertEqual(set(rows), expected)
        actual = {"/" + p.relative_to(f["tree"]).as_posix() for p in f["tree"].rglob("*")}
        self.assertEqual(actual, expected | {"/wifi", "/wifi/rcInsDriver.sh"})
        for name in DEBUG_ALL:
            row = rows["/c2m/" + name]
            want = 0o644 if name == "debug_owner.pub" else 0o755
            data = (f["tree"] / "c2m" / name).read_bytes()
            self.assertEqual(row["mode"], want, name)
            self.assertEqual(row["mode_oct"], oct(want), name)
            self.assertEqual((row["uid"], row["gid"]), (1001, 1001), name)
            self.assertEqual((row["size"], row["sha256"]), (len(data), digest(data)), name)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE((f["tree"] / "c2m" / name).stat().st_mode), want, name)
        self.assertEqual((f["tree"] / "c2m/debug_owner.pub").read_bytes(), f["key"].read_bytes())
        for name in DEBUG_NAMES:
            self.assertEqual((f["tree"] / "c2m" / name).read_bytes(), (f["dbg"] / name).read_bytes())
        # D3 boot is never altered by the debug install.
        self.assertEqual((f["tree"] / "c2m/boot.sh").read_bytes(), (f["d3"] / "boot.sh").read_bytes())
        boot_sh = (f["tree"] / "c2m/debug_boot.sh").read_bytes()
        self.assertTrue(boot_sh.startswith(b"#!/bin/sh\n"))
        self.assertNotIn(b"\r", boot_sh)
        hook = (f["tree"] / "wifi/rcInsDriver.sh").read_bytes()
        self.assertNotIn(b"\r", hook)
        text = hook.decode()
        launches = ["/customer/c2m/c2m-idle >/dev/null 2>&1 &",
                    "/bin/sh /customer/c2m/boot.sh >/dev/null 2>&1 &",
                    "/bin/sh /customer/c2m/debug_boot.sh >/dev/null 2>&1 &"]
        for launch in launches:
            self.assertEqual(text.count(launch), 1, launch)
        self.assertLess(text.index(launches[0]), text.index(launches[1]))
        self.assertLess(text.index(launches[1]), text.index(launches[2]))
        self.assertNotIn("d4_boot.sh", text)
        self.assertEqual(text.count("( _c2m_n=0"), 1)
        self.assertIn(launches[2] + " ) >/dev/null 2>&1 &\nexit $_c2m_rc\n", text)
        self.assertLess(text.index("tsr_profile_boot.sh"), text.index("( _c2m_n=0"))
        # Report carries only the key sha, never key bytes or personal fields.
        report_text = f["out"].read_text(encoding="utf-8")
        self.assertNotIn(key_b64, report_text)
        self.assertNotIn(key_b64, result.stdout)
        self.assertEqual(doc["replaced"], {})
        self.assertEqual([r["path"] for r in doc["modified"]], ["/wifi/rcInsDriver.sh"])
        self.assert_blocked(f)  # no double mutation

    def test_hook_order_with_d4(self):
        import struct as _st
        f = self.fixture()
        d4 = f["root"] / "d4"
        d4.mkdir()
        (d4 / "c2m-signs").write_bytes(arm_elf())
        (d4 / "d4_boot.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
        rec = _st.Struct("<ddf16s64s")
        row = rec.pack(1.0, 2.0, 90.0, b"R.420\0" + b"\0" * 10, b"x\0" + b"\0" * 62)
        db = f["root"] / "db.bin"
        db.write_bytes(b"C2MSDB01" + _st.pack("<I", 1) + row)
        out = f["out"]
        cmd = [sys.executable, str(TOOL), "--tree", str(f["tree"]), "--manifest", str(f["stock"]),
               "--idle-bin", str(f["idle"]), "--tsr-experiment",
               "--d3-services-dir", str(f["d3"]), "--d4-services-dir", str(d4),
               "--d4-database", str(db), "--d4-database-sha256", digest(db.read_bytes()),
               "--debug-services-dir", str(f["dbg"]), "--debug-owner-key", str(f["key"]),
               "--debug-owner-key-sha256", digest(f["key"].read_bytes()),
               "--out-manifest", str(out)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(doc["d4_services"])
        self.assertTrue(doc["debug_services"])
        text = (f["tree"] / "wifi/rcInsDriver.sh").read_text()
        launches = ["/customer/c2m/c2m-idle >/dev/null 2>&1 &",
                    "/bin/sh /customer/c2m/boot.sh >/dev/null 2>&1 &",
                    "/bin/sh /customer/c2m/d4_boot.sh >/dev/null 2>&1 &",
                    "/bin/sh /customer/c2m/debug_boot.sh >/dev/null 2>&1 &"]
        for launch in launches:
            self.assertEqual(text.count(launch), 1, launch)
        for first, second in zip(launches, launches[1:]):
            self.assertLess(text.index(first), text.index(second))
        self.assertIn(launches[-1] + " ) >/dev/null 2>&1 &\nexit $_c2m_rc\n", text)

    def test_required_options_pin_and_dependencies(self):
        for missing in ("--debug-services-dir", "--debug-owner-key", "--debug-owner-key-sha256"):
            with self.subTest(missing=missing):
                self.assert_blocked(self.fixture(), omit={missing})
        # Debug requires D3 and the checked TSR experiment, standalone D3+debug is ok.
        self.assert_blocked(self.fixture(), omit={"--d3-services-dir"})
        self.assert_blocked(self.fixture(), omit={"--tsr-experiment"})
        self.assert_blocked(self.fixture(), omit={"--tsr-experiment"}, extra=["--tsr-patch"])
        for pin in ("", "f" * 63, "f" * 65, "g" * 64, " " + "a" * 64, "0" * 64):
            with self.subTest(pin_length=len(pin)):
                self.assert_blocked(self.fixture(), override={"--debug-owner-key-sha256": pin})
        # Wrong pin for the same key bytes is rejected.
        self.assert_blocked(self.fixture(), override={"--debug-owner-key-sha256": "a" * 64})

    def test_exact_service_inputs_and_formats(self):
        for case in ("missing-supervisor", "missing-dropbear", "missing-dropbearkey",
                     "missing-boot", "extra-file", "extra-dir", "elf64", "x86",
                     "big-endian", "short-elf", "crlf", "bad-shebang", "directory",
                     "oversize-supervisor", "oversize-dropbear", "oversize-shell"):
            with self.subTest(case=case):
                f = self.fixture()
                sup, dr, drk, boot = (f["dbg"] / "c2m-debug", f["dbg"] / "dropbear",
                                     f["dbg"] / "dropbearkey", f["dbg"] / "debug_boot.sh")
                if case == "missing-supervisor": sup.unlink()
                elif case == "missing-dropbear": dr.unlink()
                elif case == "missing-dropbearkey": drk.unlink()
                elif case == "missing-boot": boot.unlink()
                elif case == "extra-file": (f["dbg"] / "unlisted").write_bytes(b"x")
                elif case == "extra-dir": (f["dbg"] / "unlisted").mkdir()
                elif case == "crlf": boot.write_bytes(b"#!/bin/sh\r\nexit 0\r\n")
                elif case == "bad-shebang": boot.write_bytes(b"#!/bin/bash\nexit 0\n")
                elif case == "directory": sup.unlink(); sup.mkdir()
                elif case == "oversize-supervisor": sup.write_bytes(arm_elf() + b"\0" * (256 * 1024))
                elif case == "oversize-dropbear": dr.write_bytes(arm_elf() + b"\0" * (2 * 1024 * 1024))
                elif case == "oversize-shell": boot.write_bytes(b"#!/bin/sh\n" + b"#" * (64 * 1024))
                else:
                    data = bytearray(arm_elf())
                    if case == "elf64": data[4] = 2
                    elif case == "x86": data[18] = 3
                    elif case == "big-endian": data[5] = 2
                    elif case == "short-elf": data = data[:51]
                    target = sup if case != "short-elf" else sup
                    target.write_bytes(bytes(data))
                    if case == "short-elf":
                        pass
                # x86/big-endian/elf64 variants target dropbear when supervisor untouched?
                if case in ("elf64", "x86", "big-endian"):
                    dr.write_bytes(bytearray(sup.read_bytes()) if False else dr.read_bytes())
                    # rewrite dropbear with the bad header instead
                    data = bytearray(arm_elf())
                    if case == "elf64": data[4] = 2
                    elif case == "x86": data[18] = 3
                    elif case == "big-endian": data[5] = 2
                    dr.write_bytes(bytes(data))
                self.assert_blocked(f)

    def test_bad_owner_keys(self):
        good = owner_pub()
        good_b64 = good.decode().split(" ")[1]
        blob = base64.b64decode(good_b64)
        cases = {
            "wrong-type": b"ssh-rsa " + good_b64.encode() + b" c2m-debug-owner\n",
            "private-pem": b"-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n",
            "options": b"command=\"x\" " + good,
            "crlf": good.replace(b"\n", b"\r\n"),
            "no-newline": good[:-1],
            "multiline": good + good,
            "empty": b"",
            "truncated": b"ssh-ed25519 " + base64.b64encode(blob[:20]).decode().encode() + b" c2m-debug-owner\n",
            "noncanonical-b64": b"ssh-ed25519 " + good_b64.encode() + b"= c2m-debug-owner\n",
            "wrong-comment": good.replace(b"c2m-debug-owner", b"someone-else"),
            "no-comment": b"ssh-ed25519 " + good_b64.encode() + b"\n",
            "extra-spaces": b"ssh-ed25519  " + good_b64.encode() + b" c2m-debug-owner\n",
            "leading-space": b" " + good,
            "garbage": b"not a key\n",
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                f = self.fixture()
                f["key"].write_bytes(data)
                self.assert_blocked(f)
        # Noncanonical base64 with same bytes but extra padding/whitespace.
        f = self.fixture()
        f["key"].write_bytes(b"ssh-ed25519 " + good_b64.encode() + b"  c2m-debug-owner\n")
        self.assert_blocked(f)

    def test_no_foreign_asset_or_report_overwrite(self):
        for name in {"c2m-idle", "tsr_profile_boot.sh"} | set(D3_NAMES) | set(DEBUG_ALL):
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

    def test_all_legacy_inputs_checked_before_debug_tree_writes(self):
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
        for target in ("binary", "boot", "key", "services", "destination", "broken", "parent", "hook"):
            with self.subTest(target=target):
                f = self.fixture()
                if target in ("binary", "boot", "key", "services"):
                    source = {"binary": f["dbg"] / "c2m-debug", "boot": f["dbg"] / "debug_boot.sh",
                              "key": f["key"], "services": f["dbg"]}[target]
                    actual = f["root"] / "actual"
                    source.rename(actual)
                    source.symlink_to(actual, target_is_directory=target == "services")
                elif target in ("destination", "broken"):
                    (f["tree"] / "c2m").mkdir()
                    other = f["root"] / "other"
                    if target == "destination": other.write_bytes(b"foreign")
                    (f["tree"] / "c2m/debug_owner.pub").symlink_to(other)
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
                stub = f["root"] / "stub"
                stub.mkdir()
                for name in ("sleep", "grep"):
                    (stub / name).write_bytes(b"#!/bin/sh\nexit 1\n" if name == "grep" else b"#!/bin/sh\nexit 0\n")
                    os.chmod(stub / name, 0o755)
                for name in ("c2m-idle", "boot.sh", "debug_boot.sh", "tsr_profile_boot.sh"):
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
                names = ("c2m-idle", "boot.sh", "debug_boot.sh", "tsr_profile_boot.sh")
                deadline = time.monotonic() + 5
                while (time.monotonic() < deadline
                       and not all((stub / (name + ".seen")).is_file() for name in names)):
                    time.sleep(0.02)
                for name in names:
                    self.assertTrue((stub / (name + ".seen")).is_file(), name)

    def test_legacy_regression_without_debug(self):
        # Stock behavior without debug flags is unchanged: D3-only still works
        # and reports no debug fields or extra paths.
        f = self.fixture()
        cmd = [sys.executable, str(TOOL), "--tree", str(f["tree"]), "--manifest", str(f["stock"]),
               "--idle-bin", str(f["idle"]), "--tsr-experiment",
               "--d3-services-dir", str(f["d3"]), "--out-manifest", str(f["out"])]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        doc = json.loads(f["out"].read_text(encoding="utf-8"))
        self.assertFalse(doc.get("debug_services", False))
        self.assertNotIn("debug_owner_key_sha256", doc)
        paths = {row["path"] for row in doc["added"]}
        self.assertEqual(paths, {"/c2m", "/c2m/c2m-idle", "/c2m/tsr_profile_boot.sh"}
                         | {"/c2m/" + n for n in D3_NAMES})
        text = (f["tree"] / "wifi/rcInsDriver.sh").read_text()
        self.assertIn("/bin/sh /customer/c2m/boot.sh", text)
        self.assertNotIn("debug_boot.sh", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
