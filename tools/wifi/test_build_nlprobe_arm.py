#!/usr/bin/env python3
"""Host-only static guards for tools/wifi/build_nlprobe_arm.sh.

No ARM toolchain, sysroot, QEMU, camera, or network needed. Validates the
portable contract: exact compat-pattern flags, ELF gate, QEMU pure tests,
log/version/hash capture, and fail-closed (no pipes hiding exit).
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "wifi" / "build_nlprobe_arm.sh"
SOURCE = ROOT / "tools" / "wifi" / "c2m_nlprobe.c"

REQUIRED = (
    "--out",
    "--sysroot",
    "armv7-a",
    "vfpv3-d16",
    "mfloat-abi=hard",
    "_TIME_BITS=32",
    "U_FILE_OFFSET_BITS",
    "FORTIFY_SOURCE=0",
    "fno-stack-protector",
    "fno-pie",
    "nostartfiles",
    "ld-linux-armhf.so.3",
    "no-undefined",
    "noexecstack",
    "check_elf.py",
    "--allow-dynamic",
    "qemu-arm-static",
    "--self-test",
    "--help",
    "readelf -V",
    "sha256sum",
    "compat.h",
    "c2m_nlprobe.c",
    "start.S",
    "set -eu",
    "--out DIR --sysroot STOCK_ROOTFS",
    "nlprobe-selftest-arm.txt",
    "nlprobe-help-arm.txt",
    "nlprobe_arm_hashes.txt",
    "toolchain_version.txt",
)

REQUIRED_HEADERS = (
    "<errno.h>",
    "<fcntl.h>",
    "<stdint.h>",
    "<stdio.h>",
    "<string.h>",
    "<sys/socket.h>",
    "<sys/stat.h>",
    "<sys/types.h>",
    "<time.h>",
    "<unistd.h>",
    "<poll.h>",
    "<net/if.h>",
    "<linux/netlink.h>",
    "<linux/genetlink.h>",
    "<linux/nl80211.h>",
    '"compat.h"',
)


class NlprobeArmScriptTests(unittest.TestCase):
    def test_script_present_lf(self):
        self.assertTrue(SCRIPT.is_file(), f"Missing {SCRIPT}")
        self.assertTrue(SOURCE.is_file(), f"Missing {SOURCE}")
        raw = SCRIPT.read_bytes()
        self.assertNotIn(b"\r", raw, "script must be LF-only")

    def test_exact_abi_pattern(self):
        raw = SCRIPT.read_text(encoding="utf-8")
        for token in REQUIRED:
            self.assertIn(token, raw, f"missing ARM script token: {token}")
        for header in REQUIRED_HEADERS:
            self.assertIn(header, raw, f"missing wrapper header: {header}")
        # Generated wrapper strips source macro duplicates before compat.h.
        self.assertIn("_POSIX_C_SOURCE 200809L", raw)
        self.assertIn("_DEFAULT_SOURCE", raw)
        self.assertIn("_GNU_SOURCE", raw)

    def test_fail_closed_no_pipes(self):
        raw = SCRIPT.read_text(encoding="utf-8")
        for token in ("| tee", "|tee", "| grep", "|grep", "| cat", "|cat", "| sha256sum"):
            self.assertNotIn(token, raw, f"pipe hiding exit: {token}")
        # Captures use redirect-or-fail so set -e sees the real status.
        self.assertIn('|| { cat "', raw)
        self.assertIn("grep -q 'self_test=passed'", raw)
        self.assertIn("grep -q 'linux_live_validated=no'", raw)
        self.assertIn("grep -q 'wlan0'", raw)

    def test_no_production_edits(self):
        raw = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("sed -i", raw)
        # Wrapper is generated under $out; source is only read.
        self.assertIn("nlprobe_compat.c", raw)
        self.assertIn("tools/wifi/c2m_nlprobe.c", raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
