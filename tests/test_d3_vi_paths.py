"""D3 VI stock-path gates (offline, rootless, no radio/hardware).

Verifies fw/d3/wifi_control.c trusts exactly the read-only observed stock
ancestors and nothing else:

  VI rootfs cpio (V2023.09.20.1_C2M_U_FR_WIFI_VI.tar, local readonly carve):
    /tmp, /var, /customer = 0755 1000:1000
  VI customer UBIFS manifest (same local carve, 227 entries):
    /minieye, /minieye/config = 0755 1000:1000
  EN preserved facts:
    /tmp = 0775 1001:1001, /customer = 1001:1001 at 0755 (legacy
    pre-preservation rebuild, observed on the D4-debug field image) and at
    0775 (stock EN customer UBIFS root, observed on the Candidate E field
    image and in the stock EN customer manifest),
    /customer/minieye(+/config) = 0775 1001:1001

Only /tmp, /customer, /customer/minieye(+/config) are trusted; /var is
documented but NOT trusted (not on the wifi config/run path). Root-sticky
/tmp still passes via the unchanged safe_dir branch, never via
stock_config_ancestor. No AP bypass, no new network operation, no
credential handling in the ancestor helper. IPv4 AP-only (wlan0/c2msta0)
pins stay.

Run: python3 -m unittest discover -s tests -p test_d3_vi_paths.py -v
Linux compiles the full production source and exercises the real helper.
Windows runs the static gates only (Linux headers unavailable).
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fw" / "d3" / "wifi_control.c"
HEADER = ROOT / "fw" / "d3" / "wifi_control.h"


def source_function(name):
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(r"^static [^\n]*\b" + re.escape(name) +
                      r"\([^{}]*\) \{\n", source, re.M)
    if not match:
        raise AssertionError(f"Missing helper {name}")
    end = source.index("\n}", match.end()) + 2
    return source[match.start():end] + "\n"


class StaticViPathGates(unittest.TestCase):
    def test_source_present(self):
        self.assertTrue(SOURCE.is_file())
        self.assertTrue(HEADER.is_file())

    def test_ap_pins_ipv4_only_stay(self):
        header = HEADER.read_text(encoding="utf-8")
        self.assertIn('#define C2M_WIFI_AP "wlan0"', header)
        self.assertIn('#define C2M_WIFI_STA "c2msta0"', header)
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('strcmp(ap.name, C2M_WIFI_AP)', source)
        self.assertIn('strcmp(ap.name, C2M_WIFI_AP) ||', source)
        self.assertIn('C2M_WIFI_STA', source)
        # No wildcard bind, no STA-facing reconfiguration in this file.
        for banned in ("0.0.0.0", "INADDR_ANY", "apsta_switch",
                       "sta.sh", "ap.sh"):
            self.assertNotIn(banned, source)

    def test_stock_ancestor_exact_tuples_present(self):
        fn = source_function("stock_config_ancestor")
        for token in ('"/tmp"', '"/customer"',
                      '"/customer/minieye"',
                      '"/customer/minieye/config"',
                      "1000", "1001", "0755", "0775"):
            self.assertIn(token, fn)
        # Both VI and EN pairs must be spelled out explicitly.
        self.assertIn("st_uid == 1000", fn)
        self.assertIn("st_uid == 1001", fn)

    def test_stock_ancestor_no_general_allow(self):
        fn = source_function("stock_config_ancestor")
        # Exact paths only; unknown paths fall through to return 0.
        self.assertIn("return 0;", fn)
        # 0777 as a standalone mode (not the 07777 mask) must never appear.
        self.assertIsNone(re.search(r"(?<![0-9])0777(?![0-9])", fn.replace("07777", "")))
        for banned in ("chmod", "chown", "mkdir",
                       "socket(", "ioctl(", "connect(", "send(",
                       "NL80211_", "ssid", "psk", "wifi.conf"):
            self.assertNotIn(banned, fn)
        # Root-sticky must NOT be accepted inside this helper (safe_dir
        # owns that branch separately and is unchanged).
        self.assertNotIn("S_ISVTX", fn)

    def test_safe_dir_root_sticky_branch_unchanged(self):
        fn = source_function("safe_dir")
        self.assertIn("S_ISVTX", fn)
        self.assertIn("O_NOFOLLOW", fn)
        self.assertIn("stock_config_ancestor(walk, &st)", fn)


@unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux headers/toolchain")
class ViAncestorLinuxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which(os.environ.get("CC", "cc"))
        if not cls.cc:
            raise unittest.SkipTest("C compiler not installed")
        cls.temp = tempfile.TemporaryDirectory(prefix="c2m-vi-paths-")
        cls.build = Path(cls.temp.name)
        cls.harness = cls.build / "vi-paths.c"
        cls.harness.write_text(
            '#define main controller_main\n'
            f'#include "{SOURCE.as_posix()}"\n'
            '#undef main\n' + HARNESS, encoding="utf-8")
        cls.binary = cls.build / "vi-paths"
        result = subprocess.run(
            [cls.cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
             str(cls.harness), "-o", str(cls.binary)],
            text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError(
                f"Compilation failed:\n{result.stdout}{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_vi_en_ancestors_and_negatives(self):
        result = subprocess.run(
            [str(self.binary)], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("vi_paths=passed", result.stdout)


HARNESS = r'''
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "check failed line %d: %s\n", __LINE__, #x); return 1; } } while (0)
static void mk(struct stat *st, unsigned uid, unsigned gid, unsigned mode) {
    memset(st, 0, sizeof(*st));
    st->st_uid = uid; st->st_gid = gid;
    st->st_mode = (mode_t)(S_IFDIR | mode);
}
static void mkreg(struct stat *st, unsigned uid, unsigned gid, unsigned mode) {
    memset(st, 0, sizeof(*st));
    st->st_uid = uid; st->st_gid = gid;
    st->st_mode = (mode_t)(S_IFREG | mode);
}
int main(void) {
    struct stat st;
    /* /tmp: VI 0755 1000:1000 and EN 0775 1001:1001 only. */
    mk(&st, 1000, 1000, 0755); CHECK(stock_config_ancestor("/tmp", &st));
    mk(&st, 1001, 1001, 0775); CHECK(stock_config_ancestor("/tmp", &st));
    mk(&st, 0, 0, 01777); CHECK(!stock_config_ancestor("/tmp", &st));
    mk(&st, 1000, 1000, 0775); CHECK(!stock_config_ancestor("/tmp", &st));
    mk(&st, 1001, 1001, 0755); CHECK(!stock_config_ancestor("/tmp", &st));
    mk(&st, 1000, 1000, 0777); CHECK(!stock_config_ancestor("/tmp", &st));
    mk(&st, 0, 0, 0755); CHECK(!stock_config_ancestor("/tmp", &st));
    /* /customer: 0755 with 1000:1000 (VI), 1001:1001 at 0755 (legacy EN
     * rebuild fact) and at 0775 (stock EN UBIFS root; Candidate E field). */
    mk(&st, 1000, 1000, 0755); CHECK(stock_config_ancestor("/customer", &st));
    mk(&st, 1001, 1001, 0755); CHECK(stock_config_ancestor("/customer", &st));
    mk(&st, 1001, 1001, 0775); CHECK(stock_config_ancestor("/customer", &st));
    mk(&st, 1000, 1000, 0775); CHECK(!stock_config_ancestor("/customer", &st));
    mk(&st, 0, 0, 0755); CHECK(!stock_config_ancestor("/customer", &st));
    /* /customer/minieye and /config: VI 0755 1000 vs EN 0775 1001. */
    mk(&st, 1000, 1000, 0755); CHECK(stock_config_ancestor("/customer/minieye", &st));
    mk(&st, 1001, 1001, 0775); CHECK(stock_config_ancestor("/customer/minieye", &st));
    mk(&st, 1001, 1001, 0755); CHECK(!stock_config_ancestor("/customer/minieye", &st));
    mk(&st, 1000, 1000, 0775); CHECK(!stock_config_ancestor("/customer/minieye", &st));
    mk(&st, 1000, 1000, 0755); CHECK(stock_config_ancestor("/customer/minieye/config", &st));
    mk(&st, 1001, 1001, 0775); CHECK(stock_config_ancestor("/customer/minieye/config", &st));
    mk(&st, 1001, 1001, 0755); CHECK(!stock_config_ancestor("/customer/minieye/config", &st));
    mk(&st, 1000, 1000, 0775); CHECK(!stock_config_ancestor("/customer/minieye/config", &st));
    mk(&st, 1000, 1000, 0777); CHECK(!stock_config_ancestor("/customer/minieye/config", &st));
    /* Untrusted paths and prefixes never pass. */
    mk(&st, 1000, 1000, 0755); CHECK(!stock_config_ancestor("/var", &st));
    mk(&st, 1001, 1001, 0775); CHECK(!stock_config_ancestor("/var", &st));
    mk(&st, 1000, 1000, 0755); CHECK(!stock_config_ancestor("/etc", &st));
    mk(&st, 1000, 1000, 0755); CHECK(!stock_config_ancestor("/customer/other", &st));
    mk(&st, 1000, 1000, 0755); CHECK(!stock_config_ancestor("/", &st));
    mk(&st, 1000, 1000, 0755); CHECK(!stock_config_ancestor("/customer/minieye/config/extra", &st));
    /* Supplicant trust stays EN 1001-only (our rebuilt binary, not VI stock). */
    mkreg(&st, 1001, 1001, 0755);
    CHECK(trusted_supplicant("/customer/c2m/wpa_supplicant", &st));
    mkreg(&st, 1000, 1000, 0755);
    CHECK(!trusted_supplicant("/customer/c2m/wpa_supplicant", &st));
    puts("vi_paths=passed"); return 0;
}
'''

if __name__ == "__main__":
    unittest.main()
