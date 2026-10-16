#!/usr/bin/env python3
"""Host guards for M4 ADB authorize (fw/m4_adb/m4_adb_authorize.c).
Synthetic-only. No camera/USB hardware/network/real /dev/bus/usb paths.
One CNXN then one RSAPUBLICKEY auth UI request; no AUTH signature/shell/
service/bypass. Portable --help/--self-test/--request-authorization checks
run on Windows+Linux. Pure pubkey APIs via compiled C harness (no TEST-only
logic). --request-authorization is NEVER executed natively on Linux (not even
without hardware); on Windows it must report unsupported. Linux-only include
shim fakes every OS syscall (open/read/close/ioctl/clock_gettime/sigaction via
macros BEFORE source include, real headers first, fake stdin feeds 711B key)
and calls real m4_authorize() (fallback m4_probe).
Pure APIs (plain C, before Linux-only body):
  static int m4_auth_pubkey_valid(const uint8_t *, size_t) -> 0/-1
  static size_t m4_auth_pubkey_frame(uint8_t *, size_t, const uint8_t *, size_t) -> 735
Fixed payload 711 = 700 base64 of 524B ANDROID pubkey (LE: len 64, n0inv,
modulus 256, rr 256, exp 65537) + space + 'c2m-owner'(9) + NUL. Frame AUTH
arg0=3 arg1=0 len 711. Wire: CNXN 31B (24+7) then RSAPUB 735B (24+711): max
4 OUT totalling 766B, max 4 IN, single blocking IN header after pubkey
(30s/35000ms, no poll retry); AUTH reply after RSAPUB stops, no signature.
"""
from __future__ import annotations
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "fw" / "m4_adb" / "m4_adb_authorize.c"
FLAGS = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
HARNESS_FLAGS = FLAGS + ["-Wno-unused-function"]
LINUX = sys.platform.startswith("linux")
NATIVE_TIMEOUT = 15.0


