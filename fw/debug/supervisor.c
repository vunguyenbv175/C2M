#define _POSIX_C_SOURCE 200809L
#ifndef _WIN32
#define _DEFAULT_SOURCE
#endif
#include "supervisor.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>

#ifndef _WIN32
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <pwd.h>
#include <dirent.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#ifdef __linux__
#include <linux/wireless.h>
#ifndef IW_MODE_MASTER
#define IW_MODE_MASTER 1
#endif
#endif
#endif

/* ---------- pure helpers (portable) ---------- */

static int is_b64char(char c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
           (c >= '0' && c <= '9') || c == '+' || c == '/';
}

static int b64_value(char c, unsigned *v)
{
    if (c >= 'A' && c <= 'Z') { *v = (unsigned)(c - 'A'); return 0; }
    if (c >= 'a' && c <= 'z') { *v = (unsigned)(c - 'a' + 26); return 0; }
    if (c >= '0' && c <= '9') { *v = (unsigned)(c - '0' + 52); return 0; }
    if (c == '+') { *v = 62; return 0; }
    if (c == '/') { *v = 63; return 0; }
    return -1;
}

/* Strict decode: no padding, len must be multiple of 4. */
static int b64_decode_strict(const char *in, size_t len,
                             unsigned char *out, size_t cap, size_t *outlen)
{
    size_t i, o = 0;
    if (len == 0 || (len % 4) != 0) return -1;
    if (cap < (len / 4) * 3) return -1;
    for (i = 0; i < len; i += 4) {
        unsigned a, b, c, d;
        unsigned long triple;
        if (!is_b64char(in[i]) || !is_b64char(in[i + 1]) ||
            !is_b64char(in[i + 2]) || !is_b64char(in[i + 3])) return -1;
        if (b64_value(in[i], &a) || b64_value(in[i + 1], &b) ||
            b64_value(in[i + 2], &c) || b64_value(in[i + 3], &d)) return -1;
        triple = (a << 18) | (b << 12) | (c << 6) | d;
        out[o++] = (unsigned char)((triple >> 16) & 0xff);
        out[o++] = (unsigned char)((triple >> 8) & 0xff);
        out[o++] = (unsigned char)(triple & 0xff);
    }
    *outlen = o;
    return 0;
}

static unsigned long long fnv1a64(const unsigned char *p, size_t n)
{
    unsigned long long h = 14695981039346656037ULL;
    size_t i;
    for (i = 0; i < n; i++) {
        h ^= (unsigned long long)p[i];
        h *= 1099511628211ULL;
    }
    return h;
}

static void fp_to_hex(unsigned long long h, char out[17])
{
    static const char *digits = "0123456789abcdef";
    int i;
    for (i = 15; i >= 0; i--) {
        out[i] = digits[h & 0xf];
        h >>= 4;
    }
    out[16] = 0;
}

static unsigned get_be32(const unsigned char *p)
{
    return ((unsigned)p[0] << 24) | ((unsigned)p[1] << 16) |
           ((unsigned)p[2] << 8) | (unsigned)p[3];
}

int c2m_debug_parse_owner(const char *line, char fp_out[17])
{
    static const char prefix[] = "ssh-ed25519 ";
    const char *keystart;
    const char *keyend;
    const char *comment = NULL;
    size_t keylen, linelen, i;
    unsigned char raw[64];
    size_t rawlen = 0;
    unsigned long long h;
    if (!line || !fp_out) return -1;
    linelen = strlen(line);
    if (linelen == 0 || linelen > 1024) return -1;
    for (i = 0; i < linelen; i++) {
        unsigned char c = (unsigned char)line[i];
        if (c < 0x20 || c > 0x7e) return -1;
    }
    if (memchr(line, '\r', linelen) || memchr(line, '\n', linelen)) return -1;
    if (strncmp(line, prefix, sizeof(prefix) - 1)) return -1;
    if (line[sizeof(prefix) - 1] == ' ' || line[sizeof(prefix) - 1] == 0) return -1;
    keystart = line + sizeof(prefix) - 1;
    keyend = strchr(keystart, ' ');
    if (keyend) {
        /* Exactly one space before an optional single-token comment. */
        if (keyend == keystart) return -1;
        if (keyend[1] == 0 || keyend[1] == ' ') return -1;
        if (strchr(keyend + 1, ' ')) return -1;
        comment = keyend + 1;
        if (strlen(comment) == 0 || strlen(comment) > 256) return -1;
        for (i = 0; comment[i]; i++) {
            unsigned char c = (unsigned char)comment[i];
            if (c < 0x21 || c > 0x7e) return -1;
        }
    } else {
        keyend = keystart + strlen(keystart);
    }
    keylen = (size_t)(keyend - keystart);
    /* 51 raw bytes -> 68 base64 chars, no padding. */
    if (keylen != 68) return -1;
    if (memchr(keystart, '=', keylen)) return -1;
    {
        char tmp[69];
        memcpy(tmp, keystart, 68);
        tmp[68] = 0;
        if (b64_decode_strict(tmp, 68, raw, sizeof(raw), &rawlen)) return -1;
    }
    if (rawlen != 51) return -1;
    if (get_be32(raw) != 11) return -1;
    if (memcmp(raw + 4, "ssh-ed25519", 11)) return -1;
    if (get_be32(raw + 15) != 32) return -1;
    h = fnv1a64(raw + 19, 32);
    fp_to_hex(h, fp_out);
    {
        volatile unsigned char *v = raw;
        for (i = 0; i < sizeof(raw); i++) v[i] = 0;
    }
    return 0;
}

static int valid_state(const char *s)
{
    return s && (!strcmp(s, "inactive") || !strcmp(s, "starting") ||
                 !strcmp(s, "active") || !strcmp(s, "expired") ||
                 !strcmp(s, "failed"));
}

static int valid_reason(const char *s)
{
    size_t i, n;
    if (!s) return 0;
    n = strlen(s);
    if (n == 0 || n > 64) return 0;
    for (i = 0; i < n; i++) {
        char c = s[i];
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_'))
            return 0;
    }
    return 1;
}

static int valid_bind(const char *addr, int port, int loopback)
{
    if (!addr || port < 1 || port > 65535) return 0;
    if (loopback) return !strcmp(addr, C2M_DEBUG_LOOPBACK_ADDR);
    return !strcmp(addr, C2M_DEBUG_BIND_ADDR);
}

/* Pure production gate: any override flag is invalid without an explicit
 * --loopback-test, regardless of flag order. No filesystem/network I/O. */
int c2m_debug_cli_valid(int loopback, int any_override, const char *bind,
                        int port, int window_sec, int poll_ms)
{
    if (port < 1 || port > 65535) return 0;
    if (window_sec < 1 || window_sec > 86400) return 0;
    if (poll_ms < 50 || poll_ms > 5000) return 0;
    if (!valid_bind(bind, port, loopback)) return 0;
    if (any_override && !loopback) return 0;
    return 1;
}

/* Pure stock-ancestor table (uid/gid/mode integers only, no stat calls),
 * so self-test covers it portably with vectors. Facts: EN cpio has /tmp,
 * /var, /customer at 0775 1001:1001; / has no entry (kernel default 0755
 * root:root); customer UBIFS flashes /customer as 0755 chown 1001. */
int c2m_debug_stock_path_ok(const char *path, unsigned uid, unsigned gid,
                            unsigned mode)
{
    int known;
    if (!path) return 0;
    known = (uid == 0 || uid == 1000 || uid == 1001) &&
            (gid == 0 || gid == 1000 || gid == 1001);
    if (!strcmp(path, "/"))
        return uid == 0 && gid == 0 && mode == 0755;
    if (!strcmp(path, "/tmp") || !strcmp(path, "/var")) {
        if (mode == 0775)
            return uid == 1001 && gid == 1001; /* actual cpio fact */
        return uid == 0 && gid == 0 && mode == 0755;
    }
    if (!strcmp(path, "/customer")) {
        if (mode == 0775)
            return uid == 1001 && gid == 1001; /* actual cpio fact */
        return known && mode == 0755; /* UBIFS flash fact + legacy */
    }
    if (!strcmp(path, "/customer/minieye") ||
        !strcmp(path, "/customer/minieye/config"))
        return known && (mode == 0755 || mode == 0775);
    if (!strcmp(path, "/customer/c2m"))
        return uid == 1001 && gid == 1001 && mode == 0755;
    return 0;
}
/* ---------- self-test (pure, no I/O beyond printf) ---------- */

