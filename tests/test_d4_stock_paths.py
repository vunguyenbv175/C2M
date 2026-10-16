#!/usr/bin/env python3
"""Pure stock-ancestor trust gate for fw/d4/main.c directory_ok.

Offline only. Never touches a camera, WLAN, flash, SD card, /tmp, or real
package paths. Compiles the ACTUAL fw/d4/main.c (production, no SHADOW) with
main renamed and stubbed core/DB/GPS symbols, then exercises directory_ok
directly with synthetic struct stat values (no filesystem I/O in C).

Verified raw cpio facts (parent):
  VI /tmp,/var,/customer 0755 1000:1000; EN /tmp 0775 1001:1001;
  live tmpfs /tmp root sticky 01777 (likely 0755 root observed).
Exact trust enforced:
  /tmp: root 01777, root 0755, 1001:1001 0775 (EN), 1000:1000 0755 (VI).
  /customer: 1000:1000 0755 (VI), 1001:1001 0755 (EN/UBIFS/installer).
  /customer/c2m: installer 1001:1001 0755 only.
  Root non-writable dirs otherwise valid (unchanged default).
NO generic uid-1000/1001 writable trust; gid always checked; /tmp never
takes a fixture override. GPS leaf (c2m_gps_read) has no owner check and
DB leaf stays 0/1001 (installer 1001), so no leaf change here.

Run: python tests/test_d4_stock_paths.py  (or python -m unittest)
CC may select a compiler. Static analysis only, not HW proof.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "fw" / "d4" / "main.c"

HARNESS = r'''
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
/* Pull the ACTUAL production translation unit; rename its entry point so
 * the harness below owns main. directory_ok is static in that TU, hence
 * directly callable here in the same TU. */
#define main c2m_d4_production_main_renamed
#include "fw/d4/main.c"
#undef main
/* Stubs for externals referenced by main.c (never called by this harness).
 * Signatures match fw/warner/db.h, fw/d4/advisory.h, fw/d3/gps_snapshot.h. */
warner_sign_t *signdb_load_stream(FILE *s, int *n) { (void)s; if (n) *n = 0; return 0; }
void signdb_free(warner_sign_t *p) { (void)p; }
void c2m_d4_init(struct c2m_d4_advisory *c, const warner_sign_t *s, int n,
                 struct c2m_d4_cooldown *k) { (void)c; (void)s; (void)n; (void)k; }
void c2m_d4_prepare(struct c2m_d4_advisory *c, const struct c2m_gps_snapshot *g,
                    uint64_t t, int ok, int dis, struct c2m_d4_status *o)
{ (void)c; (void)g; (void)t; (void)ok; (void)dis; (void)o; }
void c2m_d4_published(struct c2m_d4_advisory *c, int s) { (void)c; (void)s; }
int c2m_d4_format_status(const struct c2m_d4_status *s, char *b, size_t n)
{ (void)s; (void)b; (void)n; return -1; }
int c2m_d4_self_test(void) { return 1; }
int c2m_gps_read(const char *p, struct c2m_gps_snapshot *o) { (void)p; (void)o; return -2; }
static int run_one(const char *prefix, unsigned uid, unsigned gid,
                   unsigned mode, int isdir, int fixture) {
    struct stat st;
    memset(&st, 0, sizeof(st));
    st.st_mode = (isdir ? S_IFDIR : S_IFREG) | (mode & 07777);
    st.st_uid = (uid_t)uid;
    st.st_gid = (gid_t)gid;
    return directory_ok(&st, prefix, fixture) ? 1 : 0;
}
int main(void) {
    struct { const char *prefix; unsigned uid, gid, mode; int isdir, fixture, want; } v[] = {
        /* root default unchanged */
        {"/", 0, 0, 0755, 1, 0, 1},
        {"/", 0, 0, 0775, 1, 0, 0},
        /* /tmp exact table, production (fixture=0), never fixture override */
        {"/tmp", 0, 0, 01777, 1, 0, 1},
        {"/tmp", 0, 0, 01777, 1, 1, 1},
        {"/tmp", 0, 0, 0755, 1, 0, 1},
        {"/tmp", 1001, 1001, 0775, 1, 0, 1},
        {"/tmp", 1000, 1000, 0755, 1, 0, 1},
        {"/tmp", 1001, 1001, 0755, 1, 0, 0},
        {"/tmp", 1000, 1000, 0775, 1, 0, 0},
        {"/tmp", 0, 0, 0775, 1, 0, 0},
        {"/tmp", 1001, 0, 0775, 1, 0, 0},
        {"/tmp", 0, 1001, 01777, 1, 0, 0},
        {"/tmp", 1000, 0, 0755, 1, 0, 0},
        {"/tmp", 1001, 1001, 0777, 1, 0, 0},
        /* /customer exact 0755 only for 1000/1001 (+ root default) */
        {"/customer", 0, 0, 0755, 1, 0, 1},
        {"/customer", 1001, 1001, 0755, 1, 0, 1},
        {"/customer", 1000, 1000, 0755, 1, 0, 1},
        {"/customer", 1001, 1001, 0775, 1, 0, 0},
        {"/customer", 1000, 1000, 0775, 1, 0, 0},
        {"/customer", 1001, 0, 0755, 1, 0, 0},
        /* /customer/c2m installer 1001:1001 0755 only (+ root default) */
        {"/customer/c2m", 0, 0, 0755, 1, 0, 1},
        {"/customer/c2m", 1001, 1001, 0755, 1, 0, 1},
        {"/customer/c2m", 1000, 1000, 0755, 1, 0, 0},
        {"/customer/c2m", 1001, 1001, 0775, 1, 0, 0},
        /* no generic 1000 writable trust elsewhere; non-dirs fail */
        {"/customer/minieye", 1000, 1000, 0775, 1, 0, 0},
        {"/etc", 1000, 1000, 0755, 1, 0, 0},
        {"/tmp", 0, 0, 01777, 0, 0, 0},
    };
    size_t i; int fails = 0;
    for (i = 0; i < sizeof(v) / sizeof(v[0]); i++) {
        int got = run_one(v[i].prefix, v[i].uid, v[i].gid, v[i].mode,
                          v[i].isdir, v[i].fixture);
        printf("%s %u:%u %04o fixture=%d -> %d (want %d)\n",
               v[i].prefix, v[i].uid, v[i].gid, v[i].mode,
               v[i].fixture, got, v[i].want);
        if (got != v[i].want) { printf("FAIL row %u\n", (unsigned)i); fails++; }
    }
    if (fails) { printf("d4-stock-paths: FAIL %d\n", fails); return 1; }
    printf("d4-stock-paths: OK\n");
    return 0;
}
'''


def find_cc() -> str:
    cc = shutil.which(os.environ.get("CC", "gcc"))
    if cc:
        return cc
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    raise unittest.SkipTest("host C compiler not available")


class StockPathTests(unittest.TestCase):
    def test_actual_main_c_exact_table(self):
        self.assertTrue(MAIN_C.is_file(), "fw/d4/main.c missing")
        text = MAIN_C.read_text(encoding="utf-8")
        # Static source pins: exact tuples present, no generic 1000 trust.
        for pin in ('mode == 01777 || mode == 0755',
                    's->st_uid == 1001 && s->st_gid == 1001 && mode == 0775',
                    's->st_uid == 1000 && s->st_gid == 1000 && mode == 0755',
                    'return 0; /* exact /tmp branch never takes a fixture override */',
                    '!strcmp(prefix, "/customer")',
                    '!strcmp(prefix, "/customer/c2m")'):
            self.assertIn(pin, text, f"missing source pin: {pin}")
        if not sys.platform.startswith("linux"):
            raise unittest.SkipTest("C harness needs Linux (directory_ok is __linux__-gated)")
        cc = find_cc()
        with tempfile.TemporaryDirectory(prefix="c2m-d4-stock-paths-") as td:
            src = Path(td) / "harness.c"
            exe = Path(td) / "harness"
            src.write_text(HARNESS, encoding="utf-8")
            cmd = [cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                   "-I", str(ROOT), "-I", str(ROOT / "fw" / "d4"),
                   "-I", str(ROOT / "fw" / "d3"), "-I", str(ROOT / "fw" / "warner"),
                   str(src), "-o", str(exe)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                                  cwd=str(ROOT))
            self.assertEqual(proc.returncode, 0,
                             "C harness build failed:\n" + proc.stdout + proc.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            sys.stdout.write(run.stdout)
            sys.stderr.write(run.stderr)
            self.assertEqual(run.returncode, 0, "directory_ok exact table failed")
            self.assertIn("d4-stock-paths: OK", run.stdout)


if __name__ == "__main__":
    unittest.main()