def find_cc() -> str:
    for name in (os.environ.get("CC", "gcc"), "cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    raise unittest.SkipTest("host C compiler not available")


def compile_binary(cc: str, output: Path) -> None:
    cmd = [cc] + FLAGS + [str(MAIN_C.relative_to(ROOT)), "-o", str(output)]
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if r.returncode:
        raise AssertionError(f"compile failed:\n{r.stdout}{r.stderr}")


def strip_c_comments(src: str) -> str:
    out: list[str] = []
    i, n = 0, len(src)
    sl = bl = st = ch = False
    while i < n:
        c, nx = src[i], src[i + 1] if i + 1 < n else ""
        if sl:
            if c == "\n":
                sl = False
                out.append(c)
            i += 1
            continue
        if bl:
            if c == "*" and nx == "/":
                bl = False
                i += 2
            else:
                if c == "\n":
                    out.append("\n")
                i += 1
            continue
        if st:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == '"':
                st = False
            i += 1
            continue
        if ch:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == "'":
                ch = False
            i += 1
            continue
        if c == "/" and nx == "/":
            sl = True
            i += 2
            continue
        if c == "/" and nx == "*":
            bl = True
            i += 2
            continue
        if c == '"':
            st = True
        if c == "'":
            ch = True
        out.append(c)
        i += 1
    return "".join(out)


HARNESS_TEMPLATE = r"""
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
static int h_fail = 0, h_total = 0;
static void h_rep(int ok, const char *n) {
    ++h_total;
    printf(ok ? "[PASS] %s\n" : "[FAIL] %s\n", n);
    if (!ok) ++h_fail;
    fflush(stdout);
}
static void h_p32(uint8_t *b, uint32_t v) {
    b[0] = (uint8_t)(v & 0xFFu); b[1] = (uint8_t)((v >> 8) & 0xFFu);
    b[2] = (uint8_t)((v >> 16) & 0xFFu); b[3] = (uint8_t)((v >> 24) & 0xFFu);
}
static uint32_t h_g32(const uint8_t *b) {
    return (uint32_t)b[0] | ((uint32_t)b[1] << 8) |
        ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}
static uint32_t h_sum(const uint8_t *p, size_t n) {
    uint32_t s = 0; size_t i; for (i = 0; i < n; ++i) s += p[i]; return s;
}
static void h_b64(const uint8_t *in, size_t n, char *o) {
    static const char t[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i = 0, k = 0;
    while (i + 3 <= n) {
        uint32_t v = ((uint32_t)in[i] << 16) | ((uint32_t)in[i+1] << 8) | in[i+2];
        o[k++] = t[(v >> 18) & 63]; o[k++] = t[(v >> 12) & 63];
        o[k++] = t[(v >> 6) & 63]; o[k++] = t[v & 63]; i += 3;
    }
    if (i + 2 == n) {
        uint32_t v = ((uint32_t)in[i] << 16) | ((uint32_t)in[i+1] << 8);
        o[k++] = t[(v >> 18) & 63]; o[k++] = t[(v >> 12) & 63];
        o[k++] = t[(v >> 6) & 63]; o[k++] = '='; /* 524 % 3 == 2 */
    } else if (i + 1 == n) {
        uint32_t v = ((uint32_t)in[i] << 16);
        o[k++] = t[(v >> 18) & 63]; o[k++] = t[(v >> 12) & 63];
        o[k++] = '='; o[k++] = '=';
    }
    o[k] = 0;
}
/* Synthetic 524B: len 64, n0inv 1, modulus all-FF, rr 1, exp 65537 (N=2^2048-1 so R=RR=1). */
static void h_raw(uint8_t *r, int mod, int exp, int inv, int lenf, int top) {
    memset(r, 0, 524);
    h_p32(r + 0, lenf ? 63u : 64u);
    h_p32(r + 4, inv ? 2u : 1u);
    memset(r + 8, 0xFF, 256);
    if (mod == 1) r[8] = 0xFEu;          /* even modulus[0] */
    if (mod == 2) r[8 + 255] = 0x7Fu;    /* top bit clear */
    if (top) r[8 + 255] = 0x7Fu;
    h_p32(r + 264, 1u);                  /* rr = 1 */
    h_p32(r + 520, exp ? 3u : 65537u);
}
static size_t h_key(char *k, int mod, int exp, int inv, int lenf, int top) {
    uint8_t r[524]; char b[704];
    h_raw(r, mod, exp, inv, lenf, top);
    h_b64(r, 524, b);                    /* 700 chars incl one '=' */
    memcpy(k, b, 700);
    k[700] = ' '; memcpy(k + 701, "c2m-owner", 9); k[710] = 0;
    return 711;
}
int main(void) {
    char k[720]; uint8_t fr[800]; size_t n;
    h_rep(h_key(k, 0, 0, 0, 0, 0) == 711, "pub_build711");
    h_rep(strlen(k) == 710 && k[700] == ' ' && k[710] == 0, "pub_layout");
    h_rep(memcmp(k + 701, "c2m-owner", 9) == 0, "pub_user");
    h_rep(m4_auth_pubkey_valid((uint8_t *)k, 711) == 0, "pub_valid");
    h_rep(m4_auth_pubkey_valid(NULL, 711) == -1, "pub_null");
    h_rep(m4_auth_pubkey_valid((uint8_t *)k, 710) == -1, "pub_short");
    h_rep(m4_auth_pubkey_valid((uint8_t *)k, 712) == -1, "pub_toolong");
    { char w[720]; memcpy(w, k, 711); w[0] = '#'; h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_comment"); }
    { char w[720]; memcpy(w, k, 711); w[710] = 'X'; h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_eof"); }
    { char w[720]; memcpy(w, k, 711); w[10] = (char)0x80; h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_nonascii"); }
    { char w[720]; memcpy(w, k, 711); w[5] = '!'; h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_b64char"); }
    { char w[720]; memcpy(w, k, 711); w[699] = 'A'; h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_b64pad"); }
    { char w[720]; memcpy(w, k, 711); w[700] = 'X'; h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_nospace"); }
    { char w[720]; memcpy(w, k, 711); memcpy(w + 701, "evil-user", 9); h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_baduser"); }
    { char w[720]; h_key(w, 0, 0, 0, 1, 0); h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_badlenfield"); }
    { char w[720]; h_key(w, 1, 0, 0, 0, 0); h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_modeven"); }
    { char w[720]; h_key(w, 0, 0, 0, 0, 1); h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_topbit"); }
    { char w[720]; h_key(w, 0, 1, 0, 0, 0); h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_exponent"); }
    { char w[720]; h_key(w, 0, 0, 1, 0, 0); h_rep(m4_auth_pubkey_valid((uint8_t *)w, 711) == -1, "pub_n0inv"); }
    n = m4_auth_pubkey_frame(fr, sizeof(fr), (uint8_t *)k, 711);
    h_rep(n == 735, "frame_len735");
    if (n == 735) {
        h_rep(h_g32(fr + 0) == 0x48545541u, "frame_cmd_auth");
        h_rep(h_g32(fr + 4) == 3u, "frame_arg0_3");
        h_rep(h_g32(fr + 8) == 0u, "frame_arg1_0");
        h_rep(h_g32(fr + 12) == 711u, "frame_dlen711");
        h_rep(h_g32(fr + 16) == h_sum((uint8_t *)k, 711), "frame_sum");
        h_rep(h_g32(fr + 20) == (0x48545541u ^ 0xFFFFFFFFu), "frame_magic");
        h_rep(memcmp(fr + 24, k, 711) == 0, "frame_payload");
    } else {
        h_rep(0, "frame_cmd_auth"); h_rep(0, "frame_arg0_3"); h_rep(0, "frame_arg1_0");
        h_rep(0, "frame_dlen711"); h_rep(0, "frame_sum"); h_rep(0, "frame_magic");
        h_rep(0, "frame_payload");
    }
    h_rep(m4_auth_pubkey_frame(fr, 734, (uint8_t *)k, 711) != 735, "frame_short");
    h_rep(m4_auth_pubkey_frame(NULL, 735, (uint8_t *)k, 711) != 735, "frame_null");
    h_rep(m4_auth_pubkey_frame(fr, sizeof(fr), NULL, 711) != 735, "frame_nullkey");
    { char w[720]; memcpy(w, k, 711); w[5] = '!'; h_rep(m4_auth_pubkey_frame(fr, sizeof(fr), (uint8_t *)w, 711) != 735, "frame_badkey"); }
    printf("HARNESS_RESULT %s total=%d failures=%d\n", h_fail ? "FAIL" : "PASS", h_total, h_fail);
    return h_fail ? 1 : 0;
}
"""


def compile_harness(cc: str, tmpdir: Path) -> Path:
    src = HARNESS_TEMPLATE.replace("__INCLUDE_PATH__", MAIN_C.resolve().as_posix())
    c = tmpdir / "m4_auth_harness.c"
    c.write_text(src, encoding="utf-8")
    b = tmpdir / ("m4-auth-harness" + (".exe" if os.name == "nt" else ""))
    r = subprocess.run([cc] + HARNESS_FLAGS + [str(c), "-o", str(b)],
                       cwd=ROOT, text=True, capture_output=True, timeout=90)
    if r.returncode:
        raise AssertionError(f"harness compile failed:\n{r.stdout}{r.stderr}")
    return b


AUTH_SHIM_TEMPLATE = r"""
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
static int q_fail = 0, q_total = 0;
static void q_rep(int ok, const char *n) {
    ++q_total; printf(ok ? "[PASS] %s\n" : "[FAIL] %s\n", n);
    if (!ok) ++q_fail; fflush(stdout);
}
static void q_p32(uint8_t *b, uint32_t v) {
    b[0] = (uint8_t)(v & 0xFFu); b[1] = (uint8_t)((v >> 8) & 0xFFu);
    b[2] = (uint8_t)((v >> 16) & 0xFFu); b[3] = (uint8_t)((v >> 24) & 0xFFu);
}
static uint32_t q_g32(const uint8_t *b) {
    return (uint32_t)b[0] | ((uint32_t)b[1] << 8) |
        ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}
static uint32_t q_sum(const uint8_t *p, size_t n) {
    uint32_t s = 0; size_t i; for (i = 0; i < n; ++i) s += p[i]; return s;
}
static int g_mode = 0;          /* 0 ok(AUTH->CNXN) 1 auth-again 2 timeout 3 badkey */
static int g_claim_rc = 0, g_release_rc = 0;
static int g_out0_ret = 24, g_out1_ret = 7, g_out2_ret = 24, g_out3_ret = 711;
static int g_final_timeout = 0, g_deadline_phase = 0;
static long g_now_ms = 0; static int g_clock_calls = 0;
static int g_open_count = 0, g_bad_open = 0, g_claim_count = 0, g_release_count = 0;
static int g_bulk_count = 0, g_out_count = 0, g_in_count = 0;
static unsigned g_out_bytes = 0; static unsigned g_out_lens[6];
static int g_saw_sig = 0, g_bad_path = 0;
static char g_open_paths[12][96];
static int g_next_fd = 100, g_vfd = -1, g_pfd = -1, g_bfd = -1, g_dfd = -1, g_ufd = -1;
static uint8_t g_key[711]; static size_t g_key_off = 0;
static uint8_t g_h1[24], g_p1[64]; static size_t g_p1len = 0;
static uint8_t g_h2[24], g_p2[64]; static size_t g_p2len = 0;
static const uint8_t GOOD[50] = {
    18, 1, 0x00, 0x02, 0, 0, 0, 64, 0x07, 0x22, 0x13, 0x00, 0x00, 0x01, 1, 2, 3, 1,
    9, 2, 0x20, 0x00, 1, 1, 0, 0x80, 250,
    9, 4, 2, 0, 2, 0xFF, 0x42, 0x01, 0,
    7, 5, 0x04, 0x02, 0x00, 0x02, 0, 7, 5, 0x85, 0x02, 0x00, 0x02, 0 };
static void q_build_key(void); /* defined after source include: uses m4_selftest_key */
static void q_build_replies(void) {
    size_t k;
    if (g_mode == 3) { g_p1len = 0; g_p2len = 0; return; }
    for (k = 0; k < 20; ++k) g_p1[k] = (uint8_t)(k + 7);
    g_p1len = 20;
    q_p32(g_h1, 0x48545541u); q_p32(g_h1 + 4, 1); q_p32(g_h1 + 8, 0);
    q_p32(g_h1 + 12, 20); q_p32(g_h1 + 16, q_sum(g_p1, 20));
    q_p32(g_h1 + 20, 0x48545541u ^ 0xFFFFFFFFu);
    if (g_mode == 1) {
        for (k = 0; k < 20; ++k) g_p2[k] = (uint8_t)(k + 31);
        g_p2len = 20;
        q_p32(g_h2, 0x48545541u); q_p32(g_h2 + 4, 1); q_p32(g_h2 + 8, 0);
        q_p32(g_h2 + 12, 20); q_p32(g_h2 + 16, q_sum(g_p2, 20));
        q_p32(g_h2 + 20, 0x48545541u ^ 0xFFFFFFFFu);
    } else {
        memcpy(g_p2, "device::fake-ok\0", 16); g_p2len = 16;
        q_p32(g_h2, 0x4E584E43u); q_p32(g_h2 + 4, 0x01000000u);
        q_p32(g_h2 + 8, 4096); q_p32(g_h2 + 12, 16);
        q_p32(g_h2 + 16, q_sum(g_p2, 16));
        q_p32(g_h2 + 20, 0x4E584E43u ^ 0xFFFFFFFFu);
    }
}
static void q_reset(void) {
    g_open_count = 0; g_bad_open = 0; g_bad_path = 0;
    g_claim_count = 0; g_release_count = 0;
    g_bulk_count = 0; g_out_count = 0; g_in_count = 0; g_out_bytes = 0;
    memset(g_out_lens, 0, sizeof(g_out_lens));
    g_saw_sig = 0; g_next_fd = 100;
    g_vfd = g_pfd = g_bfd = g_dfd = g_ufd = -1;
    g_now_ms = 0; g_clock_calls = 0;
    q_build_key(); q_build_replies();
}
static void q_paths(void) {
    int i;
    if (g_bad_open) g_bad_path = 1;
    for (i = 0; i < g_open_count; ++i) {
        const char *p = g_open_paths[i];
        if (!(strstr(p, "/sys/bus/usb/devices/1-1/") == p || strstr(p, "/dev/bus/usb/") == p)) g_bad_path = 1;
    }
}
static void q_arm(int mode, int r0, int r1, int r2, int r3, int fto, int dl) {
    q_reset(); g_mode = mode; g_claim_rc = 0; g_release_rc = 0;
    g_out0_ret = r0; g_out1_ret = r1; g_out2_ret = r2; g_out3_ret = r3;
    g_final_timeout = fto; g_deadline_phase = dl;
    q_build_key(); q_build_replies();
}
static int m4_fake_open(const char *path, int flags, ...) {
    int fd; size_t L;
    if (!path) { errno = EFAULT; return -1; }
    if (g_open_count >= 12) { errno = EMFILE; return -1; }
    L = strlen(path); if (L >= 96) { errno = ENAMETOOLONG; return -1; }
    strcpy(g_open_paths[g_open_count++], path);
    if ((flags & O_CREAT) || (flags & O_TRUNC)) g_bad_open = 1;
    if ((flags & O_ACCMODE) == O_WRONLY) g_bad_open = 1;
    if (strstr(path, "1-1/idVendor")) { fd = g_next_fd++; g_vfd = fd; return fd; }
    if (strstr(path, "1-1/idProduct")) { fd = g_next_fd++; g_pfd = fd; return fd; }
    if (strstr(path, "1-1/busnum")) { fd = g_next_fd++; g_bfd = fd; return fd; }
    if (strstr(path, "1-1/devnum")) { fd = g_next_fd++; g_dfd = fd; return fd; }
    if (strstr(path, "/dev/bus/usb/") == path) { fd = g_next_fd++; g_ufd = fd; return fd; }
    g_bad_open = 1; errno = ENOENT; return -1;
}
static ssize_t m4_fake_read(int fd, void *buf, size_t count) {
    const char *s = NULL;
    if (!buf || !count) { errno = EINVAL; return -1; }
    if (fd == 0) {
        size_t rem = 711 - g_key_off, cp = rem < count ? rem : count;
        if (!rem) return 0;
        if (count > 64) cp = 64;   /* short stdin chunks, no single 711 read */
        if (cp > rem) cp = rem;
        memcpy(buf, g_key + g_key_off, cp); g_key_off += cp;
        return (ssize_t)cp;
    }
    if (fd == g_vfd) s = "2207\n";
    else if (fd == g_pfd) s = "0013\n";
    else if (fd == g_bfd) s = "001\n"; else if (fd == g_dfd) s = "002\n";
    if (s) { size_t L = strlen(s); if (L > count) L = count; memcpy(buf, s, L); return (ssize_t)L; }
    if (fd == g_ufd) {
        size_t L = sizeof(GOOD); if (L > count) L = count;
        memcpy(buf, GOOD, L); return (ssize_t)L;
    }
    errno = EBADF; return -1;
}
static int m4_fake_close(int fd) { (void)fd; return 0; }
static int m4_fake_ioctl(int fd, unsigned long req, ...) {
    va_list ap; void *arg; va_start(ap, req); arg = va_arg(ap, void *); va_end(ap);
    (void)fd;
    if (req == (unsigned long)USBDEVFS_CLAIMINTERFACE) {
        ++g_claim_count; if (g_claim_rc) { errno = EBUSY; return -1; } return 0;
    }
    if (req == (unsigned long)USBDEVFS_RELEASEINTERFACE) {
        ++g_release_count; if (g_release_rc) { errno = EINVAL; return -1; } return 0;
    }
    if (req == (unsigned long)USBDEVFS_BULK) {
        struct usbdevfs_bulktransfer *bt = arg;
        unsigned ep, len; uint8_t *d;
        static const unsigned want[4] = {24, 7, 24, 711};
        if (!bt) { errno = EFAULT; return -1; }
        ep = bt->ep; len = bt->len; d = bt->data; ++g_bulk_count;
        if (ep == 0x04u) {
            int wantlen, rv;
            if (g_out_count >= 4) { errno = EIO; return -1; }
            wantlen = (int)want[g_out_count];
            if ((int)len != wantlen) { errno = EIO; return (int)len; }
            g_out_lens[g_out_count] = len;
            if (g_out_count == 2) { /* AUTH header: record signature attempts */
                if (q_g32(d) == 0x48545541u && q_g32(d + 4) == 2u) g_saw_sig = 1;
            }
            rv = wantlen;
            if (g_out_count == 0) rv = g_out0_ret; else if (g_out_count == 1) rv = g_out1_ret;
            else if (g_out_count == 2) rv = g_out2_ret; else rv = g_out3_ret;
            ++g_out_count; g_out_bytes += (rv > 0 ? (unsigned)rv : 0);
            if (rv != wantlen) { if (rv < 0) { errno = ETIMEDOUT; return -1; } return rv; }
            return wantlen;
        } else if (ep == 0x85u) {
            ++g_in_count;
            if (g_in_count == 1) {
                if (len != 24) { errno = EINVAL; return -1; }
                memcpy(d, g_h1, 24); return 24;
            } else if (g_in_count == 2) {
                if (len != g_p1len) { errno = EINVAL; return (int)len; }
                memcpy(d, g_p1, g_p1len); return (int)g_p1len;
            } else if (g_in_count == 3) {
                if (len != 24) { errno = EINVAL; return -1; }
                if (g_final_timeout) { errno = ETIMEDOUT; return -1; }
                memcpy(d, g_h2, 24); return 24;
            } else if (g_in_count == 4) {
                if (g_final_timeout) { errno = ETIMEDOUT; return -1; }
                if (len != g_p2len) { errno = EINVAL; return (int)len; }
                memcpy(d, g_p2, g_p2len); return (int)g_p2len;
            }
            errno = EIO; return -1;
        }
        errno = EINVAL; return -1;
    }
    errno = EINVAL; return -1;
}
static int m4_fake_clock(clockid_t c, struct timespec *ts) {
    (void)c; if (!ts) { errno = EFAULT; return -1; }
    if (g_clock_calls > 0 && g_deadline_phase == 1 && g_claim_count == 0 && g_bulk_count == 0) {
        g_now_ms += 40000; g_deadline_phase = 0;
    } else g_now_ms += 5;
    ++g_clock_calls;
    ts->tv_sec = (time_t)(g_now_ms / 1000);
    ts->tv_nsec = (long)((g_now_ms % 1000) * 1000000L);
    return 0;
}
static int m4_fake_sigaction(int s, const struct sigaction *a, struct sigaction *o) {
    (void)s; (void)a; (void)o; return 0;
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
/* Fake-stdin key comes from the source's own synthetic builder: no duplicate B64 here. */
static void q_build_key(void) {
    m4_selftest_key(g_key);
    if (g_mode == 3) g_key[0] = '#';
    g_key_off = 0;
}
int main(void) {
    int rc;
    q_arm(0, 24, 7, 24, 711, 0, 0);
    rc = __CALL__;
    q_paths();
    q_rep(rc == 0, "auth_success");
    q_rep(g_out_count == 4 && g_out_bytes == 766, "auth_counts_4_766");
    q_rep(g_out_lens[0] == 24 && g_out_lens[1] == 7 && g_out_lens[2] == 24 && g_out_lens[3] == 711, "auth_split");
    q_rep(g_in_count >= 3 && g_in_count <= 4, "auth_in_bounded");
    q_rep(!g_saw_sig, "auth_no_signature");
    q_arm(1, 24, 7, 24, 711, 0, 0);
    rc = __CALL__;
    q_paths();
    q_rep(rc == 0, "auth_again_stops");
    q_rep(g_out_count == 4 && !g_saw_sig, "auth_again_no_reply");
    q_arm(0, 24, 7, 24, 711, 1, 0);
    rc = __CALL__;
    q_paths();
    q_rep(rc != 0, "auth_timeout_rc");
    q_rep(g_out_count == 4 && g_in_count <= 3, "auth_timeout_no_ui");
    q_arm(3, 24, 7, 24, 711, 0, 0);
    rc = __CALL__;
    q_paths();
    q_rep(rc != 0, "auth_badkey_rc");
    q_rep(g_bulk_count == 0 && g_claim_count == 0, "auth_badkey_no_usb");
    q_arm(0, 24, 7, 24, 711, 0, 0); g_claim_rc = -1;
    rc = __CALL__;
    q_paths();
    q_rep(rc != 0, "auth_claim_fail_rc");
    q_rep(g_out_count == 0 && g_release_count == 0, "auth_claim_fail_no_io");
    q_arm(0, 24, 7, 24, 711, 0, 0); g_release_rc = -1;
    rc = __CALL__;
    q_paths();
    q_rep(rc != 0, "auth_release_fail_error");
    q_arm(0, 10, 7, 24, 711, 0, 0);
    rc = __CALL__;
    q_paths();
    q_rep(rc != 0, "auth_hdr_short_rc");
    q_rep(g_out_count == 1 && g_in_count == 0, "auth_hdr_short_no_extra");
    q_arm(0, 24, 7, 24, 100, 0, 0);
    rc = __CALL__;
    q_paths();
    q_rep(rc != 0, "auth_pub_short_rc");
    q_rep(g_in_count <= 2, "auth_pub_short_no_extra");
    q_arm(0, 24, 7, 24, 711, 0, 1);
    rc = __CALL__;
    q_paths();
    q_rep(rc != 0, "auth_deadline_claim_rc");
    q_rep(g_claim_count == 0 && g_bulk_count == 0, "auth_deadline_claim_no_io");
    q_rep(g_bad_open == 0, "auth_no_create");
    q_rep(g_bad_path == 0, "auth_allowed_paths");
    printf("AUTH_SHIM_RESULT %s total=%d failures=%d\n", q_fail ? "FAIL" : "PASS", q_total, q_fail);
    return q_fail ? 1 : 0;
}
"""


def compile_auth_shim(cc: str, tmpdir: Path) -> Path:
    text = MAIN_C.read_text(encoding="utf-8")
    call = "m4_authorize()" if "m4_authorize" in text else "m4_probe()"
    src = AUTH_SHIM_TEMPLATE.replace("__INCLUDE_PATH__", MAIN_C.resolve().as_posix()).replace("__CALL__", call)
    c = tmpdir / "m4_auth_shim.c"
    c.write_text(src, encoding="utf-8")
    b = tmpdir / "m4-auth-shim"
    r = subprocess.run([cc] + HARNESS_FLAGS + [str(c), "-o", str(b)],
                       cwd=ROOT, text=True, capture_output=True, timeout=90)
    if r.returncode:
        raise AssertionError(f"auth shim compile failed:\n{r.stdout}{r.stderr}")
    return b


class M4AdbAuthorizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MAIN_C.is_file():
            raise unittest.SkipTest(f"missing {MAIN_C} (owner agent still writing; no polling)")
        cls.cc = find_cc()
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-m4-auth-build-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        cls.probe = base / ("c2m-m4-auth" + (".exe" if os.name == "nt" else ""))
        compile_binary(cls.cc, cls.probe)
        hbin = compile_harness(cls.cc, base)
        cls.harness_result = subprocess.run([str(hbin)], text=True, capture_output=True,
                                            timeout=NATIVE_TIMEOUT)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.tmp.cleanup()
        except Exception:
            pass

    def run_bin(self, binary: Path, *args: str, timeout: float = NATIVE_TIMEOUT):
        return subprocess.run([str(binary), *args], text=True, capture_output=True, timeout=timeout)

    def assert_harness_label(self, label: str) -> None:
        out = self.harness_result.stdout
        self.assertEqual(self.harness_result.returncode, 0,
                         f"harness failed:\nSTDOUT:\n{out[-8000:]}\nSTDERR:\n{self.harness_result.stderr[-4000:]}")
        self.assertIn("HARNESS_RESULT PASS", out, out[-8000:])
        self.assertIn(f"[PASS] {label}", out, f"missing harness case: {label}")

    def test_cli_help_selftest_unknown(self) -> None:
        r = self.run_bin(self.probe, "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        for tok in ("--help", "--self-test", "--request-authorization"):
            self.assertIn(tok, r.stdout)
        for args in ((), ("--unknown",), ("--self-test", "extra"), ("--request-authorization", "extra")):
            with self.subTest(args=args):
                self.assertEqual(self.run_bin(self.probe, *args).returncode, 2, str(args))
        r = self.run_bin(self.probe, "--self-test")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)
        self.assertIn(b"--request-authorization", self.probe.read_bytes())

    def test_source_pure_api_shape(self) -> None:
        text = MAIN_C.read_text(encoding="utf-8")
        self.assertNotIn("\r", text)
        gnu, stdio = text.find("_GNU_SOURCE"), text.find("#include <stdio.h>")
        self.assertGreaterEqual(gnu, 0)
        self.assertGreater(stdio, gnu, "_GNU_SOURCE must precede stdio")
        self.assertRegex(text, r"static\s+int\s+m4_auth_pubkey_valid\s*\(\s*const\s+uint8_t\s*\*")
        self.assertRegex(text, r"static\s+size_t\s+m4_auth_pubkey_frame\s*\(\s*uint8_t\s*\*")
        self.assertIn("m4_self_test", text)
        self.assertTrue("m4_authorize" in text or "m4_probe" in text, "missing authorize entry")
        self.assertIn("--request-authorization", text)
        self.assertTrue("stdin" in text or "STDIN" in text or "read(0" in text, "key must come from stdin")
        for const in ("711", "735", "700", "524"):
            self.assertIn(const, text, f"missing constant {const}")
        probe_pos = min((p for p in (text.find("m4_authorize"), text.find("m4_probe"),
                                     text.find("USBDEVFS_BULK")) if p >= 0), default=-1)
        pdef = text.rfind("static int m4_probe(void)")
        if pdef < 0:
            pdef = text.rfind("static int m4_authorize(void)")
        if pdef < 0:
            pdef = probe_pos
        for api in ("m4_auth_pubkey_valid", "m4_auth_pubkey_frame"):
            decl = text.find(api)
            self.assertGreaterEqual(decl, 0, f"missing {api}")
            if pdef >= 0:
                self.assertLess(decl, pdef, f"{api} must precede the probe definition")
        stripped = strip_c_comments(text)
        self.assertNotRegex(stripped, r"#\s*ifdef\s+TEST\b")
        self.assertNotIn("TEST_MODE", stripped)

    def test_source_static_guards(self) -> None:
        text = MAIN_C.read_text(encoding="utf-8")
        stripped = strip_c_comments(text)
        # Help/usage strings legitimately say 'no shell/signature/retries': drop
        # print lines so the bans below apply to real code paths only.
        code = "\n".join(ln for ln in stripped.splitlines()
                         if "printf" not in ln and "fputs" not in ln and "puts" not in ln)
        low = code.lower()
        for tok in ("socket(", "connect(", "send(", "sendto(", "sendmsg(", "ptrace",
                    "A_OPEN", "O_CREAT", "O_TRUNC", "USBDEVFS_RESET", "USBDEVFS_CLEAR_HALT",
                    "USBDEVFS_DISCONNECT", "USBDEVFS_SETCONFIGURATION", "USBDEVFS_SETINTERFACE"):
            self.assertNotIn(tok, code, f"forbidden: {tok}")
        for tok in ("signature", "retry", "attempt"):
            self.assertNotIn(tok, low, f"forbidden code path: {tok}")
        for tok in ("shell:", "sync:"):
            self.assertNotIn(tok, low, f"forbidden service: {tok}")
        for tok in ("adbkey", ".android", "private_key", "PRIVATE_KEY", "id_rsa"):
            self.assertNotIn(tok, text, f"forbidden private path: {tok}")
        for tok in ("CLAIM", "RELEASE", "BULK", "35000", "30000", "m4_remain_auth"):
            self.assertIn(tok, stripped, f"missing: {tok}")
        for tok in ("one public key", "no shell"):
            self.assertIn(tok, text, f"missing help token: {tok}")
        for big in ("60000", "120000"):
            m = re.search(r"(timeout|deadline|wait_ms|ms)\W{0,8}" + big, stripped)
            self.assertIsNone(m, f"suspicious large deadline {big}")
        body = stripped[max(0, stripped.rfind("static int m4_probe(void)") if "static int m4_probe(void)" in stripped else stripped.rfind("m4_probe")):]
        self.assertIn("24", body)
        self.assertIn("711", body)

    def test_harness_pubkey(self) -> None:
        for label in ("pub_build711", "pub_layout", "pub_user", "pub_valid", "pub_null",
                      "pub_short", "pub_toolong", "pub_comment", "pub_eof", "pub_nonascii",
                      "pub_b64char", "pub_b64pad", "pub_nospace", "pub_baduser", "pub_badlenfield",
                      "pub_modeven", "pub_topbit", "pub_exponent", "pub_n0inv",
                      "frame_len735", "frame_cmd_auth", "frame_arg0_3", "frame_arg1_0",
                      "frame_dlen711", "frame_sum", "frame_magic", "frame_payload",
                      "frame_short", "frame_null", "frame_nullkey", "frame_badkey"):
            with self.subTest(label=label):
                self.assert_harness_label(label)

    @unittest.skipUnless(LINUX, "auth shim needs Linux usbdevice_fs headers")
    def test_auth_shim_success_path(self) -> None:
        tmp = Path(self.tmp.name) / "auth_shim"
        tmp.mkdir(exist_ok=True)
        r = subprocess.run([str(compile_auth_shim(self.cc, tmp))], text=True,
                           capture_output=True, timeout=NATIVE_TIMEOUT)
        self.assertEqual(r.returncode, 0,
                         f"auth shim failed:\nSTDOUT:\n{r.stdout[-8000:]}\nSTDERR:\n{r.stderr[-4000:]}")
        self.assertIn("AUTH_SHIM_RESULT PASS", r.stdout, r.stdout[-8000:])
        for label in ("auth_success", "auth_counts_4_766", "auth_split", "auth_in_bounded",
                      "auth_no_signature", "auth_again_stops", "auth_again_no_reply",
                      "auth_timeout_rc", "auth_timeout_no_ui", "auth_badkey_rc", "auth_badkey_no_usb",
                      "auth_claim_fail_rc", "auth_claim_fail_no_io", "auth_release_fail_error",
                      "auth_hdr_short_rc", "auth_hdr_short_no_extra", "auth_pub_short_rc",
                      "auth_deadline_claim_rc", "auth_deadline_claim_no_io",
                      "auth_no_create", "auth_allowed_paths"):
            with self.subTest(label=label):
                self.assertIn(f"[PASS] {label}", r.stdout, f"missing shim case: {label}")

    def test_request_never_native(self) -> None:
        self.assertIn("--request-authorization", MAIN_C.read_text(encoding="utf-8"))
        if LINUX:
            self.skipTest("--request-authorization execution prohibited on Linux (static check only)")
        r = self.run_bin(self.probe, "--request-authorization", timeout=NATIVE_TIMEOUT)
        self.assertNotEqual(r.returncode, 0)
        combined = (r.stdout + r.stderr).lower()
        self.assertTrue("unsupported" in combined or "request" in combined or "platform" in combined,
                        f"expected unsupported on Windows, got: {combined[-500:]}")

if __name__ == "__main__":
    unittest.main()