static void b64_encode_block(const unsigned char *in, size_t n, char *out)
{
    static const char *tab =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    unsigned long t = 0;
    size_t i;
    for (i = 0; i < n; i++) t = (t << 8) | in[i];
    /* n is always 3 here (51 = 17*3). */
    out[0] = tab[(t >> 18) & 0x3f];
    out[1] = tab[(t >> 12) & 0x3f];
    out[2] = tab[(t >> 6) & 0x3f];
    out[3] = tab[t & 0x3f];
}

static int check(const char *name, int cond, int *failures)
{
    if (!cond) {
        fprintf(stderr, "FAIL %s\n", name);
        (*failures)++;
        return -1;
    }
    printf("PASS %s\n", name);
    return 0;
}

int c2m_debug_self_test(void)
{
    int failures = 0;
    /* Build a deterministic valid key: 32 bytes of 0x01..0x20. */
    unsigned char raw[51];
    char b64[69];
    char line[1100];
    char fp1[17], fp2[17];
    size_t i, o = 0;
    raw[0] = 0; raw[1] = 0; raw[2] = 0; raw[3] = 11;
    memcpy(raw + 4, "ssh-ed25519", 11);
    raw[15] = 0; raw[16] = 0; raw[17] = 0; raw[18] = 32;
    for (i = 0; i < 32; i++) raw[19 + i] = (unsigned char)(i + 1);
    for (i = 0; i < 51; i += 3) {
        char blk[4];
        b64_encode_block(raw + i, 3, blk);
        memcpy(b64 + o, blk, 4);
        o += 4;
    }
    b64[68] = 0;

    snprintf(line, sizeof(line), "ssh-ed25519 %s test-key_1", b64);
    check("owner_valid_with_comment", c2m_debug_parse_owner(line, fp1) == 0, &failures);
    {
        char bare[128];
        snprintf(bare, sizeof(bare), "ssh-ed25519 %s", b64);
        check("owner_valid_bare", c2m_debug_parse_owner(bare, fp2) == 0, &failures);
        check("owner_fp_stable", !strcmp(fp1, fp2), &failures);
        check("owner_fp_hex",
              strlen(fp1) == 16 &&
                  strspn(fp1, "0123456789abcdef") == 16,
              &failures);
    }
    {
        char bad[1100];
        snprintf(bad, sizeof(bad), "ssh-rsa %s comment", b64);
        check("owner_wrong_type_rejected", c2m_debug_parse_owner(bad, fp2) != 0, &failures);
        snprintf(bad, sizeof(bad), "ssh-ed25519 %s", "AAA");
        check("owner_short_rejected", c2m_debug_parse_owner(bad, fp2) != 0, &failures);
        snprintf(bad, sizeof(bad), "ssh-ed25519 %s!", b64);
        /* '!' is not base64; length becomes 69 -> rejected. */
        check("owner_bad_char_rejected", c2m_debug_parse_owner(bad, fp2) != 0, &failures);
        snprintf(bad, sizeof(bad), "ssh-ed25519  %s", b64);
        check("owner_double_space_rejected", c2m_debug_parse_owner(bad, fp2) != 0, &failures);
        snprintf(bad, sizeof(bad), "ssh-ed25519 %s ", b64);
        check("owner_trailing_space_rejected", c2m_debug_parse_owner(bad, fp2) != 0, &failures);
        snprintf(bad, sizeof(bad), "ssh-ed25519 %s a b", b64);
        check("owner_comment_space_rejected", c2m_debug_parse_owner(bad, fp2) != 0, &failures);
        snprintf(bad, sizeof(bad), "ssh-ed25519 %s\n", b64);
        check("owner_newline_rejected", c2m_debug_parse_owner(bad, fp2) != 0, &failures);
        check("owner_empty_rejected", c2m_debug_parse_owner("", fp2) != 0, &failures);
        check("owner_null_rejected", c2m_debug_parse_owner(NULL, fp2) != 0, &failures);
        /* Corrupt one raw byte through the base64 layer. */
        {
            char mutated[69];
            memcpy(mutated, b64, 69);
            mutated[0] = (mutated[0] == 'A') ? 'B' : 'A';
            snprintf(bad, sizeof(bad), "ssh-ed25519 %s", mutated);
            check("owner_bad_prefix_rejected", c2m_debug_parse_owner(bad, fp2) != 0, &failures);
        }
    }
    check("state_enum", valid_state("inactive") && valid_state("starting") &&
                               valid_state("active") && valid_state("expired") &&
                               valid_state("failed") && !valid_state("running") &&
                               !valid_state("running_unverified") &&
                               !valid_state("") && !valid_state(NULL),
          &failures);
    check("starting_reason_token",
          valid_reason("process_running_listener_unverified") &&
              valid_reason("listener_unverified"),
          &failures);
    check("reason_tokens", valid_reason("window_expired") &&
                               valid_reason("ap_changed_or_unverifiable") &&
                               !valid_reason("") && !valid_reason("has space") &&
                               !valid_reason("UPPER") && !valid_reason(NULL),
          &failures);
    check("bind_production", valid_bind("192.168.1.1", 2222, 0) &&
                                 !valid_bind("127.0.0.1", 2222, 0) &&
                                 !valid_bind("0.0.0.0", 2222, 0) &&
                                 !valid_bind("192.168.1.1", 0, 0),
          &failures);
    check("bind_loopback", valid_bind("127.0.0.1", 2222, 1) &&
                               valid_bind("127.0.0.1", 2223, 1) &&
                               !valid_bind("192.168.1.1", 2222, 1) &&
                               !valid_bind("0.0.0.0", 2222, 1),
          &failures);
    check("window_bounds", !(1200 < 1 || 1200 > 86400) && (0 < 1 || 0 > 86400) &&
                               (99999 > 86400),
          &failures);
    /* Production CLI gate: no I/O, order-independent by construction
     * (caller passes one any_override bit for all fixture flags). */
    check("cli_production_defaults",
          c2m_debug_cli_valid(0, 0, "192.168.1.1", 2222, 1200, 1000),
          &failures);
    check("cli_override_needs_loopback",
          !c2m_debug_cli_valid(0, 1, "192.168.1.1", 2222, 1200, 1000),
          &failures);
    check("cli_ap_bypass_rejected_without_loopback",
          !c2m_debug_cli_valid(0, 1, "192.168.1.1", 2222, 1200, 100),
          &failures);
    check("cli_override_accepted_with_loopback",
          c2m_debug_cli_valid(1, 1, "127.0.0.1", 2223, 2, 100),
          &failures);
    check("cli_loopback_wrong_bind_rejected",
          !c2m_debug_cli_valid(1, 1, "192.168.1.1", 2222, 2, 100) &&
              !c2m_debug_cli_valid(1, 0, "192.168.1.1", 2222, 1200, 1000),
          &failures);
    check("cli_bad_bounds_rejected",
          !c2m_debug_cli_valid(1, 1, "127.0.0.1", 0, 2, 100) &&
              !c2m_debug_cli_valid(1, 1, "127.0.0.1", 2222, 0, 100) &&
              !c2m_debug_cli_valid(1, 1, "127.0.0.1", 2222, 2, 49) &&
              !c2m_debug_cli_valid(1, 1, NULL, 2222, 2, 100),
          &failures);
    /* Stock table vectors from actual EN cpio facts (/tmp,/var,/customer
     * 0775 1001:1001; / kernel default 0755 root; UBIFS /customer 0755). */
    check("stock_root",
          c2m_debug_stock_path_ok("/", 0, 0, 0755) &&
              !c2m_debug_stock_path_ok("/", 0, 0, 0775) &&
              !c2m_debug_stock_path_ok("/", 1001, 1001, 0775) &&
              !c2m_debug_stock_path_ok(NULL, 0, 0, 0755) &&
              !c2m_debug_stock_path_ok("", 0, 0, 0755),
          &failures);
    check("stock_tmp_cpio_fact",
          c2m_debug_stock_path_ok("/tmp", 1001, 1001, 0775) &&
              c2m_debug_stock_path_ok("/tmp", 0, 0, 0755) &&
              !c2m_debug_stock_path_ok("/tmp", 1001, 1001, 0755) &&
              !c2m_debug_stock_path_ok("/tmp", 1000, 1000, 0775) &&
              !c2m_debug_stock_path_ok("/tmp", 0, 0, 0775) &&
              !c2m_debug_stock_path_ok("/tmp", 1001, 1001, 0777),
          &failures);
    check("stock_var_cpio_fact",
          c2m_debug_stock_path_ok("/var", 1001, 1001, 0775) &&
              c2m_debug_stock_path_ok("/var", 0, 0, 0755) &&
              !c2m_debug_stock_path_ok("/var", 1001, 1001, 0755) &&
              !c2m_debug_stock_path_ok("/var", 1001, 1001, 0777),
          &failures);
    check("stock_customer_both_facts",
          c2m_debug_stock_path_ok("/customer", 1001, 1001, 0775) &&
              c2m_debug_stock_path_ok("/customer", 1001, 1001, 0755) &&
              c2m_debug_stock_path_ok("/customer", 0, 0, 0755) &&
              c2m_debug_stock_path_ok("/customer", 1000, 1000, 0755) &&
              !c2m_debug_stock_path_ok("/customer", 1000, 1000, 0775) &&
              !c2m_debug_stock_path_ok("/customer", 1001, 1001, 0777),
          &failures);
    check("stock_package_exact_preserved",
          c2m_debug_stock_path_ok("/customer/c2m", 1001, 1001, 0755) &&
              c2m_debug_stock_path_ok("/customer/minieye/config", 1001,
                                      1001, 0775) &&
              !c2m_debug_stock_path_ok("/customer/c2m", 1001, 1001,
                                       0775) &&
              !c2m_debug_stock_path_ok("/customer/c2m", 0, 0, 0755) &&
              !c2m_debug_stock_path_ok("/etc", 0, 0, 0755),
          &failures);

    if (failures) {
        printf("c2m-debug self-test: FAILED\n");
        return 1;
    }
    printf("c2m-debug self-test: OK\n");
    return 0;
}

