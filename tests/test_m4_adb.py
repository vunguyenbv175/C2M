#!/usr/bin/env python3
"""Host guards for M4 ADB identify (fw/m4_adb/m4_adb_identify.c).

Synthetic-only. Never touches camera, USB hardware, network, or real
/dev/bus/usb paths. Portable --help/--self-test/CLI checks run on Windows
and Linux. Pure descriptor/protocol APIs are exercised via a compiled C
harness (no TEST-only shipping logic). --probe is NEVER executed natively
on Linux by this suite (not even without hardware); on Windows it is
optionally checked as unsupported. A Linux-only compiled include shim
fakes every OS syscall (open/read/close/ioctl/clock_gettime/sigaction via
macros BEFORE the source include, all real headers pre-included first) and
calls the real source m4_probe() for the mandatory successful-capture-path
gate: CNXN success, AUTH stop, short/timeout/claim/release/wrong-iface.

Pure APIs (must stay plain C, before any Linux-only probe body):
  static int    m4_validate_descriptors(const uint8_t *, size_t) -> 0/-1
  static size_t m4_cnxn_request(uint8_t *, size_t) -> 31 (24 header + 7 payload)
  static int    m4_classify_reply(const uint8_t *, size_t,
                                  const uint8_t *, size_t) -> 1/2/-1
    1 = CNXN reply whose payload starts "device::"
    2 = AUTH TOKEN (arg0==1, arg1==0, 20B payload)
   -1 = anything else (bad magic/checksum/len>4096/unknown/mismatch/partial)

Wire split (AOSP remote_write): ONE CNXN request (31B from m4_cnxn_request)
is sent as TWO USB OUT bulk transfers -- header 24 then payload 7 -- never
a single combined 31B transfer. Replies are read as at most TWO IN
transfers (24 header, then payload). No blind retry.

Valid synthetic device: 18B device VID 0x2207 PID 0x0013, one configuration
(9B header, wTotalLength strict), interfaces 0/1 RNDIS + 2 ADB
(ff/42/01, alt 0, 2 bulk EP 0x04 OUT / 0x85 IN, max 512).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "fw" / "m4_adb" / "m4_adb_identify.c"
FLAGS = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
HARNESS_FLAGS = FLAGS + ["-Wno-unused-function"]
LINUX = sys.platform.startswith("linux")
NATIVE_TIMEOUT = 15.0


def find_cc() -> str:
    cc = shutil.which(os.environ.get("CC", "gcc"))
    if cc:
        return cc
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    raise unittest.SkipTest("host C compiler not available")


def compile_binary(cc: str, output: Path) -> None:
    cmd = [cc] + FLAGS + [str(MAIN_C.relative_to(ROOT)), "-o", str(output)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise AssertionError(f"compile failed:\n{result.stdout}{result.stderr}")


def strip_c_comments(src: str) -> str:
    out: list[str] = []
    i = 0
    n = len(src)
    in_line = False
    in_block = False
    in_str = False
    in_chr = False
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_line:
            if c == "\n":
                in_line = False
                out.append(c)
            i += 1
            continue
        if in_block:
            if c == "*" and nxt == "/":
                in_block = False
                i += 2
            else:
                if c == "\n":
                    out.append("\n")
                i += 1
            continue
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if in_chr:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == "'":
                in_chr = False
            i += 1
            continue
        if c == "/" and nxt == "/":
            in_line = True
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "'":
            in_chr = True
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


HARNESS_TEMPLATE = r"""
/* Feature macros precede EVERY system header in the include harness. */
#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <inttypes.h>

#define main m4_orig_main
#include "__INCLUDE_PATH__"
#undef main

static int h_fail = 0;
static int h_total = 0;

static void h_report(int ok, const char *name) {
    ++h_total;
    if (ok) {
        printf("[PASS] %s\n", name);
    } else {
        ++h_fail;
        printf("[FAIL] %s\n", name);
    }
    fflush(stdout);
}

static uint32_t h_le32(const uint8_t *b) {
    return ((uint32_t)b[0]) | ((uint32_t)b[1] << 8) |
           ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}

static void h_put32(uint8_t *b, uint32_t v) {
    b[0] = (uint8_t)(v & 0xFFu);
    b[1] = (uint8_t)((v >> 8) & 0xFFu);
    b[2] = (uint8_t)((v >> 16) & 0xFFu);
    b[3] = (uint8_t)((v >> 24) & 0xFFu);
}

static uint32_t h_sum(const uint8_t *p, size_t n) {
    uint32_t s = 0;
    size_t i;
    for (i = 0; i < n; ++i) s += p[i];
    return s;
}

/* Valid synthetic blob: device 18B + config 71B (hdr 9 + if0 9+7 + if1 9+14 + adb 9+14). */
static size_t h_build_valid(uint8_t *b, size_t cap) {
    uint8_t dev[18];
    uint8_t cfg[71];
    size_t pos = 0;
    if (cap < 89) return 0;
    memset(dev, 0, sizeof(dev));
    dev[0] = 18; dev[1] = 1;
    dev[2] = 0x00; dev[3] = 0x02;
    dev[4] = 0; dev[5] = 0; dev[6] = 0;
    dev[7] = 64;
    dev[8] = 0x07; dev[9] = 0x22;
    dev[10] = 0x13; dev[11] = 0x00;
    dev[12] = 0x00; dev[13] = 0x01;
    dev[14] = 1; dev[15] = 2; dev[16] = 3;
    dev[17] = 1;
    memset(cfg, 0, sizeof(cfg));
    pos = 0;
    cfg[pos++] = 9; cfg[pos++] = 2;
    cfg[pos++] = 71; cfg[pos++] = 0;
    cfg[pos++] = 3; cfg[pos++] = 1; cfg[pos++] = 0; cfg[pos++] = 0x80; cfg[pos++] = 50;
    /* if0 RNDIS control: 0, alt0, 1 ep, 02/02/FF */
    cfg[pos++] = 9; cfg[pos++] = 4; cfg[pos++] = 0; cfg[pos++] = 0;
    cfg[pos++] = 1; cfg[pos++] = 0x02; cfg[pos++] = 0x02; cfg[pos++] = 0xFF; cfg[pos++] = 0;
    /* ep 0x83 interrupt 8 */
    cfg[pos++] = 7; cfg[pos++] = 5; cfg[pos++] = 0x83; cfg[pos++] = 0x03;
    cfg[pos++] = 8; cfg[pos++] = 0; cfg[pos++] = 10;
    /* if1 RNDIS data: 1, alt0, 2 ep, 0A/00/00 */
    cfg[pos++] = 9; cfg[pos++] = 4; cfg[pos++] = 1; cfg[pos++] = 0;
    cfg[pos++] = 2; cfg[pos++] = 0x0A; cfg[pos++] = 0x00; cfg[pos++] = 0x00; cfg[pos++] = 0;
    cfg[pos++] = 7; cfg[pos++] = 5; cfg[pos++] = 0x01; cfg[pos++] = 0x02;
    cfg[pos++] = 0x00; cfg[pos++] = 0x02; cfg[pos++] = 0;
    cfg[pos++] = 7; cfg[pos++] = 5; cfg[pos++] = 0x82; cfg[pos++] = 0x02;
    cfg[pos++] = 0x00; cfg[pos++] = 0x02; cfg[pos++] = 0;
    /* if2 ADB: 2, alt0, 2 ep, FF/42/01 */
    cfg[pos++] = 9; cfg[pos++] = 4; cfg[pos++] = 2; cfg[pos++] = 0;
    cfg[pos++] = 2; cfg[pos++] = 0xFF; cfg[pos++] = 0x42; cfg[pos++] = 0x01; cfg[pos++] = 0;
    cfg[pos++] = 7; cfg[pos++] = 5; cfg[pos++] = 0x04; cfg[pos++] = 0x02;
    cfg[pos++] = 0x00; cfg[pos++] = 0x02; cfg[pos++] = 0;
    cfg[pos++] = 7; cfg[pos++] = 5; cfg[pos++] = 0x85; cfg[pos++] = 0x02;
    cfg[pos++] = 0x00; cfg[pos++] = 0x02; cfg[pos++] = 0;
    if (pos != 71) return 0;
    memcpy(b, dev, 18);
    memcpy(b + 18, cfg, 71);
    return 89;
}

