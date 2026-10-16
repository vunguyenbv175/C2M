#!/usr/bin/env python3
"""Offline static gates for .github/workflows/firmware-candidateD5-vi.yml.

No hardware, network, vault, commits or subagents. Checks the workflow text
plus already-checked-in repo facts (GPS fix, supervisor lifetime header,
health source, test files). Fails closed on any missing gate.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github/workflows/firmware-candidateD5-vi.yml"

VI_TAR = "V2023.09.20.1_C2M_U_FR_WIFI_VI.tar"
VI_SHA = "f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa"
EN_TAR = "V2023.08.03.1_C2M_U_FR_WIFI_EN.tar"
EN_SHA = "3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c"


def text() -> str:
    return WF.read_text(encoding="utf-8")


class WorkflowStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert WF.is_file(), "D5-VI workflow missing"
        cls.wf = text()

    def test_manual_only(self) -> None:
        self.assertIn("workflow_dispatch", self.wf)
        for trigger in ("push:", "pull_request:", "schedule:", "workflow_call:"):
            self.assertNotIn(trigger, self.wf)

    def test_vi_base_only_no_en_mix(self) -> None:
        self.assertIn(VI_TAR, self.wf)
        self.assertIn(VI_SHA, self.wf)
        self.assertIn("20230920185743", self.wf)
        self.assertIn("8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314", self.wf)
        self.assertIn("56db44d98c9af96ef38319e95374e505a128010e91ff773d2c35843d4be9bf23", self.wf)
        self.assertIn("997b71c27edcd49c2b0465333f53274e73ec1086023af972a39a22dfa95527d1", self.wf)
        # EN identifiers may appear ONLY in explicit refusal contexts
        # (never fetch/mix EN into a VI base).
        for token in (EN_TAR, EN_SHA,
                      "c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030",
                      "344b4a3fdc1cfbb13e6d1ee8a45cd2c9c99b8d63d1f90e8c193a1cc89a288a8c"):
            for line in self.wf.splitlines():
                if token in line:
                    self.assertTrue(
                        any(k in line for k in ("must not", "refused", "refuse",
                                                "NEVER", "never mixed", "mix refused",
                                                "VI base only", "VI-only", "EN mix",
                                                "test ! -f")),
                        f"EN token outside refusal context: {line.strip()[:160]}")

    def test_vi_adas_unverified_not_incompatible(self) -> None:
        low = self.wf.lower()
        self.assertIn("unverified", low)
        # "incompatible" may appear ONLY in prohibition lines (never a claim).
        for line in self.wf.splitlines():
            if "incompatible" in line.lower():
                self.assertTrue(
                    any(k in line.lower() for k in ("never", "not ", "do not",
                                                     "unverified", "no proof")),
                    f"incompatible outside prohibition: {line.strip()[:160]}")

    def test_contract_private_and_profile(self) -> None:
        self.assertIn("work/VI_PACKAGE_CONTRACT.json", self.wf)
        self.assertIn("package_contract.py", self.wf)
        self.assertIn("--base-profile vi", self.wf)
        self.assertIn("--base-tar", self.wf)
        self.assertIn("NEVER a public artifact", self.wf)
        # Evidence allowlist must never publish the private contract/script.
        evidence = self.wf.split("Upload D5-VI evidence", 1)[1]
        for banned in ("VI_PACKAGE_CONTRACT", "EN_PACKAGE_CONTRACT_B",
                       "upgrade_script", ".wav", ".pub", "signs-d4.bin",
                       "debug_owner", ".tar"):
            # fw/d5/health.sh is the one allowed public-safe .sh source.
            if banned == ".pub":
                self.assertNotIn("debug_owner.pub", evidence)
                self.assertNotIn("debug-private", evidence)
                continue
            if banned == ".wav":
                self.assertNotIn(".wav", evidence)
                continue
            if banned == ".tar":
                # Only SHA256SUMS/FLASH_README may mention tars by hash text.
                self.assertNotIn("EN_REPACK_GOLDEN.tar\n", evidence)
                continue
            self.assertNotIn(banned, evidence)

    def test_sysroot_vi_and_nss_pin(self) -> None:
        self.assertIn("carve/rootfs.es.load0", self.wf)
        self.assertIn("VI stock", self.wf)
        self.assertIn("381a2aa8348259f1722aa09a90c4345a4460a94350d60b1df6782b3dc23ebffd", self.wf)
        self.assertIn("361400", self.wf)

    def test_gps_fix_and_connectivity_v2(self) -> None:
        self.assertIn("> 999u", self.wf)
        self.assertIn("probe=C2M_D3_PASSIVE_BLUETOOTH_V2", self.wf)
        src = (ROOT / "fw/d3/gps_snapshot.c").read_text(encoding="utf-8")
        self.assertIn("> 999u", src)
        self.assertIn("<= 999u", src)

    def test_lifetime_no_20min_window(self) -> None:
        self.assertIn("--lifetime", self.wf)
        self.assertIn("window_sec=0", self.wf)
        self.assertIn("lifetime=boot", self.wf)
        self.assertIn('"lifetime": True', self.wf)
        self.assertIn("edition=lifetime-boot", self.wf)
        self.assertIn("c2m-debug-edition.txt", self.wf)
        self.assertIn("-M", self.wf)
        self.assertIn("600", self.wf)
        self.assertIn("192.168.1.1:2222", self.wf)
        # Production must not promise a 20-minute listener window.
        prod = self.wf.split("Owner-authorized AP-only lifetime", 1)[1].split("###", 1)[0]
        self.assertIn("NO 20-minute", prod)

    def test_exact_d4_runtime_gate(self) -> None:
        self.assertIn("test_ram_d4_stock_qemu.py", self.wf)
        self.assertIn("--binary work/d4-services/c2m-signs", self.wf)
        self.assertIn("--sysroot work/sysroot", self.wf)
        self.assertIn("--report work/d5_gps_runtime.json", self.wf)
        self.assertIn("sudo timeout 60", self.wf)
        # Ordered after the D4 build and before the debug build.
        self.assertLess(self.wf.index("Mandatory D4 producer"),
                        self.wf.index("corrected fraction gate"))
        self.assertLess(self.wf.index("corrected fraction gate"),
                        self.wf.index("Mandatory lifetime debug"))

    def test_health_on_demand_17_no_boot(self) -> None:
        self.assertIn("--d5-health", self.wf)
        self.assertIn("16+1=17", self.wf)
        self.assertIn("health.sh", self.wf)
        self.assertIn("cmp -s fw/d5/health.sh work/tree/c2m/health.sh", self.wf)
        self.assertIn("tools/fw/test_d5_health.py", self.wf)
        self.assertIn('"--help/--snapshot only"', self.wf.replace("--help/--snapshot only", '"--help/--snapshot only"'))
        self.assertIn("never\n", self.wf.lower())
        # 17-file allowlist contains health.sh exactly once as added file.
        self.assertIn('"health.sh"', self.wf)
        # No boot launch of health.sh.
        p2 = self.wf.split("P2 mutate", 1)[1].split("P3 assemble", 1)[0]
        self.assertNotIn("/customer/c2m/health.sh", p2)
        self.assertIn('"health.sh" not in hook', p2)

    def test_no_m4_no_tsr_forcing(self) -> None:
        # M4 tokens may appear ONLY in explicit negation/ban-check lines.
        for line in self.wf.splitlines():
            if "m4_authorize" in line:
                self.assertTrue(
                    any(k in line for k in ("No M4", "test ! -e", "test ! -f",
                                            "banned service", '"m4_authorize"')),
                    f"m4_authorize outside negation: {line.strip()[:160]}")
            if "m4_adb" in line or "m4_sniff" in line:
                self.assertTrue(
                    any(k in line for k in ("No M4", "banned service", "for banned in")),
                    f"M4 service outside negation: {line.strip()[:160]}")
        self.assertNotIn("--m4", self.wf)
        self.assertIn("--tsr-experiment", self.wf)
        # --tsr-patch may be named ONLY in the "never" prohibition comment,
        # never as a mutator argument.
        for line in self.wf.splitlines():
            s = line.strip()
            if "--tsr-patch" in s and "never --tsr-patch" not in s:
                self.fail(f"--tsr-patch used outside prohibition: {s[:160]}")
        low = self.wf.lower().replace("adas/display", "")
        self.assertNotIn("adasenable", low)

    def test_debug_tests_14_and_defaults(self) -> None:
        self.assertIn("tests/test_debug_supervisor.py", self.wf)
        self.assertIn("tests/test_d5_debug_supervisor.py", self.wf)
        self.assertIn("tools/fw/test_d5_workflow.py", self.wf)
        self.assertIn("C2M_REQUIRE_DEBUG_SSH_TEST=1", self.wf)
        self.assertIn("C2M_DEBUG_SSH_TARGET_DIR", self.wf)
        t = (ROOT / "tests/test_d5_debug_supervisor.py").read_text(encoding="utf-8")
        cases = t.count("    def test_")
        self.assertEqual(cases, 14, f"want 14 D5 supervisor cases, got {cases}")

    def test_token_and_rollback(self) -> None:
        self.assertIn("20261016000001", self.wf)
        self.assertIn("DO NOT", self.wf)
        self.assertIn("NOT FLASH-READY", self.wf)
        self.assertIn("frozen EN_D4", self.wf)
        self.assertIn("never an EN rollback", self.wf)

    def test_publish_paths(self) -> None:
        self.assertIn("deliverables/$(date -u +%Y%m%d)-d5-vi-r${GITHUB_RUN_ID}", self.wf)
        self.assertIn("name: candidateD5-vi-evidence", self.wf)

    def test_health_source_safe_and_present(self) -> None:
        h = ROOT / "fw/d5/health.sh"
        self.assertTrue(h.is_file())
        src = h.read_text(encoding="utf-8")
        self.assertTrue(src.startswith("#!/bin/sh\n"))
        self.assertNotIn("\r", src)
        self.assertIn("--snapshot", src)
        self.assertNotIn(" > ", src.replace("printf '%s\\n'", ""))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    raise SystemExit(0 if result.wasSuccessful() else 1)