static void usage(FILE *f)
{
    fputs("Usage: c2m-debug --help | --self-test | --serve [options]\n"
          "  --serve production: fixed AP-only paths, root required.\n"
          "    Any override flag requires an explicit --loopback-test,\n"
          "    in any flag order; otherwise exit 2 with no I/O.\n"
          "  Test-only overrides (need --loopback-test): --dropbear PATH\n"
          "    --dropbearkey PATH --owner-pub PATH --run-dir DIR\n"
          "    --config-dir DIR --status-file FILE --bind ADDR --port N\n"
          "    --window-sec N --poll-ms N --ap-state-file PATH\n"
          "  --loopback-test binds 127.0.0.1 (no wlan0/radio), permits\n"
          "  non-root fixtures and omits -l wlan0. --ap-state-file with\n"
          "  content \"up\" simulates a valid AP without radio.\n"
          "  Status is starting until OUR child provably holds the bound\n"
          "  listener (/proc/net/tcp inode in the child PID fd set); only\n"
          "  then is active published. Startup AP readiness retries up to\n"
          "  60 s inside the overall 20-minute window.\n",
          f);
}

#ifdef _WIN32
int main(int argc, char **argv)
{
    int i;
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        usage(stdout);
        return 0;
    }
    if (argc == 2 && !strcmp(argv[1], "--self-test")) return c2m_debug_self_test();
    if (argc >= 2 && !strcmp(argv[1], "--serve")) {
        fputs("c2m-debug: --serve is Linux-only and unsupported on Windows\n", stderr);
        return 2;
    }
    (void)i;
    usage(stderr);
    return 2;
}
#else /* Linux / POSIX serve below */

/* ---------- Linux serve implementation ---------- */

static volatile sig_atomic_t g_stop;

static void on_signal(int sig)
{
    (void)sig;
    g_stop = 1;
}

/* Forward: verified group signaling (defined with stop_group below). */
static void signal_group(pid_t leader, int sig);

struct serve_cfg {
    const char *dropbear;
    const char *dropbearkey;
    const char *owner_pub;
    const char *run_dir;
    const char *config_dir;
    const char *status_file;
    const char *ap_state_file;
    const char *bind_addr;
    int port;
    int window_sec;
    int poll_ms;
    int loopback;
};