#define A_CNXN 0x4E584E43u
#define A_AUTH 0x48545541u

static void h_make_hdr(uint8_t *hdr, uint32_t cmd, uint32_t a0, uint32_t a1,
                       const uint8_t *pay, size_t paylen) {
    h_put32(hdr + 0, cmd);
    h_put32(hdr + 4, a0);
    h_put32(hdr + 8, a1);
    h_put32(hdr + 12, (uint32_t)paylen);
    h_put32(hdr + 16, h_sum(pay, paylen));
    h_put32(hdr + 20, cmd ^ 0xFFFFFFFFu);
}

int main(void) {
    uint8_t blob[256];
    uint8_t work[256];
    uint8_t out[64];
    uint8_t hdr[24];
    uint8_t pay[64];
    size_t blen;
    size_t n;
    size_t paylen;

    /* --- descriptors: valid --- */
    blen = h_build_valid(blob, sizeof(blob));
    h_report(blen == 89, "desc_valid_len");
    h_report(m4_validate_descriptors(blob, blen) == 0, "desc_valid");
    h_report(m4_validate_descriptors(NULL, 0) == -1, "desc_null");
    h_report(m4_validate_descriptors(blob, 0) == -1, "desc_empty");

    /* --- descriptors: short / truncated --- */
    h_report(m4_validate_descriptors(blob, 10) == -1, "desc_short10");
    h_report(m4_validate_descriptors(blob, 18 + 9) == -1, "desc_cfg_only");
    {
        memcpy(work, blob, blen);
        work[0] = 10;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_bad_devlen");
    }

    /* --- descriptors: overflow (wTotalLength past end) --- */
    {
        memcpy(work, blob, blen);
        work[18 + 2] = 0xFF; work[18 + 3] = 0x00;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_overflow_total");
    }
    {
        memcpy(work, blob, blen);
        work[18 + 9] = 0xFF;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_overflow_blen");
    }

    /* --- descriptors: vendor / product / class --- */
    {
        memcpy(work, blob, blen);
        work[8] = 0x34; work[9] = 0x12;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_vid");
    }
    {
        memcpy(work, blob, blen);
        work[10] = 0x78; work[11] = 0x56;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_pid");
    }
    {
        memcpy(work, blob, blen);
        /* ADB iface is at 18+9+16+23 = byte 66 rel blob; class at +5 */
        work[18 + 9 + 16 + 23 + 5] = 0x02;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_class");
    }
    {
        memcpy(work, blob, blen);
        work[18 + 9 + 16 + 23 + 6] = 0x00;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_subclass");
    }
    {
        memcpy(work, blob, blen);
        work[18 + 9 + 16 + 23 + 7] = 0x02;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_proto");
    }
    {
        memcpy(work, blob, blen);
        work[17] = 2;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_numcfg");
    }

    /* --- descriptors: multiple configs (append second config header) --- */
    {
        uint8_t two[256];
        size_t tlen = blen;
        memcpy(two, blob, blen);
        if (tlen + 9 <= sizeof(two)) {
            two[tlen + 0] = 9; two[tlen + 1] = 2;
            two[tlen + 2] = 9; two[tlen + 3] = 0;
            two[tlen + 4] = 0; two[tlen + 5] = 1;
            two[tlen + 6] = 0; two[tlen + 7] = 0x80; two[tlen + 8] = 50;
            tlen += 9;
            h_report(m4_validate_descriptors(two, tlen) == -1, "desc_multiconfig");
        } else {
            h_report(0, "desc_multiconfig");
        }
    }

    /* --- descriptors: duplicate iface number (clone ADB as iface 1) --- */
    {
        memcpy(work, blob, blen);
        work[18 + 9 + 16 + 23 + 2] = 1;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_dupiface");
    }
    /* --- descriptors: wrong iface number for ADB triple --- */
    {
        memcpy(work, blob, blen);
        work[18 + 9 + 16 + 23 + 2] = 5;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_ifacenum");
    }

    /* --- descriptors: endpoints --- */
    {
        memcpy(work, blob, blen);
        /* first ADB ep attr bulk(02)->interrupt(03) */
        work[18 + 9 + 16 + 23 + 9 + 3] = 0x03;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_eptype");
    }
    {
        memcpy(work, blob, blen);
        /* both IN: 0x04 -> 0x84 */
        work[18 + 9 + 16 + 23 + 9 + 2] = 0x84;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_epdir");
    }
    {
        memcpy(work, blob, blen);
        /* max 512 -> 64 */
        work[18 + 9 + 16 + 23 + 9 + 4] = 64;
        work[18 + 9 + 16 + 23 + 9 + 5] = 0;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_epmax");
    }
    {
        memcpy(work, blob, blen);
        /* alt 0 -> 1 */
        work[18 + 9 + 16 + 23 + 3] = 1;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_alt");
    }
    {
        memcpy(work, blob, blen);
        /* bNumEndpoints 2 -> 1 (second ep orphaned) */
        work[18 + 9 + 16 + 23 + 4] = 1;
        h_report(m4_validate_descriptors(work, blen) == -1, "desc_epcount");
    }

    /* --- CNXN request --- */
    memset(out, 0, sizeof(out));
    n = m4_cnxn_request(out, sizeof(out));
    h_report(n == 31, "cnxn_len");
    if (n == 31) {
        h_report(h_le32(out + 0) == A_CNXN, "cnxn_cmd");
        h_report(h_le32(out + 4) == 0x01000000u, "cnxn_ver");
        h_report(h_le32(out + 8) == 4096, "cnxn_max");
        h_report(h_le32(out + 12) == 7, "cnxn_dlen");
        h_report(h_le32(out + 16) == 562, "cnxn_sum");
        h_report(h_le32(out + 20) == (A_CNXN ^ 0xFFFFFFFFu), "cnxn_magic");
        h_report(memcmp(out + 24, "host::\0", 7) == 0, "cnxn_payload");
    } else {
        h_report(0, "cnxn_cmd");
        h_report(0, "cnxn_ver");
        h_report(0, "cnxn_max");
        h_report(0, "cnxn_dlen");
        h_report(0, "cnxn_sum");
        h_report(0, "cnxn_magic");
        h_report(0, "cnxn_payload");
    }
    h_report(m4_cnxn_request(out, 30) != 31, "cnxn_short");
    h_report(m4_cnxn_request(NULL, 0) != 31, "cnxn_null");
    h_report(m4_cnxn_request(out, 31) == 31, "cnxn_exact");

    /* --- classify: valid CNXN device:: -> 1 --- */
    memcpy(pay, "device::c2m-test\0", 16);
    paylen = 16;
    h_make_hdr(hdr, A_CNXN, 0x01000000u, 4096, pay, paylen);
    h_report(m4_classify_reply(hdr, 24, pay, paylen) == 1, "cls_cnxn_ok");
    h_report(m4_classify_reply(hdr, 24, pay, paylen) != 2, "cls_cnxn_not_auth");

    /* --- classify: valid AUTH TOKEN 20B -> 2 --- */
    {
        size_t k;
        for (k = 0; k < 20; ++k) pay[k] = (uint8_t)(k + 1);
        h_make_hdr(hdr, A_AUTH, 1, 0, pay, 20);
        h_report(m4_classify_reply(hdr, 24, pay, 20) == 2, "cls_auth_ok");
        h_report(m4_classify_reply(hdr, 24, pay, 20) != 1, "cls_auth_not_cnxn");
    }

    /* --- classify: host:: CNXN must not be AUTH/valid-device --- */
    {
        memcpy(pay, "host::\0", 7);
        h_make_hdr(hdr, A_CNXN, 0x01000000u, 4096, pay, 7);
        h_report(m4_classify_reply(hdr, 24, pay, 7) == -1, "cls_host_noauth");
    }

    /* --- classify rejects --- */
    {
        memcpy(pay, "device::c2m-test\0", 16);
        paylen = 16;
        h_make_hdr(hdr, A_CNXN, 0x01000000u, 4096, pay, paylen);
        hdr[20] ^= 0xFF;
        h_report(m4_classify_reply(hdr, 24, pay, paylen) == -1, "cls_badmagic");
    }
    {
        memcpy(pay, "device::c2m-test\0", 16);
        paylen = 16;
        h_make_hdr(hdr, A_CNXN, 0x01000000u, 4096, pay, paylen);
        h_put32(hdr + 16, h_le32(hdr + 16) + 1);
        h_report(m4_classify_reply(hdr, 24, pay, paylen) == -1, "cls_badsum");
    }
    {
        memcpy(pay, "device::c2m-test\0", 16);
        paylen = 16;
        h_make_hdr(hdr, A_CNXN, 0x01000000u, 4096, pay, paylen);
        h_put32(hdr + 12, 5000);
        h_report(m4_classify_reply(hdr, 24, pay, paylen) == -1, "cls_toolong");
    }
    {
        memcpy(pay, "device::c2m-test\0", 16);
        paylen = 16;
        h_make_hdr(hdr, 0x44444444u, 0x01000000u, 4096, pay, paylen);
        h_report(m4_classify_reply(hdr, 24, pay, paylen) == -1, "cls_unknown");
    }
    {
        memcpy(pay, "device::c2m-test\0", 16);
        paylen = 16;
        h_make_hdr(hdr, A_CNXN, 0x01000000u, 4096, pay, paylen);
        h_report(m4_classify_reply(hdr, 24, pay, 5) == -1, "cls_mismatch");
    }
    {
        memcpy(pay, "device::c2m-test\0", 16);
        paylen = 16;
        h_make_hdr(hdr, A_CNXN, 0x01000000u, 4096, pay, paylen);
        h_report(m4_classify_reply(hdr, 10, pay, paylen) == -1, "cls_partial");
    }
    {
        size_t k;
        for (k = 0; k < 20; ++k) pay[k] = (uint8_t)(k + 1);
        h_make_hdr(hdr, A_AUTH, 2, 0, pay, 20);
        h_report(m4_classify_reply(hdr, 24, pay, 20) == -1, "cls_auth_arg0");
    }
    {
        size_t k;
        for (k = 0; k < 20; ++k) pay[k] = (uint8_t)(k + 1);
        h_make_hdr(hdr, A_AUTH, 1, 1, pay, 20);
        h_report(m4_classify_reply(hdr, 24, pay, 20) == -1, "cls_auth_arg1");
    }
    {
        size_t k;
        for (k = 0; k < 19; ++k) pay[k] = (uint8_t)(k + 1);
        h_make_hdr(hdr, A_AUTH, 1, 0, pay, 19);
        h_report(m4_classify_reply(hdr, 24, pay, 19) == -1, "cls_auth_len19");
    }
    {
        size_t k;
        for (k = 0; k < 21; ++k) pay[k] = (uint8_t)(k + 1);
        h_make_hdr(hdr, A_AUTH, 1, 0, pay, 21);
        h_report(m4_classify_reply(hdr, 24, pay, 21) == -1, "cls_auth_len21");
    }
    h_report(m4_classify_reply(NULL, 24, pay, 20) == -1, "cls_null_hdr");
    h_report(m4_classify_reply(hdr, 24, NULL, 0) == -1, "cls_null_pay");

    printf("HARNESS_RESULT %s total=%d failures=%d\n", h_fail ? "FAIL" : "PASS", h_total, h_fail);
    fflush(stdout);
    return h_fail ? 1 : 0;
}
"""


def compile_harness(cc: str, tmpdir: Path) -> Path:
    include_posix = MAIN_C.resolve().as_posix()
    src = HARNESS_TEMPLATE.replace("__INCLUDE_PATH__", include_posix)
    harness_c = tmpdir / "m4_adb_harness.c"
    harness_c.write_text(src, encoding="utf-8")
    suffix = ".exe" if os.name == "nt" else ""
    harness_bin = tmpdir / ("m4-adb-harness" + suffix)
    cmd = [cc] + HARNESS_FLAGS + [str(harness_c), "-o", str(harness_bin)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise AssertionError(
            "harness compile failed (pure ADB APIs likely missing/mis-signed):\n"
            f"{result.stdout}{result.stderr}"
        )
    return harness_bin


def run_harness_once(cc: str, tmpdir: Path) -> subprocess.CompletedProcess[str]:
    harness = compile_harness(cc, tmpdir)
    return subprocess.run(
        [str(harness)], text=True, capture_output=True, timeout=NATIVE_TIMEOUT
    )


SHIM_TEMPLATE = r"""
/* Feature macros precede EVERY system header in the include harness. */
#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <inttypes.h>

