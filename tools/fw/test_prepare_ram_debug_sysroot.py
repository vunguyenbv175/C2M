#!/usr/bin/env python3
"""Synthetic pin/path tests; no private firmware or camera access."""
from __future__ import annotations

import gzip
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import prepare_ram_debug_sysroot as tool


def archive(entries):
    out = bytearray()
    for index, (name, mode, blob) in enumerate(entries + [("TRAILER!!!", 0, b"")]):
        encoded = name.encode() + b"\0"
        fields = [index + 1, mode, 0, 0, 1, 0, len(blob), 0, 0, 0, 0, len(encoded), 0]
        out += b"070701" + b"".join(f"{x:08x}".encode() for x in fields) + encoded
        out += bytes((-len(out)) % 4)
        out += blob
        out += bytes((-len(out)) % 4)
    return gzip.compress(out)


class SysrootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="c2m-sysroot-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inner = self.root / "root.gz"
        self.out = self.root / "sysroot"

    def test_pin_failure_happens_before_writes(self):
        entries = [("lib/" + name, stat.S_IFREG | 0o755, b"fake-runtime") for name in tool.PINS]
        self.inner.write_bytes(archive(entries))
        with self.assertRaisesRegex(ValueError, "pin mismatch"):
            tool.extract(self.inner, self.out)
        self.assertFalse(self.out.exists())

    def test_unsafe_archive_paths_rejected_before_write(self):
        for name in ("../outside", "/absolute", "lib/../outside"):
            with self.subTest(name=name):
                self.inner.write_bytes(archive([(name, stat.S_IFREG | 0o600, b"x")]))
                with self.assertRaisesRegex(ValueError, "unsafe archive"):
                    tool.extract(self.inner, self.out)
                self.assertFalse(self.out.exists())

    def test_existing_output_refused(self):
        self.out.mkdir()
        self.inner.write_bytes(archive([]))
        with self.assertRaisesRegex(ValueError, "must not exist"):
            tool.extract(self.inner, self.out)

    def test_only_exact_pinned_runtime_members(self):
        import hashlib
        pins = {name: hashlib.sha256(name.encode()).hexdigest() for name in tool.PINS}
        entries = [("lib/" + name, stat.S_IFREG | 0o755, name.encode()) for name in pins]
        entries += [("lib/" + name, stat.S_IFLNK | 0o777, target.encode()) for name, target in tool.LINKS.items()]
        entries += [("lib/vendor-license", stat.S_IFREG | 0o600, b"do-not-extract"),
                    ("lib/cardv", stat.S_IFREG | 0o755, b"not-needed")]
        self.inner.write_bytes(archive(entries))
        if not hasattr(__import__('os'), 'symlink'):
            self.skipTest("symlinks unavailable")
        with patch.object(tool, "PINS", pins):
            try:
                report = tool.extract(self.inner, self.out)
            except OSError as error:
                if getattr(error, "winerror", None) == 1314:
                    self.skipTest("Windows symlink privilege unavailable")
                raise
        self.assertEqual(report["entries"], 7)
        self.assertEqual({p.name for p in (self.out / "lib").iterdir()}, tool.ALLOW)
        self.assertFalse((self.out / "lib/cardv").exists())

    def test_wrong_symlink_refused_before_write(self):
        import hashlib
        pins = {name: hashlib.sha256(name.encode()).hexdigest() for name in tool.PINS}
        entries = [("lib/" + name, stat.S_IFREG | 0o755, name.encode()) for name in pins]
        entries += [("lib/" + name, stat.S_IFLNK | 0o777,
                     ("../escape" if name == "libc.so.6" else target).encode())
                    for name, target in tool.LINKS.items()]
        self.inner.write_bytes(archive(entries))
        with patch.object(tool, "PINS", pins):
            with self.assertRaisesRegex(ValueError, "symlink pin mismatch"):
                tool.extract(self.inner, self.out)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