static int64_t now_ms(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static void wipe(void *p, size_t n)
{
    volatile unsigned char *v = p;
    while (n--) *v++ = 0;
}

static int absolute_path(const char *in, char *out, size_t size)
{
    char cwd[PATH_MAX];
    int n;
    if (!in || !in[0] || strchr(in, '\n') || strchr(in, '\r')) return -1;
    if (in[0] == '/') n = snprintf(out, size, "%s", in);
    else {
        if (!getcwd(cwd, sizeof(cwd))) return -1;
        n = snprintf(out, size, "%s/%s", cwd, in);
    }
    return (n < 0 || (size_t)n >= size) ? -1 : 0;
}

/* Stock-ancestor trust policy, driven by ACTUAL EN rootfs cpio facts
 * (parent-parsed image: cpio entries /tmp 0775 1001:1001,
 * /var 0775 1001:1001, /customer 0775 1001:1001; demo.sh may tmpfs-mount
 * /tmp differently, which this table does NOT chase -- the cpio fact is
 * accepted, demo mounts stay covered only by the generic sticky-root
 * rule below). / has no cpio entry (archive starts at dev); the kernel
 * rootfs default is 0755 root:root, so / stays exactly that, unchanged.
 * Customer UBIFS is produced by mkfs from an input tree with 0755 chown
 * 1001, so on flash /customer is actually 0755; both 0755 and the 0775
 * cpio fact are accepted and documented here for the parent doc record.
 * This trusts the vendor UID set, not a hardened multiuser boundary:
 * the camera already runs vendor code as root and uid 1001.
 * Ancestors are never chmodded and intermediate ancestors never created.
 * /tmp stickiness is NOT broadened here: any non-sticky
 * group/other-writable ancestor outside this exact table still fails
 * closed; the parent checks rootfs metadata separately. */
static int stock_trusted_ancestor(const char *path, const struct stat *st)
{
    return c2m_debug_stock_path_ok(path, (unsigned)st->st_uid,
                                   (unsigned)st->st_gid,
                                   (unsigned)(st->st_mode & 07777));
}

/* Package-asset ownership: root, the running euid (loopback fixtures),
 * or exactly the stock 1000:1000 / 1001:1001 pair. */
static int pkg_asset_uid_ok(uid_t u, gid_t g)
{
    if (u == 0 || u == geteuid()) return 1;
    return (u == 1000 && g == 1000) || (u == 1001 && g == 1001);
}

/* Reject symlink components; only root sticky-writable or exact stock
 * ancestors may be group/other-writable. Never creates ancestors. */
static int safe_dir(const char *path, int private_leaf, int create)
{
    char copy[PATH_MAX], walk[PATH_MAX] = "";
    char *part, *save;
    struct stat st;
    int fd, next;
    if (absolute_path(path, copy, sizeof(copy))) return -1;
    fd = open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    if (fstat(fd, &st) || !S_ISDIR(st.st_mode) ||
        !stock_trusted_ancestor("/", &st)) goto fail;
    part = strtok_r(copy, "/", &save);
    /* Absolute path "/" itself: nothing to walk. */
    if (!part) {
        if (private_leaf) {
            close(fd);
            return -1;
        }
        return fd;
    }
    while (part) {
        char *after = strtok_r(NULL, "/", &save);
        if (!strcmp(part, ".") || !strcmp(part, "..")) goto fail;
        next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (next < 0 && errno == ENOENT && !after && create) {
            if (mkdirat(fd, part, 0700)) goto fail;
            next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        }
        if (next < 0) goto fail;
        close(fd);
        fd = next;
        {
            size_t used = strlen(walk), avail = sizeof(walk) - used;
            int len = snprintf(walk + used, avail, "/%s", part);
            if (len < 0 || (size_t)len >= avail) goto fail;
        }
        if (fstat(fd, &st) || (st.st_uid != 0 && st.st_uid != geteuid() &&
                               !stock_trusted_ancestor(walk, &st)))
            goto fail;
        if ((st.st_mode & 0022) && !(st.st_uid == 0 && (st.st_mode & S_ISVTX)) &&
            !stock_trusted_ancestor(walk, &st))
            goto fail;
        if (!after && private_leaf &&
            (st.st_uid != geteuid() || (st.st_mode & 0777) != 0700))
            goto fail;
        part = after;
    }
    if (private_leaf &&
        (fstat(fd, &st) || st.st_uid != geteuid() || (st.st_mode & 0777) != 0700))
        goto fail;
    return fd;
fail:
    close(fd);
    return -1;
}

static int private_file_ok(int fd, mode_t want_mode, size_t max)
{
    struct stat st;
    if (fstat(fd, &st)) return -1;
    if (!S_ISREG(st.st_mode)) return -1;
    if (st.st_uid != geteuid()) return -1;
    if ((st.st_mode & 0777) != want_mode) return -1;
    if (st.st_nlink != 1) return -1;
    if (st.st_size < 0 || (uint64_t)st.st_size > max) return -1;
    return 0;
}

/* Walk an absolute file's parent dirs with O_NOFOLLOW, reusing safe_dir
 * so asset/key files cannot hide behind a symlink path component. */
static int parent_dirs_safe(const char *abs_path)
{
    char path[PATH_MAX], dir[PATH_MAX];
    const char *base;
    int dfd;
    if (absolute_path(abs_path, path, sizeof(path))) return -1;
    base = strrchr(path, '/');
    if (!base || !base[1]) return -1;
    if ((size_t)(base - path) >= sizeof(dir)) return -1;
    memcpy(dir, path, (size_t)(base - path));
    dir[base - path] = 0;
    if (!dir[0]) strcpy(dir, "/");
    dfd = safe_dir(dir, 0, 0);
    if (dfd < 0) return -1;
    close(dfd);
    return 0;
}

static int write_all(int fd, const void *data, size_t n)
{
    const unsigned char *p = data;
    while (n) {
        ssize_t r = write(fd, p, n);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return -1;
        p += (size_t)r;
        n -= (size_t)r;
    }
    return 0;
}

/* Atomically publish status. Status dir must already be safe; the file
 * itself is 0600 owned by euid. Never follows symlinks. */
static int publish_status(const struct serve_cfg *c, const char *state,
                          const char *reason, const char *fp)
{
    char path[PATH_MAX], tmp[96], dir[PATH_MAX], text[1024];
    const char *base;
    char bind[64];
    int dirfd = -1, fd = -1, rc = -1, n;
    static unsigned serial;
    struct stat st;
    if (!valid_state(state) || !valid_reason(reason)) return -1;
    if (!fp) fp = "none";
    if (strcmp(fp, "none") && (strlen(fp) != 16 ||
                               strspn(fp, "0123456789abcdef") != 16))
        return -1;
    if (snprintf(bind, sizeof(bind), "%s:%d", c->bind_addr, c->port) >= (int)sizeof(bind))
        return -1;
    if (absolute_path(c->status_file, path, sizeof(path))) return -1;
    base = strrchr(path, '/');
    if (!base || !base[1]) return -1;
    if ((size_t)(base - path) >= sizeof(dir)) return -1;
    memcpy(dir, path, (size_t)(base - path));
    dir[base - path] = 0;
    if (!dir[0]) strcpy(dir, "/");
    base++;
    dirfd = safe_dir(dir, 0, 0);
    if (dirfd < 0) return -1;
    if (!fstatat(dirfd, base, &st, AT_SYMLINK_NOFOLLOW)) {
        if (!S_ISREG(st.st_mode) || st.st_uid != geteuid() || st.st_nlink != 1) goto done;
    } else if (errno != ENOENT) goto done;
    snprintf(tmp, sizeof(tmp), ".c2m-debug-status-%ld-%u.tmp", (long)getpid(), ++serial);
    fd = openat(dirfd, tmp, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) goto done;
    n = snprintf(text, sizeof(text),
                 "version=1\nstate=%s\nreason=%s\nkey_fp=%s\nwindow_sec=%d\nbind=%s\n",
                 state, reason, fp, c->window_sec, bind);
    if (n < 0 || (size_t)n >= sizeof(text)) goto done;
    if (write_all(fd, text, (size_t)n) || fsync(fd)) goto done;
    if (renameat(dirfd, tmp, dirfd, base)) goto done;
    (void)fsync(dirfd);
    rc = 0;
done:
    if (fd >= 0) {
        close(fd);
        (void)unlinkat(dirfd, tmp, 0);
    }
    if (dirfd >= 0) close(dirfd);
    wipe(text, sizeof(text));
    return rc;
}

/* AP gate. Production: wlan0 must be MASTER+UP, 192.168.1.1/255.255.255.0.
 * Fixture: --ap-state-file with exact "up" means valid. Loopback without a
 * fixture file skips the radio gate (binds loopback, no -l wlan0). */
static int ap_valid(const struct serve_cfg *c)
{
    if (c->ap_state_file) {
        char buf[64];
        int fd;
        size_t used = 0;
        struct stat st;
        fd = open(c->ap_state_file, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0) return -1;
        if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_nlink != 1) {
            close(fd);
            return -1;
        }
        while (used < sizeof(buf) - 1) {
            ssize_t r = read(fd, buf + used, sizeof(buf) - 1 - used);
            if (r < 0 && errno == EINTR) continue;
            if (r < 0) {
                close(fd);
                return -1;
            }
            if (!r) break;
            used += (size_t)r;
        }
        close(fd);
        buf[used] = 0;
        if (!strcmp(buf, "up\n") || !strcmp(buf, "up")) return 0;
        return -1;
    }
    if (c->loopback) return 0;
#ifdef __linux__
    {
        int fd;
        struct ifreq iface;
#ifdef SIOCGIWMODE
        struct iwreq wireless;
#endif
        struct in_addr want, mask;
        fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
        if (fd < 0) return -1;
#ifdef SIOCGIWMODE
        memset(&wireless, 0, sizeof(wireless));
        strcpy(wireless.ifr_name, C2M_DEBUG_IFACE);
        if (ioctl(fd, SIOCGIWMODE, &wireless) < 0 ||
            wireless.u.mode != IW_MODE_MASTER) {
            close(fd);
            return -1;
        }
#else
        close(fd);
        return -1;
#endif
        memset(&iface, 0, sizeof(iface));
        strcpy(iface.ifr_name, C2M_DEBUG_IFACE);
        if (ioctl(fd, SIOCGIFFLAGS, &iface) < 0 ||
            !(iface.ifr_flags & IFF_UP) || (iface.ifr_flags & IFF_LOOPBACK)) {
            close(fd);
            return -1;
        }
        if (ioctl(fd, SIOCGIFADDR, &iface) < 0 ||
            iface.ifr_addr.sa_family != AF_INET) {
            close(fd);
            return -1;
        }
        want = ((struct sockaddr_in *)&iface.ifr_addr)->sin_addr;
        if (ioctl(fd, SIOCGIFNETMASK, &iface) < 0 ||
            iface.ifr_netmask.sa_family != AF_INET) {
            close(fd);
            return -1;
        }
        mask = ((struct sockaddr_in *)&iface.ifr_netmask)->sin_addr;
        close(fd);
        if (want.s_addr != inet_addr(C2M_DEBUG_BIND_ADDR)) return -1;
        if (mask.s_addr != inet_addr("255.255.255.0")) return -1;
        return 0;
    }
#else
    return -1;
#endif
}

static int trusted_exec(const char *path)
{
    struct stat lst, st;
    int fd;
    if (!path || !path[0] || path[0] != '/') return -1;
    if (strchr(path, '\n') || strchr(path, '\r')) return -1;
    if (lstat(path, &lst) || !S_ISREG(lst.st_mode) || lst.st_nlink != 1) return -1;
    if ((lst.st_mode & 0022)) return -1;
    if (!(lst.st_mode & 0111)) return -1;
    if (!pkg_asset_uid_ok(lst.st_uid, lst.st_gid)) return -1;
    if (parent_dirs_safe(path)) return -1;
    fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_nlink != 1 ||
        (st.st_mode & 0022) || lst.st_ino != st.st_ino || lst.st_dev != st.st_dev) {
        close(fd);
        return -1;
    }
    close(fd);
    return access(path, X_OK) ? -1 : 0;
}

/* The only auxiliary runtime module is an exact stock-glibc file pinned
 * by the image mutator. Never load from group-writable /customer/ssh/lib.
 * This check precedes getpwnam(), which is the first NSS lookup here. */
