"""Rootless tests. Never run --probe/--serve or touch WiFi devices.

Run: python3 -m unittest discover -s tests -p test_d3_wifi_control.py -v
Portable fixtures compile the production reporting/retry helpers with mock types.
Linux fixtures additionally compile full source and test parsers/private files.
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


def source_function(name):
    """Extract the exact production helper, never a copied implementation."""
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(r"^static [^\n]*\b" + re.escape(name) +
                      r"\([^{}]*\) \{\n", source, re.M)
    if not match:
        raise AssertionError(f"Missing helper {name}")
    # This source uses an unindented closing brace only at function scope.
    end = source.index("\n}", match.end()) + 2
    return source[match.start():end] + "\n"


class PortableProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = (shutil.which(os.environ["CC"]) if os.environ.get("CC") else
                  shutil.which("cc") or shutil.which("gcc") or shutil.which("clang"))
        if not cls.cc:
            raise unittest.SkipTest("C compiler not installed")
        cls.temp = tempfile.TemporaryDirectory(prefix="c2m-wifi-pure-")
        cls.build = Path(cls.temp.name)
        source = SOURCE.read_text(encoding="utf-8")
        names = ("STARTUP_PROBE_ATTEMPTS", "STARTUP_PROBE_INTERVAL",
                 "IFACE_NAME_INVALID", "IFACE_TYPE_INVALID", "IFACE_FREQ_INVALID")
        defines = "\n".join(re.search(r"^#define " + name + r" .*$", source, re.M).group()
                            for name in names) + "\n"
        cls.harness = cls.build / "pure-helpers.c"
        helpers = "".join(source_function(name) for name in
                          ("ap_probe_error", "capability_probe_result", "probe_state",
                           "startup_probe_record", "startup_probe_tick"))
        cls.harness.write_text(PORTABLE_TYPES + defines + helpers + PORTABLE_HARNESS,
                               encoding="utf-8")
        cls.binary = cls.build / ("pure-helpers.exe" if os.name == "nt" else "pure-helpers")
        result = subprocess.run([cls.cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                                 str(cls.harness), "-o", str(cls.binary)],
                                text=True, capture_output=True, timeout=30)
        if result.returncode:
            cls.temp.cleanup()
            raise AssertionError(f"Compilation failed:\n{result.stdout}{result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_production_reporting_and_retry_helpers_without_linux_or_network(self):
        result = subprocess.run([str(self.binary)], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("portable_probe_helpers=passed", result.stdout)

    def test_startup_observer_is_read_only_and_never_associates(self):
        # Structural guard complements callback fixtures: retry has no mutable
        # driver, shell, supplicant, credential-read or cleanup dependencies.
        names = ("observe_capability", "probe", "get_interface", "wiphy_reply",
                 "startup_probe_no_intent", "startup_probe_tick")
        observer = "\n".join(source_function(name) for name in names)
        for forbidden in ("start_association(", "create_sta(", "cleanup(",
                          "launch_supplicant(", "read_private(", "SIOCSIFFLAGS",
                          "NL80211_CMD_NEW_INTERFACE", "NL80211_CMD_DEL_INTERFACE",
                          "execl(", "system("):
            self.assertNotIn(forbidden, observer)
        self.assertIn("NL80211_CMD_GET_INTERFACE", observer)
        self.assertIn("NL80211_CMD_GET_WIPHY", observer)
        self.assertIn('"wifi.conf"', source_function("startup_probe_no_intent"))
        self.assertIn('"connect.request"', source_function("startup_probe_no_intent"))

    def test_production_status_has_explicit_observation_errors(self):
        source = SOURCE.read_text(encoding="utf-8")
        for error in ("ap_nl80211_query_failed", "ap_name_missing_or_invalid",
                      "ap_type_missing_or_invalid", "ap_frequency_missing_or_invalid",
                      "capability_nl80211_query_failed", "capability_proof_unavailable",
                      "capability_combinations_empty", "capability_combinations_unadvertised",
                      "capability_missing_or_malformed"):
            self.assertIn('"' + error + '"', source)
        self.assertIn('w->supported = -1;', source)
        self.assertIn('STARTUP_PROBE_ATTEMPTS 30', source)
        self.assertIn('STARTUP_PROBE_INTERVAL 2000', source)


PORTABLE_TYPES = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define C2M_WIFI_AP "wlan0"
#define NL80211_IFTYPE_AP 3
struct iface { uint32_t index, phy, type, freq; char name[16]; };
struct proof { uint32_t phy, freq; int replies, seen, supported; const char *error; };
struct worker {
    int supported, owned, cfg_owned, ctrl_owned, pid_owned;
    const char *state, *error;
    int64_t next_probe;
    unsigned startup_probe_attempts;
    int startup_probe_retry;
};
'''

PORTABLE_HARNESS = r'''
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "check failed line %d: %s\n", __LINE__, #x); return 1; } } while (0)
static unsigned observations;
static int unknown(struct worker *w) {
    ++observations; w->supported = -1; w->error = "ap_frequency_missing_or_invalid"; return -1;
}
static int supported(struct worker *w) {
    ++observations; w->supported = 1; w->error = ""; return 0;
}
static int insufficient(struct worker *w) {
    ++observations; w->supported = 0; w->error = "ap_sta_combination_not_proven"; return -1;
}
int main(void) {
    struct iface ap = { 7, 0, NL80211_IFTYPE_AP, 2412, C2M_WIFI_AP };
    struct proof proof;
    struct worker w;
    unsigned i, before;
    CHECK(!*ap_probe_error(0, &ap));
    CHECK(!strcmp(ap_probe_error(-1, &ap), "ap_nl80211_query_failed"));
    CHECK(!strcmp(ap_probe_error(IFACE_NAME_INVALID, &ap), "ap_name_missing_or_invalid"));
    CHECK(!strcmp(ap_probe_error(IFACE_TYPE_INVALID, &ap), "ap_type_missing_or_invalid"));
    CHECK(!strcmp(ap_probe_error(IFACE_FREQ_INVALID, &ap), "ap_frequency_missing_or_invalid"));
    strcpy(ap.name, "wrong"); CHECK(!strcmp(ap_probe_error(0, &ap), "ap_name_missing_or_invalid"));
    strcpy(ap.name, C2M_WIFI_AP); ap.type = 2;
    CHECK(!strcmp(ap_probe_error(0, &ap), "ap_type_missing_or_invalid"));
    ap.type = NL80211_IFTYPE_AP; ap.freq = 0;
    CHECK(!strcmp(ap_probe_error(0, &ap), "ap_frequency_missing_or_invalid"));
    memset(&w, 0, sizeof(w)); memset(&proof, 0, sizeof(proof)); w.supported = 1;
    CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
    CHECK(!strcmp(w.error, "capability_nl80211_query_failed"));
    CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == -1);
    CHECK(!strcmp(w.error, "capability_missing_or_malformed"));
    proof.replies = proof.seen = 1;
    CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == 0);
    CHECK(!strcmp(probe_state(w.supported), "unsupported"));
    proof.supported = 1;
    CHECK(capability_probe_result(&w, 0, &proof) == 0 && w.supported == 1);
    CHECK(!strcmp(probe_state(w.supported), "idle"));
    CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
    proof.error = "capability_missing_or_malformed";
    CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
    CHECK(!strcmp(w.error, proof.error));
    CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == -1);
    proof.error = NULL; proof.supported = -2;
    CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == -1);
    CHECK(!strcmp(w.error, "capability_proof_unavailable"));
    proof.supported = 1; proof.replies = 2;
    CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == -1);
    proof.replies = 1; proof.seen = 2;
    CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == -1);
    proof.replies = 1; proof.seen = 1; proof.supported = 1;
    proof.error = "capability_combinations_empty";
    CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
    CHECK(!strcmp(w.error, "capability_combinations_empty"));
    CHECK(strcmp(probe_state(w.supported), "unsupported") != 0);
    proof.error = "capability_combinations_unadvertised";
    CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
    CHECK(!strcmp(w.error, "capability_combinations_unadvertised"));
    CHECK(strcmp(probe_state(w.supported), "unsupported") != 0);
    memset(&proof, 0, sizeof(proof)); proof.replies = 1;
    CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == -1);
    CHECK(!strcmp(w.error, "capability_combinations_unadvertised"));
    memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "ap_nl80211_query_failed";
    startup_probe_record(&w, 1000);
    CHECK(w.startup_probe_attempts == 1 && !strcmp(w.state, "unknown") && w.startup_probe_retry);
    CHECK(startup_probe_tick(&w, 2999, 1, unknown) == 0 && observations == 0);
    CHECK(startup_probe_tick(&w, 3000, 1, unknown) == 1 && observations == 1);
    CHECK(startup_probe_tick(&w, 5000, 1, unknown) == 0 && observations == 2);
    CHECK(startup_probe_tick(&w, 7000, 1, supported) == 1 && observations == 3);
    CHECK(!strcmp(w.state, "idle") && !w.startup_probe_retry && !*w.error);
    CHECK(startup_probe_tick(&w, 9000, 1, unknown) == 0 && observations == 3);
    memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "ap_frequency_missing_or_invalid";
    startup_probe_record(&w, 0); before = observations;
    for (i = 1; i < STARTUP_PROBE_ATTEMPTS; ++i)
        CHECK(startup_probe_tick(&w, (int64_t)i * STARTUP_PROBE_INTERVAL, 1, unknown) == 0);
    CHECK(w.startup_probe_attempts == STARTUP_PROBE_ATTEMPTS && !w.startup_probe_retry);
    CHECK(observations - before == STARTUP_PROBE_ATTEMPTS - 1);
    CHECK(startup_probe_tick(&w, 100000, 1, supported) == 0 && w.supported == -1);
    for (i = 0; i < 7; ++i) {
        memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "ap_nl80211_query_failed";
        startup_probe_record(&w, 0); before = observations;
        if (i == 1) w.owned = 1;
        if (i == 2) w.cfg_owned = 1;
        if (i == 3) w.ctrl_owned = 1;
        if (i == 4) w.pid_owned = 1;
        if (i == 5) w.state = "failed";
        CHECK(startup_probe_tick(&w, i == 6 ? -1 : 2000, i != 0, supported) == 0);
        CHECK(!w.startup_probe_retry && observations == before && w.supported == -1);
        CHECK(startup_probe_tick(&w, 4000, 1, supported) == 0 && observations == before);
    }
    memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "nl80211_unavailable";
    startup_probe_record(&w, 0);
    CHECK(startup_probe_tick(&w, 2000, 1, insufficient) == 1);
    CHECK(w.supported == 0 && !strcmp(w.state, "unsupported") && !w.startup_probe_retry);
    memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "nl80211_unavailable";
    startup_probe_record(&w, -1); CHECK(!w.startup_probe_retry);
    puts("portable_probe_helpers=passed"); return 0;
}
'''


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
                     "beacon_constraint_unverified", "config_directive_injection_blocked",
                     "combinations_empty_blocked", "combinations_empty_propagated",
                     "combinations_unadvertised_blocked", "combinations_unadvertised_propagated",
                     "combinations_absent_fallback_error", "wiphy_valid_insufficient_is_no",
                     "combinations_duplicate_malformed", "combinations_empty_before_wiphy_error",
                     "combinations_empty_wrong_phy_error", "combinations_empty_missing_phy_error",
                     "combinations_empty_duplicate_error",
                     "combinations_empty_trailing_truncated_error"):
            self.assertIn("PASS " + case, result.stdout)
        self.assertIn("self_test=passed", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_parsers_and_private_files(self):
        result = self.run_binary(self.harness_binary, str(self.build))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rootless_helpers=passed", result.stdout)

    def test_probe_classification_and_startup_retry_helpers(self):
        result = self.run_binary(self.harness_binary, str(self.build), "classification")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("probe_helpers=passed", result.stdout)

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
static int mock_probe_unknown(struct worker *w) {
    w->supported = -1; w->error = "ap_frequency_missing_or_invalid"; return -1;
}
static int mock_probe_supported(struct worker *w) {
    w->supported = 1; w->error = ""; return 0;
}
int main(int argc, char **argv) {
    struct msg m;
    struct worker w;
    struct proof proof;
    struct iface iface;
    struct interfaces interfaces;
    size_t combo;
    struct stat st;
    struct attrs it;
    struct attr a;
    char path[PATH_MAX], linkpath[PATH_MAX], status[PATH_MAX], input[8193], ssid[65], psk[65];
    unsigned char unaligned[4097];
    uint32_t v;
    size_t i;
    int fd;
    CHECK(argc == 2 || (argc == 3 && !strcmp(argv[2], "classification")));
    if (argc == 3) {
        /* Only fixtures and callbacks: no sockets, ioctls or hardware queries. */
        memset(&iface, 0, sizeof(iface)); iface.index = 7; iface.type = NL80211_IFTYPE_AP;
        strcpy(iface.name, C2M_WIFI_AP); iface.freq = 2412;
        CHECK(!strcmp(ap_probe_error(-1, &iface), "ap_nl80211_query_failed"));
        CHECK(!strcmp(ap_probe_error(IFACE_NAME_INVALID, &iface), "ap_name_missing_or_invalid"));
        CHECK(!strcmp(ap_probe_error(IFACE_TYPE_INVALID, &iface), "ap_type_missing_or_invalid"));
        CHECK(!strcmp(ap_probe_error(IFACE_FREQ_INVALID, &iface), "ap_frequency_missing_or_invalid"));
        CHECK(!*ap_probe_error(0, &iface));
        strcpy(iface.name, "other"); CHECK(!strcmp(ap_probe_error(0, &iface), "ap_name_missing_or_invalid"));
        strcpy(iface.name, C2M_WIFI_AP); iface.type = NL80211_IFTYPE_STATION;
        CHECK(!strcmp(ap_probe_error(0, &iface), "ap_type_missing_or_invalid"));
        iface.type = NL80211_IFTYPE_AP; iface.freq = 0;
        CHECK(!strcmp(ap_probe_error(0, &iface), "ap_frequency_missing_or_invalid"));
        fixture_init(&m);
        CHECK(msg_u32(&m, NL80211_ATTR_IFINDEX, 7) == 0);
        CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        CHECK(msg_u32(&m, NL80211_ATTR_IFTYPE, NL80211_IFTYPE_AP) == 0);
        CHECK(parse_iface(m.data, m.n, &iface) == IFACE_NAME_INVALID);
        CHECK(msg_attr(&m, NL80211_ATTR_IFNAME, C2M_WIFI_AP, sizeof(C2M_WIFI_AP)) == 0);
        CHECK(parse_iface(m.data, m.n, &iface) == 0 && iface.freq == 0);
        memset(&interfaces, 0, sizeof(interfaces)); interfaces.index = 7; interfaces.one = 1;
        CHECK(interface_reply(NL80211_CMD_NEW_INTERFACE, m.data, m.n, &interfaces) == 0);
        CHECK(!strcmp(ap_probe_error(0, &interfaces.target), "ap_frequency_missing_or_invalid"));
        CHECK(msg_attr(&m, NL80211_ATTR_WIPHY_FREQ, "x", 1) == 0);
        memset(&interfaces, 0, sizeof(interfaces)); interfaces.index = 7; interfaces.one = 1;
        CHECK(interface_reply(NL80211_CMD_NEW_INTERFACE, m.data, m.n, &interfaces) == -1);
        CHECK(interfaces.error == IFACE_FREQ_INVALID);
        fixture_init(&m);
        CHECK(msg_u32(&m, NL80211_ATTR_IFINDEX, 7) == 0);
        CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        CHECK(msg_attr(&m, NL80211_ATTR_IFNAME, C2M_WIFI_AP, sizeof(C2M_WIFI_AP)) == 0);
        CHECK(parse_iface(m.data, m.n, &iface) == IFACE_TYPE_INVALID);

        memset(&w, 0, sizeof(w)); w.supported = 1;
        memset(&proof, 0, sizeof(proof)); proof.freq = 2412;
        CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
        CHECK(!strcmp(w.error, "capability_nl80211_query_failed"));
        CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == -1);
        CHECK(!strcmp(w.error, "capability_missing_or_malformed"));
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        combo = fixture_begin(&m, NL80211_ATTR_INTERFACE_COMBINATIONS);
        fixture_combo(&m, 1, 1, 1, 0, 1, 1, 1); fixture_end(&m, combo);
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == 0);
        CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == 0);
        CHECK(!strcmp(w.error, "ap_sta_combination_not_proven"));
        CHECK(!strcmp(probe_state(w.supported), "unsupported"));
        /* A positive/negative fixture followed by any malformed reply is unknown. */
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        combo = fixture_begin(&m, NL80211_ATTR_INTERFACE_COMBINATIONS);
        fixture_combo(&m, 1, 1, 1, 0, 2, 1, 1); fixture_end(&m, combo);
        memset(&proof, 0, sizeof(proof)); proof.freq = 2412;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == 0);
        CHECK(capability_probe_result(&w, 0, &proof) == 0 && w.supported == 1);
        CHECK(!strcmp(probe_state(w.supported), "idle"));
        memset(&proof, 0, sizeof(proof)); proof.freq = 2412;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n - 1, &proof) == -1);
        CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
        CHECK(!strcmp(w.error, "capability_missing_or_malformed"));
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 1) == 0);
        combo = fixture_begin(&m, NL80211_ATTR_INTERFACE_COMBINATIONS);
        fixture_combo(&m, 1, 1, 1, 0, 1, 1, 1); fixture_end(&m, combo);
        memset(&proof, 0, sizeof(proof)); proof.freq = 2412;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        combo = fixture_begin(&m, NL80211_ATTR_INTERFACE_COMBINATIONS);
        {
            size_t one = fixture_begin(&m, 1), limits;
            CHECK(msg_u32(&m, NL80211_IFACE_COMB_MAXNUM, 2) == 0);
            CHECK(msg_u32(&m, NL80211_IFACE_COMB_NUM_CHANNELS, 1) == 0);
            limits = fixture_begin(&m, NL80211_IFACE_COMB_LIMITS);
            fixture_limit(&m, 1, 1, 1, 2); fixture_end(&m, limits);
            CHECK(msg_attr(&m, NL80211_IFACE_COMB_STA_AP_BI_MATCH, NULL, 0) == 0);
            fixture_end(&m, one);
        }
        fixture_end(&m, combo);
        memset(&proof, 0, sizeof(proof)); proof.freq = 2412;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
        CHECK(!strcmp(w.error, "capability_proof_unavailable"));
        /* Live bytes=0: top combinations attr present with zero payload. */
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        CHECK(msg_attr(&m, NL80211_ATTR_INTERFACE_COMBINATIONS, NULL, 0) == 0);
        memset(&proof, 0, sizeof(proof)); proof.freq = 5180;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(!strcmp(proof.error, "capability_combinations_empty"));
        CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
        CHECK(!strcmp(w.error, "capability_combinations_empty"));
        CHECK(strcmp(probe_state(w.supported), "unsupported") != 0);
        /* Valid reply with no combinations attr: unadvertised unknown. */
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        memset(&proof, 0, sizeof(proof)); proof.freq = 5180;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(!strcmp(proof.error, "capability_combinations_unadvertised"));
        CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
        CHECK(!strcmp(w.error, "capability_combinations_unadvertised"));
        CHECK(strcmp(probe_state(w.supported), "unsupported") != 0);
        /* Defensive fallback without callback error stays unadvertised. */
        memset(&proof, 0, sizeof(proof)); proof.freq = 5180; proof.replies = 1;
        CHECK(capability_probe_result(&w, 0, &proof) == -1 && w.supported == -1);
        CHECK(!strcmp(w.error, "capability_combinations_unadvertised"));
        /* Duplicate combinations attr stays malformed unknown. */
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        combo = fixture_begin(&m, NL80211_ATTR_INTERFACE_COMBINATIONS);
        fixture_combo(&m, 1, 1, 1, 0, 2, 1, 1); fixture_end(&m, combo);
        combo = fixture_begin(&m, NL80211_ATTR_INTERFACE_COMBINATIONS);
        fixture_combo(&m, 2, 1, 1, 0, 2, 1, 1); fixture_end(&m, combo);
        memset(&proof, 0, sizeof(proof)); proof.freq = 2412;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(!strcmp(proof.error, "capability_missing_or_malformed"));
        CHECK(capability_probe_result(&w, 1, &proof) == -1 && w.supported == -1);
        CHECK(!strcmp(w.error, "capability_missing_or_malformed"));
        /* Combos before WIPHY with valid empty stays empty (order-independent). */
        fixture_init(&m);
        CHECK(msg_attr(&m, NL80211_ATTR_INTERFACE_COMBINATIONS, NULL, 0) == 0);
        CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        memset(&proof, 0, sizeof(proof)); proof.freq = 5180;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(!strcmp(proof.error, "capability_combinations_empty"));
        /* Wrong PHY + empty is malformed, never empty. */
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 1) == 0);
        CHECK(msg_attr(&m, NL80211_ATTR_INTERFACE_COMBINATIONS, NULL, 0) == 0);
        memset(&proof, 0, sizeof(proof)); proof.freq = 5180;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(!strcmp(proof.error, "capability_missing_or_malformed"));
        /* Missing PHY + empty is malformed, never empty/unadvertised. */
        fixture_init(&m);
        CHECK(msg_attr(&m, NL80211_ATTR_INTERFACE_COMBINATIONS, NULL, 0) == 0);
        memset(&proof, 0, sizeof(proof)); proof.freq = 5180;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(!strcmp(proof.error, "capability_missing_or_malformed"));
        /* Empty then duplicate empty is malformed, never empty. */
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        CHECK(msg_attr(&m, NL80211_ATTR_INTERFACE_COMBINATIONS, NULL, 0) == 0);
        CHECK(msg_attr(&m, NL80211_ATTR_INTERFACE_COMBINATIONS, NULL, 0) == 0);
        memset(&proof, 0, sizeof(proof)); proof.freq = 5180;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n, &proof) == -1);
        CHECK(!strcmp(proof.error, "capability_missing_or_malformed"));
        /* Valid framing + empty + trailing truncation is malformed. */
        fixture_init(&m); CHECK(msg_u32(&m, NL80211_ATTR_WIPHY, 0) == 0);
        CHECK(msg_attr(&m, NL80211_ATTR_INTERFACE_COMBINATIONS, NULL, 0) == 0);
        memset(&proof, 0, sizeof(proof)); proof.freq = 5180;
        CHECK(wiphy_reply(NL80211_CMD_NEW_WIPHY, m.data, m.n - 1, &proof) == -1);
        CHECK(!strcmp(proof.error, "capability_missing_or_malformed"));

        memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "ap_nl80211_query_failed";
        startup_probe_record(&w, 1000);
        CHECK(!strcmp(w.state, "unknown") && w.startup_probe_attempts == 1 && w.startup_probe_retry);
        CHECK(startup_probe_tick(&w, 2999, 1, mock_probe_unknown) == 0 && w.startup_probe_attempts == 1);
        CHECK(startup_probe_tick(&w, 3000, 1, mock_probe_unknown) == 1 && w.startup_probe_attempts == 2);
        CHECK(!strcmp(w.error, "ap_frequency_missing_or_invalid"));
        CHECK(startup_probe_tick(&w, 5000, 1, mock_probe_unknown) == 0 && w.startup_probe_attempts == 3);
        CHECK(startup_probe_tick(&w, 7000, 1, mock_probe_supported) == 1);
        CHECK(w.supported == 1 && !strcmp(w.state, "idle") && !*w.error && !w.startup_probe_retry);
        CHECK(startup_probe_tick(&w, 9000, 1, mock_probe_unknown) == 0 && w.supported == 1);
        memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "ap_frequency_missing_or_invalid";
        startup_probe_record(&w, 0);
        for (i = 1; i < STARTUP_PROBE_ATTEMPTS; ++i)
            CHECK(startup_probe_tick(&w, (int64_t)i * STARTUP_PROBE_INTERVAL, 1, mock_probe_unknown) == 0);
        CHECK(w.startup_probe_attempts == STARTUP_PROBE_ATTEMPTS && !w.startup_probe_retry);
        CHECK(startup_probe_tick(&w, 100000, 1, mock_probe_supported) == 0 && w.supported == -1);
        /* Saved configuration/request intent, failure or owned resources cancel permanently. */
        for (i = 0; i < 6; ++i) {
            memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "ap_nl80211_query_failed";
            startup_probe_record(&w, 0);
            if (i == 1) w.owned = 1;
            if (i == 2) w.cfg_owned = 1;
            if (i == 3) w.ctrl_owned = 1;
            if (i == 4) w.pid_owned = 1;
            if (i == 5) w.state = "failed";
            CHECK(startup_probe_tick(&w, 2000, i != 0, mock_probe_supported) == 0);
            CHECK(!w.startup_probe_retry && w.startup_probe_attempts == 1 && w.supported == -1);
        }
        memset(&w, 0, sizeof(w)); w.supported = 0; w.error = "ap_sta_combination_not_proven";
        startup_probe_record(&w, 0); CHECK(!w.startup_probe_retry && !strcmp(w.state, "unsupported"));
        memset(&w, 0, sizeof(w)); w.supported = -1; w.error = "nl80211_unavailable";
        startup_probe_record(&w, -1); CHECK(!w.startup_probe_retry);
        puts("probe_helpers=passed"); return 0;
    }
    /* Rebuilt package services deliberately retain vendor UID/GID 1001. */
    memset(&st, 0, sizeof(st)); st.st_uid = st.st_gid = 1001;
    st.st_mode = S_IFREG | 0755;
    CHECK(trusted_supplicant("/customer/c2m/wpa_supplicant", &st));
    st.st_mode = S_IFREG | 0775;
    CHECK(!trusted_supplicant("/customer/c2m/wpa_supplicant", &st));
    st.st_mode = S_IFDIR | 0755;
    CHECK(!trusted_supplicant("/customer/c2m/wpa_supplicant", &st));
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
    memset(&w, 0, sizeof(w)); w.configfd = w.runfd = fd;
    CHECK(startup_probe_no_intent(&w));
    CHECK(make_file(fd, "wifi.conf", "not credentials", 0600) == 0);
    CHECK(!startup_probe_no_intent(&w)); CHECK(unlinkat(fd, "wifi.conf", 0) == 0);
    CHECK(symlinkat("absent", fd, "wifi.conf") == 0);
    CHECK(!startup_probe_no_intent(&w)); CHECK(unlinkat(fd, "wifi.conf", 0) == 0);
    CHECK(make_file(fd, "connect.request", "invalid", 0644) == 0);
    CHECK(!startup_probe_no_intent(&w)); CHECK(unlinkat(fd, "connect.request", 0) == 0);
    w.configfd = -1; CHECK(!startup_probe_no_intent(&w)); w.configfd = fd;
    w.runfd = -1; CHECK(!startup_probe_no_intent(&w)); w.runfd = fd;
    CHECK(!strcmp(bluetooth_presence(&w), "unknown"));
    CHECK(make_file(fd, "bluetooth.txt", "\nstatus=COMPLETE\nverdict=HCI_PRESENT_NOT_RADIO_TESTED\n", 0600) == 0);
    CHECK(!strcmp(bluetooth_presence(&w), "seen"));
    CHECK(unlinkat(fd, "bluetooth.txt", 0) == 0);
    CHECK(make_file(fd, "bluetooth.txt", "\nstatus=COMPLETE\nverdict=NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE\n", 0600) == 0);
    CHECK(!strcmp(bluetooth_presence(&w), "not_seen"));
    CHECK(unlinkat(fd, "bluetooth.txt", 0) == 0);
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
    w.status = status; w.supported = -1; w.state = "unknown"; w.error = "ap_nl80211_query_failed";
    startup_probe_record(&w, 0);
    CHECK(status_write(&w) == 0);
    CHECK(read_private(fd, "status", input, sizeof(input), NULL) > 0);
    CHECK(strstr(input, "sta_supported=unknown\n"));
    CHECK(strstr(input, "sta_state=unknown\n"));
    CHECK(strstr(input, "last_error=ap_nl80211_query_failed\n"));
    CHECK(strstr(input, "dhcp_helper=missing\n"));
    CHECK(!strstr(input, "sta_state=connected\n"));
    CHECK(fstatat(fd, "status", &st, AT_SYMLINK_NOFOLLOW) == 0 && (st.st_mode & 0777) == 0600);
    CHECK(startup_probe_tick(&w, 2000, 1, mock_probe_unknown) == 1);
    CHECK(status_write(&w) == 0);
    CHECK(read_private(fd, "status", input, sizeof(input), NULL) > 0);
    CHECK(strstr(input, "sta_supported=unknown\n"));
    CHECK(strstr(input, "last_error=ap_frequency_missing_or_invalid\n"));
    CHECK(startup_probe_tick(&w, 4000, 1, mock_probe_supported) == 1);
    CHECK(status_write(&w) == 0);
    CHECK(read_private(fd, "status", input, sizeof(input), NULL) > 0);
    CHECK(strstr(input, "sta_supported=yes\nsta_state=idle\n"));
    CHECK(strstr(input, "last_error=none\n"));
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
