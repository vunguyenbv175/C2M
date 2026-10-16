#!/usr/bin/env python3
"""Synthetic ownership tests for tools/fw/apply_tree_ownership.py.

Offline, portable (Windows-safe via mocked os.chown), no firmware/private
data. Verifies per-manifest uid/gid preservation (VI 1000/1001 mixture),
exact VI root inode 1 (1000:1000 0755) recorded by ubifs_manifest,
legacy-added 1001 fallback, replaced-absent sibling/parent inference, and
fail-closed preflight (zero chowns on any violation, no chmod).
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "fw" / "apply_tree_ownership.py"
MANIFEST_PATH = ROOT / "tools" / "fw" / "ubifs_manifest.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("apply_tree_ownership", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_manifest_tool():
    spec = importlib.util.spec_from_file_location("ubifs_manifest", MANIFEST_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = load_tool()
UMAN = load_manifest_tool()


def tmp_root(testcase):
    td = tempfile.TemporaryDirectory()
    testcase.addCleanup(td.cleanup)
    return Path(td.name)


def write_manifest(path: Path, doc: dict) -> Path:
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def stock_doc(entries):
    return {"entries": entries}


def reg(path, uid, gid, mode=0o644):
    return {"path": path, "type": "reg", "mode": mode,
            "mode_oct": oct(mode), "uid": uid, "gid": gid,
            "size": 1, "sha256": "x", "mtime": 0}


def directory(path, uid, gid, mode=0o755):
    return {"path": path, "type": "dir", "mode": mode,
            "mode_oct": oct(mode), "uid": uid, "gid": gid, "mtime": 0}


def symlink_row(path, uid, gid, mode=0o777):
    return {"path": path, "type": "symlink", "mode": mode,
            "mode_oct": oct(mode), "uid": uid, "gid": gid,
            "target": "target", "mtime": 0}


class OwnershipTest(unittest.TestCase):
    def run_tool(self, tree, stock_entries, mut_doc=None):
        stock_p = write_manifest(tree.parent / "stock.json", stock_doc(stock_entries))
        args = ["--tree", str(tree), "--stock-manifest", str(stock_p)]
        if mut_doc is not None:
            mut_p = tree.parent / "mut.json"
            write_manifest(mut_p, mut_doc)
            args += ["--mut-manifest", str(mut_p)]
        calls: dict[str, tuple] = {}

        def fake_chown(path, uid, gid, *, follow_symlinks=True):
            # Record; do not touch the filesystem.
            calls[str(Path(path))] = (uid, gid, follow_symlinks)
            if follow_symlinks is not False:
                raise AssertionError("must use follow_symlinks=False")

        with mock.patch.object(os, "chown", create=True, new=fake_chown):
            # Fail if the tool ever tries to chmod (mode preserved).
            with mock.patch.object(os, "chmod", create=True,
                                   side_effect=AssertionError("chmod forbidden")):
                rc = MOD.main(args)
        return rc, calls

    def mkfile(self, tree: Path, rel: str, mode=0o644) -> Path:
        p = tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"data-" + rel.encode())
        try:
            os.chmod(p, mode)
        except OSError:
            pass
        return p

    def mkdir(self, tree: Path, rel: str, mode=0o755) -> Path:
        p = tree / rel if rel else tree
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(p, mode)
        except OSError:
            pass
        return p

    def test_stock_mixture_preserved_not_uniform(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkdir(tree, "a")
        self.mkfile(tree, "a/f1")
        self.mkdir(tree, "b")
        self.mkfile(tree, "b/f2")
        entries = [directory("/a", 1000, 1000),
                   reg("/a/f1", 1000, 1000),
                   directory("/b", 1001, 1001),
                   reg("/b/f2", 1001, 1001)]
        rc, calls = self.run_tool(tree, entries)
        self.assertEqual(rc, 0)
        # Root fallback 1001 (no "/" record) + 4 stock entries.
        self.assertEqual(len(calls), 5)
        self.assertEqual(calls[str(tree)], (1001, 1001, False))
        self.assertEqual(calls[str(tree / "a" / "f1")], (1000, 1000, False))
        self.assertEqual(calls[str(tree / "b" / "f2")], (1001, 1001, False))
        self.assertEqual(calls[str(tree / "a")], (1000, 1000, False))
        self.assertEqual(calls[str(tree / "b")], (1001, 1001, False))

    def test_root_fallback_1001_when_no_slash(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        rc, calls = self.run_tool(tree, [])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, {str(tree): (1001, 1001, False)})

    def test_root_from_manifest_when_present(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkdir(tree, "a")
        entries = [directory("/", 0, 0), directory("/a", 1000, 1000)]
        rc, calls = self.run_tool(tree, entries)
        self.assertEqual(rc, 0)
        self.assertEqual(calls[str(tree)], (0, 0, False))
        self.assertEqual(calls[str(tree / "a")], (1000, 1000, False))

    def test_legacy_added_fallback_and_explicit(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkdir(tree, "wifi")
        self.mkfile(tree, "wifi/rcInsDriver.sh")
        hook = {"path": "/wifi/rcInsDriver.sh", "type": "reg", "mode": 0o755,
                "mode_oct": "0o755", "uid": 1000, "gid": 1000,
                "size": 1, "sha256": "x", "mtime": 0}
        self.mkdir(tree, "c2m")
        self.mkfile(tree, "c2m/c2m-idle", mode=0o755)
        self.mkfile(tree, "c2m/custom", mode=0o755)
        mut = {"added": [
            {"path": "/c2m", "type": "dir", "mode": 0o755,
             "mode_oct": "0o755", "uid": 1001, "gid": 1001},
            {"path": "/c2m/c2m-idle", "type": "reg", "mode": 0o755,
             "mode_oct": "0o755", "size": 5, "sha256": "y"},
            {"path": "/c2m/custom", "type": "reg", "mode": 0o755,
             "mode_oct": "0o755", "uid": 1000, "gid": 1000,
             "size": 5, "sha256": "z"}],
            "replaced": {},
            "hook": "/wifi/rcInsDriver.sh", "modified": []}
        rc, calls = self.run_tool(tree, [hook, directory("/wifi", 1000, 1000)], mut)
        # Note: stock has no /c2m (added), only hook+wifi dir.
        self.assertEqual(rc, 0)
        self.assertEqual(calls[str(tree / "c2m" / "c2m-idle")], (1001, 1001, False))
        self.assertEqual(calls[str(tree / "c2m" / "custom")], (1000, 1000, False))
        self.assertEqual(calls[str(tree / "c2m")], (1001, 1001, False))

    def test_replaced_absent_inferred_from_sibling(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkdir(tree, "minieye/adas/audios")
        self.mkfile(tree, "minieye/adas/audios/A.wav")
        self.mkfile(tree, "minieye/adas/audios/tlr_green_on.wav")
        self.mkfile(tree, "minieye/adas/md5sum.txt")
        entries = [directory("/minieye", 1000, 1000),
                   directory("/minieye/adas", 1000, 1000),
                   directory("/minieye/adas/audios", 1000, 1000),
                   reg("/minieye/adas/audios/A.wav", 1000, 1000),
                   reg("/minieye/adas/md5sum.txt", 1000, 1000)]
        mut = {"added": [], "replaced": {
            "/minieye/adas/audios/tlr_green_on.wav": {
                "old_sha256": "(absent-in-image)", "old_size": 0,
                "new_sha256": "n", "new_size": 10},
            "/minieye/adas/md5sum.txt": {
                "old_sha256": "o", "old_size": 5, "new_sha256": "n", "new_size": 6}},
            "hook": "/x", "modified": []}
        rc, calls = self.run_tool(tree, entries, mut)
        self.assertEqual(rc, 0, calls)
        # VI-like 1000, not the 1001 fallback.
        self.assertEqual(calls[str(tree / "minieye/adas/audios/tlr_green_on.wav")],
                         (1000, 1000, False))

    def test_replaced_absent_inferred_from_parent(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkdir(tree, "newdir")
        self.mkfile(tree, "newdir/added.wav")
        entries = [directory("/newdir", 1001, 1001)]
        mut = {"added": [], "replaced": {
            "/newdir/added.wav": {"old_sha256": "(absent-in-image)",
                                  "old_size": 0, "new_sha256": "n", "new_size": 4}},
            "hook": "/x", "modified": []}
        rc, calls = self.run_tool(tree, entries, mut)
        self.assertEqual(rc, 0)
        self.assertEqual(calls[str(tree / "newdir" / "added.wav")], (1001, 1001, False))

    def test_replaced_absent_ambiguous_blocked_no_writes(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkdir(tree, "adas")
        self.mkfile(tree, "adas/a.wav")
        self.mkfile(tree, "adas/b.wav")
        self.mkfile(tree, "adas/new.wav")
        entries = [directory("/adas", 1001, 1001),
                   reg("/adas/a.wav", 1000, 1000),
                   reg("/adas/b.wav", 1001, 1001)]
        mut = {"added": [], "replaced": {
            "/adas/new.wav": {"old_sha256": "(absent-in-image)",
                              "old_size": 0, "new_sha256": "n", "new_size": 4}}}
        rc, calls = self.run_tool(tree, entries, mut)
        self.assertNotEqual(rc, 0)
        self.assertEqual(calls, {}, "ambiguous inference must do zero chowns")

    def test_invalid_paths_blocked_no_writes(self):
        bad = ["relative/path", "/a/../b", "/a/./b", "/a//b", "/a/",
               "/a\\b", "/a:b", "", "/a/\x00b"]
        for b in bad:
            with self.subTest(path=b):
                root = tmp_root(self)
                tree = root / "tree"
                tree.mkdir()
                entries = [reg(b, 1001, 1001)] if b.startswith("/") else [
                    {"path": b, "type": "reg", "mode": 0o644,
                     "uid": 1001, "gid": 1001}]
                rc, calls = self.run_tool(tree, entries)
                self.assertNotEqual(rc, 0, b)
                self.assertEqual(calls, {})

    def test_duplicate_paths_blocked_no_writes(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkfile(tree, "f")
        entries = [reg("/f", 1001, 1001), reg("/f", 1000, 1000)]
        rc, calls = self.run_tool(tree, entries)
        self.assertNotEqual(rc, 0)
        self.assertEqual(calls, {})

    def test_added_collision_blocked_no_writes(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkfile(tree, "f")
        entries = [reg("/f", 1001, 1001)]
        mut = {"added": [{"path": "/f", "type": "reg", "mode": 0o644,
                          "mode_oct": "0o644"}],
               "replaced": {}}
        rc, calls = self.run_tool(tree, entries, mut)
        self.assertNotEqual(rc, 0)
        self.assertEqual(calls, {})

    def test_missing_path_blocked_no_writes(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkfile(tree, "present")
        entries = [reg("/present", 1001, 1001), reg("/absent", 1001, 1001)]
        rc, calls = self.run_tool(tree, entries)
        self.assertNotEqual(rc, 0)
        self.assertEqual(calls, {}, "preflight must precede any chown")

    def test_leaf_type_mismatch_blocked_no_writes(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkfile(tree, "f")
        rc, calls = self.run_tool(tree, [directory("/f", 1001, 1001)])
        self.assertNotEqual(rc, 0)
        self.assertEqual(calls, {})
        root2 = tmp_root(self)
        tree2 = root2 / "tree"
        tree2.mkdir()
        self.mkdir(tree2, "d")
        rc, calls = self.run_tool(tree2, [reg("/d", 1001, 1001)])
        self.assertNotEqual(rc, 0)
        self.assertEqual(calls, {})

    def test_bad_ids_and_modes_blocked_no_writes(self):
        for field, value in (("uid", "1001"), ("gid", -1), ("uid", 2**32),
                             ("mode", "0755"), ("mode", 0o10000), ("type", "fifo")):
            with self.subTest(field=field, value=value):
                root = tmp_root(self)
                tree = root / "tree"
                tree.mkdir()
                self.mkfile(tree, "f")
                row = dict(reg("/f", 1001, 1001))
                row[field] = value
                rc, calls = self.run_tool(tree, [row])
                self.assertNotEqual(rc, 0)
                self.assertEqual(calls, {})

    def test_mode_preserved_no_chmod(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        p = self.mkfile(tree, "f", mode=0o640)
        d = self.mkdir(tree, "sub", mode=0o750)
        before = (stat.S_IMODE(p.lstat().st_mode), stat.S_IMODE(d.lstat().st_mode))
        entries = [reg("/f", 1000, 1000, mode=0o640),
                   directory("/sub", 1001, 1001, mode=0o750)]
        rc, calls = self.run_tool(tree, entries)
        self.assertEqual(rc, 0)
        after = (stat.S_IMODE(p.lstat().st_mode), stat.S_IMODE(d.lstat().st_mode))
        self.assertEqual(before, after, "tool must never chmod")

    def test_no_arbitrary_extras_untouched(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkfile(tree, "listed")
        self.mkfile(tree, "extra-unlisted")
        rc, calls = self.run_tool(tree, [reg("/listed", 1000, 1000)])
        self.assertEqual(rc, 0)
        self.assertNotIn(str(tree / "extra-unlisted"), calls)
        self.assertIn(str(tree / "listed"), calls)

    def test_vi_root_explicit_not_fallback(self):
        # VI customer root inode 1 is 1000:1000 0755 (never the 1001 fallback).
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        self.mkdir(tree, "minieye")
        entries = [directory("/", 1000, 1000, mode=0o755),
                   directory("/minieye", 1000, 1000)]
        rc, calls = self.run_tool(tree, entries)
        self.assertEqual(rc, 0)
        self.assertEqual(calls[str(tree)], (1000, 1000, False))

    @unittest.skipIf(os.name == "nt", "POSIX symlink gate")
    def test_symlink_ancestor_blocked_no_writes(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        outside = root / "outside"
        outside.mkdir()
        (outside / "secret").write_bytes(b"x")
        (tree / "link").symlink_to(outside, target_is_directory=True)
        # Image path /link/file would resolve through a symlinked ancestor.
        entries = [directory("/link", 1001, 1001), reg("/link/file", 1001, 1001)]
        rc, calls = self.run_tool(tree, entries)
        self.assertNotEqual(rc, 0)
        self.assertEqual(calls, {})

    @unittest.skipIf(os.name == "nt", "POSIX symlink gate")
    def test_symlink_leaf_owned_without_follow(self):
        root = tmp_root(self)
        tree = root / "tree"
        tree.mkdir()
        (tree / "real").write_bytes(b"real")
        (tree / "link").symlink_to("real")
        entries = [reg("/real", 1000, 1000), symlink_row("/link", 1001, 1001)]
        rc, calls = self.run_tool(tree, entries)
        self.assertEqual(rc, 0)
        self.assertEqual(calls[str(tree / "link")], (1001, 1001, False))
        # A symlink where a regular file is expected must fail.
        rc2, calls2 = self.run_tool(tree, [reg("/link", 1001, 1001)])
        self.assertNotEqual(rc2, 0)
        self.assertEqual(calls2, {})


class ManifestRootTest(unittest.TestCase):
    """Pure read-only root-inode extraction (mocked nodes, no image bytes).

    Proves ubifs_manifest.build_manifest records "/" from inode 1 with the
    observed VI metadata (uid 1000, gid 1000, mode 0755, mtime 1695207460).
    Parent CI validates the same against the real VI image.
    """

    VI_META = {"size": 0, "mode": 0o040755, "uid": 1000, "gid": 1000,
               "nlink": 2, "flags": 0, "atime": 1695207460,
               "ctime": 1695207460, "mtime": 1695207460,
               "sqnum": 1, "offset": 0}

    def build_with_inodes(self, inodes):
        root = tmp_root(self)
        img = root / "dummy.es"
        img.write_bytes(b"dummy")
        with mock.patch.object(UMAN, "scan_nodes", return_value=["n"]), \
             mock.patch.object(UMAN, "latest_dentries", return_value=[]), \
             mock.patch.object(UMAN, "path_index", return_value={}), \
             mock.patch.object(UMAN, "latest_inodes", return_value=inodes), \
             mock.patch.object(UMAN, "read_all_files", return_value=[]):
            return UMAN.build_manifest(img)

    def test_vi_root_recorded_exact(self):
        doc = self.build_with_inodes({1: dict(self.VI_META)})
        self.assertGreaterEqual(len(doc["entries"]), 1)
        row = next(r for r in doc["entries"] if r["path"] == "/")
        self.assertEqual(row["inode"], 1)
        self.assertEqual(row["type"], "dir")
        self.assertEqual(row["mode"], 0o755)
        self.assertEqual(row["mode_oct"], oct(0o755))
        self.assertEqual((row["uid"], row["gid"]), (1000, 1000))
        self.assertEqual(row["mtime"], 1695207460)
        self.assertEqual(doc["entry_count"], len(doc["entries"]))

    def test_root_missing_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.build_with_inodes({})

    def test_root_non_dir_fails_closed(self):
        bad = dict(self.VI_META)
        bad["mode"] = 0o100644
        with self.assertRaises(SystemExit):
            self.build_with_inodes({1: bad})


if __name__ == "__main__":
    unittest.main(verbosity=2)