static int trusted_nss_module(void)
{
    const char *path = C2M_DEBUG_NSS_MODULE;
    struct stat before, after;
    int fd, ok;
    if (parent_dirs_safe(path) || lstat(path, &before) ||
        !S_ISREG(before.st_mode) || before.st_nlink != 1 ||
        !pkg_asset_uid_ok(before.st_uid, before.st_gid) ||
        (before.st_mode & 07777) != 0644 ||
        before.st_size != C2M_DEBUG_NSS_BYTES) return -1;
    fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    ok = !fstat(fd, &after) && after.st_ino == before.st_ino &&
        after.st_dev == before.st_dev && S_ISREG(after.st_mode) &&
        after.st_nlink == 1 && (after.st_mode & 07777) == 0644 &&
        after.st_size == C2M_DEBUG_NSS_BYTES &&
        pkg_asset_uid_ok(after.st_uid, after.st_gid);
    close(fd);
    return ok ? 0 : -1;
}

/* Read and validate the owner pubkey file. No key bytes are logged. */
static int read_owner(const char *path, char *lineout, size_t cap, char fp[17])
{
    int fd;
    struct stat st;
    ssize_t r;
    size_t used = 0;
    if (!path || path[0] != '/') return -1;
    if (lstat(path, &st) || !S_ISREG(st.st_mode) || st.st_nlink != 1) return -1;
    if ((st.st_mode & 0022)) return -1;
    if (!pkg_asset_uid_ok(st.st_uid, st.st_gid)) return -1;
    if (st.st_size <= 0 || (uint64_t)st.st_size > C2M_DEBUG_OWNER_MAX) return -1;
    if (parent_dirs_safe(path)) return -1;
    fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    {
        /* Owner pub is a package asset: exact ownership above, and never
         * group/other writes, symlinks, hardlinks, or special files. */
        struct stat fst;
        if (fstat(fd, &fst) || !S_ISREG(fst.st_mode) || fst.st_nlink != 1 ||
            (fst.st_mode & 0022) || fst.st_ino != st.st_ino ||
            fst.st_dev != st.st_dev || fst.st_uid != st.st_uid ||
            fst.st_gid != st.st_gid ||
            !pkg_asset_uid_ok(fst.st_uid, fst.st_gid)) {
            close(fd);
            return -1;
        }
        if (fst.st_size <= 0 || (uint64_t)fst.st_size > C2M_DEBUG_OWNER_MAX) {
            close(fd);
            return -1;
        }
    }
    while (used < cap - 1) {
        r = read(fd, lineout + used, cap - 1 - used);
        if (r < 0 && errno == EINTR) continue;
        if (r < 0) {
            close(fd);
            wipe(lineout, cap);
            return -1;
        }
        if (!r) break;
        used += (size_t)r;
    }
    close(fd);
    if (used >= cap - 1 || memchr(lineout, 0, used)) {
        wipe(lineout, cap);
        return -1;
    }
    lineout[used] = 0;
    /* Exactly one line; allow a single trailing LF from editors. */
    if (used && lineout[used - 1] == '\n') lineout[--used] = 0;
    if (!used || strchr(lineout, '\n') || strchr(lineout, '\r')) {
        wipe(lineout, cap);
        return -1;
    }
    if (c2m_debug_parse_owner(lineout, fp)) {
        wipe(lineout, cap);
        return -1;
    }
    return 0;
}

/* Validate an existing hostkey file (0600, owned by euid, single link). */
static int hostkey_ok(const char *path)
{
    struct stat lst;
    int fd;
    struct stat st;
    if (lstat(path, &lst) || !S_ISREG(lst.st_mode)) return -1;
    if (lst.st_nlink != 1) return -1;
    fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    if (private_file_ok(fd, 0600, 8192)) {
        close(fd);
        return -1;
    }
    if (fstat(fd, &st) || st.st_ino != lst.st_ino) {
        close(fd);
        return -1;
    }
    close(fd);
    return 0;
}

/* One-time hostkey generation via dropbearkey, no shell, bounded 15 s,
 * own process group, cleared environment. Temp names are unique per
 * pid+time+counter (up to 32 attempts); a pre-existing temp name is
 * skipped and never unlinked. Only the unique name this call reserved is
 * ever removed. Final install is atomic no-overwrite via link(). */
static int generate_hostkey(const char *dropbearkey, const char *final_path,
                           const char *config_dir, int configfd, int loopback)
{
    static unsigned hk_serial;
    int attempt;
    for (attempt = 0; attempt < C2M_DEBUG_HOSTKEY_TMP_RETRIES; attempt++) {
        char tmpname[96], tmppath[PATH_MAX];
        pid_t child;
        int64_t until, ms;
        int status = -1;
        struct stat st;
        ms = now_ms();
        if (ms < 0) return -1;
        snprintf(tmpname, sizeof(tmpname), ".host_ed25519.tmp-%ld-%llx-%u",
                 (long)getpid(),
                 (unsigned long long)((unsigned long long)ms & 0xffffffffULL),
                 hk_serial++);
        if (snprintf(tmppath, sizeof(tmppath), "%s/%s", config_dir,
                     tmpname) >= (int)sizeof(tmppath))
            return -1;
        if (!fstatat(configfd, tmpname, &st, AT_SYMLINK_NOFOLLOW))
            continue; /* stale or foreign: never unlink, try next name */
        if (errno != ENOENT) return -1;
    child = fork();
    if (child < 0) return -1;
    if (child == 0) {
        char *const argv[] = { (char *)dropbearkey, (char *)"-t",
                               (char *)"ed25519", (char *)"-f", tmppath, NULL };
        char *envp[] = { (char *)"PATH=/bin:/usr/bin",
                          (char *)"HOME=/root", (char *)"LANG=C",
                          (char *)C2M_DEBUG_LIBRARY_ENV, NULL };
        if (loopback) envp[3] = NULL;
        int nullfd;
        if (setpgid(0, 0)) _exit(126);
        nullfd = open("/dev/null", O_RDWR);
        if (nullfd < 0) _exit(126);
        (void)dup2(nullfd, STDIN_FILENO);
        (void)dup2(nullfd, STDOUT_FILENO);
        (void)dup2(nullfd, STDERR_FILENO);
        if (nullfd > STDERR_FILENO) close(nullfd);
        execve(dropbearkey, argv, envp);
        _exit(127);
    }
    if (setpgid(child, child)) {
        /* Best effort; parent still waits on the exact child PID. */
    }
    until = now_ms() + 15000;
    for (;;) {
        pid_t r = waitpid(child, &status, WNOHANG);
        int64_t now;
        struct timespec pause = { 0, 50000000 };
        if (r == child) break;
        if (r < 0 && errno != EINTR) {
                signal_group(child, SIGKILL);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
            }
            return -1;
        }
        now = now_ms();
        if (now < 0 || now >= until) {
                signal_group(child, SIGKILL);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
            }
            (void)unlinkat(configfd, tmpname, 0);
            return -1;
        }
        nanosleep(&pause, NULL);
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        (void)unlinkat(configfd, tmpname, 0);
        return -1;
    }
    /* dropbearkey created tmppath; enforce 0600 owned by euid, then link. */
    {
        int fd = openat(configfd, tmpname, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
        struct stat tst;
        if (fd < 0) return -1;
        if (fstat(fd, &tst) || !S_ISREG(tst.st_mode) || tst.st_nlink != 1 ||
            tst.st_uid != geteuid()) {
            close(fd);
            (void)unlinkat(configfd, tmpname, 0);
            return -1;
        }
        close(fd);
        if ((tst.st_mode & 0777) != 0600) {
            if (fchmodat(configfd, tmpname, 0600, 0)) {
                (void)unlinkat(configfd, tmpname, 0);
                return -1;
            }
        }
    }
    if (linkat(configfd, tmpname, configfd, C2M_DEBUG_HOSTKEY_NAME, 0)) {
        int e = errno;
        (void)unlinkat(configfd, tmpname, 0);
        if (e == EEXIST) return hostkey_ok(final_path);
        return -1;
    }
    (void)unlinkat(configfd, tmpname, 0);
    return hostkey_ok(final_path);
    }
    return -1;
}

