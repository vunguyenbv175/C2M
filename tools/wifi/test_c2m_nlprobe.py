#!/usr/bin/env python3
"""Host-only guards for tools/wifi/c2m_nlprobe.c.

Never runs live modes (--get-interface/--get-wiphy*), never touches Wi-Fi
devices, routes, or camera. Compiles --self-test/--help only.
Portable-only: Linux live path is NOT validated here (see README + CI job).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "wifi" / "c2m_nlprobe.c"

FORBIDDEN = (
    "SIOCSIFFLAGS",
    "execl(",
    "execvp(",
    "system(",
    "popen(",
    "wpa_supplicant",
    "udhcpc",
    "iptables",
    "ap.sh",
    "sta.sh",
    "apsta_switch",
    "TRIGGER_SCAN",
    "START_AP",
    "CONNECT",
)

# NEW/SET/DEL_INTERFACE may appear ONLY as reply validation (NEW_*) or
# fallback defines; they must never be used as a send command.
FORBIDDEN_SEND_PATTERNS = (
    "c2m_send_init(&m, nl->family, NL80211_CMD_NEW_INTERFACE",
    "c2m_send_init(&m, nl->family, NL80211_CMD_DEL_INTERFACE",
    "c2m_send_init(&m, nl->family, NL80211_CMD_SET_INTERFACE",
    "msg_init(&m, nl->family, NL80211_CMD_NEW_INTERFACE",
    "msg_init(&m, nl->family, NL80211_CMD_DEL_INTERFACE",
)

REQUIRED = (
    "CTRL_CMD_GETFAMILY",
    "NL80211_CMD_GET_INTERFACE",
    "NL80211_CMD_GET_WIPHY",
    "C2M_NLPROBE_IFNAME",
    '"wlan0"',
    "concurrency=unknown_not_inferred",
    "value=redacted",
    "mode=single",
    "mode=dump",
    "split-dump",
    "--self-test",
    "C2M_MAX_LINES",
    "C2M_MAX_BYTES",
    "C2M_NL_TIMEOUT_MS",
    "linux_live_validated=no",
    "C2M_NLPROBE_LINUX_VALIDATED",
    "combos_summary",
    "combo_missing_maxnum",
    "combo_missing_channels",
    "combo_missing_limits",
)

# Real stable ABI numbers (linux/nl80211.h enum order). Fake test-only
# numbers (101/111/118/119) must NOT appear.
REQUIRED_ABI = (
    "NL80211_ATTR_INTERFACE_COMBINATIONS 116",
    "NL80211_ATTR_SPLIT_WIPHY_DUMP 167",
    "NL80211_ATTR_WIPHY_FREQ 38",
    "NL80211_ATTR_SSID 51",
    "NL80211_IFACE_COMB_LIMITS 1",
    "NL80211_IFACE_COMB_MAXNUM 2",
    "NL80211_IFACE_COMB_STA_AP_BI_MATCH 3",
    "NL80211_IFACE_COMB_NUM_CHANNELS 4",
)

FORBIDDEN_ABI = (
    "GET_WIPHY 101",
    "ATTR_WIPHY 111",
    "COMBINATIONS 118",
    "SPLIT_WIPHY_DUMP 119",
)


def find_cc():
    if os.environ.get("CC"):
        found = shutil.which(os.environ["CC"])
        if found:
            return found
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Git/mingw64/bin/gcc.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    win_get = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
    if win_get.is_dir():
        for gcc in win_get.glob("BrechtSanders.WinLibs*/mingw64/bin/gcc.exe"):
            if gcc.is_file():
                return str(gcc)
    return None


class NlprobeHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise AssertionError(f"Missing probe source: {SOURCE}")
        cls.cc = find_cc()
        if not cls.cc:
            raise unittest.SkipTest("C compiler not installed")
        cls.temp = tempfile.TemporaryDirectory(prefix="c2m-nlprobe-")
        cls.build = Path(cls.temp.name)
        cls.binary = cls.build / ("c2m-nlprobe.exe" if os.name == "nt" else "c2m-nlprobe")
        cmd = [cls.cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
               str(SOURCE), "-o", str(cls.binary)]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(f"Compilation failed:\n{result.stdout}{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_probe(self, *args):
        return subprocess.run([str(self.binary), *args], text=True,
                              capture_output=True, timeout=10)

    def test_source_is_read_only_allowlist(self):
        raw = SOURCE.read_text(encoding="utf-8")
        import re
        code = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
        code = re.sub(r"//.*", "", code)
        for token in FORBIDDEN:
            self.assertNotIn(token, code, f"forbidden live-mutation token: {token}")
        for token in FORBIDDEN_SEND_PATTERNS:
            self.assertNotIn(token, code, f"forbidden send token: {token}")
        for token in REQUIRED:
            self.assertIn(token, raw, f"missing required token: {token}")
        for token in REQUIRED_ABI:
            self.assertIn(token, raw, f"missing real ABI: {token}")
        for token in FORBIDDEN_ABI:
            self.assertNotIn(token, raw, f"fake test-only ABI still present: {token}")
        # Namespace-aware decoding: no global u32 allowlist, schema functions exist.
        self.assertNotIn("c2m_u32_printable", code)
        for token in ("c2m_describe_wiphy_top", "c2m_describe_combo",
                      "c2m_describe_limit", "c2m_describe_types"):
            self.assertIn(token, code, f"missing namespace decoder: {token}")
        # Enum split flag used directly (no #ifdef on enum).
        self.assertNotIn("#ifdef NL80211_ATTR_SPLIT_WIPHY_DUMP", code)
        self.assertIn("NL80211_ATTR_SPLIT_WIPHY_DUMP, NULL, 0", code)
        # Correct nlmsghdr layout (u16 type/flags).
        self.assertIn("uint16_t type", code)
        # Fixed interface: no CLI override for ifname/device.
        self.assertNotIn("--ifname", raw)
        self.assertNotIn("--interface", code)
        self.assertNotIn("--device", code)
        # Never infer unsupported.
        self.assertNotIn("supported=no", code)
        self.assertNotIn("sta_supported=no", code)

    def test_self_test_passes_and_bounded(self):
        result = self.run_probe("--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        for case in ("single_valid_combo_present", "absent_is_unknown_not_no",
                      "missing_channels_malformed", "missing_channels_detail",
                      "missing_maxnum_detail", "missing_limits_detail",
                      "truncation_malformed", "truncation_empty_absent",
                      "bi_match_unverified", "privacy_collision_no_u32_leak",
                      "privacy_secret_bytes_absent", "dump_single_explicit",
                      "shared_limit_present", "fuzz_bounded_no_crash",
                      "nlmsg_layout_16", "abi_comb_maxnum_is_2",
                      "noflag_known_schema_present"):
            self.assertIn("PASS " + case, result.stdout)
        self.assertNotIn("PASS truncation_never_present", result.stdout)
        self.assertIn("concurrency=unknown_not_inferred", result.stdout)
        self.assertIn("combos_summary", result.stdout)
        self.assertIn("linux_live_validated=no", result.stdout)
        self.assertIn("self_test=passed", result.stdout)
        self.assertLess(len(result.stdout.encode("utf-8")), 8192)
        self.assertNotIn("02:11:22", result.stdout)
        self.assertNotIn("305419896", result.stdout)

    def test_cli_usage_without_network(self):
        result = self.run_probe("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("wlan0", result.stdout)
        self.assertIn("--self-test", result.stdout)
        self.assertIn("linux_live_validated=no", result.stdout)
        for args in ((), ("--bogus",), ("--get-wiphy", "--get-wiphy-dump")):
            result = self.run_probe(*args)
            self.assertEqual(result.returncode, 2, str(args))

    def test_line_endings_and_no_shell(self):
        raw = SOURCE.read_bytes()
        self.assertNotIn(b"\r", raw, "source must be LF-only")
        text = raw.decode("utf-8")
        for token in ("system(", "popen(", "execl(", "`iw ", "$(iw"):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