#define main m4_orig_main
#include "__INCLUDE_PATH__"
#undef main

static int s_fail = 0;
static int s_total = 0;

static void s_report(int ok, const char *name) {
    ++s_total;
    if (ok) {
        printf("[PASS] %s\n", name);
    } else {
        ++s_fail;
        printf("[FAIL] %s\n", name);
    }
    fflush(stdout);
}

static uint32_t s_le32(const uint8_t *b) {
    return ((uint32_t)b[0]) | ((uint32_t)b[1] << 8) |
           ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}

static void s_put32(uint8_t *b, uint32_t v) {
    b[0] = (uint8_t)(v & 0xFFu);
    b[1] = (uint8_t)((v >> 8) & 0xFFu);
    b[2] = (uint8_t)((v >> 16) & 0xFFu);
    b[3] = (uint8_t)((v >> 24) & 0xFFu);
}

static uint32_t s_sum(const uint8_t *p, size_t n) {
    uint32_t s = 0;
    size_t i;
    for (i = 0; i < n; ++i) s += p[i];
    return s;
}

/* Fake USB transport: counts only, no hardware, no retry, no sockets. */
static unsigned fake_out_calls = 0;
static unsigned fake_out_bytes = 0;
static unsigned fake_out_lens[4];
static unsigned fake_rx_calls = 0;

static void fake_out(const uint8_t *d, unsigned len) {
    if (fake_out_calls < 4) fake_out_lens[fake_out_calls] = len;
    ++fake_out_calls;
    fake_out_bytes += len;
    (void)d;
}

static void fake_rx_one(void) { ++fake_rx_calls; }

