#!/usr/bin/env python3
"""Host-only Candidate F boot voice gates.

Synthetic tests for:
  - tools/fw/mutate_customer.py --bootvoice-services-dir
    (exact five-file set, ELF32/ARM helper, LF shell, PCM16/mono/24 kHz wavs,
    duplicate/path/symlink refusal, required D3+checked-TSR host);
  - the detached launch position (before the bounded SD mount wait);
  - tools/fw/verify_b_manifest.py round-trip for the added voice assets;
  - fail-closed boot hook / read-only helper source expectations.

No device, card, private vault, firmware byte or network access.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / "tools" / "fw"
sys.path.insert(0, str(FW))

VOICE_NAMES = ("c2m-light", "boot_voice.sh", "Boot_Greeting.wav",
               "Light_Dark_TurnOn.wav", "Light_Bright_TurnOff.wav")
D3_NAMES = ("boot.sh", "connectivity_probe.sh", "c2m-web", "c2m-wifi",
            "wpa_supplicant")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wav(payload: bytes = b"voice") -> bytes:
    data = payload * 16
    fmt = struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16)
    chunks = (b"fmt " + struct.pack("<I", len(fmt)) + fmt
              + b"data" + struct.pack("<I", len(data)) + data)
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def fake_elf() -> bytes:
    data = bytearray(64)
    data[:6] = b"\x7fELF\x01\x01"
    data[16:18] = struct.pack("<H", 2)   # ET_EXEC
    data[18:20] = struct.pack("<H", 40)  # EM_ARM
    return bytes(data)


def shell(text: str) -> bytes:
    return ("#!/bin/sh\n" + text + "\nexit 0\n").encode("ascii")


class BootVoiceFixture:
    def __init__(self, root: Path):
        self.root = root
        self.tree = root / "tree"
        (self.tree / "wifi").mkdir(parents=True)
        (self.tree / "other").mkdir()
        self.hook = self.tree / "wifi" / "rcInsDriver.sh"
        self.hook.write_bytes(shell(
            "sleep 1\n"
            "WIFIFUNC=`nvconf get 0 Camera.Menu.WifiConf`\n"
            "echo done"))
        self.stock = root / "stock.json"
        entries = [
            {"path": "/", "type": "dir", "mode": 0o775,
             "uid": 1001, "gid": 1001},
            {"path": "/wifi", "type": "dir", "mode": 0o775,
             "uid": 1001, "gid": 1001},
        ]
        hook_data = self.hook.read_bytes()
        entries.append({"path": "/wifi/rcInsDriver.sh", "type": "reg",
                        "mode": 0o755, "uid": 1001, "gid": 1001,
                        "size": len(hook_data), "sha256": digest(hook_data),
                        "mtime": 1691062660})
        self.stock.write_text(json.dumps({"entries": entries}),
                              encoding="utf-8")
        self.entries = entries

        self.idle = root / "c2m-idle"
        self.idle.write_bytes(b"idle-binary")

        self.d3 = root / "d3-services"
        self.d3.mkdir()
        (self.d3 / "boot.sh").write_bytes(shell("echo boot"))
        (self.d3 / "connectivity_probe.sh").write_bytes(shell("echo probe"))
        for name in ("c2m-web", "c2m-wifi", "wpa_supplicant"):
            (self.d3 / name).write_bytes(fake_elf())

        self.voice = root / "bootvoice-services"
        self.voice.mkdir()
        (self.voice / "c2m-light").write_bytes(fake_elf())
        (self.voice / "boot_voice.sh").write_bytes(
            shell("echo boot voice"))
        (self.voice / "Boot_Greeting.wav").write_bytes(wav(b"greet"))
        (self.voice / "Light_Dark_TurnOn.wav").write_bytes(wav(b"dark"))
        (self.voice / "Light_Bright_TurnOff.wav").write_bytes(wav(b"bright"))

        self.out = root / "mutation.json"

    def mutate(self, tool_extra=None):
        command = [
            sys.executable, str(FW / "mutate_customer.py"),
            "--tree", str(self.tree),
            "--manifest", str(self.stock),
            "--idle-bin", str(self.idle),
            "--d3-services-dir", str(self.d3),
            "--bootvoice-services-dir", str(self.voice),
            "--tsr-experiment",
            "--out-manifest", str(self.out),
        ]
        if tool_extra:
            command += tool_extra
        return subprocess.run(command, capture_output=True, text=True, timeout=60)

    def actual_manifest(self, path: Path) -> Path:
        actual = []
        for entry in self.entries:
            row = dict(entry)
            if row["path"] == "/wifi/rcInsDriver.sh":
                data = self.hook.read_bytes()
                row["size"] = len(data)
                row["sha256"] = digest(data)
                row["mtime"] = 1799999999
            actual.append(row)
        actual.append({"path": "/c2m", "type": "dir", "mode": 0o755,
                       "uid": 1001, "gid": 1001})
        for item in json.loads(self.out.read_text(encoding="utf-8"))["added"]:
            if item["type"] == "dir":
                row = dict(item)
            else:
                data = (self.tree / item["path"].lstrip("/")).read_bytes()
                row = dict(item)
                row["size"] = len(data)
                row["sha256"] = digest(data)
            actual.append(row)
        path.write_text(json.dumps({"entries": actual}), encoding="utf-8")
        return path

    def verify(self):
        actual = self.actual_manifest(self.root / "actual.json")
        report = self.root / "verify.json"
        result = subprocess.run([
            sys.executable, str(FW / "verify_b_manifest.py"),
            "--stock", str(self.stock),
            "--mut", str(self.out),
            "--actual", str(actual),
            "--out", str(report),
        ], capture_output=True, text=True, timeout=60)
        return result, json.loads(report.read_text(encoding="utf-8"))


class BootVoiceTest(unittest.TestCase):
    def setUp(self):
        temporary_root = (Path(os.environ["LOCALAPPDATA"]) / "Temp/opencode"
                          if os.name == "nt" else None)
        self.tmp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._fixture_index = 0

    def fixture(self) -> BootVoiceFixture:
        self._fixture_index += 1
        root = self.root / f"fixture{self._fixture_index}"
        root.mkdir()
        return BootVoiceFixture(root)

    def test_exact_set_and_round_trip(self):
        fixture = self.fixture()
        result = fixture.mutate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        mutation = json.loads(fixture.out.read_text(encoding="utf-8"))
        self.assertTrue(mutation.get("bootvoice_services"))
        self.assertEqual(mutation["bootvoice"]["threshold"], 500)
        self.assertEqual(mutation["bootvoice"]["light_default_source"],
                         "stock-day-night-schedule")
        self.assertEqual(mutation["bootvoice"]["light_schedule"],
                         "06:00:01-17:59:59")
        self.assertEqual(mutation["bootvoice"]["ae_helper"], "manual-only")
        self.assertIn("voice-only", mutation["bootvoice"]["actuation"])
        added = {item["path"] for item in mutation["added"]}
        for name in VOICE_NAMES:
            self.assertIn("/c2m/" + name, added)
        self.assertIn("/c2m/c2m-idle", added)
        self.assertIn("/c2m/tsr_profile_boot.sh", added)
        for name, mode in (("c2m-light", 0o755), ("boot_voice.sh", 0o755),
                           ("Boot_Greeting.wav", 0o644),
                           ("Light_Dark_TurnOn.wav", 0o644),
                           ("Light_Bright_TurnOff.wav", 0o644)):
            item = next(x for x in mutation["added"] if x["path"] == "/c2m/" + name)
            self.assertEqual(item["mode"], mode)
            self.assertEqual(item["uid"], 1001)
            self.assertEqual(item["gid"], 1001)
            self.assertTrue((fixture.tree / "c2m" / name).is_file())

        hook = fixture.hook.read_text(encoding="utf-8")
        voice_index = hook.index("/customer/c2m/boot_voice.sh")
        idle_index = hook.index("/customer/c2m/c2m-idle")
        mount_wait = hook.index("grep -qs ' /mnt/mmc ' /proc/mounts")
        self.assertLess(voice_index, idle_index)
        self.assertLess(voice_index, mount_wait)
        self.assertEqual(hook.count("/customer/c2m/boot_voice.sh"), 1)

        result, report = fixture.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["verdict"], "OK")
        self.assertTrue(report["hook"])

    def test_refuses_missing_and_extra_voice_assets(self):
        fixture = self.fixture()
        (fixture.voice / "Light_Bright_TurnOff.wav").unlink()
        result = fixture.mutate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly", result.stdout + result.stderr)

        fixture = self.fixture()
        (fixture.voice / "extra.bin").write_bytes(b"extra")
        result = fixture.mutate()
        self.assertNotEqual(result.returncode, 0)

    def test_refuses_bad_wav_and_bad_elf(self):
        fixture = self.fixture()
        (fixture.voice / "Boot_Greeting.wav").write_bytes(b"not a wav")
        result = fixture.mutate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("wav rejected", result.stdout + result.stderr)

        fixture = self.fixture()
        (fixture.voice / "c2m-light").write_bytes(b"not an elf")
        result = fixture.mutate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ELF32", result.stdout + result.stderr)

    def test_bootvoice_requires_d3_and_checked_tsr(self):
        fixture = self.fixture()
        command = [
            sys.executable, str(FW / "mutate_customer.py"),
            "--tree", str(fixture.tree),
            "--manifest", str(fixture.stock),
            "--idle-bin", str(fixture.idle),
            "--bootvoice-services-dir", str(fixture.voice),
            "--out-manifest", str(fixture.out),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)

    def test_source_shape_is_fail_closed(self):
        hook = (ROOT / "fw" / "voice" / "boot_voice.sh").read_text(encoding="utf-8")
        self.assertIn("audioplay 1 dev0", hook)
        self.assertIn("Light_Dark_TurnOn.wav", hook)
        self.assertIn("Light_Bright_TurnOff.wav", hook)
        self.assertIn("state=dark", hook)
        self.assertIn("state=bright", hook)
        self.assertIn("timeout 5", hook)
        self.assertIn("exit 0", hook)
        self.assertIn("_clock_state", hook)
        self.assertIn("06:00:01-17:59:59", hook)
        self.assertIn("AE_LIGHT_ENABLE", hook)
        self.assertIn("date +%H", hook)

        helper = (ROOT / "fw" / "voice" / "light.c").read_text(encoding="utf-8")
        self.assertIn("MI_ISP_AE_QueryExposureInfo", helper)
        self.assertIn("0x230", helper)
        self.assertIn("DEFAULT_THRESHOLD 500", helper)
        self.assertIn('"state=%s lv=%d samples=%d threshold=%d\\n"', helper)
        self.assertIn("libmi_sys.so", helper)
        self.assertIn("libcam_os_wrapper.so", helper)
        self.assertIn("libcus3a.so", helper)
        self.assertIn("RTLD_GLOBAL", helper)
        self.assertIn("return 2;", helper)

        build = (ROOT / "fw" / "voice" / "build.sh").read_text(encoding="utf-8")
        self.assertIn("--sysroot", build)
        self.assertIn("libdl-2.30.so", build)
        self.assertIn("--allow-shlib-undefined", build)
        self.assertIn("check_elf.py", build)
        self.assertIn("--self-test", build)

    def test_rebuild_manifest_gate_allows_only_voice_additions(self):
        fixture = self.fixture()
        result = fixture.mutate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        mutation = json.loads(fixture.out.read_text(encoding="utf-8"))
        added_paths = {item["path"] for item in mutation["added"]}
        self.assertTrue(added_paths.issuperset({"/c2m/" + n for n in VOICE_NAMES}))
        # A stray extra path in the rebuilt image must remain a BLOCK.
        actual_path = fixture.actual_manifest(self.root / "actual.json")
        document = json.loads(actual_path.read_text(encoding="utf-8"))
        document["entries"].append({"path": "/c2m/rogue.bin", "type": "reg",
                                    "mode": 0o755, "uid": 1001, "gid": 1001,
                                    "size": 1, "sha256": "00" * 32})
        actual_path.write_text(json.dumps(document), encoding="utf-8")
        result = subprocess.run([
            sys.executable, str(FW / "verify_b_manifest.py"),
            "--stock", str(fixture.stock),
            "--mut", str(fixture.out),
            "--actual", str(actual_path),
        ], capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UNEXPECTED-PATHS", result.stdout + result.stderr)

    def test_host_light_logic_with_fake_isp(self):
        """Compile the real helper on the host and drive a fake ISP library.

        Linux-only: it exercises the exact light.c argument/offset/median/
        fail-closed logic with dlopen, without any ARM toolchain or device.
        """
        if not sys.platform.startswith("linux"):
            self.skipTest("host dlopen/dlfcn test is Linux-only")
        compiler = os.environ.get("CC", "cc")
        if shutil.which(compiler) is None:
            self.skipTest("no host C compiler")
        work = self.root / "hostlight"
        work.mkdir()
        fake = work / "fake_isp.c"
        fake.write_text(
            "#include <stdlib.h>\n"
            "#include <string.h>\n"
            "static int calls = 0;\n"
            "static int seq[16];\n"
            "static int seq_count = 0;\n"
            "__attribute__((constructor)) static void init_seq(void) {\n"
            "    const char *s = getenv(\"FAKE_SEQ\");\n"
            "    if (!s) { seq[0] = 800; seq_count = 1; return; }\n"
            "    while (*s && seq_count < 16) {\n"
            "        seq[seq_count++] = atoi(s);\n"
            "        while (*s && *s != ',') s++;\n"
            "        if (*s) s++;\n"
            "    }\n"
            "    if (seq_count == 0) { seq[0] = 800; seq_count = 1; }\n"
            "}\n"
            "int MI_ISP_AE_QueryExposureInfo(int dev, int chn, void *info) {\n"
            "    int lv;\n"
            "    (void)dev; (void)chn;\n"
            "    if (getenv(\"FAKE_RC\")) return 1;\n"
            "    lv = seq[calls < seq_count ? calls : seq_count - 1];\n"
            "    calls++;\n"
            "    memset(info, 0, 0x404);\n"
            "    memcpy((char *)info + 0x230, &lv, sizeof lv);\n"
            "    return 0;\n"
            "}\n", encoding="ascii")
        lib = work / "libmi_isp.so"
        binary = work / "c2m-light"
        for command in (
            [compiler, "-shared", "-fPIC", "-O2", str(fake), "-o", str(lib)],
            [compiler, "-O2", str(ROOT / "fw" / "voice" / "light.c"),
             "-o", str(binary), "-ldl"],
        ):
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        def run(fake_seq, extra=()):
            environment = dict(os.environ)
            environment["FAKE_SEQ"] = fake_seq
            environment.pop("FAKE_RC", None)
            return subprocess.run(
                [str(binary), "--lib", str(lib), "--interval-ms", "0",
                 "--samples", "3", *extra],
                capture_output=True, text=True, timeout=30, env=environment)

        result = run("800")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("state=bright lv=800", result.stdout)

        result = run("100")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("state=dark lv=100", result.stdout)

        # Median rejects the single outlier on either side.
        result = run("900,100,900")
        self.assertIn("state=bright lv=900", result.stdout)
        result = run("100,900,100")
        self.assertIn("state=dark lv=100", result.stdout)

        # Threshold is inclusive.
        result = run("500", ("--threshold", "501"))
        self.assertIn("state=dark lv=500", result.stdout)

        # API failure and implausible values stay unknown, never guessed.
        environment = dict(os.environ)
        environment["FAKE_RC"] = "1"
        result = subprocess.run(
            [str(binary), "--lib", str(lib), "--interval-ms", "0",
             "--samples", "1"],
            capture_output=True, text=True, timeout=30, env=environment)
        self.assertEqual(result.returncode, 2)

        result = run("999999")
        self.assertEqual(result.returncode, 2)

        result = subprocess.run([str(binary), "--self-test"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertIn("c2m-light", result.stdout)


if __name__ == "__main__":
    unittest.main()
