#!/usr/bin/env python3
"""Host-only guards for the RTL8821CS offline build lab.

No network, no ARM toolchain, no kernel source, no device. Validates the
portable contract: pinned hashes, profile patches, env/CLI wiring, kernel
config parsing, metadata labelling and report assembly. The actual cross
compile runs only in the manual CI workflow.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIFI = ROOT / "tools" / "wifi"
LAB_PY = WIFI / "rtl8821cs_lab.py"
SCRIPT = WIFI / "build_rtl8821cs_lab.sh"
PROFILES = WIFI / "rtl8821cs_profiles"

sys.path.insert(0, str(WIFI))
import rtl8821cs_lab as lab  # noqa: E402

# Independently recorded pins (parent-confirmed, from the upstream HTTPS
# checksum file and the public driver archive). These must not drift.
KERNEL_SHA = "38c485b411a14e825f8a66a5c2e64f1480397325a5f692b4929f68d228070c5f"
DRIVER_ARCHIVE_SHA = "f7f6cdf34260f55bbca7ad0e3ce5959f4f8ee41dead30d1ee52ae1255c85347e"
RTW_VERSION_SHA = "aae92ac00973d72e56b7b03023c2aa1184e1e0a53b914e0995be00ca6dc39e53"

SCRIPT_TOKENS = (
    "set -uo pipefail",
    "arm-linux-gnueabi-",
    "multi_v7_defconfig",
    "olddefconfig",
    "modules_prepare",
    "scripts/config",
    "MODVERSIONS",
    "THUMB2_KERNEL",
    "ARM_PATCH_PHYS_VIRT",
    "DEBUG_KERNEL",
    "DEBUG_SPINLOCK",
    "DEBUG_MUTEXES",
    "DEBUG_LOCK_ALLOC",
    "PROVE_LOCKING",
    "CC_STACKPROTECTOR_REGULAR",
    "CC_STACKPROTECTOR_STRONG",
    "IPV6",
    "KCFLAGS",
    "HOSTCFLAGS",
    "-fcommon",
    "config-sticky",
    "layout-probe.json",
    "layout-probe.log",
    "probe.o",
    'M="$PROBEDIR"',
    "NO LOAD, EVER",
    "NOT the camera",
    "report.json",
    "metadata.json",
    "build-baseline.log",
    "build-concurrent.log",
    "kernel-prepare.log",
    "toolchain.txt",
    "--exit-code",
    "sha256_mismatch",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class PinTests(unittest.TestCase):
    def test_pinned_hashes(self):
        self.assertEqual(lab.PINS["kernel"]["sha256"], KERNEL_SHA)
        self.assertEqual(lab.PINS["driver"]["archive_sha256"], DRIVER_ARCHIVE_SHA)
        self.assertEqual(lab.PINS["driver"]["files"]["include/rtw_version.h"], RTW_VERSION_SHA)
        self.assertEqual(lab.PINS["driver"]["version_string"], "v5.14.2-28-g6011b0372.20220328")

    def test_hash_format(self):
        for value in (KERNEL_SHA, DRIVER_ARCHIVE_SHA, RTW_VERSION_SHA):
            self.assertRegex(value, r"^[0-9a-f]{64}$")
        for value in lab.PINS["driver"]["files"].values():
            self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_no_camera_abi_claim(self):
        claim = lab.PINS["claim"]
        self.assertEqual(claim["camera_abi_claim"], "NOT_CAMERA_ABI")
        self.assertFalse(claim["load_authorized"])
        self.assertEqual(claim["load_policy"], "NO_LOAD_EVER_FROM_THIS_LAB")
        self.assertFalse(claim["camera_config_reproduced"])


class ScriptTests(unittest.TestCase):
    def test_script_present_lf(self):
        self.assertTrue(SCRIPT.is_file(), f"missing {SCRIPT}")
        raw = SCRIPT.read_bytes()
        self.assertNotIn(b"\r", raw, "script must be LF-only")

    def test_run_step_preserves_failure_status(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash unavailable")
        script = SCRIPT.read_text(encoding="utf-8")
        start = script.index("run_step() {")
        end = script.index("\n}\n", start) + 3
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "step.log").replace("\\", "/")
            snippet = 'record_step() { :; }; remaining() { echo 30; };\n' + script[start:end] + '\nrun_step deliberate_failure "' + log + '" 5 false\n'
            result = subprocess.run([bash, "-c", snippet], capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)

    def test_required_tokens(self):
        raw = _read(SCRIPT)
        for token in SCRIPT_TOKENS:
            self.assertIn(token, raw, f"missing script token: {token}")

    def test_no_firmware_or_load(self):
        raw = _read(SCRIPT)
        for forbidden in ("insmod", "modprobe", "rmmod", "dd if=", "dd of=", "flash", "fw_setenv"):
            self.assertNotIn(forbidden, raw, f"forbidden token in lab script: {forbidden}")

    def test_layout_probe_is_compile_only(self):
        raw = _read(SCRIPT)
        # The probe requests a single object from external kbuild; it must never
        # ask for a .ko module (which would run modpost/licence checks).
        self.assertIn("probe.o", raw)
        self.assertNotIn("probe.ko", raw)
        self.assertIn('M="$PROBEDIR"', raw)
        self.assertIn("layout-probe.json", raw)
        self.assertIn("layout-probe.log", raw)
        # Nothing is uploaded: the object must stay under ephemeral WORK.
        self.assertIn("PROBEDIR=$WORK/layout-probe", raw)

    def test_bash_syntax_when_available(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not available on this host")
        proc = subprocess.run([bash, "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class ProfileTests(unittest.TestCase):
    def test_patches_present(self):
        for profile in lab.PINS["profiles"]:
            patch = PROFILES / profile / "Makefile.patch"
            self.assertTrue(patch.is_file(), f"missing {patch}")
            self.assertNotIn(b"\r", patch.read_bytes(), "patch must be LF-only")

    def test_baseline_single_vif(self):
        raw = _read(PROFILES / "baseline" / "Makefile.patch")
        self.assertIn("CONFIG_PLATFORM_ARM_RK3188 = n", raw)
        self.assertIn("CONFIG_PLATFORM_C2M = y", raw)
        self.assertIn("-DCONFIG_IOCTL_CFG80211", raw)
        # The baseline patch must not add the concurrency flag (a comment may
        # still refer to it).
        self.assertNotIn("EXTRA_CFLAGS += -DCONFIG_CONCURRENT_MODE", raw)

    def test_concurrent_two_vif(self):
        raw = _read(PROFILES / "concurrent" / "Makefile.patch")
        self.assertIn("CONFIG_PLATFORM_C2M = y", raw)
        self.assertIn("EXTRA_CFLAGS += -DCONFIG_CONCURRENT_MODE", raw)


class CliTests(unittest.TestCase):
    def test_env_output(self):
        proc = subprocess.run([sys.executable, str(LAB_PY), "env"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        env = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
        self.assertEqual(env["C2M_KERNEL_SHA256"], KERNEL_SHA)
        self.assertEqual(env["C2M_DRIVER_ARCHIVE_SHA256"], DRIVER_ARCHIVE_SHA)
        self.assertEqual(env["C2M_DRIVER_DIR"], lab.PINS["driver"]["extracted_dir"])
        self.assertEqual(env["C2M_KERNEL_DIR"], lab.PINS["kernel"]["extracted_dir"])

    def test_verify_file_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "artifact.bin"
            target.write_bytes(b"c2m-rtl8821cs-lab")
            good = lab.sha256_file(target)
            ok = subprocess.run([sys.executable, str(LAB_PY), "verify-file", str(target), good], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertTrue(json.loads(ok.stdout)["match"])
            bad = subprocess.run([sys.executable, str(LAB_PY), "verify-file", str(target), "0" * 64], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertFalse(json.loads(bad.stdout)["match"])


class ConfigStateTests(unittest.TestCase):
    REQUIRED = {
        "CONFIG_MODULES": "y",
        "CONFIG_SMP": "y",
        "CONFIG_PREEMPT": "y",
        "CONFIG_MODULE_UNLOAD": "y",
        "CONFIG_THUMB2_KERNEL": "y",
        "CONFIG_ARM_PATCH_PHYS_VIRT": "y",
        "CONFIG_LOCALVERSION": "",
    }

    def _write(self, tmp, extra_lines=()):
        lines = []
        for key, value in self.REQUIRED.items():
            if value == "":
                lines.append(f'{key}=""')
            else:
                lines.append(f"{key}={value}")
        lines.extend(
            [
                "CONFIG_AEABI=y",
                "CONFIG_CPU_V7=y",
                "CONFIG_CFG80211=m",
                "CONFIG_MMC=m",
                "CONFIG_WIRELESS_EXT=y",
                "CONFIG_CFG80211_WEXT=y",
                "# CONFIG_MODVERSIONS is not set",
                "# CONFIG_GCC_PLUGINS is not set",
                "CONFIG_DEBUG_KERNEL=y",
                "CONFIG_DEBUG_SPINLOCK=y",
                "CONFIG_DEBUG_MUTEXES=y",
                "# CONFIG_DEBUG_LOCK_ALLOC is not set",
                "# CONFIG_PROVE_LOCKING is not set",
                "CONFIG_CC_STACKPROTECTOR=y",
                "CONFIG_CC_STACKPROTECTOR_REGULAR=y",
                "# CONFIG_CC_STACKPROTECTOR_STRONG is not set",
                "# CONFIG_CC_STACKPROTECTOR_NONE is not set",
                "# CONFIG_IPV6 is not set",
            ]
        )
        lines.extend(extra_lines)
        path = Path(tmp) / ".config"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_all_required_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = lab.config_state(self._write(tmp))
        self.assertTrue(state["vermagic_required_ok"], state["vermagic_required_missing"])
        self.assertTrue(state["expected_ok"], state["expected_mismatch"])
        self.assertTrue(state["sticky_ok"], state["sticky_mismatch"])
        self.assertEqual(state["observed"]["CONFIG_THUMB2_KERNEL"], "y")

    def test_missing_required_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp)
            text = path.read_text(encoding="utf-8").replace("CONFIG_PREEMPT=y\n", "")
            path.write_text(text, encoding="utf-8")
            state = lab.config_state(path)
        self.assertFalse(state["vermagic_required_ok"])
        self.assertTrue(any("CONFIG_PREEMPT" in item for item in state["vermagic_required_missing"]))
        self.assertEqual(state["observed"]["CONFIG_PREEMPT"], "n")

    def test_sticky_choice_reverted_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp)
            text = path.read_text(encoding="utf-8").replace("CONFIG_DEBUG_MUTEXES=y\n", "")
            path.write_text(text, encoding="utf-8")
            state = lab.config_state(path)
        self.assertFalse(state["sticky_ok"])
        self.assertTrue(any("CONFIG_DEBUG_MUTEXES" in item for item in state["sticky_mismatch"]))
        self.assertTrue(state["vermagic_required_ok"])


class ReportTests(unittest.TestCase):
    def test_report_assembled_from_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "steps.tsv").write_text(
                "kernel-download\tok\tsha256_verified\nbuild-baseline\tok\tok\n",
                encoding="utf-8",
            )
            (out / "toolchain.txt").write_text("arm-linux-gnueabi-gcc 13\n", encoding="utf-8")
            (out / "kernel-config.json").write_text(
                json.dumps({"vermagic_required_ok": True, "expected_mismatch": [], "sticky_ok": True, "sticky_mismatch": []}),
                encoding="utf-8",
            )
            (out / "baseline.metadata.json").write_text(
                json.dumps({"profile": "baseline", "camera_abi_claim": "NOT_CAMERA_ABI"}),
                encoding="utf-8",
            )
            (out / "layout-probe.json").write_text(
                json.dumps({"probe_iteration": 2, "object": {"status": "parsed", "struct_sizes": {"mutex": 40}}}),
                encoding="utf-8",
            )
            report = lab.build_report(out, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["failed_steps"], [])
        self.assertEqual(report["profiles"]["baseline"]["status"], "built")
        self.assertEqual(report["profiles"]["concurrent"]["status"], "absent")
        self.assertEqual(report["identity"]["camera_abi_claim"], "NOT_CAMERA_ABI")
        self.assertFalse(report["identity"]["load_authorized"])
        self.assertEqual(report["iteration"], 2)
        self.assertEqual(report["hypothesis"]["label"], lab.HYPOTHESIS["label"])
        self.assertFalse(report["hypothesis"]["abi_success_claim"])
        self.assertTrue(report["hypothesis"]["config_choices_ok"])
        self.assertEqual(report["hypothesis"]["camera_debug_lock_alloc_state"], "inferred_not_proven")
        self.assertEqual(report["layout_probe"]["object"]["struct_sizes"]["mutex"], 40)

    def test_report_marks_unstuck_config_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "steps.tsv").write_text("kernel-config-sticky\twarn\tchoices_changed_by_olddefconfig\n", encoding="utf-8")
            (out / "kernel-config.json").write_text(
                json.dumps({"vermagic_required_ok": True, "expected_mismatch": [], "sticky_ok": False, "sticky_mismatch": ["CONFIG_DEBUG_MUTEXES (forced 'y', saw 'n')"]}),
                encoding="utf-8",
            )
            report = lab.build_report(out, 0)
        self.assertFalse(report["hypothesis"]["config_choices_ok"])
        self.assertTrue(any("did not stick" in w for w in report["warnings"]))
        # A warning step is not a hard failure.
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["failed_steps"], [])

    def test_report_failure_is_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "steps.tsv").write_text("build-concurrent\tfail\texit=2\n", encoding="utf-8")
            report = lab.build_report(out, 1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed_steps"], ["build-concurrent"])


class LayoutProbeTests(unittest.TestCase):
    @staticmethod
    def _probe_elf(symbols):
        """Build a minimal ELF32 little-endian ET_REL object.

        ``symbols`` is an iterable of ``(name, shndx, size)``; ``shndx == 0``
        marks an undefined symbol.
        """
        import struct as _struct

        shstr = b"\0.data\0.shstrtab\0.strtab\0.symtab\0"

        def sh_name(name):
            return shstr.index(name.encode("ascii"))

        strtab = bytearray(b"\0")
        name_offsets = {}
        for name, _shndx, _size in symbols:
            name_offsets[name] = len(strtab)
            strtab += name.encode("ascii") + b"\0"
        symtab = bytearray(16)  # leading null symbol
        for name, shndx, size in symbols:
            info = 0x00 if shndx == 0 else 0x10  # GLOBAL | OBJECT
            symtab += _struct.pack("<IIIBBH", name_offsets[name], 0, size, info, 0, shndx)
        shoff = 52
        shstr_off = shoff + 5 * 40
        strtab_off = shstr_off + len(shstr)
        symtab_off = strtab_off + len(strtab)
        ehdr = _struct.pack(
            "<16sHHIIIIIHHHHHH",
            b"\x7fELF\x01\x01\x01" + b"\0" * 9,
            1, 40, 1, 0, 0, shoff, 0, 52, 0, 0, 40, 5, 2,
        )
        shdrs = _struct.pack("<IIIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        shdrs += _struct.pack("<IIIIIIIIII", sh_name(".data"), 1, 0, 0, 0, 0, 0, 0, 1, 0)
        shdrs += _struct.pack("<IIIIIIIIII", sh_name(".shstrtab"), 3, 0, 0, shstr_off, len(shstr), 0, 0, 1, 0)
        shdrs += _struct.pack("<IIIIIIIIII", sh_name(".strtab"), 3, 0, 0, strtab_off, len(strtab), 0, 0, 1, 0)
        shdrs += _struct.pack("<IIIIIIIIII", sh_name(".symtab"), 2, 0, 0, symtab_off, len(symtab), 3, 1, 4, 16)
        return bytes(ehdr) + shdrs + shstr + bytes(strtab) + bytes(symtab)

    def test_extract_sizes_offsets_and_undefined(self):
        blob = self._probe_elf(
            [
                ("c2m_probe_sizeof_spinlock", 1, 16),
                ("c2m_probe_sizeof_raw_spinlock", 1, 16),
                ("c2m_probe_sizeof_mutex", 1, 40),
                ("c2m_probe_offsetof_mutex_owner", 1, 24),
                ("c2m_probe_offsetof_mutex_magic", 1, 32),
                ("c2m_probe_memset_var", 1, 20),
                ("memset", 0, 0),
                ("__memzero", 0, 0),
            ]
        )
        result = lab.layout_probe_bytes(blob, "probe.o")
        self.assertEqual(result["struct_sizes"], {"mutex": 40, "raw_spinlock": 16, "spinlock": 16})
        self.assertEqual(result["struct_offsets"], {"mutex_magic": 32, "mutex_owner": 24})
        self.assertEqual(result["undefined_symbols"], ["__memzero", "memset"])
        self.assertEqual(result["undefined_symbol_count"], 2)
        self.assertEqual(result["elf"]["machine"], "ARM")
        self.assertEqual(result["elf"]["type"], "ET_REL")
        self.assertEqual(result["load_safety"], "NOT_ESTABLISHED")

    def test_parse_rejects_non_elf(self):
        with self.assertRaises(ValueError):
            lab.parse_elf32(b"not an elf file")

    def test_layout_probe_reports_missing_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = lab.layout_probe(Path(tmp) / "probe.o")
        self.assertEqual(result["object"]["status"], "missing")
        self.assertEqual(result["probe_iteration"], 2)


class MemzeroScanTests(unittest.TestCase):
    @staticmethod
    def _ksrc(tmp, armksyms="EXPORT_SYMBOL(__memzero);\n", memzero="ENTRY(__memzero)\n"):
        root = Path(tmp)
        (root / "arch" / "arm" / "kernel").mkdir(parents=True, exist_ok=True)
        (root / "arch" / "arm" / "lib").mkdir(parents=True, exist_ok=True)
        if armksyms is not None:
            (root / "arch" / "arm" / "kernel" / "armksyms.c").write_text(armksyms, encoding="utf-8")
        if memzero is not None:
            (root / "arch" / "arm" / "lib" / "memzero.S").write_text(memzero, encoding="utf-8")
        return root

    def test_export_detected_in_armksyms(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan = lab.memzero_export(self._ksrc(tmp))
        self.assertEqual(scan["memzero_export_verdict"], "exported")
        entry = scan["files"]["arch/arm/kernel/armksyms.c"]
        self.assertTrue(entry["exports_memzero"])
        self.assertIn("EXPORT_SYMBOL(__memzero)", entry["export_symbol_lines"][0])
        self.assertRegex(scan["arch_string_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(set(scan["files"]), {"arch/arm/kernel/armksyms.c", "arch/arm/lib/memzero.S"})

    def test_absence_in_both_scanned_files_is_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan = lab.memzero_export(self._ksrc(tmp, armksyms="/* nothing here */\n"))
        self.assertEqual(scan["memzero_export_verdict"], "not_exported_in_scanned_files")
        self.assertFalse(scan["files"]["arch/arm/kernel/armksyms.c"]["exports_memzero"])

    def test_partial_scan_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan = lab.memzero_export(self._ksrc(tmp, armksyms=None))
        self.assertEqual(scan["memzero_export_verdict"], "unknown_partial_scan")


class ModuleMetadataTests(unittest.TestCase):
    def test_labels_without_pyelftools(self):
        import module_abi_report

        original = module_abi_report.report
        with tempfile.TemporaryDirectory() as tmp:
            ko = Path(tmp) / "8821cs.ko"
            ko.write_bytes(b"\x7fELF")
            module_abi_report.report = lambda blob: {  # noqa: ARG005
                "sha256": lab.sha256_file(ko),
                "bytes": 4,
                "modinfo": {"vermagic": ["4.9.227 SMP preempt mod_unload ARMv7 thumb2 p2v8"]},
                "undefined_symbols": ["kmalloc", "cfg80211_connect_result"],
                "undefined_symbol_count": 2,
                "has_symbol_versions": False,
                "load_safety": "NOT_ESTABLISHED",
            }
            try:
                meta = lab.module_metadata(ko, "concurrent")
            finally:
                module_abi_report.report = original
        self.assertEqual(meta["camera_abi_claim"], "NOT_CAMERA_ABI")
        self.assertFalse(meta["load_authorized"])
        self.assertEqual(meta["load_policy"], "NO_LOAD_EVER_FROM_THIS_LAB")
        self.assertEqual(meta["elf"]["undefined_symbols"], ["kmalloc", "cfg80211_connect_result"])
        self.assertEqual(meta["elf"]["undefined_symbol_count"], 2)
        self.assertEqual(meta["elf"]["load_safety"], "NOT_ESTABLISHED")
        self.assertEqual(meta["role"], "reconstructed_upstream_armv7_thumb2_same_channel_two_vif")


if __name__ == "__main__":
    unittest.main(verbosity=2)