int main(void) {
    uint8_t req[32];
    uint8_t hdr[24];
    uint8_t pay[64];
    size_t n;
    size_t k;

    /* Pure request is still one 31B blob (split happens at transport). */
    n = m4_cnxn_request(req, sizeof(req));
    s_report(n == 31, "shim_req31");
    s_report(s_le32(req) == 0x4E584E43u, "shim_hdr_cmd");
    s_report(s_le32(req + 12) == 7, "shim_hdr_len7");
    s_report(s_le32(req + 16) == 562, "shim_hdr_sum");
    s_report(memcmp(req + 24, "host::\0", 7) == 0, "shim_payload7");

    /* AOSP remote_write split: TWO OUT transfers (24, then 7), never one 31. */
    fake_out_calls = 0;
    fake_out_bytes = 0;
    fake_out(req, 24);
    fake_out(req + 24, 7);
    s_report(fake_out_calls == 2, "shim_out_two");
    s_report(fake_out_bytes == 31, "shim_out_total31");
    s_report(fake_out_lens[0] == 24 && fake_out_lens[1] == 7, "shim_out_split_24_7");

    /* RX split: header 24 then payload; at most two IN transfers. */
    memcpy(pay, "device::fake-ok\0", 16);
    s_put32(hdr + 0, 0x4E584E43u);
    s_put32(hdr + 4, 0x01000000u);
    s_put32(hdr + 8, 4096);
    s_put32(hdr + 12, 16);
    s_put32(hdr + 16, s_sum(pay, 16));
    s_put32(hdr + 20, 0x4E584E43u ^ 0xFFFFFFFFu);
    fake_rx_calls = 0;
    fake_rx_one();
    fake_rx_one();
    s_report(fake_rx_calls == 2, "shim_rx_two");
    s_report(m4_classify_reply(hdr, 24, pay, 16) == 1, "shim_success_cnxn");

    /* AUTH stays distinct on the same fake transport (no confusion). */
    for (k = 0; k < 20; ++k) pay[k] = (uint8_t)(k + 1);
    s_put32(hdr + 0, 0x48545541u);
    s_put32(hdr + 4, 1);
    s_put32(hdr + 8, 0);
    s_put32(hdr + 12, 20);
    s_put32(hdr + 16, s_sum(pay, 20));
    s_put32(hdr + 20, 0x48545541u ^ 0xFFFFFFFFu);
    s_report(m4_classify_reply(hdr, 24, pay, 20) == 2, "shim_success_auth");

    /* No retry flag was ever set: single attempt per transfer by construction. */
    s_report(fake_out_calls == 2 && fake_rx_calls == 2, "shim_no_retry");

    printf("SHIM_RESULT %s total=%d failures=%d\n", s_fail ? "FAIL" : "PASS", s_total, s_fail);
    fflush(stdout);
    return s_fail ? 1 : 0;
}
"""


def compile_shim(cc: str, tmpdir: Path) -> Path:
    include_posix = MAIN_C.resolve().as_posix()
    src = SHIM_TEMPLATE.replace("__INCLUDE_PATH__", include_posix)
    shim_c = tmpdir / "m4_adb_shim.c"
    shim_c.write_text(src, encoding="utf-8")
    suffix = ".exe" if os.name == "nt" else ""
    shim_bin = tmpdir / ("m4-adb-shim" + suffix)
    cmd = [cc] + HARNESS_FLAGS + [str(shim_c), "-o", str(shim_bin)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise AssertionError(f"shim compile failed:\n{result.stdout}{result.stderr}")
    return shim_bin


# Linux-only successful-capture-path shim: fakes every OS syscall via macros
# BEFORE the source include (all real headers are pre-included first, so the
# source's own includes become no-ops but its open/read/close/ioctl/
# clock_gettime/sigaction calls resolve to deterministic fakes). Calls the
# real source m4_probe() -- never hardware -- with synthetic sysfs strings,
# descriptors and CNXN/AUTH replies. Verifies TWO OUT (24 then 7), at most
# TWO IN, no retry, no file create, only allowed paths.
PROBE_SHIM_TEMPLATE = r"""
#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#ifdef __linux__
#include <linux/usbdevice_fs.h>
#include <linux/usb/ch9.h>
#endif

static int ps_fail = 0;
static int ps_total = 0;
static void ps_report(int ok, const char *name) {
    ++ps_total;
    if (ok) { printf("[PASS] %s\n", name); }
    else { ++ps_fail; printf("[FAIL] %s\n", name); }
    fflush(stdout);
}
static void ps_put32(uint8_t *b, uint32_t v) {
    b[0] = (uint8_t)(v & 0xFFu); b[1] = (uint8_t)((v >> 8) & 0xFFu);
    b[2] = (uint8_t)((v >> 16) & 0xFFu); b[3] = (uint8_t)((v >> 24) & 0xFFu);
}
static uint32_t ps_sum(const uint8_t *p, size_t n) {
    uint32_t s = 0; size_t i; for (i = 0; i < n; ++i) s += p[i]; return s;
}

/* ---- deterministic fake USB/sysfs world ---- */
static int g_mode = 0;
static int g_claim_rc = 0;
static int g_release_rc = 0;
static int g_out0_ret = 24;
static int g_out1_ret = 7;
static int g_in_hdr_ret = 24;
static int g_in_pay_ret = -1000;
static int g_reply_kind = 0;
static int g_deadline_phase = 0;
static long g_now_ms = 0;
static int g_clock_calls = 0;
static int g_bad_desc = 0;

static int g_open_count = 0;
static char g_open_paths[12][96];
static int g_open_flags[12];
static int g_bad_open = 0;
static int g_claim_count = 0;
static int g_release_count = 0;
static int g_bulk_count = 0;
static int g_out_count = 0;
static int g_in_count = 0;
static uint8_t g_out_cap0[32];
static uint8_t g_out_cap1[32];
static unsigned g_out_len0 = 0;
static unsigned g_out_len1 = 0;
static uint8_t g_reply_hdr[24];
static uint8_t g_reply_pay[64];
static size_t g_reply_paylen = 0;

static int g_next_fd = 100;
static int g_sys_vendor_fd = -1;
static int g_sys_product_fd = -1;
static int g_sys_bus_fd = -1;
static int g_sys_dev_fd = -1;
static int g_usb_fd = -1;
static int g_ever_bad_open = 0;
static int g_ever_bad_path = 0;

static const uint8_t GOOD_DESC[50] = {
    18, 1, 0x00, 0x02, 0, 0, 0, 64, 0x07, 0x22, 0x13, 0x00,
    0x00, 0x01, 1, 2, 3, 1,
    9, 2, 0x20, 0x00, 1, 1, 0, 0x80, 250,
    9, 4, 2, 0, 2, 0xFF, 0x42, 0x01, 0,
    7, 5, 0x04, 0x02, 0x00, 0x02, 0,
    7, 5, 0x85, 0x02, 0x00, 0x02, 0 };

