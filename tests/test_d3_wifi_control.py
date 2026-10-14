"""Rootless Linux-only tests. Never run --probe/--serve or touch WiFi devices.

Run: python3 -m unittest discover -s tests -p test_d3_wifi_control.py -v
The compiled harness calls only pure parsers and temporary-file helpers.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fw" / "d3" / "wifi_control.c"


@unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux headers/toolchain")
class WifiControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which(os.environ.get("CC", "cc"))
        if not cls.cc:
            raise unittest.SkipTest("C compiler not installed")
        cls.temp = tempfile.TemporaryDirectory(prefix="c2m-wifi-tests-")
        cls.build = Path(cls.temp.name)
        cls.binary = cls.build / "c2m-wifi"
        cls.compile(SOURCE, cls.binary)
        cls.harness = cls.build / "parser-tests.c"
        cls.harness.write_text(
            '#define main controller_main\n'
            f'#include "{SOURCE.as_posix()}"\n'
            '#undef main\n' + HARNESS, encoding="utf-8")
        cls.harness_binary = cls.build / "parser-tests"
        cls.compile(cls.harness, cls.harness_binary)

    @classmethod
    def compile(cls, source, output):
        command = [cls.cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                   str(source), "-o", str(output)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError(f"Compilation failed:\n{result.stdout}{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_binary(self, binary, *args):
        return subprocess.run([str(binary), *args], text=True, capture_output=True,
                              timeout=10, cwd=self.build)

    def test_pure_self_test(self):
        result = self.run_binary(self.binary, "--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for case in ("one_channel_requires_current_frequency", "one_channel_ap_sta",
                     "separate_combinations_not_combined", "shared_limit_one_blocked",
                     "missing_combinations_blocked", "missing_channels_blocked",
                     "valid_then_malformed_blocked", "duplicate_scalar_blocked",
                     "beacon_constraint_blocked", "config_directive_injection_blocked"):
            self.assertIn("PASS " + case, result.stdout)
        self.assertIn("self_test=passed", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_parsers_and_private_files(self):
        result = self.run_binary(self.harness_binary, str(self.build))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rootless_helpers=passed", result.stdout)

    def test_cli_usage_without_network(self):
        result = self.run_binary(self.binary, "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Association only", result.stdout)
        for args in ((), ("--bogus",), ("--config-dir",), ("--probe", "--serve")):
            result = self.run_binary(self.binary, *args)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


HARNESS = r'''
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "check failed line %d: %s\n", __LINE__, #x); return 1; } } while (0)
static int make_file(int dir, const char *name, const char *text, mode_t mode) {
    int fd = openat(dir, name, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, mode);
    int rc;
    if (fd < 0) return -1;
    rc = write_all(fd, text, strlen(text)); close(fd); return rc;
}
int main(int argc, char **argv) {
    struct msg m;
    struct worker w;
    struct stat st;
    struct attrs it;
    struct attr a;
    char path[PATH_MAX], linkpath[PATH_MAX], status[PATH_MAX], input[8193], ssid[65], psk[65];
    unsigned char unaligned[4097];
    uint32_t v;
    size_t i;
    int fd;
    CHECK(argc == 2);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 0, 2, 1, 1);
    memcpy(unaligned + 1, m.data, m.n);
    CHECK(prove_combinations(unaligned + 1, m.n, 2412) == 1);
    /* Every possible truncation is denied, including unaligned input. */
    for (i = 0; i < m.n; i++) CHECK(prove_combinations(unaligned + 1, i, 2412) < 1);
    fixture_init(&m); fixture_combo(&m, 1, 1, 0, 0, 2, 1, 1);
    fixture_combo(&m, 2, 1, 1, 0, 2, 1, 1);
    CHECK(prove_combinations(m.data, m.n, 2412) == 1);
    fixture_init(&m); fixture_combo(&m, 1, 1, 1, 0, 2, 1, 0);
    CHECK(prove_combinations(m.data, m.n, 2412) == -1);
    fixture_init(&m); CHECK(msg_attr(&m, 123, "abc", 3) == 0);
    it = (struct attrs){ m.data, m.n, 0 };
    CHECK(next_attr(&it, &a) == 1); CHECK(attr_u32(&a, &v) == -1);
    CHECK(next_attr(&it, &a) == 0 && !it.bad);
    fixture_init(&m); CHECK(msg_attr(&m, 123 | NLA_F_NET_BYTEORDER, NULL, 0) == 0);
    it = (struct attrs){ m.data, m.n, 0 };
    CHECK(next_attr(&it, &a) == 0 && it.bad);
    /* Random bounded TLV input: sanitizer-friendly, pure and deterministic. */
    v = 0x12345678;
    for (i = 0; i < 10000; ++i) {
        size_t j, n = i % 256;
        for (j = 0; j < n; ++j) { v = v * 1664525U + 1013904223U; unaligned[j] = (unsigned char)(v >> 24); }
        CHECK(prove_combinations(unaligned, n, 2412) <= 1);
    }
    snprintf(input, sizeof(input), "network={\nssid=aa\nssid=bb\npsk=%064d\n}\n", 0);
    CHECK(parse_config(input, ssid, psk) == -1);
    snprintf(input, sizeof(input), "network={\nssid=\"quoted\"\npsk=%064d\n}\n", 0);
    CHECK(parse_config(input, ssid, psk) == -1);
    snprintf(input, sizeof(input), "network={\nssid=aa\npsk=%064d\n}\nnetwork={\n}\n", 0);
    CHECK(parse_config(input, ssid, psk) == -1);
    snprintf(path, sizeof(path), "%s/private", argv[1]);
    CHECK(mkdir(path, 0700) == 0);
    fd = safe_dir(path, 1, 0); CHECK(fd >= 0);
    snprintf(linkpath, sizeof(linkpath), "%s/link", argv[1]);
    CHECK(symlink(path, linkpath) == 0); CHECK(safe_dir(linkpath, 1, 0) < 0);
    CHECK(fchmod(fd, 0755) == 0); CHECK(safe_dir(path, 1, 0) < 0); CHECK(fchmod(fd, 0700) == 0);
    memset(&w, 0, sizeof(w)); w.runfd = fd;
    CHECK(consume_request(&w) == 0);
    CHECK(make_file(fd, "connect.request", "version=1\naction=connect\n", 0600) == 0);
    CHECK(consume_request(&w) == 1);
    CHECK(fstatat(fd, "connect.request", &st, AT_SYMLINK_NOFOLLOW) < 0 && errno == ENOENT);
    CHECK(make_file(fd, "connect.request", "version=1\naction=disconnect\n", 0600) == 0);
    CHECK(consume_request(&w) == -1);
    CHECK(make_file(fd, "connect.request", "version=1\naction=connect\n", 0644) == 0);
    CHECK(consume_request(&w) == -1); CHECK(unlinkat(fd, "connect.request", 0) == 0);
    CHECK(make_file(fd, "secret", "top-secret", 0600) == 0);
    CHECK(symlinkat("secret", fd, "connect.request") == 0);
    CHECK(consume_request(&w) == -1); CHECK(unlinkat(fd, "connect.request", 0) == 0);
    CHECK(read_private(fd, "secret", input, sizeof(input), NULL) == 10);
    CHECK(linkat(fd, "secret", fd, "hardlink", 0) == 0);
    CHECK(read_private(fd, "secret", input, sizeof(input), NULL) < 0);
    CHECK(unlinkat(fd, "hardlink", 0) == 0);
    CHECK(strlen(path) + sizeof("/status") <= sizeof(status));
    memcpy(status, path, strlen(path));
    memcpy(status + strlen(path), "/status", sizeof("/status"));
    w.status = status; w.supported = -1; w.state = "unknown"; w.error = "nl80211_unavailable";
    CHECK(status_write(&w) == 0);
    CHECK(read_private(fd, "status", input, sizeof(input), NULL) > 0);
    CHECK(strstr(input, "sta_supported=unknown\n"));
    CHECK(strstr(input, "dhcp_helper=missing\n"));
    CHECK(!strstr(input, "sta_state=connected\n"));
    CHECK(fstatat(fd, "status", &st, AT_SYMLINK_NOFOLLOW) == 0 && (st.st_mode & 0777) == 0600);
    w.supported = 1; w.state = "associated_no_ip"; w.error = "dhcp_helper_missing";
    CHECK(status_write(&w) == 0);
    CHECK(read_private(fd, "status", input, sizeof(input), NULL) > 0);
    CHECK(strstr(input, "sta_state=associated_no_ip\n"));
    CHECK(unlinkat(fd, "status", 0) == 0);
    CHECK(symlinkat("secret", fd, "status") == 0);
    CHECK(status_write(&w) < 0);
    CHECK(read_private(fd, "secret", input, sizeof(input), NULL) == 10);
    CHECK(strcmp(input, "top-secret") == 0);
    close(fd); puts("rootless_helpers=passed"); return 0;
}
'''

if __name__ == "__main__":
    unittest.main()
