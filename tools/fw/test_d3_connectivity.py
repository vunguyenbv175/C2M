#!/usr/bin/env python3
"""Host-only synthetic guards for the D3 passive Bluetooth boot probe.

Never accesses a camera, card, network or the host's live sysfs. Runs the probe
with C2M_PROBE_ROOT pointing at private fixtures. Optional C2M_PROBE_SHELL is a
JSON command array, e.g. '["/bin/busybox", "sh"]'; defaults to available sh.
The exact target BusyBox/QEMU boot integration is a separate parent gate.
"""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "fw" / "d3" / "connectivity_probe.sh"
PRESENT = "HCI_PRESENT_NOT_RADIO_TESTED"
ABSENT = "NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE"
OUTPUT_LIMIT = 16384
FORBIDDEN_COMMANDS = (
    "hciconfig", "hcitool", "bluetoothctl", "btmgmt", "rfkill", "iw", "ip",
    "ifconfig", "hciattach", "rtk_hciattach", "insmod", "modprobe", "rmmod",
    "stty", "dd", "cat", "tee", "touch", "mkdir", "rm", "mv", "cp", "mount",
    "umount", "wget", "curl", "nc", "ping", "sleep", "ps", "dmesg",
)


def shell_command():
    value = os.environ.get("C2M_PROBE_SHELL")
    if value:
        command = json.loads(value)
        if not isinstance(command, list) or not command or not all(
                isinstance(item, str) and item for item in command):
            raise ValueError("C2M_PROBE_SHELL must be a nonempty JSON string array")
        return command
    found = shutil.which("sh")
    if not found and os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/sh.exe"
        if candidate.is_file():
            found = str(candidate)
    if not found:
        raise RuntimeError("A POSIX sh is required for these host-only tests")
    return [found]


def shell_path(path, command):
    """Translate native Windows paths only for the local Git/MSYS shell."""
    if os.name != "nt":
        return str(path)
    converted = subprocess.run(
        command + ["-c", 'cygpath -u -- "$1"', "path-converter", str(path)],
        capture_output=True, text=True, timeout=5, check=True,
    )
    return converted.stdout.strip()


def snapshot(root):
    result = {}
    for path in root.rglob("*"):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            result[relative] = ("directory",)
        else:
            result[relative] = ("special", stat.S_IFMT(path.lstat().st_mode))
    return result