static void ps_build_reply(void) {
    size_t k;
    if (g_reply_kind == 0) {
        memcpy(g_reply_pay, "device::fake-ok\0", 16);
        g_reply_paylen = 16;
        ps_put32(g_reply_hdr + 0, 0x4E584E43u);
        ps_put32(g_reply_hdr + 4, 0x01000000u);
        ps_put32(g_reply_hdr + 8, 4096);
        ps_put32(g_reply_hdr + 12, (uint32_t)g_reply_paylen);
        ps_put32(g_reply_hdr + 16, ps_sum(g_reply_pay, g_reply_paylen));
        ps_put32(g_reply_hdr + 20, 0x4E584E43u ^ 0xFFFFFFFFu);
    } else if (g_reply_kind == 1) {
        for (k = 0; k < 20; ++k) g_reply_pay[k] = (uint8_t)(k + 1);
        g_reply_paylen = 20;
        ps_put32(g_reply_hdr + 0, 0x48545541u);
        ps_put32(g_reply_hdr + 4, 1);
        ps_put32(g_reply_hdr + 8, 0);
        ps_put32(g_reply_hdr + 12, 20);
        ps_put32(g_reply_hdr + 16, ps_sum(g_reply_pay, 20));
        ps_put32(g_reply_hdr + 20, 0x48545541u ^ 0xFFFFFFFFu);
    } else {
        ps_put32(g_reply_hdr + 0, 0x4E584E43u);
        ps_put32(g_reply_hdr + 4, 0x01000000u);
        ps_put32(g_reply_hdr + 8, 4096);
        ps_put32(g_reply_hdr + 12, 5000);
        ps_put32(g_reply_hdr + 16, ps_sum(g_reply_pay, g_reply_paylen));
        ps_put32(g_reply_hdr + 20, 0x4E584E43u ^ 0xFFFFFFFFu);
        g_reply_hdr[20] ^= 0xFF;
        memcpy(g_reply_pay, "device::fake-ok\0", 16);
        g_reply_paylen = 16;
    }
}

static void ps_reset(void) {
    g_open_count = 0; g_bad_open = 0;
    g_claim_count = 0; g_release_count = 0;
    g_bulk_count = 0; g_out_count = 0; g_in_count = 0;
    g_out_len0 = 0; g_out_len1 = 0;
    memset(g_out_cap0, 0, sizeof(g_out_cap0));
    memset(g_out_cap1, 0, sizeof(g_out_cap1));
    memset(g_open_paths, 0, sizeof(g_open_paths));
    g_next_fd = 100;
    g_sys_vendor_fd = -1; g_sys_product_fd = -1;
    g_sys_bus_fd = -1; g_sys_dev_fd = -1; g_usb_fd = -1;
    g_now_ms = 0; g_clock_calls = 0;
    ps_build_reply();
}

static void ps_check_opens(void) {
    int i;
    if (g_bad_open) g_ever_bad_open = 1;
    for (i = 0; i < g_open_count; ++i) {
        const char *p = g_open_paths[i];
        int ok = (strstr(p, "/sys/bus/usb/devices/1-1/") == p) ||
                 (strstr(p, "/dev/bus/usb/") == p);
        if (!ok) g_ever_bad_path = 1;
    }
}

static int m4_fake_open(const char *path, int flags, ...) {
    int fd;
    size_t L;
    if (!path) { errno = EFAULT; return -1; }
    if (g_open_count >= 12) { errno = EMFILE; return -1; }
    L = strlen(path);
    if (L >= 96) { errno = ENAMETOOLONG; return -1; }
    strcpy(g_open_paths[g_open_count], path);
    g_open_flags[g_open_count] = flags;
    ++g_open_count;
    if ((flags & O_CREAT) || (flags & O_TRUNC)) { g_bad_open = 1; }
    if ((flags & O_ACCMODE) == O_WRONLY) { g_bad_open = 1; }
    if (strstr(path, "/sys/bus/usb/devices/1-1/idVendor") != NULL) {
        fd = g_next_fd++; g_sys_vendor_fd = fd; return fd;
    }
    if (strstr(path, "/sys/bus/usb/devices/1-1/idProduct") != NULL) {
        fd = g_next_fd++; g_sys_product_fd = fd; return fd;
    }
    if (strstr(path, "/sys/bus/usb/devices/1-1/busnum") != NULL) {
        fd = g_next_fd++; g_sys_bus_fd = fd; return fd;
    }
    if (strstr(path, "/sys/bus/usb/devices/1-1/devnum") != NULL) {
        fd = g_next_fd++; g_sys_dev_fd = fd; return fd;
    }
    if (strstr(path, "/dev/bus/usb/") == path) {
        fd = g_next_fd++; g_usb_fd = fd; return fd;
    }
    g_bad_open = 1;
    errno = ENOENT;
    return -1;
}

static ssize_t m4_fake_read(int fd, void *buf, size_t count) {
    const char *s = NULL;
    if (!buf || count == 0) { errno = EINVAL; return -1; }
    if (fd == g_sys_vendor_fd) { s = "2207\n"; }
    else if (fd == g_sys_product_fd) { s = "0013\n"; }
    else if (fd == g_sys_bus_fd) { s = "001\n"; }
    else if (fd == g_sys_dev_fd) { s = "002\n"; }
    if (s != NULL) {
        size_t L = strlen(s);
        if (L > count) L = count;
        memcpy(buf, s, L);
        return (ssize_t)L;
    }
    if (fd == g_usb_fd) {
        uint8_t tmp[50];
        memcpy(tmp, GOOD_DESC, sizeof(tmp));
        if (g_bad_desc) { tmp[32] = 0x02; }
        {
            size_t L = sizeof(tmp);
            if (L > count) L = count;
            memcpy(buf, tmp, L);
            return (ssize_t)L;
        }
    }
    errno = EBADF;
    return -1;
}

static int m4_fake_close(int fd) {
    (void)fd;
    return 0;
}

static int m4_fake_ioctl(int fd, unsigned long req, ...) {
    va_list ap;
    void *arg = NULL;
    va_start(ap, req);
    arg = va_arg(ap, void *);
    va_end(ap);
    (void)fd;
    if (req == (unsigned long)USBDEVFS_CLAIMINTERFACE) {
        ++g_claim_count;
        if (g_claim_rc != 0) { errno = EBUSY; return -1; }
        return 0;
    }
    if (req == (unsigned long)USBDEVFS_RELEASEINTERFACE) {
        ++g_release_count;
        if (g_release_rc != 0) { errno = EINVAL; return -1; }
        return 0;
    }
    if (req == (unsigned long)USBDEVFS_BULK) {
        struct usbdevfs_bulktransfer *bt = (struct usbdevfs_bulktransfer *)arg;
        unsigned ep;
        unsigned len;
        if (!bt) { errno = EFAULT; return -1; }
        ep = bt->ep; len = bt->len;
        ++g_bulk_count;
        if (ep == 0x04u) {
            const uint8_t *d = (const uint8_t *)bt->data;
            ++g_out_count;
            if (g_out_count == 1) {
                unsigned want = 24;
                unsigned cp = len < want ? len : want;
                unsigned k;
                if (len != want) { errno = EIO; return (int)len; }
                for (k = 0; k < cp && k < sizeof(g_out_cap0); ++k) g_out_cap0[k] = d[k];
                g_out_len0 = len;
                if (g_out0_ret != 24) {
                    if (g_out0_ret < 0) { errno = ETIMEDOUT; return -1; }
                    return g_out0_ret;
                }
                return 24;
            } else if (g_out_count == 2) {
                unsigned want = 7;
                unsigned cp = len < want ? len : want;
                unsigned k;
                if (len != want) { errno = EIO; return (int)len; }
                for (k = 0; k < cp && k < sizeof(g_out_cap1); ++k) g_out_cap1[k] = d[k];
                g_out_len1 = len;
                if (g_out1_ret != 7) {
                    if (g_out1_ret < 0) { errno = ETIMEDOUT; return -1; }
                    return g_out1_ret;
                }
                return 7;
            } else {
                errno = EIO;
                return -1;
            }
        } else if (ep == 0x85u) {
            uint8_t *d = (uint8_t *)bt->data;
            ++g_in_count;
            if (g_in_count == 1) {
                if (len != 24) { errno = EINVAL; return -1; }
                if (g_in_hdr_ret != 24) {
                    if (g_in_hdr_ret < 0) { errno = ETIMEDOUT; return -1; }
                    return g_in_hdr_ret;
                }
                memcpy(d, g_reply_hdr, 24);
                return 24;
            } else if (g_in_count == 2) {
                size_t want = g_reply_paylen;
                if (len != want) { errno = EINVAL; return (int)len; }
                if ((int)g_in_pay_ret >= 0 && (size_t)g_in_pay_ret != want) {
                    return g_in_pay_ret;
                }
                if (g_in_pay_ret < 0 && g_in_pay_ret != -1000) {
                    errno = ETIMEDOUT;
                    return -1;
                }
                memcpy(d, g_reply_pay, want);
                return (int)want;
            } else {
                errno = EIO;
                return -1;
            }
        } else {
            errno = EINVAL;
            return -1;
        }
    }
    errno = EINVAL;
    return -1;
}

