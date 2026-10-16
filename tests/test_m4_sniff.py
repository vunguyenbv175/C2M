#!/usr/bin/env python3
"""Host guards for M4 passive usb0 observer (fw/m4_sniff/m4_usb_observe.c).

Never touches camera, UART, network, vendor IPC, real package paths, or any
status file. Portable --help/--self-test/CLI checks run on Windows and Linux.
--observe runtime is Linux-only and must stay finite without usb0.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "fw" / "m4_sniff" / "m4_usb_observe.c"
ARM_SCRIPT = ROOT / "fw" / "m4_sniff" / "build_arm.sh"
FLAGS = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
LINUX = sys.platform.startswith("linux")

REQUIRED_SOURCE = (
    "M4_SNIFF_IFACE_FIXED",
    "M4_SNIFF_MAX_PACKETS",
    "M4_SNIFF_SNAPLEN",
    "M4_SNIFF_PAYLOAD_HEX_BYTES",
    "M4_SNIFF_MAX_MS",
    "m4_parse_frame",
    "m4_self_test",
    "m4_observe",
    "observer_simulation_not_production_delivery",
    "status_writes=0",
    "transmit_bytes=0",
    "iface_fixed",
    "payload_hex_fixed",
    "payload_len=",
    "payload_hex=",
    "data_packets=",
    "completion=",
    "interrupted_signal",
    "iface_unavailable",
    "capture_unavailable",
    "if_nametoindex",
    "AF_PACKET",
    "SOCK_RAW",
    "recvfrom",
    "MSG_TRUNC",
    "clock_gettime",
    "poll(",
)

REQUIRED_ARM = (
    "--out",
    "--sysroot",
    "armv7-a",
    "vfpv3-d16",
    "mfloat-abi=hard",
    "_TIME_BITS=32",
    "nostartfiles",
    "ld-linux-armhf.so.3",
    "check_elf.py",
    "--allow-dynamic",
    "qemu-arm-static",
    "--self-test",
    "--help",
    "readelf -V",
    "sha256sum",
    "compat.h",
    "fw/m4_sniff/m4_usb_observe.c",
    "c2m-m4-sniff",
    "sniff-selftest-arm.txt",
    "sniff-help-arm.txt",
    "--observe",
    "usb0",
    "set -eu",
)


def find_cc() -> str:
    cc = shutil.which(os.environ.get("CC", "gcc"))
    if cc:
        return cc
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    raise unittest.SkipTest("host C compiler not available")


def compile_binary(cc: str, output: Path) -> None:
    cmd = [cc] + FLAGS + [str(MAIN_C.relative_to(ROOT)), "-o", str(output)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise AssertionError(f"compile failed:\n{result.stdout}{result.stderr}")


class M4SniffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for path in (MAIN_C, ARM_SCRIPT):
            if not path.is_file():
                raise AssertionError(f"Missing file: {path}")
        cls.cc = find_cc()
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-m4-sniff-build-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        suffix = ".exe" if os.name == "nt" else ""
        cls.sniff = base / ("c2m-m4-sniff" + suffix)
        compile_binary(cls.cc, cls.sniff)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_bin(self, binary: Path, *args: str, timeout: float = 10.0):
        return subprocess.run([str(binary), *args], text=True, capture_output=True, timeout=timeout)

    def test_cli_only_observe_help_selftest(self) -> None:
        result = self.run_bin(self.sniff, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--observe", result.stdout)
        self.assertIn("--self-test", result.stdout)
        self.assertIn("usb0", result.stdout)
        self.assertIn("observer simulation", result.stdout)
        self.assertIn("never transmits", result.stdout)
        self.assertIn("Payload-only", result.stdout)
        self.assertNotIn("--serve", result.stdout)
        self.assertNotIn("--db", result.stdout)
        self.assertNotIn("--gps-file", result.stdout)
        self.assertNotIn("--status-file", result.stdout)
        result = self.run_bin(self.sniff, "--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("M4 USB observe self-test: OK", result.stdout)
        for args in ((), ("--unknown",), ("--serve",),
                     ("--observe", "extra"), ("--self-test", "extra")):
            with self.subTest(args=args):
                result = self.run_bin(self.sniff, *args)
                self.assertEqual(result.returncode, 2, str(args))
        raw = self.sniff.read_bytes()
        self.assertIn(b"--observe", raw)
        self.assertNotIn(b"--serve", raw)
        self.assertNotIn(b"--db", raw)
        self.assertNotIn(b"c2m_d4_status", raw)

    def test_source_shares_no_transmit_no_writer(self) -> None:
        text = MAIN_C.read_text(encoding="utf-8")
        for token in REQUIRED_SOURCE:
            self.assertIn(token, text, f"missing sniffer token: {token}")
        self.assertIn("m4_sniff=observer_v2", text)
        self.assertNotIn("m4_sniff=observer_v1", text)
        self.assertIn("delivery_sim=observer_simulation_not_production_delivery", text)
        # Observer body must never transmit or write files.
        start = text.find("static int m4_observe(")
        self.assertGreaterEqual(start, 0)
        # Bound to the observer function through the next #endif.
        end = text.find("#endif", start)
        self.assertGreater(end, start)
        body = text[start:end]
        for token in ("send(", "sendto(", "sendmsg(", "sendmmsg(", "connect(",
                      "ioctl", "setsockopt", "system(", "popen(", "fopen(",
                      "open(", "openat(", "O_CREAT", "O_WRONLY", "O_RDWR",
                      "write_status", "renameat", "c2m_d4_status",
                      "--serve", "--db", "--gps-file", "--status-file",
                      "getenv(", "/dev/", "uart"):
            self.assertNotIn(token, body, f"forbidden sniffer observer token: {token}")
        # Receive-only attach is allowed and explicitly documented.
        self.assertIn("bind(fd", body)
        self.assertIn("recvfrom", body)
        self.assertNotIn("\r", text)

    def test_arm_script_guards(self) -> None:
        raw = ARM_SCRIPT.read_bytes().decode("utf-8")
        self.assertNotIn("\r", raw, "script must be LF-only")
        for token in REQUIRED_ARM:
            self.assertIn(token, raw, f"missing ARM script token: {token}")
        for token in ("| tee", "|tee", "| grep", "|grep", "| cat", "|cat", "| sha256sum"):
            self.assertNotIn(token, raw, f"pipe hiding exit: {token}")
        self.assertIn("set -eu", raw)
        self.assertIn("--out DIR --sysroot STOCK_ROOTFS", raw)
        self.assertNotIn("sed -i", raw)
        self.assertIn("c2m_d4_status", raw)
        self.assertIn("--serve", raw)

    @unittest.skipUnless(LINUX, "--observe runtime is Linux-only")
    def test_observe_without_usb0_finite(self) -> None:
        # CI/QEMU hosts have no usb0; observer must finish finite gracefully.
        # If a host unexpectedly has usb0, accept either finite completion
        # with bounded output, never a hang or file write.
        result = self.run_bin(self.sniff, "--observe", timeout=25)
        self.assertEqual(result.stderr, "", result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr)
        self.assertLess(len(result.stdout.encode("utf-8")), 8192)
        self.assertIn("m4_sniff=observer_v2", result.stdout)
        self.assertIn("iface_fixed=usb0", result.stdout)
        self.assertIn("payload_hex_fixed=96", result.stdout)
        self.assertIn("delivery_sim=observer_simulation_not_production_delivery", result.stdout)
        self.assertIn("status_writes=0", result.stdout)
        self.assertIn("transmit_bytes=0", result.stdout)
        self.assertIn("summary packets=", result.stdout)
        self.assertIn("data_packets=", result.stdout)
        # No raw coordinates, DB labels, or status path in metadata output.
        for forbidden in ("c2m_d4_status", "--serve", "R.420", "latitude", "longitude"):
            self.assertNotIn(forbidden, result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