static int ensure_hostkey(const struct serve_cfg *c, int configfd,
                          char *final_path, size_t cap)
{
    struct stat st;
    if (snprintf(final_path, cap, "%s/%s", c->config_dir,
                 C2M_DEBUG_HOSTKEY_NAME) >= (int)cap)
        return -1;
    if (!fstatat(configfd, C2M_DEBUG_HOSTKEY_NAME, &st, AT_SYMLINK_NOFOLLOW)) {
        return hostkey_ok(final_path);
    }
    if (errno != ENOENT) return -1;
    return generate_hostkey(c->dropbearkey, final_path, c->config_dir, configfd,
                            c->loopback);
}

static int stage_run_file(int runfd, const char *name, const char *data)
{
    char tmp[96];
    int fd;
    static unsigned serial;
    size_t n = strlen(data);
    snprintf(tmp, sizeof(tmp), ".stage-%ld-%u.tmp", (long)getpid(), ++serial);
    (void)unlinkat(runfd, tmp, 0);
    fd = openat(runfd, tmp, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
                0600);
    if (fd < 0) return -1;
    if (private_file_ok(fd, 0600, 8192) || write_all(fd, data, n) || fsync(fd)) {
        close(fd);
        (void)unlinkat(runfd, tmp, 0);
        return -1;
    }
    close(fd);
    if (renameat(runfd, tmp, runfd, name)) {
        (void)unlinkat(runfd, tmp, 0);
        return -1;
    }
    (void)fsync(runfd);
    return 0;
}

/* Signal one owned child. The caller must hold the child unreaped (no
 * PID reuse possible), then the group signal goes to -leader only after
 * verifying getpgid(leader)==leader; otherwise only the single PID is
 * signaled (a raced ESRCH from getpgid/kill is harmless either way). */
static void signal_group(pid_t leader, int sig)
{
    pid_t pg;
    if (leader <= 1) return;
    errno = 0;
    pg = getpgid(leader);
    if (pg == leader)
        (void)kill(-leader, sig);
    else
        (void)kill(leader, sig);
}

static void stop_group(pid_t leader)
{
    int64_t until;
    struct timespec pause = { 0, 100000000 };
    int status;
    if (leader <= 1) return;
    signal_group(leader, SIGTERM);
    until = now_ms() + 2000;
    while (now_ms() < until) {
        pid_t r = waitpid(leader, &status, WNOHANG);
        if (r == leader) return;
        if (r < 0 && errno != EINTR) break;
        nanosleep(&pause, NULL);
    }
    signal_group(leader, SIGKILL);
    until = now_ms() + 500;
    while (now_ms() < until) {
        pid_t r = waitpid(leader, &status, WNOHANG);
        if (r == leader) return;
        if (r < 0 && errno != EINTR) break;
        nanosleep(&pause, NULL);
    }
    while (waitpid(leader, &status, WNOHANG) == leader) {
    }
}

#ifdef __linux__
/* Owned-listener proof without any TCP connect (no auth-session overhead,
 * no interference with Dropbear, and a foreign listener on the same port
 * cannot satisfy the owned-PID fd check). /proc/net/tcp prints each
 * IPv4 word byte-swapped hex on little-endian (127.0.0.1 -> 0100007F);
 * the camera target is little-endian ARM, fixtures run little-endian. */
static int proc_ip_expect(const char *bind_addr, char out[9])
{
    unsigned char b[4];
    if (inet_pton(AF_INET, bind_addr, b) != 1) return -1;
    snprintf(out, 9, "%02X%02X%02X%02X", b[3], b[2], b[1], b[0]);
    return 0;
}

static int collect_listen_inodes(const char *bind_addr, int port,
                                 unsigned long *inos, int cap)
{
    FILE *f;
    char line[512];
    char expect[9], portexp[8];
    int n = 0;
    if (proc_ip_expect(bind_addr, expect)) return -1;
    snprintf(portexp, sizeof(portexp), "%04X", (unsigned)port);
    f = fopen("/proc/net/tcp", "r");
    if (!f) return -1;
    if (!fgets(line, sizeof(line), f)) {
        fclose(f);
        return -1;
    }
    while (fgets(line, sizeof(line), f)) {
        char *tok[12];
        int nt = 0;
        char *s, *save, *colon;
        for (s = strtok_r(line, " \t\n", &save);
             s && nt < 12; s = strtok_r(NULL, " \t\n", &save))
            tok[nt++] = s;
        if (nt < 10) continue;
        colon = strchr(tok[1], ':');
        if (!colon) continue;
        *colon = 0;
        if (strcmp(tok[1], expect) || strcmp(colon + 1, portexp)) continue;
        if (strcmp(tok[3], "0A")) continue; /* LISTEN only */
        if (n < cap)
            inos[n++] = (unsigned long)strtoul(tok[9], NULL, 10);
    }
    fclose(f);
    return n;
}

static int pid_holds_inode(pid_t pid, unsigned long ino)
{
    char dir[64], path[96], link[128], want[64];
    DIR *d;
    struct dirent *e;
    ssize_t n;
    snprintf(dir, sizeof(dir), "/proc/%ld/fd", (long)pid);
    snprintf(want, sizeof(want), "socket:[%lu]", ino);
    d = opendir(dir);
    if (!d) return 0;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        if (snprintf(path, sizeof(path), "%s/%s", dir, e->d_name) >=
            (int)sizeof(path))
            continue;
        n = readlink(path, link, sizeof(link) - 1);
        if (n < 0) continue;
        link[n] = 0;
        if (!strcmp(link, want)) {
            closedir(d);
            return 1;
        }
    }
    closedir(d);
    return 0;
}

static int listener_owned_by(pid_t pid, const char *bind_addr, int port)
{
    unsigned long inos[16];
    int n, i;
    if (pid <= 1) return 0;
    n = collect_listen_inodes(bind_addr, port, inos, 16);
    if (n <= 0) return 0;
    for (i = 0; i < n; i++)
        if (pid_holds_inode(pid, inos[i])) return 1;
    return 0;
}
#endif