class D3ConnectivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = shell_command()
        cls.script_path = shell_path(SCRIPT, cls.shell)

    def setUp(self):
        # Use the explicitly approved temp location on this Windows workspace.
        temp_parent = None
        if os.name == "nt":
            approved = Path(os.environ["LOCALAPPDATA"]) / "Temp/opencode"
            if approved.is_dir():
                temp_parent = str(approved)
        self.temp = tempfile.TemporaryDirectory(prefix="d3-connectivity-", dir=temp_parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.fixture = self.base / "fixture"
        self.fixture.mkdir()
        self.fixture_path = shell_path(self.fixture, self.shell)

    def put(self, relative, content=""):
        path = self.fixture / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("ascii") if isinstance(content, str) else content)
        return path

    def directory(self, relative):
        path = self.fixture / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def probe(self, *, override=None, path=None):
        env = os.environ.copy()
        env["C2M_PROBE_ROOT"] = self.fixture_path if override is None else override
        if path is not None:
            env["PATH"] = path
        before = snapshot(self.fixture)
        command = self.shell + [self.script_path]
        if path is not None:
            # Git/MSYS may prepend /usr/bin at startup; set PATH inside the
            # shell so missing-tool and execution-trap guards are meaningful.
            command = self.shell + ["-c", 'PATH=$1; export PATH; . "$2"',
                                    "fixture-probe", path, self.script_path]
        result = subprocess.run(
            command, env=env, capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertLess(len(result.stdout.encode("utf-8")), OUTPUT_LIMIT)
        self.assertEqual(before, snapshot(self.fixture), "probe changed fixture filesystem")
        self.assertIn("radio_test=NOT_PERFORMED", result.stdout)
        self.assertIn("state_changes=NONE", result.stdout)
        self.assertEqual(result.stdout.count("verdict="), 1)
        return result.stdout

    def assert_verdict(self, output, expected):
        self.assertIn("verdict=" + expected + "\n", output)

    def test_positive_hci0_down(self):
        self.put("sys/class/bluetooth/hci0/operstate", "down\n")
        output = self.probe()
        self.assertIn("hci=hci0 sysfs_operstate=down", output)
        self.assert_verdict(output, PRESENT)

    def test_rfcomm_and_malformed_hci_names_are_not_hci(self):
        for name in ("rfcomm0", "hci", "hci0junk", "hci1-private", "hci_private"):
            self.directory("sys/class/bluetooth/" + name)
        output = self.probe()
        self.assertIn("bluetooth_class=present", output)
        self.assertIn("hci=none_observed", output)
        self.assert_verdict(output, ABSENT)

    def test_absent_and_missing_optional_files(self):
        output = self.probe()
        self.assertIn("bluetooth_class=not_observed", output)
        self.assertIn("loaded_modules=unavailable", output)
        self.assertIn("device_tree=unavailable", output)
        self.assert_verdict(output, ABSENT)
        self.directory("sys/class/bluetooth/hci12")
        output = self.probe()
        self.assertIn("hci=hci12 sysfs_operstate=not_reported", output)
        self.assert_verdict(output, PRESENT)

    def test_modules_only_are_inconclusive(self):
        self.directory("sys/module/bluetooth")
        self.directory("sys/module/hci_uart")
        self.put("proc/modules", "bluetooth 45056 2 - Live 0xPRIVATE\n"
                 "hci_uart 20480 0 - Live 0xPRIVATE\n"
                 "private_serial_module 42 0 - Live 0xPRIVATE\n")
        self.put("proc/config.gz", b"not decoded\x00PRIVATE")
        output = self.probe()
        self.assertIn("sysfs_module=bluetooth", output)
        self.assertIn("loaded_module=hci_uart", output)
        self.assertIn("kernel_config_gz=present_not_decoded", output)
        self.assertNotIn("PRIVATE", output)
        self.assertNotIn("private_serial_module", output)
        self.assert_verdict(output, ABSENT)

    def test_rfkill_and_dt_only_are_context_not_hardware(self):
        self.put("sys/class/rfkill/rfkill0/type", "bluetooth\n")
        self.put("sys/class/rfkill/rfkill0/soft", "1\n")
        self.put("sys/class/rfkill/rfkill0/hard", "0\n")
        self.put("sys/class/rfkill/rfkill0/name", "PRIVATE controller\n")
        self.put("sys/class/rfkill/rfkill1/type", "wlan\n")
        self.put("sys/firmware/devicetree/base/soc/serial@123/bluetooth@0/compatible",
                 b"vendor,PRIVATE\x00")
        output = self.probe()
        self.assertIn("rfkill=rfkill0 type=bluetooth soft=1 hard=0", output)
        self.assertIn("bluetooth_named_node=observed_context_only", output)
        self.assertNotIn("rfkill1", output)
        self.assertNotIn("serial@123", output)
        self.assertNotIn("PRIVATE", output)
        self.assert_verdict(output, ABSENT)

    def test_no_private_identifiers_or_raw_uart_output(self):
        secret = "AA:BB:CC:DD:EE:FF PRIVATE_SSID PRIVATE_SERIAL GPS_51.2345"
        for relative in ("sys/class/bluetooth/hci0/address", "sys/class/bluetooth/hci0/name",
                         "sys/class/bluetooth/hci0/uevent", "sys/class/bluetooth/hci0/operstate",
                         "sys/class/rfkill/rfkill0/type", "dev/ttyS0", "dev/ttyAMA0",
                         "dev/ttyUSB0", "proc/net/wireless", "proc/cmdline"):
            self.put(relative, secret + "\n")
        output = self.probe()
        self.assertIn("hci=hci0 sysfs_operstate=not_reported", output)
        for token in secret.split():
            self.assertNotIn(token, output)
        self.assertNotIn("tty", output)
        self.assert_verdict(output, PRESENT)

    def test_command_presence_never_executes_tools(self):
        bin_dir = self.base / "trap-bin"
        bin_dir.mkdir()
        marker = self.base / "unsafe-command-executed"
        marker_path = shell_path(marker, self.shell)
        for name in FORBIDDEN_COMMANDS:
            trap = bin_dir / name
            trap.write_bytes(("#!/bin/sh\nprintf 'EXECUTED\\n' >> '" + marker_path + "'\nexit 99\n").encode("ascii"))
            trap.chmod(0o755)
        bin_path = shell_path(bin_dir, self.shell)
        sep = ":"
        if os.name == "nt":
            # Request the shell's already translated PATH, not native Windows PATH.
            current = subprocess.run(self.shell + ["-c", 'printf "%s" "$PATH"'],
                                     capture_output=True, text=True, timeout=5, check=True).stdout
        else:
            current = os.environ.get("PATH", "")
        output = self.probe(path=bin_path + sep + current)
        for tool in ("hciconfig", "hcitool", "bluetoothctl", "btmgmt", "rfkill"):
            self.assertIn("tool=" + tool + " present_not_executed", output)
        self.assertFalse(marker.exists(), "probe executed a forbidden command")
        self.assert_verdict(output, ABSENT)

    def test_output_and_reads_are_bounded(self):
        for number in range(40):
            self.put(f"sys/class/bluetooth/hci{number}/operstate", "down\n")
            self.put(f"sys/class/rfkill/rfkill{number}/type", "bluetooth\n")
            self.put(f"sys/class/rfkill/rfkill{number}/soft", "1\n")
        self.put("proc/modules", "bluetooth 1 0 - Live 0x0\n" * 4000)
        output = self.probe()
        self.assertEqual(output.count("hci=hci"), 16)
        self.assertEqual(output.count("rfkill=rfkill"), 16)
        self.assertEqual(output.count("loaded_module=bluetooth"), 32)
        self.assertIn("hci_inventory=truncated_at_16", output)
        self.assertIn("rfkill_inventory=truncated_at_16", output)
        self.assert_verdict(output, PRESENT)

    def test_bad_roots_skip_without_failure_or_host_fallback(self):
        for root in ("", "/", ".", "relative", self.fixture_path + "/..",
                     self.fixture_path + "/../fixture", self.fixture_path + "//child",
                     self.fixture_path + "/./child", self.fixture_path + "/missing",
                     self.fixture_path + "\ncontrol", self.fixture_path + "\tcontrol"):
            with self.subTest(root=root):
                output = self.probe(override=root)
                self.assertIn("status=SKIPPED_UNSAFE_OR_MISSING_ROOT", output)
                self.assert_verdict(output, ABSENT)

    def test_symlink_override_and_fixture_links_are_rejected(self):
        target = self.base / "outside-fixture"
        (target / "hci0").mkdir(parents=True)
        link = self.fixture / "sys/class/bluetooth"
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest("Symlink creation unavailable on this host: " + str(error))
        output = self.probe()
        self.assert_verdict(output, ABSENT)
        root_link = self.base / "root-link"
        root_link.symlink_to(self.fixture, target_is_directory=True)
        output = self.probe(override=shell_path(root_link, self.shell))
        self.assertIn("status=SKIPPED_UNSAFE_OR_MISSING_ROOT", output)
        self.assert_verdict(output, ABSENT)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO fixture required")
    def test_fifo_is_not_opened(self):
        path = self.fixture / "proc/modules"
        path.parent.mkdir()
        os.mkfifo(path)
        self.directory("sys/class/bluetooth/hci0")
        os.mkfifo(self.fixture / "sys/class/bluetooth/hci0/operstate")
        output = self.probe()
        self.assertIn("loaded_modules=unavailable", output)
        self.assertIn("sysfs_operstate=not_reported", output)
        self.assert_verdict(output, PRESENT)

    def test_missing_read_tools_still_exit_safely(self):
        self.put("sys/class/bluetooth/hci0/operstate", "down\n")
        self.put("proc/modules", "bluetooth 1 0 - Live 0x0\n")
        empty_bin = self.base / "empty-bin"
        empty_bin.mkdir()
        output = self.probe(path=shell_path(empty_bin, self.shell))
        self.assert_verdict(output, PRESENT)
        self.assertIn("sysfs_operstate=not_reported", output)

    def test_lf_posix_syntax_and_no_mutation_or_uart_code(self):
        source = SCRIPT.read_bytes()
        self.assertNotIn(b"\r", source, "deploy script must have LF-only bytes")
        self.assertTrue(source.startswith(b"#!/bin/sh\n"))
        self.assertTrue(source.endswith(b"\n"))
        syntax = subprocess.run(self.shell + ["-n", self.script_path],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        text = source.decode("ascii")
        self.assertNotIn("/dev/", text.replace("/dev/null", ""))
        for unsafe in ("hciattach", "insmod", "modprobe", "hciconfig -",
                       "hcitool -", "eval ", "exec ", "set -e", "tee ", "touch ",
                       "mount ", "sleep ", "while true", ">>"):
            self.assertNotIn(unsafe, text)
        for line in text.splitlines():
            if not line.lstrip().startswith("#"):
                self.assertNotRegex(line, r"(?<![0-9&])>(?!/dev/null|&|gt)")
                self.assertNotRegex(line, r"^\s*(?:bluetoothctl|hciconfig|hcitool|btmgmt|rfkill|iw|ip)\s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
