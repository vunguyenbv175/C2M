#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE
#endif
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
/* M4 ADB active identifier: fixed USB 1-1, one finite handshake.
 * Active CNXN identification is NOT a passive sniffer and NOT an M4
 * rendering test. One CNXN handshake only; no key/shell/files/app/UI.
 * Camera 1-1 VID 2207 PID 0013, iface 1-1:1.2 num 02 ff/42/01, bulk
 * OUT 04 / IN 85 512. Ifaces 0/1 left alone; only iface 2 claimed.
 * AOSP transport_usb remote_write sends header 24 then data apart;
 * gadget expects 24 then 7, so OUT is TWO transfers (24, then 7 = 31).
 * Never a single combined 31 transfer. CLI --probe/--self-test/--help.
 */
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if !defined(_WIN32) && !defined(_WIN64)
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>
#include <sys/ioctl.h>
#ifdef __linux__
#include <linux/usbdevice_fs.h>
#include <linux/usb/ch9.h>
#endif
#endif
#define M4_ADB_VID 0x2207u
#define M4_ADB_PID 0x0013u
#define M4_ADB_IFACE 2u
#define M4_ADB_EP_OUT 0x04u
#define M4_ADB_EP_IN 0x85u
#define M4_ADB_CMD_CNXN 0x4E584E43u
#define M4_ADB_CMD_AUTH 0x48545541u
#define M4_ADB_VER 0x01000000u
#define M4_ADB_MAXDATA 4096u
#define M4_ADB_REQ_LEN 31u
#define M4_ADB_HDR_LEN 24u
#define M4_ADB_PAY_LEN 7u
#define M4_ADB_DESC_MAX 4096u
#define M4_ADB_MAX_MS 5000L
#define M4_ADB_SYS_BASE "/sys/bus/usb/devices/1-1"
static uint32_t m4_le32_rd(const uint8_t *b)
{
    return (uint32_t)b[0] | ((uint32_t)b[1] << 8) |
        ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}