static int serve(const struct serve_cfg *c)
{
    int runfd = -1, configfd = -1, lockfd = -1;
    char owner_line[C2M_DEBUG_OWNER_MAX];
    char fp[17] = "none";
    char hostkey[PATH_MAX];
    char pidpath[PATH_MAX], bindspec[64], authdata[C2M_DEBUG_OWNER_MAX + 2];
    struct stat a, b;
    struct passwd *pw;
    pid_t child = -1;
    int64_t serve_start = 0, deadline = 0;
    int staged = 0;
    int execpipe[2] = { -1, -1 };
    int rc = 1;

    /* Pure gate first: no filesystem or network I/O on this path. */
    if (!c2m_debug_cli_valid(c->loopback, 0, c->bind_addr, c->port,
                             c->window_sec, c->poll_ms)) {
        fputs("c2m-debug: invalid serve bounds\n", stderr);
        return 2;
    }
    serve_start = now_ms();
    if (serve_start < 0) {
        fputs("c2m-debug: clock unavailable\n", stderr);
        return 1;
    }
    deadline = serve_start + (int64_t)c->window_sec * 1000;

    runfd = safe_dir(c->run_dir, 1, 1);
    configfd = safe_dir(c->config_dir, 1, 1);
    if (runfd < 0 || configfd < 0 ||
        fstat(runfd, &a) || fstat(configfd, &b) ||
        (a.st_dev == b.st_dev && a.st_ino == b.st_ino)) {
        fputs("c2m-debug: private directories unavailable\n", stderr);
        rc = 1;
        goto out;
    }
    lockfd = openat(runfd, "supervisor.lock",
                    O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (lockfd < 0 || private_file_ok(lockfd, 0600, 0)) {
        fputs("c2m-debug: lock unavailable\n", stderr);
        rc = 1;
        goto out;
    }
    {
        struct flock fl;
        memset(&fl, 0, sizeof(fl));
        fl.l_type = F_WRLCK;
        fl.l_whence = SEEK_SET;
        if (fcntl(lockfd, F_SETLK, &fl)) {
            /* Another supervisor owns the lock (and the status file);
             * never publish here, just exit. */
            fputs("c2m-debug: already running\n", stderr);
            rc = 1;
            goto out;
        }
    }
    if (!c->loopback && geteuid() != 0) {
        publish_status(c, "inactive", "root_required", "none");
        fputs("c2m-debug: root required\n", stderr);
        return 1;
    }
    if (!c->loopback && trusted_nss_module()) {
        publish_status(c, "inactive", "nss_asset_unavailable", "none");
        fputs("c2m-debug: pinned stock NSS module unavailable\n", stderr);
        rc = 1;
        goto out;
    }
    /* Root account must exist with a usable shell (read-only check). */
    errno = 0;
    pw = getpwnam("root");
    if (!pw || pw->pw_uid != 0 || !pw->pw_shell || !pw->pw_shell[0] ||
        pw->pw_shell[0] != '/') {
        publish_status(c, "inactive", "root_account_unavailable", "none");
        fputs("c2m-debug: root account unavailable\n", stderr);
        return 1;
    }

    if (trusted_exec(c->dropbear) || trusted_exec(c->dropbearkey)) {
        publish_status(c, "inactive", "dropbear_assets_unavailable", "none");
        fputs("c2m-debug: dropbear assets unavailable\n", stderr);
        rc = 1;
        goto out;
    }
    memset(owner_line, 0, sizeof(owner_line));
    if (read_owner(c->owner_pub, owner_line, sizeof(owner_line), fp)) {
        publish_status(c, "inactive", "key_missing_or_invalid", "none");
        fputs("c2m-debug: owner key missing or invalid\n", stderr);
        rc = 1;
        goto out;
    }
    if (ensure_hostkey(c, configfd, hostkey, sizeof(hostkey))) {
        publish_status(c, "inactive", "hostkey_unavailable", fp);
        fputs("c2m-debug: hostkey unavailable\n", stderr);
        rc = 1;
        goto out;
    }
    /* Startup AP readiness: retry up to 60 s (poll interval) inside the
     * same overall window, so a still-coming-up AP is not permanently
     * missed at boot. */
    {
        int64_t ap_start = now_ms();
        struct timespec pause;
        if (ap_start < 0) {
            publish_status(c, "inactive", "clock_unavailable", fp);
            fputs("c2m-debug: clock unavailable\n", stderr);
            rc = 1;
            goto out;
        }
        while (ap_valid(c)) {
            int64_t now = now_ms();
            if (now < 0 || now - ap_start >= C2M_DEBUG_STARTUP_AP_MS ||
                now >= deadline) {
                publish_status(c, "inactive", "ap_not_validated", fp);
                fputs("c2m-debug: AP not validated; refusing to listen\n",
                      stderr);
                rc = 1;
                goto out;
            }
            pause.tv_sec = c->poll_ms / 1000;
            pause.tv_nsec = (long)(c->poll_ms % 1000) * 1000000L;
            nanosleep(&pause, NULL);
        }
    }
    /* Stage run files. Refuse to reclaim unsafe pre-existing objects. */
    {
        struct stat st;
        if (!fstatat(runfd, "authorized_keys", &st, AT_SYMLINK_NOFOLLOW)) {
            if (!S_ISREG(st.st_mode) || st.st_uid != geteuid() ||
                st.st_nlink != 1) {
                publish_status(c, "inactive", "run_conflict", fp);
                fputs("c2m-debug: unsafe run file\n", stderr);
                rc = 1;
                goto out;
            }
        } else if (errno != ENOENT) {
            publish_status(c, "inactive", "run_conflict", fp);
            rc = 1;
            goto out;
        }
        if (!fstatat(runfd, "dropbear.pid", &st, AT_SYMLINK_NOFOLLOW)) {
            if (!S_ISREG(st.st_mode) || st.st_uid != geteuid() ||
                st.st_nlink != 1) {
                publish_status(c, "inactive", "run_conflict", fp);
                fputs("c2m-debug: unsafe pid file\n", stderr);
                rc = 1;
                goto out;
            }
            (void)unlinkat(runfd, "dropbear.pid", 0);
        } else if (errno != ENOENT) {
            publish_status(c, "inactive", "run_conflict", fp);
            rc = 1;
            goto out;
        }
    }
    if (snprintf(pidpath, sizeof(pidpath), "%s/dropbear.pid", c->run_dir) >=
        (int)sizeof(pidpath)) {
        publish_status(c, "inactive", "run_conflict", fp);
        rc = 1;
        goto out;
    }
    if (snprintf(bindspec, sizeof(bindspec), "%s:%d", c->bind_addr, c->port) >=
        (int)sizeof(bindspec)) {
        publish_status(c, "inactive", "run_conflict", fp);
        rc = 1;
        goto out;
    }
    if (snprintf(authdata, sizeof(authdata), "%s\n", owner_line) >=
        (int)sizeof(authdata)) {
        publish_status(c, "inactive", "key_missing_or_invalid", "none");
        rc = 1;
        goto out;
    }
    if (stage_run_file(runfd, "authorized_keys", authdata)) {
        publish_status(c, "inactive", "run_conflict", fp);
        fputs("c2m-debug: cannot stage authorized_keys\n", stderr);
        rc = 1;
        goto out;
    }
    wipe(owner_line, sizeof(owner_line));
    wipe(authdata, sizeof(authdata));
    staged = 1;

    /* Exec-result pipe: CLOEXEC write end closes on successful execve
     * (parent reads EOF); a failed exec writes errno first. */
    if (pipe(execpipe)) {
        publish_status(c, "failed", "dropbear_fork_failed", fp);
        fputs("c2m-debug: pipe unavailable\n", stderr);
        rc = 1;
        goto out;
    }
    {
        int fd0 = fcntl(execpipe[0], F_GETFD);
        int fd1 = fcntl(execpipe[1], F_GETFD);
        int rw = fcntl(execpipe[0], F_GETFL);
        if (fd0 < 0 || fd1 < 0 || rw < 0 ||
            fcntl(execpipe[0], F_SETFD, fd0 | FD_CLOEXEC) ||
            fcntl(execpipe[1], F_SETFD, fd1 | FD_CLOEXEC) ||
            fcntl(execpipe[0], F_SETFL, rw | O_NONBLOCK)) {
            publish_status(c, "failed", "dropbear_fork_failed", fp);
            rc = 1;
            goto out;
        }
    }
    /* Honest transient state: the listener is NOT yet proven. active is
     * published only after owned-listener proof below. */
    if (publish_status(c, "starting",
                       "process_running_listener_unverified", fp)) {
        fputs("c2m-debug: status publication failed\n", stderr);
        rc = 1;
        goto out;
    }

    child = fork();
    if (child < 0) {
        publish_status(c, "failed", "dropbear_fork_failed", fp);
        rc = 1;
        goto out;
    }
    if (child == 0) {
        /* Owned dropbear in its own session/group; stderr to /dev/null
         * (no log file). Clean environment, no shell. */
        char *argv[26];
        char *envp[5];
        int nullfd, i = 0;
        close(execpipe[0]);
        if (setsid() < 0) _exit(126);
        nullfd = open("/dev/null", O_RDWR);
        if (nullfd < 0) _exit(126);
        (void)dup2(nullfd, STDIN_FILENO);
        (void)dup2(nullfd, STDOUT_FILENO);
        (void)dup2(nullfd, STDERR_FILENO);
        if (nullfd > STDERR_FILENO) close(nullfd);
        argv[i++] = (char *)c->dropbear;
        argv[i++] = (char *)"-F";
        argv[i++] = (char *)"-E";
        argv[i++] = (char *)"-s";
        argv[i++] = (char *)"-j";
        argv[i++] = (char *)"-k";
        argv[i++] = (char *)"-D";
        argv[i++] = (char *)c->run_dir;
        argv[i++] = (char *)"-r";
        argv[i++] = hostkey;
        argv[i++] = (char *)"-p";
        argv[i++] = bindspec;
        if (!c->loopback) {
            argv[i++] = (char *)"-l";
            argv[i++] = (char *)C2M_DEBUG_IFACE;
        }
        argv[i++] = (char *)"-P";
        argv[i++] = pidpath;
        argv[i++] = (char *)"-I";
        argv[i++] = (char *)"120";
        argv[i++] = (char *)"-K";
        argv[i++] = (char *)"20";
        argv[i++] = (char *)"-T";
        argv[i++] = (char *)"3";
        argv[i++] = (char *)"-M";
        argv[i++] = (char *)"600";
        argv[i++] = NULL;
        envp[0] = (char *)"PATH=/bin:/usr/bin";
        envp[1] = (char *)"HOME=/root";
        envp[2] = (char *)"LANG=C";
        envp[3] = (char *)C2M_DEBUG_LIBRARY_ENV;
        envp[4] = NULL;
        if (c->loopback) envp[3] = NULL;
        execve(c->dropbear, argv, envp);
        {
            const unsigned char failed_exec = 1;
            ssize_t sent;
            do { sent = write(execpipe[1], &failed_exec, 1); }
            while (sent < 0 && errno == EINTR);
            if (sent != 1) _exit(127);
        }
        _exit(127);
    }
    /* Parent owns only the read end from here on. */
    close(execpipe[1]);
    execpipe[1] = -1;
    /* Owned-listener proof: active requires the kernel to show OUR child
     * holding the bound LISTEN socket (no TCP connect probe). */
    {
        int exec_failed = 0, exec_ok = 0, proved = 0;
        int64_t fork_ms = now_ms();
        struct timespec proof_pause = { 0, 50000000 };
        int status;
        if (fork_ms < 0) {
            publish_status(c, "failed", "clock_unavailable", fp);
            rc = 1;
            stop_group(child);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
            }
            child = -1;
            goto out;
        }
        while (!proved && !g_stop) {
            int64_t now = now_ms();
            pid_t r;
            if (now < 0 || now - fork_ms >= C2M_DEBUG_PROOF_MS) break;
            r = waitpid(child, &status, WNOHANG);
            if (r == child) {
                publish_status(c, "failed",
                               exec_failed ? "dropbear_exec_failed"
                                           : "dropbear_exited",
                               fp);
                child = -1;
                rc = 1;
                goto out;
            }
            if (r < 0 && errno != EINTR) {
                publish_status(c, "failed", "dropbear_wait_failed", fp);
                rc = 1;
                goto out;
            }
            for (;;) {
                char eb;
                ssize_t n = read(execpipe[0], &eb, 1);
                if (n == 1) {
                    exec_failed = 1;
                } else if (n == 0) {
                    exec_ok = 1;
                    break;
                } else if (errno == EINTR) {
                    continue;
                } else {
                    break; /* EAGAIN: pre-exec; other errors: retry next tick */
                }
            }
#ifdef __linux__
            if (exec_ok &&
                listener_owned_by(child, c->bind_addr, c->port)) {
                proved = 1;
                break;
            }
#else
            (void)exec_ok;
#endif
            nanosleep(&proof_pause, NULL);
        }
        if (g_stop) {
            if (child > 1) {
                stop_group(child);
                while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
                }
                child = -1;
            }
            publish_status(c, "expired", "stopped", fp);
            rc = 0;
            goto out;
        }
        if (!proved) {
            if (child > 1) {
                stop_group(child);
                while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
                }
                child = -1;
            }
            publish_status(c, "failed", "listener_unverified", fp);
            fputs("c2m-debug: listener ownership unproven\n", stderr);
            rc = 1;
            goto out;
        }
        close(execpipe[0]);
        execpipe[0] = -1;
        if (publish_status(c, "active", "listening", fp)) {
            fputs("c2m-debug: status publication failed\n", stderr);
            stop_group(child);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
            }
            child = -1;
            rc = 1;
            goto out;
        }
    }
    /* Parent supervises within the overall window from serve start. */
    rc = 0;
    while (!g_stop) {
        pid_t r;
        int status;
        int64_t now = now_ms();
        struct timespec pause;
        if (now < 0) {
            publish_status(c, "failed", "clock_unavailable", fp);
            rc = 1;
            break;
        }
        r = waitpid(child, &status, WNOHANG);
        if (r == child) {
            publish_status(c, "failed", "dropbear_exited", fp);
            child = -1;
            rc = 1;
            break;
        }
        if (r < 0 && errno != EINTR) {
            publish_status(c, "failed", "dropbear_wait_failed", fp);
            rc = 1;
            break;
        }
        if (now >= deadline) {
            stop_group(child);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
            }
            child = -1;
            publish_status(c, "expired", "window_expired", fp);
            rc = 0;
            break;
        }
        if (ap_valid(c)) {
            stop_group(child);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
            }
            child = -1;
            publish_status(c, "failed", "ap_changed_or_unverifiable", fp);
            rc = 1;
            break;
        }
        pause.tv_sec = c->poll_ms / 1000;
        pause.tv_nsec = (long)(c->poll_ms % 1000) * 1000000L;
        nanosleep(&pause, NULL);
    }
    if (child > 1) {
        int status;
        pid_t r = waitpid(child, &status, WNOHANG);
        if (r == 0) {
            stop_group(child);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
            }
        }
        if (g_stop && rc == 0) {
            publish_status(c, "expired", "stopped", fp);
        }
        child = -1;
    }
    /* Transient listener artifacts are revoked on every exit below;
     * the hostkey persists, and foreign run-conflict objects stay untouched. */

