#!/usr/bin/env python3
"""Host guards for M4 passive usb0 observer (fw/m4_sniff/m4_usb_observe.c).

Never touches camera, UART, network, vendor IPC, real package paths, or any
status file. Portable --help/--self-test/CLI checks run on Windows and Linux.
--observe runtime is Linux-only and must stay finite without usb0.
observer_v3: shared pure m4_packet_line, IP-total payload, single-VLAN+options.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "fw" / "m4_sniff" / "m4_usb_observe.c"
ARM_SCRIPT = ROOT / "fw" / "m4_sniff" / "build_arm.sh"
FLAGS = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror"]
HARNESS_FLAGS = FLAGS + ["-Wno-unused-function"]
LINUX = sys.platform.startswith("linux")

REQUIRED_SOURCE = (
    "M4_SNIFF_IFACE_FIXED",
    "M4_SNIFF_MAX_PACKETS",
    "M4_SNIFF_SNAPLEN",
    "M4_SNIFF_PAYLOAD_HEX_BYTES",
    "M4_SNIFF_MAX_MS",
    "m4_parse_frame",
    "m4_packet_line",
    "m4_self_test",
    "m4_observe",
    "payload_length",
    "payload_captured",
    "observer_simulation_not_production_delivery",
    "status_writes=0",
    "transmit_bytes=0",
    "iface_fixed",
    "payload_hex_fixed",
    "payload_len=",
    "captured=",
    "truncated=",
    "payload_hex=",
    "data_packets=",
    "completion=",
    "interrupted_signal",
    "iface_unavailable",
    "capture_unavailable",
    "if_nametoindex",
    "AF_PACKET",
    "SOCK_RAW",
    "recvfrom",
    "MSG_TRUNC",
    "clock_gettime",
    "poll(",
)

REQUIRED_ARM = (
    "--out",
    "--sysroot",
    "armv7-a",
    "vfpv3-d16",
    "mfloat-abi=hard",
    "_TIME_BITS=32",
    "nostartfiles",
    "ld-linux-armhf.so.3",
    "check_elf.py",
    "--allow-dynamic",
    "qemu-arm-static",
    "--self-test",
    "--help",
    "readelf -V",
    "sha256sum",
    "compat.h",
    "fw/m4_sniff/m4_usb_observe.c",
    "c2m-m4-sniff",
    "sniff-selftest-arm.txt",
    "sniff-help-arm.txt",
    "--observe",
    "usb0",
    "set -eu",
)

FORBIDDEN_CALLS = (
    "send(",
    "sendto(",
    "sendmsg(",
    "sendmmsg(",
    "connect(",
    "ioctl",
    "setsockopt",
    "system(",
    "popen(",
    "fopen(",
    "open(",
    "openat(",
    "O_CREAT",
    "O_WRONLY",
    "O_RDWR",
    "write_status",
    "renameat",
    "c2m_d4_status",
    "--serve",
    "--db",
    "--gps-file",
    "--status-file",
    "getenv(",
    "/dev/",
    "uart",
)


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


def has_usb0() -> bool:
    try:
        if Path("/sys/class/net/usb0").exists():
            return True
    except Exception:
        pass
    try:
        socket.if_nametoindex("usb0")
        return True
    except Exception:
        return False


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

#define main m4_observer_entry
#include "__INCLUDE_PATH__"
#undef main

static int h_fail = 0;
static int h_total = 0;
static unsigned h_max_line = 0;

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

static int h_has(const char *hay, const char *needle) {
    return hay && needle && strstr(hay, needle) != NULL;
}

static int h_get_uint(const char *out, const char *key, unsigned *val) {
    const char *p;
    unsigned v = 0;
    int n = 0;
    if (!out || !key || !val) return -1;
    p = strstr(out, key);
    if (!p) return -1;
    p += strlen(key);
    if (sscanf(p, "%u%n", &v, &n) != 1 || n <= 0) return -1;
    *val = v;
    return 0;
}

static int h_get_leg(const char *out, char *buf, size_t cap) {
    const char *p;
    size_t i = 0;
    if (!out || !buf || cap == 0) return -1;
    p = strstr(out, "leg=");
    if (!p) return -1;
    p += 4;
    while (*p && *p != ' ' && *p != '\n' && *p != '\r' && *p != '\t') {
        if (i + 1 < cap) buf[i] = *p;
        ++i;
        ++p;
    }
    if (i < cap) buf[i] = '\0';
    else buf[cap - 1] = '\0';
    return (i > 0) ? 0 : -1;
}

static int h_get_hex(const char *out, char *buf, size_t cap) {
    const char *p;
    size_t i = 0;
    if (!out || !buf || cap == 0) return -1;
    p = strstr(out, "payload_hex=");
    if (!p) return -1;
    p += 12;
    while ((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f') || (*p >= 'A' && *p <= 'F')) {
        if (i + 1 < cap) buf[i] = *p;
        ++i;
        ++p;
    }
    if (i < cap) buf[i] = '\0';
    else buf[cap - 1] = '\0';
    return (int)i;
}

static int h_hex_ci_eq(const char *a, const char *b) {
    while (*a && *b) {
        char ca = *a;
        char cb = *b;
        if (ca >= 'A' && ca <= 'F') ca = (char)(ca - 'A' + 'a');
        if (cb >= 'A' && cb <= 'F') cb = (char)(cb - 'A' + 'a');
        if (ca != cb) return 0;
        ++a;
        ++b;
    }
    return *a == '\0' && *b == '\0';
}

static void h_put16(uint8_t *b, unsigned off, unsigned v) {
    b[off] = (uint8_t)((v >> 8) & 0xFFu);
    b[off + 1] = (uint8_t)(v & 0xFFu);
}

static void h_note_line(const char *name, const char *out, int ret) {
    size_t sl = 0;
    if (out) sl = strlen(out);
    if (ret > 0 && (size_t)ret > h_max_line) h_max_line = (unsigned)ret;
    printf("LINE %s ret=%d slen=%u out=%s", name, ret, (unsigned)sl, out ? out : "(null)");
    if (out && sl > 0 && out[sl - 1] != '\n') printf("\n");
    fflush(stdout);
}

int main(void) {
    char out[1024];
    char hex[512];
    struct m4_parsed p;
    int ret;
    int hexlen;
    unsigned vlen = 0;
    unsigned vcap = 0;
    unsigned vtrunc = 999;
    unsigned i;

    h_report(M4_SNIFF_MAX_PACKETS == 20, "const_max_packets");
    h_report(M4_SNIFF_SNAPLEN == 512, "const_snaplen");
    h_report(M4_SNIFF_PAYLOAD_HEX_BYTES == 96, "const_payload_hex");
    h_report(M4_SNIFF_MAX_POLLS == 15, "const_max_polls");
    h_report(M4_SNIFF_MAX_MS == UINT64_C(30000), "const_max_ms");
    h_report(m4_self_test() == 0, "selftest");

    /* null-out must not crash (checks before memset) */
    m4_parse_frame(NULL, 0, NULL);
    {
        uint8_t dummy[16];
        memset(dummy, 0xAB, sizeof(dummy));
        m4_parse_frame(dummy, (unsigned)sizeof(dummy), NULL);
        m4_parse_frame(NULL, 10, NULL);
    }
    h_report(1, "null_out_no_crash");

    /* --- plain TCP: ETH+IP(20)+TCP(20)+5 "hello", sport 26012 --- */
    {
        uint8_t f[14 + 20 + 20 + 5];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45; f[15] = 0x00;
        h_put16(f, 16, 45);
        f[23] = 6;
        f[26] = 192; f[27] = 168; f[28] = 32; f[29] = 123;
        f[30] = 192; f[31] = 168; f[32] = 32; f[33] = 129;
        f[34] = 0x65; f[35] = 0x9C; f[36] = 0xA8; f[37] = 0xFD;
        f[46] = 0x50; f[47] = 0x18;
        f[54] = 0x68; f[55] = 0x65; f[56] = 0x6c; f[57] = 0x6c; f[58] = 0x6f;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 1, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("plain_tcp", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0 && (size_t)ret == strlen(out), "plain_tcp_ret");
        h_report(ret > 0 && out[strlen(out) - 1] == '\n', "plain_tcp_nl");
        h_report(h_has(out, "pkt=1"), "plain_tcp_pkt");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 5, "plain_tcp_len");
        h_report(h_get_uint(out, "captured=", &vcap) == 0 && vcap == 5, "plain_tcp_cap");
        h_report(h_get_uint(out, "truncated=", &vtrunc) == 0 && vtrunc == 0, "plain_tcp_trunc");
        h_report(h_has(out, "leg=adas_26012"), "plain_tcp_leg");
        h_report(hexlen == 10 && h_hex_ci_eq(hex, "68656c6c6f"), "plain_tcp_hex");
        h_report(p.payload_length == 5 && p.payload_captured == 5, "plain_tcp_struct");
        h_report(p.payload_offset == 54, "plain_tcp_off");
    }

    /* --- IP/TCP options: IP IHL6 (24B), TCP off8 (32B), 6B "hello!" --- */
    {
        uint8_t f[14 + 24 + 32 + 6];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x46; f[15] = 0x00;
        h_put16(f, 16, 62);
        f[23] = 6;
        f[26] = 10; f[27] = 0; f[28] = 0; f[29] = 1;
        f[30] = 10; f[31] = 0; f[32] = 0; f[33] = 2;
        f[38] = 0x65; f[39] = 0x9C; f[40] = 0xA8; f[41] = 0xFD;
        f[38 + 12] = 0x80; f[38 + 13] = 0x10;
        f[70] = 0x68; f[71] = 0x65; f[72] = 0x6c; f[73] = 0x6c; f[74] = 0x6f; f[75] = 0x21;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 2, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("ip_tcp_options", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0 && (size_t)ret == strlen(out), "ip_tcp_options_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 6, "ip_tcp_options_len");
        h_report(h_get_uint(out, "captured=", &vcap) == 0 && vcap == 6, "ip_tcp_options_cap");
        h_report(hexlen == 12 && h_hex_ci_eq(hex, "68656c6c6f21"), "ip_tcp_options_hex");
        h_report(p.payload_length == 6 && p.payload_captured == 6, "ip_tcp_options_struct");
        h_report(p.payload_offset == 70, "ip_tcp_options_off");
    }

    /* --- single VLAN + options: 18B eth, IP24, TCP32, 5B "VLAN!" --- */
    {
        uint8_t f[18 + 24 + 32 + 5];
        memset(f, 0, sizeof(f));
        f[12] = 0x81; f[13] = 0x00;
        f[14] = 0x00; f[15] = 0x01;
        f[16] = 0x08; f[17] = 0x00;
        f[18] = 0x46; f[19] = 0x00;
        h_put16(f, 20, 61);
        f[27] = 6;
        f[42] = 0x1F; f[43] = 0x90; f[44] = 0xA8; f[45] = 0xFD;
        f[42 + 12] = 0x80; f[42 + 13] = 0x18;
        f[74] = 0x56; f[75] = 0x4c; f[76] = 0x41; f[77] = 0x4e; f[78] = 0x21;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 3, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("vlan_single_options", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0 && (size_t)ret == strlen(out), "vlan_single_options_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 5, "vlan_single_options_len");
        h_report(h_get_uint(out, "captured=", &vcap) == 0 && vcap == 5, "vlan_single_options_cap");
        h_report(hexlen == 10 && h_hex_ci_eq(hex, "564c414e21"), "vlan_single_options_hex");
        h_report(p.payload_length == 5 && p.payload_captured == 5, "vlan_single_options_struct");
        h_report(p.payload_offset == 74, "vlan_single_options_off");
    }

    /* --- padded ACK: IP total 40, TCP20, 6B ether padding, no L7 --- */
    {
        uint8_t f[60];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45; f[15] = 0x00;
        h_put16(f, 16, 40);
        f[23] = 6;
        f[26] = 192; f[27] = 168; f[28] = 32; f[29] = 123;
        f[30] = 192; f[31] = 168; f[32] = 32; f[33] = 129;
        f[34] = 0x65; f[35] = 0x9C; f[36] = 0xA8; f[37] = 0xFD;
        f[46] = 0x50; f[47] = 0x10;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 4, 60u, f, 60u, &p);
        h_note_line("padded_ack_no_payload", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0 && (size_t)ret == strlen(out), "padded_ack_no_payload_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 0, "padded_ack_no_payload_len");
        h_report(h_get_uint(out, "captured=", &vcap) == 0 && vcap == 0, "padded_ack_no_payload_cap");
        h_report(hexlen == 0, "padded_ack_no_payload_hex");
        h_report(p.payload_length == 0 && p.payload_captured == 0, "padded_ack_no_payload_struct");
    }

    /* --- UDP: ETH+IP(32)+UDP(8)+4B "test" --- */
    {
        uint8_t f[14 + 20 + 8 + 4];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45; f[15] = 0x00;
        h_put16(f, 16, 32);
        f[23] = 17;
        f[34] = 0x04; f[35] = 0xD2; f[36] = 0x04; f[37] = 0xD3;
        h_put16(f, 38, 12);
        f[42] = 0x74; f[43] = 0x65; f[44] = 0x73; f[45] = 0x74;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 5, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("udp_basic", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0 && (size_t)ret == strlen(out), "udp_basic_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 4, "udp_basic_len");
        h_report(h_get_uint(out, "captured=", &vcap) == 0 && vcap == 4, "udp_basic_cap");
        h_report(hexlen == 8 && h_hex_ci_eq(hex, "74657374"), "udp_basic_hex");
        h_report(p.payload_length == 4 && p.payload_captured == 4, "udp_basic_struct");
        h_report(p.payload_offset == 42, "udp_basic_off");
    }

    /* --- fragment MF set --- */
    {
        uint8_t f[42];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 28);
        f[20] = 0x20; f[21] = 0x01;
        f[23] = 6;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 6, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("frag_mf", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "frag_mf_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 0, "frag_mf_len");
        h_report(hexlen == 0, "frag_mf_hex");
        h_report(p.is_frag == 1 && p.is_tcp == 0, "frag_mf_struct");
    }

    /* --- fragment offset nonzero, no MF --- */
    {
        uint8_t f[42];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 28);
        f[20] = 0x00; f[21] = 0x08;
        f[23] = 6;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 7, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("frag_offset", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "frag_offset_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 0, "frag_offset_len");
        h_report(hexlen == 0, "frag_offset_hex");
        h_report(p.is_frag == 1, "frag_offset_struct");
    }

    /* --- truncated: len<14 --- */
    {
        uint8_t f[10];
        memset(f, 0, sizeof(f));
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 8, 10u, f, 10u, &p);
        h_note_line("trunc_short", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "trunc_short_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 0, "trunc_short_len");
        h_report(hexlen == 0, "trunc_short_hex");
    }

    /* --- malformed: IP total too small for TCP (total 20, need ihl+20) --- */
    {
        uint8_t f[14 + 20];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 20);
        f[23] = 6;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 9, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("ip_total_too_small", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "ip_total_too_small_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 0, "ip_total_too_small_len");
        h_report(hexlen == 0, "ip_total_too_small_hex");
    }

    /* --- malformed: TCP data offset too small (<20) --- */
    {
        uint8_t f[14 + 20 + 16 + 5];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 41);
        f[23] = 6;
        f[34] = 0x65; f[35] = 0x9C; f[36] = 0xA8; f[37] = 0xFD;
        f[46] = 0x40; f[47] = 0x18;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 10, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("tcp_offset_small", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "tcp_offset_small_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 0, "tcp_offset_small_len");
        h_report(hexlen == 0, "tcp_offset_small_hex");
    }

    /* --- malformed: TCP offset beyond IP transport --- */
    {
        uint8_t f[14 + 20 + 20];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 40);
        f[23] = 6;
        f[34] = 0x65; f[35] = 0x9C; f[36] = 0xA8; f[37] = 0xFD;
        f[46] = 0x80; f[47] = 0x18;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 11, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("tcp_offset_beyond", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "tcp_offset_beyond_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 0, "tcp_offset_beyond_len");
        h_report(hexlen == 0, "tcp_offset_beyond_hex");
    }

    /* --- truncated headers: real 59 but shown 30 --- */
    {
        uint8_t f[14 + 20 + 20 + 5];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 45);
        f[23] = 6;
        f[34] = 0x65; f[35] = 0x9C; f[36] = 0xA8; f[37] = 0xFD;
        f[46] = 0x50; f[47] = 0x18;
        f[54] = 0x68; f[55] = 0x65; f[56] = 0x6c; f[57] = 0x6c; f[58] = 0x6f;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 12, 59u, f, 30u, &p);
        h_note_line("truncated_headers", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "truncated_headers_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 0, "truncated_headers_len");
        h_report(hexlen == 0, "truncated_headers_hex");
        h_report(h_get_uint(out, "truncated=", &vtrunc) == 0 && vtrunc == 0, "truncated_headers_trunc");
    }

    /* --- max payload truncation: 200B payload, captured 96 --- */
    {
        static uint8_t f[14 + 20 + 20 + 200];
        char exp[193];
        size_t k;
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 240);
        f[23] = 6;
        f[34] = 0x65; f[35] = 0x9C; f[36] = 0xA8; f[37] = 0xFD;
        f[46] = 0x50; f[47] = 0x18;
        for (i = 0; i < 200; ++i) f[54 + i] = (uint8_t)(i & 0xFFu);
        for (k = 0; k < 96; ++k) {
            static const char hd[] = "0123456789abcdef";
            uint8_t v = (uint8_t)(k & 0xFFu);
            exp[2 * k] = hd[(v >> 4) & 0x0Fu];
            exp[2 * k + 1] = hd[v & 0x0Fu];
        }
        exp[192] = '\0';
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 13, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_note_line("max_payload_trunc", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "max_payload_trunc_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 200, "max_payload_trunc_len");
        h_report(h_get_uint(out, "captured=", &vcap) == 0 && vcap == 96, "max_payload_trunc_cap");
        h_report(hexlen == 192 && h_hex_ci_eq(hex, exp), "max_payload_trunc_hex");
        h_report(p.payload_length == 200 && p.payload_captured == 96, "max_payload_trunc_struct");
    }

    /* --- snap truncation: 600B payload, real 654, shown 512 --- */
    {
        static uint8_t f[512];
        char exp[193];
        size_t k;
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 640);
        f[23] = 6;
        f[34] = 0x65; f[35] = 0x9C; f[36] = 0xA8; f[37] = 0xFD;
        f[46] = 0x50; f[47] = 0x18;
        for (i = 0; i < (unsigned)(512 - 54); ++i) f[54 + i] = (uint8_t)(i & 0xFFu);
        for (k = 0; k < 96; ++k) {
            static const char hd[] = "0123456789abcdef";
            uint8_t v = (uint8_t)(k & 0xFFu);
            exp[2 * k] = hd[(v >> 4) & 0x0Fu];
            exp[2 * k + 1] = hd[v & 0x0Fu];
        }
        exp[192] = '\0';
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 14, 654u, f, 512u, &p);
        h_note_line("snap_trunc_large", out, ret);
        hexlen = h_get_hex(out, hex, sizeof(hex));
        h_report(ret > 0, "snap_trunc_large_ret");
        h_report(h_get_uint(out, "payload_len=", &vlen) == 0 && vlen == 600, "snap_trunc_large_len");
        h_report(h_get_uint(out, "captured=", &vcap) == 0 && vcap == 96, "snap_trunc_large_cap");
        h_report(h_get_uint(out, "truncated=", &vtrunc) == 0 && vtrunc == 1, "snap_trunc_large_trunc");
        h_report(hexlen == 192 && h_hex_ci_eq(hex, exp), "snap_trunc_large_hex");
    }

    /* --- return / capacity / null contract for packet_line --- */
    {
        uint8_t f[14 + 20 + 20 + 5];
        char small[10];
        memset(f, 0, sizeof(f));
        f[12] = 0x08; f[13] = 0x00;
        f[14] = 0x45;
        h_put16(f, 16, 45);
        f[23] = 6;
        f[34] = 0x65; f[35] = 0x9C; f[36] = 0xA8; f[37] = 0xFD;
        f[46] = 0x50; f[47] = 0x18;
        f[54] = 0x68; f[55] = 0x65; f[56] = 0x6c; f[57] = 0x6c; f[58] = 0x6f;
        memset(&p, 0, sizeof(p));
        memset(out, 0, sizeof(out));
        ret = m4_packet_line(out, sizeof(out), 15, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
        h_report(ret > 0 && (size_t)ret == strlen(out) && out[strlen(out) - 1] == '\n', "packet_line_ret_nl");
        h_report(h_has(out, "payload_len=") && h_has(out, "captured=") && h_has(out, "truncated=") && h_has(out, "leg=") && h_has(out, "payload_hex="), "packet_line_fields");
        {
            char tmp[64];
            size_t cap = sizeof(tmp);
            (void)cap;
            h_report(m4_packet_line(NULL, 100, 1, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p) == -1, "packet_line_null_out");
            h_report(m4_packet_line(small, sizeof(small), 1, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p) == -1, "packet_line_small_cap");
            h_report(m4_packet_line(out, 0, 1, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p) == -1, "packet_line_zero_cap");
        }
        {
            char lb[64];
            memset(&p, 0, sizeof(p));
            memset(out, 0, sizeof(out));
            ret = m4_packet_line(out, sizeof(out), 16, (unsigned)sizeof(f), f, (unsigned)sizeof(f), &p);
            h_report(h_get_leg(out, lb, sizeof(lb)) == 0 && strcmp(lb, "adas_26012") == 0, "packet_line_leg_adas");
        }
    }

    printf("MAX_LINE len=%u\n", h_max_line);
    printf("HARNESS_RESULT %s total=%d failures=%d\n", h_fail ? "FAIL" : "PASS", h_total, h_fail);
    fflush(stdout);
    return h_fail ? 1 : 0;
}
"""