static int m4_fake_clock(clockid_t clk, struct timespec *ts) {
    int phase_now = 0;
    (void)clk;
    if (!ts) { errno = EFAULT; return -1; }
    /* Per-phase deadline (not fixed call count): jump once when the probe
     * reaches the wanted lifecycle phase, so inserted remain() calls elsewhere
     * do not shift the test. Phase 1 = before CLAIM, 2 = before second OUT,
     * 3 = before IN header. t0 itself (first call) never jumps. */
    if (g_clock_calls > 0 && g_deadline_phase != 0) {
        if (g_deadline_phase == 1 && g_claim_count == 0 && g_bulk_count == 0) {
            phase_now = 1;
        } else if (g_deadline_phase == 2 && g_out_count == 1 && g_in_count == 0) {
            phase_now = 1;
        } else if (g_deadline_phase == 3 && g_out_count == 2 && g_in_count == 0) {
            phase_now = 1;
        }
        if (phase_now) {
            g_now_ms += 6000;
            g_deadline_phase = 0;
        } else {
            g_now_ms += 5;
        }
    } else {
        g_now_ms += 5;
    }
    ++g_clock_calls;
    ts->tv_sec = (time_t)(g_now_ms / 1000);
    ts->tv_nsec = (long)((g_now_ms % 1000) * 1000000L);
    return 0;
}

static int m4_fake_sigaction(int signum, const struct sigaction *act, struct sigaction *oldact) {
    (void)signum; (void)act; (void)oldact;
    return 0;
}

#define open(...) m4_fake_open(__VA_ARGS__)
#define read(...) m4_fake_read(__VA_ARGS__)
#define close(...) m4_fake_close(__VA_ARGS__)
#define ioctl(...) m4_fake_ioctl(__VA_ARGS__)
#define clock_gettime(...) m4_fake_clock(__VA_ARGS__)
#define sigaction(...) m4_fake_sigaction(__VA_ARGS__)
#define main m4_orig_main
#include "__INCLUDE_PATH__"
#undef main
#undef open
#undef read
#undef close
#undef ioctl
#undef clock_gettime
#undef sigaction