static void m4_le32_wr(uint8_t *b, uint32_t v)
{
    b[0] = (uint8_t)(v & 0xFFu); b[1] = (uint8_t)((v >> 8) & 0xFFu);
    b[2] = (uint8_t)((v >> 16) & 0xFFu); b[3] = (uint8_t)((v >> 24) & 0xFFu);
}
static uint32_t m4_sum(const uint8_t *p, size_t n)
{
    uint32_t s = 0; size_t i;
    for (i = 0; i < n; i++) s += p[i];
    return s;
}
static size_t m4_cnxn_request(uint8_t *out, size_t cap)
{
    static const uint8_t pay[7] = { 'h', 'o', 's', 't', ':', ':', 0 };
    uint32_t cmd = M4_ADB_CMD_CNXN;
    if (!out || cap < M4_ADB_REQ_LEN) return 0;
    m4_le32_wr(out + 0, cmd); m4_le32_wr(out + 4, M4_ADB_VER);
    m4_le32_wr(out + 8, M4_ADB_MAXDATA); m4_le32_wr(out + 12, M4_ADB_PAY_LEN);
    m4_le32_wr(out + 16, m4_sum(pay, sizeof pay));
    m4_le32_wr(out + 20, cmd ^ 0xFFFFFFFFu);
    memcpy(out + 24, pay, sizeof pay);
    return M4_ADB_REQ_LEN;
}
static int m4_validate_descriptors(const uint8_t *b, size_t n)
{
    size_t off = 0, coff = 0, ctot = 0;
    int cfgs = 0, if2 = 0, epn = 0, epo = 0, epi = 0, cif = -1, cal = -1;
    unsigned vid, pid;
    if (!b || n < 18 || n > M4_ADB_DESC_MAX) return -1;
    if (b[0] != 18 || b[1] != 1) return -1;
    vid = (unsigned)b[8] | ((unsigned)b[9] << 8);
    pid = (unsigned)b[10] | ((unsigned)b[11] << 8);
    if (vid != M4_ADB_VID || pid != M4_ADB_PID || b[17] != 1) return -1;
    while (off + 2 <= n) {
        unsigned bl = b[off], tp = b[off + 1];
        if (bl < 2 || off + bl > n) return -1;
        if (tp == 1) { if (off != 0 || bl != 18) return -1; }
        else if (tp == 2) {
            unsigned tot;
            if (bl != 9) return -1;
            tot = (unsigned)b[off + 2] | ((unsigned)b[off + 3] << 8);
            if (tot < 9 || off + tot > n) return -1;
            cfgs++; coff = off; ctot = tot; cif = -1; cal = -1;
        } else if (tp == 4) {
            if (bl != 9 || cfgs != 1 || off + bl > coff + ctot) return -1;
            cif = b[off + 2]; cal = b[off + 3];
            if (cif == 2 && cal != 0) return -1;
            if (cif == 2 && cal == 0) {
                if2++;
                if (b[off + 4] != 2 || b[off + 5] != 0xFF ||
                    b[off + 6] != 0x42 || b[off + 7] != 0x01) return -1;
                epn = 0; epo = 0; epi = 0;
            }
        } else if (tp == 5) {
            if (bl != 7) return -1;
            if (cif == 2 && cal == 0) {
                unsigned ea = b[off + 2], at = b[off + 3];
                unsigned mx = (unsigned)b[off + 4] | ((unsigned)b[off + 5] << 8);
                if (cfgs != 1 || off + bl > coff + ctot) return -1;
                if (at != 0x02u || mx != 512) return -1;
                if (ea == M4_ADB_EP_OUT) { epo++; epn++; }
                else if (ea == M4_ADB_EP_IN) { epi++; epn++; }
                else return -1;
                if (epn > 2 || epo > 1 || epi > 1) return -1;
            }
        }
        off += bl;
    }
    if (off != n || cfgs != 1 || if2 != 1) return -1;
    if (coff != 18 || coff + ctot != n) return -1;
    if (epn != 2 || epo != 1 || epi != 1) return -1;
    return 0;
}
static int m4_classify_reply(const uint8_t *h, size_t hlen,
    const uint8_t *p, size_t plen)
{
    uint32_t cmd, a0, a1, ln, ck, mag, calc = 0;
    size_t i;
    if (!h || hlen != M4_ADB_HDR_LEN || plen > M4_ADB_MAXDATA) return -1;
    if (plen > 0 && !p) return -1;
    cmd = m4_le32_rd(h); a0 = m4_le32_rd(h + 4); a1 = m4_le32_rd(h + 8);
    ln = m4_le32_rd(h + 12); ck = m4_le32_rd(h + 16); mag = m4_le32_rd(h + 20);
    if (ln > M4_ADB_MAXDATA || ln != plen) return -1;
    if (mag != (cmd ^ 0xFFFFFFFFu)) return -1;
    for (i = 0; i < plen; i++) calc += p[i];
    if (calc != ck) return -1;
    if (cmd == M4_ADB_CMD_CNXN) {
        if (plen < 8 || memcmp(p, "device::", 8) != 0) return -1;
        return 1;
    }
    if (cmd == M4_ADB_CMD_AUTH) {
        if (a0 != 1 || a1 != 0 || plen != 20) return -1;
        return 2;
    }
    return -1;
}
int m4_adb_validate_descriptors(const uint8_t *b, size_t n)
{ return m4_validate_descriptors(b, n); }
size_t m4_adb_cnxn_request(uint8_t *o, size_t c)
{ return m4_cnxn_request(o, c); }
int m4_adb_classify_reply(const uint8_t *h, size_t hl, const uint8_t *p, size_t pl)
{ return m4_classify_reply(h, hl, p, pl); }
static void m4_build_hdr(uint8_t *h, uint32_t cmd, uint32_t a0,
    uint32_t a1, const uint8_t *p, size_t plen)
{
    m4_le32_wr(h, cmd); m4_le32_wr(h + 4, a0); m4_le32_wr(h + 8, a1);
    m4_le32_wr(h + 12, (uint32_t)plen);
    m4_le32_wr(h + 16, plen ? m4_sum(p, plen) : 0);
    m4_le32_wr(h + 20, cmd ^ 0xFFFFFFFFu);
}
static int m4_self_test(void)
{
    /* Synthetic valid descriptors: dev 18 + cfg 9 + if2 9 + ep 7 + ep 7. */
    static const uint8_t good[50] = {
        18, 1, 0x00, 0x02, 0, 0, 0, 64, 0x07, 0x22, 0x13, 0x00,
        0x00, 0x01, 1, 2, 3, 1,
        9, 2, 0x20, 0x00, 1, 1, 0, 0x80, 250,
        9, 4, 2, 0, 2, 0xFF, 0x42, 0x01, 0,
        7, 5, 0x04, 0x02, 0x00, 0x02, 0,
        7, 5, 0x85, 0x02, 0x00, 0x02, 0 };
    uint8_t req[32], hdr[24], pay[20], bad[50];
    size_t i;
    if (m4_cnxn_request(0, sizeof req) != 0) return 1;
    if (m4_cnxn_request(req, 30) != 0) return 1;
    if (m4_cnxn_request(req, sizeof req) != 31) return 1;
    if (m4_le32_rd(req) != M4_ADB_CMD_CNXN) return 1;
    if (m4_le32_rd(req + 4) != M4_ADB_VER) return 1;
    if (m4_le32_rd(req + 8) != 4096 || m4_le32_rd(req + 12) != 7) return 1;
    if (m4_le32_rd(req + 16) != 562) return 1;
    if (m4_le32_rd(req + 20) != (M4_ADB_CMD_CNXN ^ 0xFFFFFFFFu)) return 1;
    if (memcmp(req + 24, "host::", 6) != 0 || req[30] != 0) return 1;
    if (m4_validate_descriptors(good, sizeof good) != 0) return 1;
    memcpy(bad, good, sizeof bad); bad[8] = 0x34;
    if (m4_validate_descriptors(bad, sizeof bad) != -1) return 1;
    memcpy(bad, good, sizeof bad); bad[sizeof bad - 5] = 0x03;
    if (m4_validate_descriptors(bad, sizeof bad) != -1) return 1;
    if (m4_validate_descriptors(good, 10) != -1) return 1;
    memcpy(pay, "device::test123", 14);
    m4_build_hdr(hdr, M4_ADB_CMD_CNXN, M4_ADB_VER, 4096, pay, 14);
    if (m4_classify_reply(hdr, 24, pay, 14) != 1) return 1;
    for (i = 0; i < 20; i++) pay[i] = (uint8_t)i;
    m4_build_hdr(hdr, M4_ADB_CMD_AUTH, 1, 0, pay, 20);
    if (m4_classify_reply(hdr, 24, pay, 20) != 2) return 1;
    m4_build_hdr(hdr, M4_ADB_CMD_CNXN, M4_ADB_VER, 4096, pay, 14);
    if (m4_classify_reply(hdr, 23, pay, 14) != -1) return 1;
    if (m4_classify_reply(hdr, 24, pay, 13) != -1) return 1;
    hdr[20] ^= 0xFF;
    if (m4_classify_reply(hdr, 24, pay, 14) != -1) return 1;
    printf("M4 ADB identify self-test: OK\n");
    return 0;
}
static void m4_help(void)
{
    printf("m4_adb_identify - active identification only\n");
    printf("usage: m4_adb_identify --probe | --self-test | --help\n");
    printf("fixed USB 1-1 vid 2207 pid 0013, interface 2 ff/42/01\n");
    printf("bulk OUT 04 / IN 85, 512; interfaces 0/1 left alone\n");
    printf("sends one CNXN handshake (header 24 then payload 7, total 31)\n");
    printf("reads one reply in at most two transfers; no shell or authentication reply\n");
    printf("no follow-up frames are sent after the single handshake\n");
}
static int m4_probe(void);
int main(int argc, char **argv)
{
    if (argc != 2) {
        fputs("usage: m4_adb_identify --probe|--self-test|--help\n", stderr);
        return 2;
    }
    if (strcmp(argv[1], "--help") == 0) { m4_help(); return 0; }
    if (strcmp(argv[1], "--self-test") == 0) return m4_self_test();
    if (strcmp(argv[1], "--probe") == 0) return m4_probe();
    fputs("usage: m4_adb_identify --probe|--self-test|--help\n", stderr);
    return 2;
}
#if defined(_WIN32) || defined(_WIN64)
static int m4_probe(void)
{
    printf("status=unsupported\noutcome=unsupported\n");
    return 2;
}
#else
static volatile sig_atomic_t m4_sig = 0;
static void m4_on_sig(int s) { (void)s; m4_sig = 1; }
static int m4_elapsed_checked(const struct timespec *a, const struct timespec *b,
    long *out)
{
    long s, ns;
    if (!a || !b || !out) return -1;
    s = (long)(b->tv_sec - a->tv_sec);
    ns = (long)(b->tv_nsec - a->tv_nsec);
    if (s < 0 || (s == 0 && ns < 0)) return -1;
    *out = s * 1000L + ns / 1000000L;
    if (*out < 0) return -1;
    return 0;
}
static int m4_read_sysfs_u(const char *path, unsigned *out, int hex)
{
    char buf[32]; int fd; ssize_t r; size_t n, k; unsigned v = 0;
    if (!path || !out) return -1;
    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    r = read(fd, buf, sizeof buf - 1); close(fd);
    if (r <= 0 || r >= (ssize_t)sizeof buf) return -1;
    n = (size_t)r;
    if (n > 0 && buf[n - 1] == '\n') n--;
    if (n == 0 || n > 8) return -1;
    for (k = 0; k < n; k++) {
        char c = buf[k];
        if (hex) {
            unsigned d;
            if (c >= '0' && c <= '9') d = (unsigned)(c - '0');
            else if (c >= 'a' && c <= 'f') d = (unsigned)(c - 'a') + 10u;
            else if (c >= 'A' && c <= 'F') d = (unsigned)(c - 'A') + 10u;
            else return -1;
            if (v > 0xFFFFFFFu) return -1;
            v = (v << 4) | d;
        } else {
            if (c < '0' || c > '9' || v > 429496729u) return -1;
            v = v * 10u + (unsigned)(c - '0');
            if (v > 1000000u) return -1;
        }
    }
    *out = v; return 0;
}
static int m4_bulk(int fd, unsigned ep, uint8_t *d, unsigned len, int t)
{
    struct usbdevfs_bulktransfer bt;
    memset(&bt, 0, sizeof bt);
    bt.ep = ep; bt.len = len; bt.timeout = (unsigned)t; bt.data = d;
    return ioctl(fd, USBDEVFS_BULK, &bt);
}
static int m4_remain(const struct timespec *t0, long *last, int *t)
{
    struct timespec nw; long el; long rem;
    if (!t0 || !last || !t) return -1;
    if (clock_gettime(CLOCK_MONOTONIC, &nw) != 0) return -1;
    if (m4_elapsed_checked(t0, &nw, &el) != 0) return -1;
    if (el < *last) return -1;
    *last = el;
    rem = M4_ADB_MAX_MS - el;
    if (m4_sig || rem <= 0) return -1;
    *t = rem > 1000 ? 1000 : (int)rem;
    return 0;
}
static int m4_probe(void)
{
    struct timespec t0 = {0, 0}, now;
    struct sigaction sa;
    unsigned vid = 0, pid = 0, bus = 0, devn = 0;
    char usbpath[32]; int fd = -1, claimed = 0, released = 0;
    int out_calls = 0, rx_calls = 0, txbytes = 0, rc, ret, timeout;
    long readbytes = 0, elapsed = -1, last = 0;
    uint8_t dbuf[M4_ADB_DESC_MAX], req[M4_ADB_REQ_LEN], hdr[24];
    uint8_t pay[M4_ADB_MAXDATA];
    ssize_t dr = -1; unsigned plen = 0;
    const char *status = "error", *outcome = "error";
    memset(&sa, 0, sizeof sa); sa.sa_handler = m4_on_sig;
    sigaction(SIGINT, &sa, 0); sigaction(SIGTERM, &sa, 0);
    if (clock_gettime(CLOCK_MONOTONIC, &t0) != 0) {
        status = "error_timeout"; goto done; }
    if (m4_read_sysfs_u(M4_ADB_SYS_BASE "/idVendor", &vid, 1) != 0 ||
        m4_read_sysfs_u(M4_ADB_SYS_BASE "/idProduct", &pid, 1) != 0 ||
        m4_read_sysfs_u(M4_ADB_SYS_BASE "/busnum", &bus, 0) != 0 ||
        m4_read_sysfs_u(M4_ADB_SYS_BASE "/devnum", &devn, 0) != 0) {
        status = "error_sysfs"; goto done; }
    if (vid != M4_ADB_VID || pid != M4_ADB_PID ||
        bus < 1 || bus > 255 || devn < 1 || devn > 255) {
        status = "error_nomatch"; goto done; }
    snprintf(usbpath, sizeof usbpath, "/dev/bus/usb/%03u/%03u", bus, devn);
    fd = open(usbpath, O_RDWR | O_CLOEXEC);
    if (fd < 0) { status = "error_open"; goto done; }
    dr = read(fd, dbuf, sizeof dbuf);
    if (dr < 18 || dr > (ssize_t)sizeof dbuf) { status = "error_descriptors"; goto done; }
    readbytes = (long)dr;
    if (m4_validate_descriptors(dbuf, (size_t)dr) != 0) {
        status = "error_descriptors"; goto done; }
    if (m4_remain(&t0, &last, &timeout) != 0) { status = "error_timeout"; goto done; }
    { unsigned int ifno = M4_ADB_IFACE;
        if (ioctl(fd, USBDEVFS_CLAIMINTERFACE, &ifno) != 0) {
            status = "error_claim"; goto done; }
        claimed = 1; }
    if (m4_cnxn_request(req, sizeof req) != M4_ADB_REQ_LEN) {
        status = "error_internal"; goto done; }
    if (m4_remain(&t0, &last, &timeout) != 0) { status = "error_timeout"; goto done; }
    ret = m4_bulk(fd, M4_ADB_EP_OUT, req, 24, timeout);
    out_calls++;
    if (ret > 0) txbytes += ret;
    if (ret != 24) {
        status = (ret < 0 && (errno == ETIMEDOUT || m4_sig)) ?
            "error_timeout" : "error_short"; goto done; }
    /* Deadline guard: never blind-retry a partial handshake. */
    if (m4_remain(&t0, &last, &timeout) != 0) { status = "error_timeout"; goto done; }
    ret = m4_bulk(fd, M4_ADB_EP_OUT, req + 24, 7, timeout);
    out_calls++;
    if (ret > 0) txbytes += ret;
    if (ret != 7) {
        status = (ret < 0 && (errno == ETIMEDOUT || m4_sig)) ?
            "error_timeout" : "error_short"; goto done; }
    if (m4_remain(&t0, &last, &timeout) != 0) { status = "error_timeout"; goto done; }
    ret = m4_bulk(fd, M4_ADB_EP_IN, hdr, 24, timeout);
    rx_calls++; if (ret > 0) readbytes += ret;
    if (ret != 24) {
        status = (ret < 0 && (errno == ETIMEDOUT || m4_sig)) ?
            "error_timeout" : "error_short"; goto done; }
    plen = m4_le32_rd(hdr + 12);
    if (plen > M4_ADB_MAXDATA) { status = "error_reply"; goto done; }
    { uint32_t hcmd = m4_le32_rd(hdr), hmag = m4_le32_rd(hdr + 20);
        if (hmag != (hcmd ^ 0xFFFFFFFFu) ||
            (hcmd != M4_ADB_CMD_CNXN && hcmd != M4_ADB_CMD_AUTH) ||
            (hcmd == M4_ADB_CMD_AUTH && (plen != 20 || m4_le32_rd(hdr + 4) != 1 || m4_le32_rd(hdr + 8) != 0))) {
            status = "error_reply"; goto done; } }
    if (plen > 0) {
        if (m4_remain(&t0, &last, &timeout) != 0) { status = "error_timeout"; goto done; }
        ret = m4_bulk(fd, M4_ADB_EP_IN, pay, plen, timeout);
        rx_calls++; if (ret > 0) readbytes += ret;
        if (ret != (int)plen) {
            status = (ret < 0 && (errno == ETIMEDOUT || m4_sig)) ?
                "error_timeout" : "error_short"; goto done; }
    }
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0 ||
        m4_elapsed_checked(&t0, &now, &elapsed) != 0 ||
        elapsed < last || elapsed > M4_ADB_MAX_MS) {
        status = "error_timeout"; goto done; }
    last = elapsed;
    rc = m4_classify_reply(hdr, sizeof hdr, pay, plen);
    if (rc == 1) {
        status = "cnxn_identified"; outcome = "identified"; goto release; }
    if (rc == 2) {
        status = "authentication_required"; outcome = "auth_stop"; goto release; }
    status = "error_reply";
done:
release:
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0 ||
        m4_elapsed_checked(&t0, &now, &elapsed) != 0 || elapsed < last) {
        status = "error_timeout"; outcome = "error"; elapsed = last; }
    else last = elapsed;
    if (elapsed > M4_ADB_MAX_MS) { status = "error_timeout"; outcome = "error"; }
    if (claimed) {
        unsigned int ifno = M4_ADB_IFACE;
        if (ioctl(fd, USBDEVFS_RELEASEINTERFACE, &ifno) != 0) {
            status = "error_release"; outcome = "error"; }
        else released = 1; }
    if (fd >= 0) close(fd);
    printf("status=%s\npayload_len=%u\n", status, plen);
    printf("txbytes=%d\nout_calls=%d\nrxcalls=%d\nreadbytes=%ld\n",
        txbytes, out_calls, rx_calls, readbytes);
    printf("elapsed_ms=%ld\nclaimed=%d\nreleased=%d\noutcome=%s\n",
        elapsed, claimed, released, outcome);
    return (outcome[0] == 'i' || outcome[0] == 'a') ? 0 : 1;
}
#endif