def compile_harness(cc: str, tmpdir: Path) -> Path:
    include_posix = MAIN_C.resolve().as_posix()
    src = HARNESS_TEMPLATE.replace("__INCLUDE_PATH__", include_posix)
    harness_c = tmpdir / "m4_harness.c"
    harness_c.write_text(src, encoding="utf-8")
    suffix = ".exe" if os.name == "nt" else ""
    harness_bin = tmpdir / ("m4-harness" + suffix)
    cmd = [cc] + HARNESS_FLAGS + [str(harness_c), "-o", str(harness_bin)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise AssertionError(
            f"harness compile failed (observer_v3 m4_packet_line likely missing):\n"
            f"{result.stdout}{result.stderr}"
        )
    return harness_bin


class M4SniffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for path in (MAIN_C, ARM_SCRIPT):
            if not path.is_file():
                raise AssertionError(f"Missing file: {path}")
        cls.cc = find_cc()
        cls.tmp = tempfile.TemporaryDirectory(prefix="c2m-m4-sniff-build-")
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        suffix = ".exe" if os.name == "nt" else ""
        cls.sniff = base / ("c2m-m4-sniff" + suffix)
        compile_binary(cls.cc, cls.sniff)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.tmp.cleanup()
        except Exception:
            pass

    def run_bin(self, binary: Path, *args: str, timeout: float = 10.0):
        return subprocess.run([str(binary), *args], text=True, capture_output=True, timeout=timeout)

    def test_cli_only_observe_help_selftest(self) -> None:
        result = self.run_bin(self.sniff, "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--observe", result.stdout)
        self.assertIn("--self-test", result.stdout)
        self.assertIn("usb0", result.stdout)
        self.assertIn("observer simulation", result.stdout)
        self.assertIn("never transmits", result.stdout)
        self.assertIn("Payload-only", result.stdout)
        self.assertNotIn("--serve", result.stdout)
        self.assertNotIn("--db", result.stdout)
        self.assertNotIn("--gps-file", result.stdout)
        self.assertNotIn("--status-file", result.stdout)
        result = self.run_bin(self.sniff, "--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("M4 USB observe self-test: OK", result.stdout)
        for args in ((), ("--unknown",), ("--serve",),
                     ("--observe", "extra"), ("--self-test", "extra")):
            with self.subTest(args=args):
                result = self.run_bin(self.sniff, *args)
                self.assertEqual(result.returncode, 2, str(args))
        raw = self.sniff.read_bytes()
        self.assertIn(b"--observe", raw)
        self.assertNotIn(b"--serve", raw)
        self.assertNotIn(b"--db", raw)
        self.assertNotIn(b"c2m_d4_status", raw)

    def test_source_shares_no_transmit_no_writer(self) -> None:
        text = MAIN_C.read_text(encoding="utf-8")
        for token in REQUIRED_SOURCE:
            self.assertIn(token, text, f"missing sniffer token: {token}")
        self.assertIn("m4_sniff=observer_v3", text)
        self.assertNotIn("m4_sniff=observer_v1", text)
        self.assertNotIn("m4_sniff=observer_v2", text)
        self.assertIn("delivery_sim=observer_simulation_not_production_delivery", text)
        # Observer body must never transmit or write files (comments ignored).
        start = text.find("static int m4_observe(")
        self.assertGreaterEqual(start, 0)
        end = text.find("#endif", start)
        self.assertGreater(end, start)
        body = text[start:end]
        stripped_body = strip_c_comments(body)
        for token in FORBIDDEN_CALLS:
            self.assertNotIn(token, stripped_body, f"forbidden sniffer observer token: {token}")
        # Whole-program actual calls (not comments) must also stay clean.
        stripped_all = strip_c_comments(text)
        for token in FORBIDDEN_CALLS:
            self.assertNotIn(token, stripped_all, f"forbidden whole-program token: {token}")
        # Receive-only attach is allowed and explicitly documented.
        self.assertIn("bind(fd", stripped_body)
        self.assertIn("recvfrom", stripped_body)
        self.assertNotIn("\r", text)

    def test_source_v3_schema(self) -> None:
        text = MAIN_C.read_text(encoding="utf-8")
        # Fixed bounds unchanged: 20pkt / 512 snap / 96 payload / 15 poll / 30s.
        self.assertRegex(text, r"#define\s+M4_SNIFF_MAX_PACKETS\s+20\b")
        self.assertRegex(text, r"#define\s+M4_SNIFF_SNAPLEN\s+512\b")
        self.assertRegex(text, r"#define\s+M4_SNIFF_PAYLOAD_HEX_BYTES\s+96\b")
        self.assertRegex(text, r"#define\s+M4_SNIFF_MAX_POLLS\s+15\b")
        self.assertRegex(text, r"#define\s+M4_SNIFF_MAX_MS\b.*30000")
        self.assertRegex(text, r"#define\s+M4_SNIFF_POLL_MS\s+1000\b")
        # Struct keeps old fields plus IP-total payload helpers.
        for field in ("eth_type", "ip_proto", "sport", "dport", "tcp_flags",
                      "payload_offset", "is_arp", "is_ip", "is_tcp", "is_udp",
                      "is_frag", "payload_length", "payload_captured"):
            self.assertIn(field, text, f"missing m4_parsed field: {field}")
        # m4_parse_frame must guard null out before memset.
        pstart = text.find("m4_parse_frame")
        self.assertGreaterEqual(pstart, 0)
        window = text[pstart:pstart + 600]
        memset_pos = window.find("memset(o")
        null_pos = window.find("!o")
        if null_pos < 0:
            null_pos = window.find("o ==")
        if null_pos < 0:
            null_pos = window.find("NULL")
        self.assertGreaterEqual(memset_pos, 0, "m4_parse_frame must memset(o)")
        self.assertGreaterEqual(null_pos, 0, "m4_parse_frame must null-check out")
        self.assertLess(null_pos, memset_pos, "null out check must precede memset")
        # Shared pure packet-line helper.
        self.assertIn("m4_packet_line", text)
        self.assertRegex(
            text,
            r"static\s+int\s+m4_packet_line\s*\(\s*char\s*\*\s*out\s*,\s*size_t\s+capacity\s*,"
            r"\s*unsigned\s+number\s*,\s*unsigned\s+real_len\s*,"
            r"\s*const\s+uint8_t\s*\*\s*buf\s*,\s*unsigned\s+shown\s*,"
            r"\s*struct\s+m4_parsed\s*\*\s*p\s*\)",
            "m4_packet_line signature must match spec",
        )
        pl_start = text.find("static int m4_packet_line(")
        self.assertGreaterEqual(pl_start, 0)
        # Shared: defined before the Linux-only observer body.
        obs_start = text.find("static int m4_observe(")
        self.assertGreaterEqual(obs_start, 0)
        self.assertLess(pl_start, obs_start, "m4_packet_line must be shared pure (before m4_observe)")
        pl_window = text[pl_start:pl_start + 4000]
        self.assertIn("m4_parse_frame", pl_window, "m4_packet_line must call parser internally")
        for token in ("payload_len=", "captured=", "truncated=", "leg=", "payload_hex="):
            self.assertIn(token, pl_window, f"m4_packet_line must format {token}")
        self.assertIn(r"\n", pl_window, "m4_packet_line must terminate with newline")
        # Single-VLAN + IP-total + TCP/UDP length discipline present.
        lowered = text.lower()
        for token in ("0x8100", "payload_length", "payload_captured", "truncated"):
            self.assertIn(token, text, f"missing v3 parser token: {token}")
        self.assertIn("0x3fff", lowered, "missing v3 frag mask 0x3FFF")

    def test_arm_script_guards(self) -> None:
        raw = ARM_SCRIPT.read_bytes().decode("utf-8")
        self.assertNotIn("\r", raw, "script must be LF-only")
        for token in REQUIRED_ARM:
            self.assertIn(token, raw, f"missing ARM script token: {token}")
        for token in ("| tee", "|tee", "| grep", "|grep", "| cat", "|cat", "| sha256sum"):
            self.assertNotIn(token, raw, f"pipe hiding exit: {token}")
        self.assertIn("set -eu", raw)
        self.assertIn("--out DIR --sysroot STOCK_ROOTFS", raw)
        self.assertNotIn("sed -i", raw)
        self.assertIn("c2m_d4_status", raw)
        self.assertIn("--serve", raw)

    @unittest.skipUnless(LINUX, "--observe runtime is Linux-only")
    def test_observe_without_usb0_finite(self) -> None:
        if has_usb0():
            raise unittest.SkipTest("host has usb0; skip live --observe")
        result = self.run_bin(self.sniff, "--observe", timeout=25)
        self.assertEqual(result.stderr, "", result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr)
        self.assertLess(len(result.stdout.encode("utf-8")), 8192)
        self.assertIn("m4_sniff=observer_v3", result.stdout)
        self.assertIn("iface_fixed=usb0", result.stdout)
        self.assertIn("payload_hex_fixed=96", result.stdout)
        self.assertIn("delivery_sim=observer_simulation_not_production_delivery", result.stdout)
        self.assertIn("status_writes=0", result.stdout)
        self.assertIn("transmit_bytes=0", result.stdout)
        self.assertIn("summary packets=", result.stdout)
        self.assertIn("data_packets=", result.stdout)
        for forbidden in ("c2m_d4_status", "--serve", "R.420", "latitude", "longitude"):
            self.assertNotIn(forbidden, result.stdout)

    def test_packet_line_synthetic_frames(self) -> None:
        harness = compile_harness(self.cc, Path(self.tmp.name))
        suffix = ".exe" if os.name == "nt" else ""
        _ = suffix
        result = subprocess.run([str(harness)], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         f"harness failed:\nSTDOUT:\n{result.stdout[-8000:]}\nSTDERR:\n{result.stderr[-4000:]}")
        self.assertIn("HARNESS_RESULT PASS", result.stdout, result.stdout[-8000:])
        for label in (
            "[PASS] plain_tcp_hex",
            "[PASS] ip_tcp_options_hex",
            "[PASS] vlan_single_options_hex",
            "[PASS] padded_ack_no_payload_hex",
            "[PASS] udp_basic_hex",
            "[PASS] frag_mf_hex",
            "[PASS] frag_offset_hex",
            "[PASS] trunc_short_hex",
            "[PASS] ip_total_too_small_hex",
            "[PASS] tcp_offset_small_hex",
            "[PASS] tcp_offset_beyond_hex",
            "[PASS] truncated_headers_hex",
            "[PASS] max_payload_trunc_hex",
            "[PASS] snap_trunc_large_hex",
            "[PASS] packet_line_ret_nl",
            "[PASS] null_out_no_crash",
        ):
            self.assertIn(label, result.stdout, f"missing harness case: {label}")
        # Real hex equals chosen payloads (lowercase).
        self.assertIn("68656c6c6f", result.stdout)
        self.assertIn("74657374", result.stdout)
        # Offset-0 invalid produces zero hex: at least one empty payload_hex line.
        self.assertRegex(result.stdout, r"payload_hex=(\s|\n)")
        # Labeled packet lines for assertions.
        for name in ("plain_tcp", "vlan_single_options", "padded_ack_no_payload",
                     "udp_basic", "max_payload_trunc", "snap_trunc_large"):
            self.assertIn(f"LINE {name} ", result.stdout)

    def test_output_bound_worst(self) -> None:
        harness = compile_harness(self.cc, Path(self.tmp.name))
        result = subprocess.run([str(harness)], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:])
        m = re.search(r"MAX_LINE len=(\d+)", result.stdout)
        self.assertIsNotNone(m, "harness must print MAX_LINE")
        assert m is not None
        max_line = int(m.group(1))
        self.assertGreater(max_line, 0)
        self.assertLess(max_line, 1024, f"single record too large: {max_line}")
        # Worst case: 20 max records + headers/trailer must stay <8192.
        header_budget = 1024
        if LINUX and not has_usb0():
            obs = subprocess.run([str(self.sniff), "--observe"],
                                 text=True, capture_output=True, timeout=25)
            if obs.returncode == 0:
                header_budget = len(obs.stdout.encode("utf-8"))
        worst = header_budget + 20 * max_line
        self.assertLess(worst, 8192, f"worst 20*({max_line})+{header_budget}={worst} >= 8192")


if __name__ == "__main__":
    unittest.main(verbosity=2)