out:
    wipe(owner_line, sizeof(owner_line));
    wipe(authdata, sizeof(authdata));
    if (execpipe[0] >= 0) close(execpipe[0]);
    if (execpipe[1] >= 0) close(execpipe[1]);
    /* Early exec/proof failures also revoke the staged authorization file. */
    if (staged && runfd >= 0) {
        (void)unlinkat(runfd, "dropbear.pid", 0);
        (void)unlinkat(runfd, "authorized_keys", 0);
    }
    if (runfd >= 0) close(runfd);
    if (configfd >= 0) close(configfd);
    if (lockfd >= 0) close(lockfd);
    return rc;
}

int main(int argc, char **argv)
{
    struct serve_cfg c;
    int mode = 0, any_override = 0, i;
    memset(&c, 0, sizeof(c));
    c.dropbear = C2M_DEBUG_DROPBEAR;
    c.dropbearkey = C2M_DEBUG_DROPBEARKEY;
    c.owner_pub = C2M_DEBUG_OWNER_PUB;
    c.run_dir = C2M_DEBUG_RUN_DIR;
    c.config_dir = C2M_DEBUG_CONFIG_DIR;
    c.status_file = C2M_DEBUG_STATUS_FILE;
    c.bind_addr = C2M_DEBUG_BIND_ADDR;
    c.port = C2M_DEBUG_BIND_PORT;
    c.window_sec = C2M_DEBUG_WINDOW_SEC;
    c.poll_ms = C2M_DEBUG_POLL_MS;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--help")) {
            usage(stdout);
            return 0;
        }
        if (!strcmp(argv[i], "--self-test") || !strcmp(argv[i], "--serve") ||
            !strcmp(argv[i], "--loopback-test")) {
            if (!strcmp(argv[i], "--loopback-test")) {
                c.loopback = 1;
                c.bind_addr = C2M_DEBUG_LOOPBACK_ADDR;
                continue;
            }
            if (mode) {
                usage(stderr);
                return 2;
            }
            mode = !strcmp(argv[i], "--self-test") ? 1 : 2;
        } else if (i + 1 < argc && !strcmp(argv[i], "--dropbear")) {
            c.dropbear = argv[++i]; any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--dropbearkey")) {
            c.dropbearkey = argv[++i]; any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--owner-pub")) {
            c.owner_pub = argv[++i]; any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--run-dir")) {
            c.run_dir = argv[++i]; any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--config-dir")) {
            c.config_dir = argv[++i]; any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--status-file")) {
            c.status_file = argv[++i]; any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--bind")) {
            c.bind_addr = argv[++i]; any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--port")) {
            c.port = atoi(argv[++i]); any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--window-sec")) {
            c.window_sec = atoi(argv[++i]); any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--poll-ms")) {
            c.poll_ms = atoi(argv[++i]); any_override = 1;
        } else if (i + 1 < argc && !strcmp(argv[i], "--ap-state-file")) {
            c.ap_state_file = argv[++i]; any_override = 1;
        } else {
            usage(stderr);
            return 2;
        }
    }
    if (mode == 1) return c2m_debug_self_test();
    if (mode != 2) {
        usage(stderr);
        return 2;
    }
    /* Production gate: any override without an explicit --loopback-test
     * is rejected here with no filesystem or network I/O, in any order. */
    if (!c2m_debug_cli_valid(c.loopback, any_override, c.bind_addr, c.port,
                             c.window_sec, c.poll_ms)) {
        usage(stderr);
        return 2;
    }
    umask(0077);
    signal(SIGTERM, on_signal);
    signal(SIGINT, on_signal);
    signal(SIGPIPE, SIG_IGN);
    return serve(&c);
}
#endif