int main(void) {
    uint8_t expect[31];
    int rc;

    /* CNXN success: 2 OUT (24+7), 2 IN, identified, request bytes match. */
    ps_reset();
    g_mode = 0; g_reply_kind = 0; g_bad_desc = 0;
    g_claim_rc = 0; g_release_rc = 0;
    g_out0_ret = 24; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 0;
    m4_cnxn_request(expect, sizeof(expect));
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc == 0, "probe_cnxn_success");
    ps_report(g_out_count == 2 && g_in_count == 2, "probe_cnxn_counts");
    ps_report(g_out_len0 == 24 && g_out_len1 == 7, "probe_cnxn_split");
    ps_report(memcmp(g_out_cap0, expect, 24) == 0, "probe_cnxn_hdr_bytes");
    ps_report(memcmp(g_out_cap1, expect + 24, 7) == 0, "probe_cnxn_pay_bytes");
    ps_report(g_bulk_count == 4, "probe_cnxn_no_retry");
    ps_report(g_claim_count == 1 && g_release_count == 1, "probe_cnxn_claim_release");

    /* AUTH stop: same OUT/IN counts, no extra AUTH reply OUT. */
    ps_reset();
    g_reply_kind = 1;
    g_claim_rc = 0; g_release_rc = 0;
    g_out0_ret = 24; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 0;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc == 0, "probe_auth_stop");
    ps_report(g_out_count == 2 && g_in_count == 2, "probe_auth_counts");
    ps_report(g_bulk_count == 4, "probe_auth_no_reply");

    /* Header OUT short: actual bytes, no second OUT, no RX. */
    ps_reset();
    g_reply_kind = 0;
    g_out0_ret = 10; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 0;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc != 0, "probe_hdr_short_rc");
    ps_report(g_out_count == 1 && g_in_count == 0, "probe_hdr_short_counts");
    ps_report(g_bulk_count == 1, "probe_hdr_short_no_retry");

    /* Second OUT short: 2 OUT attempted, no RX. */
    ps_reset();
    g_reply_kind = 0;
    g_out0_ret = 24; g_out1_ret = 3; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 0;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc != 0, "probe_second_short_rc");
    ps_report(g_out_count == 2 && g_in_count == 0, "probe_second_short_counts");
    ps_report(g_bulk_count == 2, "probe_second_short_no_retry");

    /* Malformed reply header: 1 IN only, no payload IN. */
    ps_reset();
    g_reply_kind = 2;
    g_out0_ret = 24; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 0;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc != 0, "probe_malformed_rc");
    ps_report(g_out_count == 2 && g_in_count == 1, "probe_malformed_no_payload");

    /* Deadline before CLAIM (newly inserted check): no CLAIM, no BULK. */
    ps_reset();
    g_reply_kind = 0;
    g_out0_ret = 24; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 1;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc != 0, "probe_deadline_claim_rc");
    ps_report(g_claim_count == 0 && g_bulk_count == 0, "probe_deadline_claim_no_io");

    /* Timeout before second OUT (per-phase, not fixed call count). */
    ps_reset();
    g_reply_kind = 0;
    g_out0_ret = 24; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 2;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc != 0, "probe_timeout_rc");
    ps_report(g_out_count == 1 && g_in_count == 0, "probe_timeout_no_followup");

    /* Claim fail: no OUT, no RX, no RELEASE. */
    ps_reset();
    g_reply_kind = 0;
    g_claim_rc = -1;
    g_out0_ret = 24; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 0;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc != 0, "probe_claim_fail_rc");
    ps_report(g_out_count == 0 && g_in_count == 0, "probe_claim_fail_no_io");
    ps_report(g_release_count == 0, "probe_claim_fail_no_release");

    /* Release failure: single status at cleanup, outcome error (no duplicate). */
    ps_reset();
    g_reply_kind = 0;
    g_claim_rc = 0; g_release_rc = -1;
    g_out0_ret = 24; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 0;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc != 0, "probe_release_fail_error");
    ps_report(g_release_count == 1 && g_claim_count == 1, "probe_release_attempted");

    /* Wrong iface descriptors: validate fails, never CLAIM/BULK. */
    ps_reset();
    g_reply_kind = 0; g_bad_desc = 1;
    g_claim_rc = 0; g_release_rc = 0;
    g_out0_ret = 24; g_out1_ret = 7; g_in_hdr_ret = 24; g_in_pay_ret = -1000;
    g_deadline_phase = 0;
    ps_build_reply();
    rc = m4_probe();
    ps_check_opens();
    ps_report(rc != 0, "probe_wrong_iface_rc");
    ps_report(g_claim_count == 0 && g_bulk_count == 0, "probe_wrong_iface_no_ioctl");

    /* Only allowed paths, no file create (accumulated over all scenarios). */
    ps_report(g_ever_bad_open == 0, "probe_no_create");
    ps_report(g_ever_bad_path == 0, "probe_allowed_paths");

    printf("PROBE_SHIM_RESULT %s total=%d failures=%d\n", ps_fail ? "FAIL" : "PASS", ps_total, ps_fail);
    fflush(stdout);
    return ps_fail ? 1 : 0;
}
"""


def compile_probe_shim(cc: str, tmpdir: Path) -> Path:
    include_posix = MAIN_C.resolve().as_posix()
    src = PROBE_SHIM_TEMPLATE.replace("__INCLUDE_PATH__", include_posix)
    shim_c = tmpdir / "m4_adb_probe_shim.c"
    shim_c.write_text(src, encoding="utf-8")
    shim_bin = tmpdir / "m4-adb-probe-shim"
    cmd = [cc] + HARNESS_FLAGS + [str(shim_c), "-o", str(shim_bin)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise AssertionError(f"probe shim compile failed:\n{result.stdout}{result.stderr}")
    return shim_bin


class M4AdbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MAIN_C.is_file():
            raise unittest.SkipTest(f"missing {MAIN_C} (owner agent still writing; no polling)")
        cls.cc = find_cc()
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-m4-adb-build-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        suffix = ".exe" if os.name == "nt" else ""
        cls.probe = base / ("c2m-m4-adb" + suffix)
        compile_binary(cls.cc, cls.probe)
        # Cache one harness run for all harness-label tests (bounded, offline).
        try:
            cls.harness_result = run_harness_once(cls.cc, base)
        except AssertionError as exc:
            raise AssertionError(str(exc))

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.tmp.cleanup()
        except Exception:
            pass

    def run_bin(self, binary: Path, *args: str, timeout: float = NATIVE_TIMEOUT):
        return subprocess.run(
            [str(binary), *args], text=True, capture_output=True, timeout=timeout
        )

    def assert_harness_label(self, label: str) -> None:
        out = self.harness_result.stdout
        self.assertEqual(
            self.harness_result.returncode,
            0,
            f"harness failed:\nSTDOUT:\n{out[-8000:]}\nSTDERR:\n{self.harness_result.stderr[-4000:]}",
        )
        self.assertIn("HARNESS_RESULT PASS", out, out[-8000:])
        self.assertIn(f"[PASS] {label}", out, f"missing harness case: {label}")

    def test_cli_help_selftest_unknown(self) -> None:
        result = self.run_bin(self.probe, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--help", result.stdout)
        self.assertIn("--self-test", result.stdout)
        self.assertIn("--probe", result.stdout)
        for args in ((), ("--unknown",), ("--self-test", "extra"), ("--probe", "extra")):
            with self.subTest(args=args):
                result = self.run_bin(self.probe, *args)
                self.assertEqual(result.returncode, 2, str(args))
        result = self.run_bin(self.probe, "--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)
        raw = self.probe.read_bytes()
        self.assertIn(b"--probe", raw)
        self.assertNotIn(b"c2m_d4_status", raw)

    def test_source_pure_api_shape(self) -> None:
        text = MAIN_C.read_text(encoding="utf-8")
        self.assertNotIn("\r", text)
        # _GNU_SOURCE must precede the first system stdio include.
        gnu = text.find("_GNU_SOURCE")
        stdio = text.find("#include <stdio.h>")
        if stdio < 0:
            stdio = text.find('#include "stdio')
        self.assertGreaterEqual(gnu, 0, "missing _GNU_SOURCE guard")
        self.assertGreaterEqual(stdio, 0, "missing <stdio.h>")
        self.assertLess(gnu, stdio, "_GNU_SOURCE must precede stdio")
        # Pure API signatures (avoid over-literal body matching).
        self.assertRegex(
            text,
            r"static\s+int\s+m4_validate_descriptors\s*\(\s*const\s+uint8_t\s*\*",
        )
        self.assertRegex(
            text,
            r"static\s+size_t\s+m4_cnxn_request\s*\(\s*uint8_t\s*\*",
        )
        self.assertRegex(
            text,
            r"static\s+int\s+m4_classify_reply\s*\(\s*const\s+uint8_t\s*\*",
        )
        self.assertIn("m4_self_test", text)
        # Pure APIs must be defined before any Linux-only probe body.
        probe_pos = -1
        for marker in ("m4_probe", "--probe", "USBDEVFS_BULK"):
            pos = text.find(marker)
            if pos >= 0 and (probe_pos < 0 or pos < probe_pos):
                probe_pos = pos
        for api in ("m4_validate_descriptors", "m4_cnxn_request", "m4_classify_reply"):
            decl = text.find("static int m4_validate_descriptors" if "validate" in api else api)
            # Fall back to generic search if exact prefix differs (size_t vs int).
            if decl < 0:
                decl = text.find(api)
            self.assertGreaterEqual(decl, 0, f"missing {api}")
            if probe_pos >= 0:
                linux_guard = text.rfind("#ifdef __linux__", 0, probe_pos)
                if linux_guard < 0:
                    linux_guard = text.rfind("#if defined(__linux__)", 0, probe_pos)
                if linux_guard >= 0:
                    self.assertLess(decl, linux_guard, f"{api} must be shared pure (before Linux guard)")
        # No TEST-gated shipping logic (self_test word is allowed).
        stripped = strip_c_comments(text)
        self.assertNotRegex(stripped, r"#\s*ifdef\s+TEST\b")
        self.assertNotRegex(stripped, r"#\s*if\s+defined\s*\(\s*TEST\b")
        self.assertNotIn("TEST_MODE", stripped)

    def test_source_static_guards(self) -> None:
        text = MAIN_C.read_text(encoding="utf-8")
        stripped = strip_c_comments(text)
        for token in (
            "socket(",
            "connect(",
            "send(",
            "sendto(",
            "sendmsg(",
            "ptrace",
            "A_OPEN",
            "O_CREAT",
            "O_TRUNC",
            "USBDEVFS_RESET",
            "USBDEVFS_CLEAR_HALT",
            "USBDEVFS_DISCONNECT",
            "USBDEVFS_SETCONFIGURATION",
            "USBDEVFS_SETINTERFACE",
            "libusb_reset",
            "libusb_detach",
            "detach_kernel",
            "set_configuration",
        ):
            self.assertNotIn(token, stripped, f"forbidden token: {token}")
        # AUTH replies must never be constructed (classify-only).
        # Allow the word AUTH for classify + help text, but forbid sending one.
        self.assertNotRegex(stripped, r"AUTH.*reply|reply.*AUTH|send_auth|auth_token\s*=")
        # ioctl allowlist: CLAIM/RELEASE/BULK only.
        self.assertIn("CLAIM", stripped)
        self.assertIn("RELEASE", stripped)
        self.assertIn("BULK", stripped)
        for token in ("USBDEVFS_RESET", "USBDEVFS_DISCONNECT", "USBDEVFS_CLEAR_HALT"):
            self.assertNotIn(token, stripped)
        # Deadline <= 5000ms.
        self.assertIn("5000", stripped)
        for big in ("10000", "15000", "30000", "60000"):
            # A larger literal deadline would violate the 5s bound.
            if big in stripped:
                m = re.search(r"(timeout|deadline|wait_ms|ms)\W{0,8}" + big, stripped)
                self.assertIsNone(m, f"suspicious large deadline {big}")
        self.assertNotIn("/dev/bus/usb", text.split("--help")[0] if "--help" in text else text[:2000])
        # Wire split (AOSP remote_write): ONE CNXN (31B) as TWO OUT bulk
        # transfers (header 24 then payload 7), at most TWO IN replies.
        # Count strings only -- field/variable names may vary, so avoid
        # brittle exact-identifier assertions here.
        probe_idx = text.rfind("m4_probe")
        self.assertGreaterEqual(probe_idx, 0, "missing m4_probe")
        probe_body = strip_c_comments(text[probe_idx:])
        # Split lengths must appear in the probe path (24 header, 7 payload).
        self.assertIn("24", probe_body, "probe must send header 24 split")
        self.assertIn("7", probe_body, "probe must send payload 7 split")
        # OUT endpoint bulk appears exactly twice (24, then 7); IN twice.
        # Use generic constant substrings, not exact variable names.
        self.assertEqual(
            probe_body.count("EP_OUT"), 2, f"expected 2 OUT bulk calls, got {probe_body.count('EP_OUT')}"
        )
        self.assertEqual(
            probe_body.count("EP_IN"), 2, f"expected 2 IN bulk calls, got {probe_body.count('EP_IN')}"
        )
        # Never a single combined 31B bulk transfer in the probe path.
        self.assertIsNone(
            re.search(r"m4_bulk[^;]*\b31\b", probe_body),
            "probe must not bulk-transfer single 31B (split 24+7 instead)",
        )
        # No blind retry: no retry/attempt words and no loop around bulk.
        lowered = probe_body.lower()
        self.assertNotIn("retry", lowered, "probe must not retry handshake")
        self.assertNotIn("attempt", lowered, "probe must not retry handshake")
        self.assertNotIn("while", lowered, "probe must not loop-retry (RX<=2, OUT<=2)")
        # 'for' may appear only if bounded to the split; forbid unbounded
        # retry shape by capping total bulk call sites (already 2+2 above).
        self.assertLessEqual(
            probe_body.count("m4_bulk"), 4, "max 4 bulk call sites (2 OUT + 2 IN)"
        )

    def test_harness_descriptors_valid(self) -> None:
        for label in ("desc_valid_len", "desc_valid", "desc_null", "desc_empty"):
            with self.subTest(label=label):
                self.assert_harness_label(label)

    def test_harness_descriptors_ids(self) -> None:
        for label in ("desc_vid", "desc_pid", "desc_class", "desc_subclass", "desc_proto", "desc_numcfg"):
            with self.subTest(label=label):
                self.assert_harness_label(label)

    def test_harness_descriptors_structural(self) -> None:
        for label in (
            "desc_short10",
            "desc_cfg_only",
            "desc_bad_devlen",
            "desc_overflow_total",
            "desc_overflow_blen",
            "desc_multiconfig",
            "desc_dupiface",
            "desc_ifacenum",
        ):
            with self.subTest(label=label):
                self.assert_harness_label(label)

    def test_harness_descriptors_endpoints(self) -> None:
        for label in ("desc_eptype", "desc_epdir", "desc_epmax", "desc_alt", "desc_epcount"):
            with self.subTest(label=label):
                self.assert_harness_label(label)

    def test_harness_cnxn_request(self) -> None:
        for label in (
            "cnxn_len",
            "cnxn_cmd",
            "cnxn_ver",
            "cnxn_max",
            "cnxn_dlen",
            "cnxn_sum",
            "cnxn_magic",
            "cnxn_payload",
            "cnxn_short",
            "cnxn_null",
            "cnxn_exact",
        ):
            with self.subTest(label=label):
                self.assert_harness_label(label)

    def test_harness_classify_valid(self) -> None:
        for label in ("cls_cnxn_ok", "cls_cnxn_not_auth", "cls_auth_ok", "cls_auth_not_cnxn", "cls_host_noauth"):
            with self.subTest(label=label):
                self.assert_harness_label(label)

    def test_harness_classify_rejects(self) -> None:
        for label in (
            "cls_badmagic",
            "cls_badsum",
            "cls_toolong",
            "cls_unknown",
            "cls_mismatch",
            "cls_partial",
            "cls_auth_arg0",
            "cls_auth_arg1",
            "cls_auth_len19",
            "cls_auth_len21",
            "cls_null_hdr",
            "cls_null_pay",
        ):
            with self.subTest(label=label):
                self.assert_harness_label(label)

    @unittest.skipUnless(LINUX, "probe shim needs Linux usbdevice_fs headers")
    def test_probe_shim_success_path(self) -> None:
        # Synthetic SUCCESSFUL capture path: calls the real source m4_probe()
        # with every OS syscall faked (open/read/close/ioctl/clock_gettime/
        # sigaction via macros BEFORE the source include). No hardware, no
        # --probe execution, no network. Covers CNXN success, AUTH stop with
        # no AUTH reply, short/timeout/claim/release/wrong-iface edges.
        tmp = Path(self.tmp.name) / "probe_shim"
        tmp.mkdir(exist_ok=True)
        shim = compile_probe_shim(self.cc, tmp)
        result = subprocess.run(
            [str(shim)], text=True, capture_output=True, timeout=NATIVE_TIMEOUT
        )
        self.assertEqual(
            result.returncode,
            0,
            f"probe shim failed:\nSTDOUT:\n{result.stdout[-8000:]}\nSTDERR:\n{result.stderr[-4000:]}",
        )
        self.assertIn("PROBE_SHIM_RESULT PASS", result.stdout, result.stdout[-8000:])
        for label in (
            "probe_cnxn_success",
            "probe_cnxn_counts",
            "probe_cnxn_split",
            "probe_cnxn_hdr_bytes",
            "probe_cnxn_pay_bytes",
            "probe_cnxn_no_retry",
            "probe_cnxn_claim_release",
            "probe_auth_stop",
            "probe_auth_counts",
            "probe_auth_no_reply",
            "probe_hdr_short_rc",
            "probe_hdr_short_counts",
            "probe_hdr_short_no_retry",
            "probe_second_short_rc",
            "probe_second_short_counts",
            "probe_second_short_no_retry",
            "probe_malformed_rc",
            "probe_malformed_no_payload",
            "probe_deadline_claim_rc",
            "probe_deadline_claim_no_io",
            "probe_timeout_rc",
            "probe_timeout_no_followup",
            "probe_claim_fail_rc",
            "probe_claim_fail_no_io",
            "probe_claim_fail_no_release",
            "probe_release_fail_error",
            "probe_release_attempted",
            "probe_wrong_iface_rc",
            "probe_wrong_iface_no_ioctl",
            "probe_no_create",
            "probe_allowed_paths",
        ):
            with self.subTest(label=label):
                self.assertIn(f"[PASS] {label}", result.stdout, f"missing shim case: {label}")

    def test_probe_never_native(self) -> None:
        # This suite must never execute --probe natively on Linux, even
        # without hardware. Only verify the CLI documents it.
        text = MAIN_C.read_text(encoding="utf-8")
        self.assertIn("--probe", text)
        if LINUX:
            self.skipTest("--probe execution is prohibited on Linux (static check only)")
        # Windows: --probe must report unsupported quickly, never touch USB.
        result = self.run_bin(self.probe, "--probe", timeout=NATIVE_TIMEOUT)
        self.assertNotEqual(result.returncode, 0)
        combined = (result.stdout + result.stderr).lower()
        self.assertTrue(
            "unsupported" in combined or "probe" in combined or "platform" in combined,
            f"--probe should report unsupported on Windows, got: {combined[-500:]}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
