#!/usr/bin/env python3
"""Synthetic, host-only unittest coverage for reversion_sd_package.py.

Run: python -B -m unittest discover -s tools/fw -p test_reversion_sd_package.py -v
No vendor firmware, device, SD card, network, or pytest dependency is used.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import reversion_sd_package as rep

OLD = "20230803193750"
NEW = "20261013123456"
FIRST = 0x400
SECOND = 0x420
CUSTOMER = 0x480
LAST = 0x4C0
CUSTOMER_BYTES = b"customer:\nsysVer " + OLD.encode("ascii") + b"\nretained\x00"
FOOTER = b"12345678\n# File Partitio"


def md5_line(inner: bytes) -> bytes:
    return (hashlib.md5(inner).hexdigest() + "  " + rep.INNER + "\n").encode("ascii")


def with_inner(source: dict[str, bytes], inner: bytes) -> dict[str, bytes]:
    result = dict(source)
    result[rep.INNER] = inner
    result["minieye_firmware.md5"] = md5_line(inner)
    return result


def make_package(*, script_token: str = OLD, extra_line: bytes = b"",
                 trailer_lf: bool = True) -> dict[str, bytes]:
    script = (
        f"\n# File Partition: cis.es\nsysVer {script_token}\n"
        f"fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x4 {FIRST:#x}\n"
        f"fatload mmc 0 0x21800000 $(SdUpgradeImage) 0x6 {SECOND:#x}\n"
        "writecis 0x21000000 0x21800000 0 0 0 5\n"
        "\n# File Partition: set_partition.es\nsaveenv\n"
        "\n# File Partition: customer.es\n"
        f"fatload mmc 0 0x21000000 $(SdUpgradeImage) {len(CUSTOMER_BYTES)} {CUSTOMER}\n"
        "ubi write 0x21000000 customer 0x28\n"
        "\n# File Partition: misc.es\n"
        f"fatload mmc 0 0x21000000 $(SdUpgradeImage) 0x7 {LAST:#x}\n"
        "nand write.e 0x21000000 MISC 0x7\n"
    ).encode("ascii") + extra_line + rep.package_contract.END_MARKER
    if trailer_lf:
        script += b"\n"
    if len(script) >= FIRST:
        raise AssertionError("synthetic script must fit before first payload")
    inner = bytearray(b"\xff" * (LAST + 7))
    inner[:len(script)] = script
    inner[FIRST:FIRST + 4] = b"ABCD"
    inner[SECOND:SECOND + 6] = b"second"
    inner[CUSTOMER:CUSTOMER + len(CUSTOMER_BYTES)] = CUSTOMER_BYTES
    inner[LAST:LAST + 7] = b"PAYLOAD"
    inner.extend(FOOTER)
    return {
        rep.INNER: bytes(inner),
        "sysVer.txt": f"sysVer {OLD}\nend\n".encode("ascii"),
        "minieye_firmware.md5": md5_line(bytes(inner)),
        "adas_upgrade.sh": b"#!/bin/sh\nprintf 'unchanged\\n'\n",
    }


class ReversionPackageTests(unittest.TestCase):
    def test_exact_allowed_edits_and_pure_input(self) -> None:
        source = make_package()
        snapshot = dict(source)
        output, proof = rep.reversion_package(source, OLD, NEW)
        self.assertIsNot(source, output)
        self.assertEqual(source, snapshot)
        self.assertEqual(set(output), set(rep.MEMBERS))
        offset = source[rep.INNER].index(b"sysVer " + OLD.encode()) + len(b"sysVer ")
        self.assertEqual(proof["token_offset"], offset)
        self.assertEqual(output[rep.INNER],
                         source[rep.INNER][:offset] + NEW.encode() + source[rep.INNER][offset + 14:])
        self.assertEqual(output["sysVer.txt"], f"sysVer {NEW}\nend\n".encode())
        self.assertEqual(output["minieye_firmware.md5"], md5_line(output[rep.INNER]))
        self.assertEqual(output["adas_upgrade.sh"], source["adas_upgrade.sh"])
        expected_diff = [offset + index for index, (a, b) in enumerate(zip(OLD, NEW)) if a != b]
        self.assertEqual(proof["changed_inner_byte_offsets"], expected_diff)
        self.assertEqual(proof["token_span"], [offset, offset + 14])
        self.assertEqual(proof["verdict"], "ALLOWLIST-OK")
        self.assertTrue(proof["host_byte_proof_only"])
        self.assertFalse(proof["device_tested"])
        self.assertFalse(proof["flash_proven"])
        self.assertTrue(all(proof["proof"].values()))
        self.assertEqual(proof["new_md5"], hashlib.md5(output[rep.INNER]).hexdigest())
        for name in rep.MEMBERS:
            self.assertEqual(proof["source_sha256"][name], hashlib.sha256(source[name]).hexdigest())
            self.assertEqual(proof["output_sha256"][name], hashlib.sha256(output[name]).hexdigest())

    def test_identical_token_string_in_customer_payload_and_footer_not_replaced(self) -> None:
        source = make_package()
        source = with_inner(source, source[rep.INNER] + b"\nsysVer " + OLD.encode() + b"\n")
        output, proof = rep.reversion_package(source, OLD, NEW)
        self.assertEqual(output[rep.INNER][CUSTOMER:CUSTOMER + len(CUSTOMER_BYTES)], CUSTOMER_BYTES)
        self.assertEqual(output[rep.INNER][LAST + 7:], source[rep.INNER][LAST + 7:])
        self.assertEqual(output[rep.INNER].count(OLD.encode()), 2)
        self.assertEqual(len(proof["loads"]), 4)

    def test_every_load_including_multiple_per_section_and_customer_proved(self) -> None:
        source = make_package()
        output, proof = rep.reversion_package(source, OLD, NEW)
        self.assertEqual([(r["section"], r["load_index"]) for r in proof["loads"]],
                         [("cis.es", 0), ("cis.es", 1), ("customer.es", 0), ("misc.es", 0)])
        self.assertEqual([r["offset"] for r in proof["loads"]], [FIRST, SECOND, CUSTOMER, LAST])
        self.assertEqual([r["size"] for r in proof["loads"]], [4, 6, len(CUSTOMER_BYTES), 7])
        for row in proof["loads"]:
            self.assertTrue(row["unchanged"])
            self.assertEqual(row["source_sha256"], row["output_sha256"])
            self.assertEqual(row["source_sha256"], hashlib.sha256(
                source[rep.INNER][row["offset"]:row["end"]]).hexdigest())
            self.assertEqual(source[rep.INNER][row["offset"]:row["end"]],
                             output[rep.INNER][row["offset"]:row["end"]])
        kinds = [r["kind"] for r in proof["preserved_regions"]]
        self.assertEqual(kinds.count("head_padding"), 1)
        self.assertEqual(kinds.count("inter_payload_gap"), 3)
        self.assertEqual(kinds.count("unknown_footer"), 1)
        self.assertEqual(proof["preserved_regions"][-1]["size"], len(FOOTER))
        self.assertTrue(all(r["unchanged"] for r in proof["preserved_regions"]))

    def test_optional_script_trailing_lf(self) -> None:
        for trailer_lf in (True, False):
            with self.subTest(trailer_lf=trailer_lf):
                source = make_package(trailer_lf=trailer_lf)
                output, proof = rep.reversion_package(source, OLD, NEW)
                self.assertEqual(proof["script_trailer_newline"], trailer_lf)
                self.assertEqual(source[rep.INNER][proof["script_end"]:],
                                 output[rep.INNER][proof["script_end"]:])

    def test_unchanged_token_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must differ"):
            rep.reversion_package(make_package(), OLD, OLD)

    def test_nondecimal_nonascii_wrong_width_tokens_rejected(self) -> None:
        bad_tokens = ["", "2026101312345", "202610131234567", "20261013abcdef",
                      "2026101312345 ", "+2026101312345", "２０２６１０１３１２３４５６",
                      "٢٠٢٦١٠١٣١٢٣٤٥٦", b"20261013123456", None, 20261013123456]
        for token in bad_tokens:
            for old, new in ((OLD, token), (token, NEW)):
                with self.subTest(old=old, new=new):
                    with self.assertRaisesRegex(ValueError, "14 ASCII digits"):
                        rep.reversion_package(make_package(), old, new)

    def test_duplicate_version_lines_rejected(self) -> None:
        for extra in (f"sysVer {OLD}\n", f"sysVer {NEW}\n", f" sysVer {OLD}\n"):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ValueError, "exactly one exact sysVer"):
                    rep.reversion_package(make_package(extra_line=extra.encode()), OLD, NEW)

    def test_inner_source_token_mismatch_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one exact sysVer"):
            rep.reversion_package(make_package(script_token=NEW), OLD, NEW)

    def test_external_source_token_mismatch_rejected(self) -> None:
        source = make_package()
        source["sysVer.txt"] = f"sysVer {NEW}\nend\n".encode()
        with self.assertRaisesRegex(ValueError, "sysVer.txt"):
            rep.reversion_package(source, OLD, NEW)

    def test_md5_mismatch_and_noncanonical_sidecar_rejected(self) -> None:
        source = make_package()
        md5 = hashlib.md5(source[rep.INNER]).hexdigest()
        bad_lines = [b"0" * 32 + b"  " + rep.INNER.encode() + b"\n",
                     f"{md5} {rep.INNER}\n".encode(), f"{md5}  {rep.INNER}\r\n".encode(),
                     f"{md5.upper()}  {rep.INNER}\n".encode(),
                     f"{md5}  wrong.bin\n".encode(), source["minieye_firmware.md5"] + b"\n"]
        for line in bad_lines:
            with self.subTest(line=line):
                bad = dict(source)
                bad["minieye_firmware.md5"] = line
                with self.assertRaisesRegex(ValueError, "minieye_firmware.md5"):
                    rep.reversion_package(bad, OLD, NEW)

    def test_metadata_requires_exact_lf_shape(self) -> None:
        source = make_package()
        for line in (f"sysVer {OLD}\r\nend\r\n", f"sysVer {OLD}\nend", f"sysVer {OLD}\nend\n\n"):
            with self.subTest(line=line):
                bad = dict(source)
                bad["sysVer.txt"] = line.encode()
                with self.assertRaisesRegex(ValueError, "sysVer.txt"):
                    rep.reversion_package(bad, OLD, NEW)

    def test_exact_member_set_and_bytes_required(self) -> None:
        source = make_package()
        bad = dict(source)
        bad["extra"] = b"extra"
        missing = dict(source)
        del missing["adas_upgrade.sh"]
        mutable = dict(source)
        mutable[rep.INNER] = bytearray(source[rep.INNER])
        for package in (bad, missing, mutable, None):
            with self.subTest(package_type=type(package)):
                with self.assertRaises(ValueError):
                    rep.reversion_package(package, OLD, NEW)

    def test_missing_or_nonstandalone_end_marker_rejected(self) -> None:
        source = make_package()
        for replacement in (b"x" * len(rep.package_contract.END_MARKER),
                            b"# " + rep.package_contract.END_MARKER):
            with self.subTest(replacement=replacement):
                inner = source[rep.INNER].replace(rep.package_contract.END_MARKER, replacement, 1)
                with self.assertRaisesRegex(ValueError, "END_MARKER"):
                    rep.reversion_package(with_inner(source, inner), OLD, NEW)

    def test_script_crlf_or_nonascii_rejected(self) -> None:
        source = make_package()
        for inner in (source[rep.INNER].replace(b"saveenv\n", b"saveenv\r\n", 1),
                      source[rep.INNER].replace(b"saveenv", b"saveen\x80", 1)):
            with self.subTest(inner_prefix=inner[:20]):
                with self.assertRaisesRegex(ValueError, "ASCII|CRLF"):
                    rep.reversion_package(with_inner(source, inner), OLD, NEW)

    def test_non_ff_head_padding_rejected(self) -> None:
        source = make_package()
        inner = bytearray(source[rep.INNER])
        inner[FIRST - 1] = 0
        with self.assertRaisesRegex(ValueError, "FF head padding"):
            rep.reversion_package(with_inner(source, bytes(inner)), OLD, NEW)

    def test_invalid_load_bounds_zero_length_and_script_overlap_rejected(self) -> None:
        source = make_package()
        original = b"0x4 0x400\n"
        for replacement in (b"0 0x400\n", b"4 999999\n", b"99999 0x400\n",
                            b"4 0\n", b"4 34\n"):
            with self.subTest(replacement=replacement):
                inner = source[rep.INNER].replace(original, replacement, 1)
                with self.assertRaisesRegex(ValueError, "fatload range"):
                    rep.reversion_package(with_inner(source, inner), OLD, NEW)

    def test_overlapping_load_ranges_rejected(self) -> None:
        source = make_package()
        inner = source[rep.INNER].replace(b"0x6 0x420\n", b"0x6 0x402\n", 1)
        with self.assertRaisesRegex(ValueError, "overlapping"):
            rep.reversion_package(with_inner(source, inner), OLD, NEW)

    def test_unsectioned_load_rejected(self) -> None:
        source = make_package()
        inner = source[rep.INNER].replace(b"# File Partition: cis.es", b"# Unnamed partition cis", 1)
        with self.assertRaisesRegex(ValueError, "every fatload must belong"):
            rep.reversion_package(with_inner(source, inner), OLD, NEW)

    def test_duplicate_section_rejected(self) -> None:
        source = make_package()
        inner = source[rep.INNER].replace(b"# File Partition: misc.es", b"# File Partition: cis.es ", 1)
        with self.assertRaisesRegex(ValueError, "duplicate File Partition"):
            rep.reversion_package(with_inner(source, inner), OLD, NEW)

    def test_unparsed_partial_or_multiline_load_rejected(self) -> None:
        source = make_package()
        for replacement in (b"fatload usb 0", b"fatload mmc\n0", b"fatload mmc 0"):
            inner = source[rep.INNER].replace(b"fatload mmc 0", replacement, 1)
            if replacement == b"fatload mmc 0":
                inner = inner.replace(b"0x4 0x400\n", b"0x4 0x400BADjunk\n", 1)
            with self.subTest(replacement=replacement):
                with self.assertRaisesRegex(ValueError, "fatload|single-line"):
                    rep.reversion_package(with_inner(source, inner), OLD, NEW)

    def test_allowlist_proof_rejects_customer_pad_footer_or_other_script_edits(self) -> None:
        source = make_package()
        output, proof = rep.reversion_package(source, OLD, NEW)
        for offset in (FIRST, SECOND, CUSTOMER, LAST, FIRST - 1, SECOND - 1,
                       len(output[rep.INNER]) - 1, output[rep.INNER].index(b"saveenv")):
            inner = bytearray(output[rep.INNER])
            inner[offset] ^= 1
            tampered = with_inner(output, bytes(inner))
            with self.subTest(offset=offset):
                with self.assertRaises(ValueError):
                    rep.prove_version_only(source, tampered, OLD, NEW)
        self.assertTrue(proof["proof"]["inner_equal_outside_token_span"])

    def test_allowlist_proof_rejects_adas_and_load_command_changes(self) -> None:
        source = make_package()
        output, _ = rep.reversion_package(source, OLD, NEW)
        tampered = dict(output)
        tampered["adas_upgrade.sh"] += b"# extra\n"
        with self.assertRaisesRegex(ValueError, "adas_upgrade.sh changed"):
            rep.prove_version_only(source, tampered, OLD, NEW)
        for old, new in ((b"0x4 0x400", b"0x3 0x400"),
                         (b"0x6 0x420", b"0x6 0x421"),
                         (b"0x21800000", b"0x21900000"),
                         (b"customer 0x28", b"customer 0x29")):
            with self.subTest(old=old):
                tampered = with_inner(output, output[rep.INNER].replace(old, new, 1))
                with self.assertRaisesRegex(ValueError, "outside the 14-byte"):
                    rep.prove_version_only(source, tampered, OLD, NEW)

    def test_allowlist_proof_rejects_image_length_change(self) -> None:
        source = make_package()
        output, _ = rep.reversion_package(source, OLD, NEW)
        with self.assertRaisesRegex(ValueError, "length changed"):
            rep.prove_version_only(source, with_inner(output, output[rep.INNER] + b"\xff"), OLD, NEW)

    def test_complete_source_pin_map_required(self) -> None:
        source = make_package()
        pins = {name: hashlib.sha256(data).hexdigest() for name, data in source.items()}
        self.assertEqual(rep.verify_pins(source, pins), pins)
        self.assertEqual(rep.verify_pins(source, {name: value.upper() for name, value in pins.items()}), pins)
        bad_maps = [{}, dict(pins, extra="0" * 64), dict(pins, **{rep.INNER: "0" * 64}),
                    dict(pins, **{rep.INNER: "a" * 63}), dict(pins, **{rep.INNER: 1}), []]
        for bad in bad_maps:
            with self.subTest(bad_type=type(bad)):
                with self.assertRaises(ValueError):
                    rep.verify_pins(source, bad)


class ReversionCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source_dir = self.root / "source"
        self.out_dir = self.root / "out"
        self.report = self.root / "reports" / "report.json"
        self.pins_path = self.root / "pins.json"
        self.source_dir.mkdir()
        self.source = make_package()
        for name, data in self.source.items():
            (self.source_dir / name).write_bytes(data)
        self.pins = {name: hashlib.sha256(data).hexdigest() for name, data in self.source.items()}
        self.pins_path.write_text(json.dumps(self.pins), encoding="utf-8")

    def run_cli(self, *, out_dir: Path | None = None, report: Path | None = None,
                include_pins: bool = True) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-B", str(Path(__file__).with_name("reversion_sd_package.py")),
                   "--source-dir", str(self.source_dir), "--out-dir", str(out_dir or self.out_dir),
                   "--old-version", OLD, "--new-version", NEW, "--report", str(report or self.report)]
        if include_pins:
            command.extend(["--pins", str(self.pins_path)])
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def test_success_writes_exact_four_files_and_readback_report(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected, proof = rep.reversion_package(self.source, OLD, NEW)
        self.assertEqual({p.name for p in self.out_dir.iterdir()}, set(rep.MEMBERS))
        for name in rep.MEMBERS:
            self.assertEqual((self.out_dir / name).read_bytes(), expected[name])
            self.assertEqual((self.source_dir / name).read_bytes(), self.source[name])
        evidence = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertTrue(evidence["readback_verified"])
        self.assertEqual(evidence["readback_sha256"], proof["output_sha256"])
        self.assertEqual(evidence["verified_source_pins"], self.pins)
        self.assertEqual(evidence["loads"], proof["loads"])
        self.assertFalse(evidence["device_tested"])
        self.assertFalse(evidence["flash_proven"])
        self.assertIn("not device-tested or FLASH-proven", result.stdout)

    def test_existing_empty_output_directory_allowed(self) -> None:
        self.out_dir.mkdir()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_pin_mismatch_writes_nothing(self) -> None:
        self.pins[rep.INNER] = "0" * 64
        self.pins_path.write_text(json.dumps(self.pins), encoding="utf-8")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source SHA-256 pin mismatch", result.stderr)
        self.assertFalse(self.out_dir.exists())
        self.assertFalse(self.report.parent.exists())

    def test_pin_checks_cover_each_of_four_members(self) -> None:
        for name in rep.MEMBERS:
            with self.subTest(name=name):
                bad = dict(self.pins)
                bad[name] = "0" * 64
                self.pins_path.write_text(json.dumps(bad), encoding="utf-8")
                result = self.run_cli()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name, result.stderr)
                self.assertFalse(self.out_dir.exists())
                self.assertFalse(self.report.exists())

    def test_pins_required_and_exact_mapping(self) -> None:
        result = self.run_cli(include_pins=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--pins", result.stderr)
        self.assertFalse(self.out_dir.exists())
        self.pins_path.write_text(json.dumps({rep.INNER: self.pins[rep.INNER]}), encoding="utf-8")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly the four", result.stderr)
        self.assertFalse(self.out_dir.exists())

    def test_duplicate_pin_json_keys_rejected(self) -> None:
        original = json.dumps(self.pins)
        duplicate = original[:-1] + ', "sysVer.txt": "' + self.pins["sysVer.txt"] + '"}'
        self.pins_path.write_text(duplicate, encoding="utf-8")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate JSON pin key", result.stderr)
        self.assertFalse(self.out_dir.exists())

    def test_nonempty_output_no_overwrite(self) -> None:
        self.out_dir.mkdir()
        sentinel = self.out_dir / rep.INNER
        sentinel.write_bytes(b"sentinel")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing overwrite", result.stderr)
        self.assertEqual(sentinel.read_bytes(), b"sentinel")
        self.assertEqual(list(self.out_dir.iterdir()), [sentinel])
        self.assertFalse(self.report.exists())

    def test_existing_report_no_overwrite_or_payload_writes(self) -> None:
        self.report.parent.mkdir()
        self.report.write_bytes(b"existing report")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("report already exists", result.stderr)
        self.assertEqual(self.report.read_bytes(), b"existing report")
        self.assertFalse(self.out_dir.exists())

    def test_source_output_alias_or_overlap_rejected(self) -> None:
        for out_dir in (self.source_dir, self.source_dir / "nested", self.root):
            with self.subTest(out_dir=out_dir):
                result = self.run_cli(out_dir=out_dir)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("alias or overlap", result.stderr)
                self.assertFalse(self.report.exists())
        for name in rep.MEMBERS:
            self.assertEqual((self.source_dir / name).read_bytes(), self.source[name])

    def test_report_inside_either_package_rejected(self) -> None:
        for report in (self.source_dir / "report.json", self.out_dir / "report.json"):
            with self.subTest(report=report):
                result = self.run_cli(report=report)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("outside both package", result.stderr)
                self.assertFalse(self.out_dir.exists())

    def test_extra_source_member_rejected(self) -> None:
        (self.source_dir / "unexpected.txt").write_bytes(b"extra")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly the four SD files", result.stderr)
        self.assertFalse(self.out_dir.exists())

    def test_invalid_but_pinned_package_writes_nothing(self) -> None:
        self.source["sysVer.txt"] = f"sysVer {NEW}\nend\n".encode()
        (self.source_dir / "sysVer.txt").write_bytes(self.source["sysVer.txt"])
        self.pins["sysVer.txt"] = hashlib.sha256(self.source["sysVer.txt"]).hexdigest()
        self.pins_path.write_text(json.dumps(self.pins), encoding="utf-8")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sysVer.txt", result.stderr)
        self.assertFalse(self.out_dir.exists())
        self.assertFalse(self.report.parent.exists())


if __name__ == "__main__":
    unittest.main()
