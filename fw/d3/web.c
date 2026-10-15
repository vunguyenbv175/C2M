#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "web.h"

#include <ctype.h>
#include <limits.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Core-only is for portable crypto/parser self-tests, never a web server. */
#ifndef C2M_WEB_CORE_ONLY
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <net/if.h>
#include <linux/wireless.h>
#include <poll.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#ifndef O_NOFOLLOW
#error "The service requires O_NOFOLLOW; do not build without symlink protection"
#endif
#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif
#endif

#define TOKEN_BYTES 32
#define TOKEN_HEX (TOKEN_BYTES * 2)
#define CONFIG_NAME "wifi.conf"
#define REQUEST_NAME "connect.request"

struct sha1 {
    uint32_t h[5];
    uint64_t length;
    unsigned char block[64];
    size_t used;
};
struct request {
    char method[8], path[128];
    char host[80], origin[128], content_type[96], fetch_site[32];
    size_t length;
    int has_length, http11;
    unsigned char body[C2M_WEB_MAX_BODY + 1];
};
struct form {
    unsigned char ssid[33], password[65];
    char csrf[TOKEN_HEX + 1];
    size_t ssid_len, password_len;
    unsigned fields;
};
enum sign_state { SIGN_WAITING, SIGN_WARMING, SIGN_READY, SIGN_STALE,
                  SIGN_NO_DATABASE, SIGN_DISABLED, SIGN_ERROR };
enum sign_code { SIGN_NONE, SIGN_SPEED, SIGN_RESIDENTIAL_START, SIGN_RESIDENTIAL_END };
static const char *const sign_states[] = {"waiting_gps", "warming_up", "ready", "stale",
                                        "no_database", "disabled", "error"};
static const char *const sign_codes[] = {"none", "speed_limit", "residential_start", "residential_end"};
struct sign_status {
    enum sign_state state;
    enum sign_code code;
    unsigned gps_fresh, active, available, speed, distance, expires;
    uint32_t sequence, event_id;
    uint64_t monotonic_ms;
};
#ifndef C2M_WEB_CORE_ONLY
struct status {
    char supported[16], state[24], ssid[129], ipv4[INET_ADDRSTRLEN];
    char error[96], bt[24];
    int available;
};
struct service {
    int config_fd, run_fd, loopback;
    unsigned short port;
    struct in_addr address, mask;
    char address_text[INET_ADDRSTRLEN], host[80], origin[96];
    char token[TOKEN_HEX + 1];
    const char *status_path, *sign_status_path;
};
static volatile sig_atomic_t stopped;
#endif

static void erase(void *p, size_t n)
{
    volatile unsigned char *v = (volatile unsigned char *)p;
    while (n--) *v++ = 0;
}
static uint32_t rol(uint32_t x, unsigned n)
{
    return (x << n) | (x >> (32 - n));
}
static void sha1_block(struct sha1 *s, const unsigned char *p)
{
    uint32_t w[80], a, b, c, d, e, f, k, t;
    unsigned i;
    for (i = 0; i < 16; i++) {
        w[i] = ((uint32_t)p[4*i] << 24) | ((uint32_t)p[4*i+1] << 16)
             | ((uint32_t)p[4*i+2] << 8) | p[4*i+3];
    }
    for (i = 16; i < 80; i++) w[i] = rol(w[i-3] ^ w[i-8] ^ w[i-14] ^ w[i-16], 1);
    a = s->h[0]; b = s->h[1]; c = s->h[2]; d = s->h[3]; e = s->h[4];
    for (i = 0; i < 80; i++) {
        if (i < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
        else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
        else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
        else { f = b ^ c ^ d; k = 0xca62c1d6; }
        t = rol(a, 5) + f + e + k + w[i];
        e = d; d = c; c = rol(b, 30); b = a; a = t;
    }
    s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d; s->h[4] += e;
    erase(w, sizeof(w));
}
static void sha1_init(struct sha1 *s)
{
    memset(s, 0, sizeof(*s));
    s->h[0] = 0x67452301; s->h[1] = 0xefcdab89; s->h[2] = 0x98badcfe;
    s->h[3] = 0x10325476; s->h[4] = 0xc3d2e1f0;
}
static void sha1_update(struct sha1 *s, const void *data, size_t n)
{
    const unsigned char *p = (const unsigned char *)data;
    s->length += n;
    while (n) {
        size_t count = 64 - s->used;
        if (count > n) count = n;
        memcpy(s->block + s->used, p, count);
        s->used += count; p += count; n -= count;
        if (s->used == 64) { sha1_block(s, s->block); s->used = 0; }
    }
}
static void sha1_finish(struct sha1 *s, unsigned char out[20])
{
    uint64_t bits = s->length * 8;
    unsigned char pad[72] = {0x80};
    size_t count = s->used < 56 ? 56 - s->used : 120 - s->used;
    unsigned i;
    sha1_update(s, pad, count);
    for (i = 0; i < 8; i++) pad[i] = (unsigned char)(bits >> (56 - i*8));
    sha1_update(s, pad, 8);
    for (i = 0; i < 20; i++) out[i] = (unsigned char)(s->h[i/4] >> (24 - 8*(i%4)));
    erase(pad, sizeof(pad)); erase(s, sizeof(*s));
}
static void hmac_sha1(const unsigned char *key, size_t keylen,
                      const unsigned char *data, size_t n, unsigned char out[20])
{
    unsigned char pad[64], digest[20];
    struct sha1 s;
    size_t i;
    memset(pad, 0, sizeof(pad));
    if (keylen > 64) {
        sha1_init(&s); sha1_update(&s, key, keylen); sha1_finish(&s, digest);
        memcpy(pad, digest, 20);
    } else memcpy(pad, key, keylen);
    for (i = 0; i < 64; i++) pad[i] ^= 0x36;
    sha1_init(&s); sha1_update(&s, pad, 64); sha1_update(&s, data, n);
    sha1_finish(&s, digest);
    for (i = 0; i < 64; i++) pad[i] ^= (0x36 ^ 0x5c);
    sha1_init(&s); sha1_update(&s, pad, 64); sha1_update(&s, digest, 20);
    sha1_finish(&s, out);
    erase(pad, sizeof(pad)); erase(digest, sizeof(digest));
}
static void derive_psk(const unsigned char *password, size_t password_len,
                       const unsigned char *ssid, size_t ssid_len, unsigned char psk[32])
{
    unsigned char salt[36], u[20], t[20];
    unsigned block, round, i;
    memcpy(salt, ssid, ssid_len);
    for (block = 1; block <= 2; block++) {
        salt[ssid_len] = 0; salt[ssid_len+1] = 0; salt[ssid_len+2] = 0;
        salt[ssid_len+3] = (unsigned char)block;
        hmac_sha1(password, password_len, salt, ssid_len+4, u);
        memcpy(t, u, 20);
        for (round = 1; round < 4096; round++) {
            hmac_sha1(password, password_len, u, 20, u);
            for (i = 0; i < 20; i++) t[i] ^= u[i];
        }
        memcpy(psk + (block-1)*20, t, block == 1 ? 20 : 12);
    }
    erase(salt, sizeof(salt)); erase(u, sizeof(u)); erase(t, sizeof(t));
}
static void to_hex(const unsigned char *in, size_t n, char *out)
{
    static const char hex[] = "0123456789abcdef";
    size_t i;
    for (i = 0; i < n; i++) { out[2*i] = hex[in[i] >> 4]; out[2*i+1] = hex[in[i] & 15]; }
    out[2*n] = '\0';
}
static int hex_value(unsigned char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
/* D4 accepts only this closed schema, never controller strings/coordinates.
 * Portable parser takes an explicit monotonic time for deterministic tests. */
static int sign_number(const char *text, uint64_t max, uint64_t *out)
{
    uint64_t value = 0;
    const unsigned char *p = (const unsigned char *)text;
    if (!*p || (p[0] == '0' && p[1])) return -1;
    for (; *p; p++) {
        unsigned digit;
        if (*p < '0' || *p > '9') return -1;
        digit = *p - '0';
        if (value > max / 10 || (value == max / 10 && digit > max % 10)) return -1;
        value = value * 10 + digit;
    }
    *out = value; return 0;
}
static void sign_unavailable(struct sign_status *out)
{
    memset(out, 0, sizeof(*out)); out->state = SIGN_ERROR;
}
static int parse_sign_status(char *text, size_t n, uint64_t now, struct sign_status *out)
{
    static const char *const keys[] = {"version", "source", "state", "gps_fresh", "active",
        "sequence", "code", "speed_kmh", "distance_m", "event_id", "monotonic_ms"};
    struct sign_status parsed;
    size_t i, start = 0;
    unsigned seen = 0;
    uint64_t age;
    sign_unavailable(out); memset(&parsed, 0, sizeof(parsed));
    if (!n || n > C2M_WEB_MAX_BODY || text[n-1] != '\n') return -1;
    for (i = 0; i < n; i++)
        if (text[i] != '\n' && ((unsigned char)text[i] < 0x21 || (unsigned char)text[i] > 0x7e)) return -1;
    while (start < n) {
        size_t end = start;
        unsigned key, value_index;
        char *eq, *value;
        uint64_t number;
        while (end < n && text[end] != '\n') end++;
        if (end == start || end - start > 80) return -1;
        text[end] = 0;
        eq = strchr(text+start, '=');
        if (!eq || !eq[1]) return -1;
        *eq = 0; value = eq+1;
        for (key = 0; key < sizeof(keys)/sizeof(keys[0]); key++)
            if (!strcmp(text+start, keys[key])) break;
        if (key == sizeof(keys)/sizeof(keys[0]) || (seen & (1U << key))) return -1;
        seen |= 1U << key;
        switch (key) {
        case 0: if (strcmp(value, "1")) return -1; break;
        case 1: if (strcmp(value, "gps_offline")) return -1; break;
        case 2:
            for (value_index = 0; value_index < sizeof(sign_states)/sizeof(sign_states[0]); value_index++)
                if (!strcmp(value, sign_states[value_index])) break;
            if (value_index == sizeof(sign_states)/sizeof(sign_states[0])) return -1;
            parsed.state = (enum sign_state)value_index; break;
        case 6:
            for (value_index = 0; value_index < sizeof(sign_codes)/sizeof(sign_codes[0]); value_index++)
                if (!strcmp(value, sign_codes[value_index])) break;
            if (value_index == sizeof(sign_codes)/sizeof(sign_codes[0])) return -1;
            parsed.code = (enum sign_code)value_index; break;
        default:
            if (sign_number(value, key == 10 ? UINT64_MAX : UINT32_MAX, &number) < 0) return -1;
            switch (key) {
            case 3: if (number > 1) return -1; parsed.gps_fresh = (unsigned)number; break;
            case 4: if (number > 1) return -1; parsed.active = (unsigned)number; break;
            case 5: parsed.sequence = (uint32_t)number; break;
            case 7:
                if (number && (number < 10 || number > 130)) return -1;
                parsed.speed = (unsigned)number; break;
            case 8: if (number > 2000) return -1; parsed.distance = (unsigned)number; break;
            case 9: parsed.event_id = (uint32_t)number; break;
            case 10: parsed.monotonic_ms = number; break;
            }
        }
        start = end+1;
    }
    if (seen != (1U << (sizeof(keys)/sizeof(keys[0]))) - 1) return -1;
    if (parsed.monotonic_ms > now && parsed.monotonic_ms - now > C2M_WEB_SIGN_FUTURE_MS) return -1;
    age = now > parsed.monotonic_ms ? now - parsed.monotonic_ms : 0;
    parsed.available = 1;
    if (age >= C2M_WEB_SIGN_MAX_AGE_MS) parsed.state = SIGN_STALE;
    else parsed.expires = C2M_WEB_SIGN_MAX_AGE_MS - (unsigned)age;
    if (parsed.state == SIGN_STALE) parsed.gps_fresh = 0;
    if (parsed.state != SIGN_READY || !parsed.gps_fresh || parsed.code == SIGN_NONE
        || (parsed.code == SIGN_SPEED && !parsed.speed)) parsed.active = 0;
    if (!parsed.active) { parsed.code = SIGN_NONE; parsed.speed = parsed.distance = 0; }
    else if (parsed.code != SIGN_SPEED) parsed.speed = 0;
    *out = parsed; return 0;
}
#ifndef C2M_WEB_CORE_ONLY
static int random_bytes(unsigned char *p, size_t n)
{
    int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    size_t done = 0;
    if (fd < 0) return -1;
    while (done < n) {
        ssize_t r = read(fd, p + done, n - done);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) { close(fd); return -1; }
        done += (size_t)r;
    }
    close(fd); return 0;
}
/* Walk every directory component without following symlinks. Absolute only. */
static int open_directory(const char *path, int create_private)
{
    char copy[PATH_MAX], *part, *save = NULL;
    int fd, next;
    struct stat st;
    if (!path || path[0] != '/' || strlen(path) >= sizeof(copy)) { errno = EINVAL; return -1; }
    strcpy(copy, path);
    fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return -1;
    part = strtok_r(copy, "/", &save);
    while (part) {
        char *following = strtok_r(NULL, "/", &save);
        if (!strcmp(part, ".") || !strcmp(part, "..")) { close(fd); errno = EINVAL; return -1; }
        next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
        if (next < 0 && errno == ENOENT && create_private && !following) {
            if (mkdirat(fd, part, 0700) < 0 && errno != EEXIST) { close(fd); return -1; }
            next = openat(fd, part, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
        }
        close(fd);
        if (next < 0) return -1;
        fd = next; part = following;
    }
    if (create_private && (fstat(fd, &st) < 0 || st.st_uid != geteuid()
        || (st.st_mode & 07777) != 0700)) { close(fd); errno = EACCES; return -1; }
    return fd;
}
static int open_status(const char *path)
{
    char parent[PATH_MAX], *leaf;
    struct stat st;
    int dir, fd;
    if (!path || path[0] != '/' || strlen(path) >= sizeof(parent)) return -1;
    strcpy(parent, path); leaf = strrchr(parent, '/');
    if (!leaf || !leaf[1]) return -1;
    *leaf++ = '\0';
    if (!strcmp(leaf, ".") || !strcmp(leaf, "..")) return -1;
    dir = open_directory(*parent ? parent : "/", 0);
    if (dir < 0) return -1;
    fd = openat(dir, leaf, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    close(dir);
    if (fd < 0) return -1;
    if (fstat(fd, &st) < 0 || !S_ISREG(st.st_mode) || st.st_uid != geteuid()
        || st.st_nlink != 1 || (st.st_mode & 0022) || st.st_size > C2M_WEB_MAX_BODY) {
        close(fd); return -1;
    }
    return fd;
}
/* 1 = valid service-owned file, 0 = absent, -1 = unsafe/unreadable. */
static int owned_file(int dir, const char *name)
{
    struct stat st;
    if (fstatat(dir, name, &st, AT_SYMLINK_NOFOLLOW) < 0) return errno == ENOENT ? 0 : -1;
    if (!S_ISREG(st.st_mode) || st.st_uid != geteuid() || st.st_nlink != 1
        || (st.st_mode & 07777) != 0600) return -1;
    return 1;
}
static int write_all(int fd, const void *data, size_t n)
{
    const unsigned char *p = data;
    while (n) {
        ssize_t r = write(fd, p, n);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return -1;
        p += r; n -= (size_t)r;
    }
    return 0;
}
/* Return 1 for an existing pending request; otherwise 0/-1. */
static int atomic_publish(int dir, const char *name, const char *content, int no_replace)
{
    unsigned char random[12];
    char hex[25], temp[48];
    int fd = -1, result = -1, existing;
    existing = owned_file(dir, name);
    if (existing < 0) return -1;
    if (no_replace && existing) return 1;
    if (random_bytes(random, sizeof(random)) < 0) return -1;
    to_hex(random, sizeof(random), hex); erase(random, sizeof(random));
    snprintf(temp, sizeof(temp), ".c2m-web-%s.tmp", hex);
    fd = openat(dir, temp, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) return -1;
    if (fchmod(fd, 0600) < 0 || write_all(fd, content, strlen(content)) < 0 || fsync(fd) < 0) goto done;
    if (close(fd) < 0) { fd = -1; goto done; }
    fd = -1;
    /* Re-check immediately before publishing. Private directory prevents
     * unprivileged replacements; linkat provides atomic no-clobber for jobs. */
    if (owned_file(dir, name) < 0) goto done;
    if (no_replace) {
        if (linkat(dir, temp, dir, name, 0) < 0) {
            if (errno == EEXIST) result = 1;
            goto done;
        }
        if (unlinkat(dir, temp, 0) < 0) goto done;
    } else if (renameat(dir, temp, dir, name) < 0) goto done;
    if (fsync(dir) < 0) goto done;
    result = 0;
done:
    if (fd >= 0) close(fd);
    unlinkat(dir, temp, 0);
    return result;
}
#endif
static int valid_utf8_ssid(const unsigned char *s, size_t n)
{
    size_t i = 0;
    if (!n || n > 32) return 0;
    while (i < n) {
        uint32_t cp;
        unsigned need, j;
        unsigned char c = s[i++];
        if (c < 0x80) { if (c < 0x20 || c == 0x7f) return 0; continue; }
        if (c >= 0xc2 && c <= 0xdf) { cp = c & 31; need = 1; }
        else if (c >= 0xe0 && c <= 0xef) { cp = c & 15; need = 2; }
        else if (c >= 0xf0 && c <= 0xf4) { cp = c & 7; need = 3; }
        else return 0;
        if (n - i < need) return 0;
        for (j = 0; j < need; j++) {
            c = s[i++]; if ((c & 0xc0) != 0x80) return 0;
            cp = (cp << 6) | (c & 63);
        }
        if ((need == 1 && cp < 0x80) || (need == 2 && cp < 0x800)
            || (need == 3 && cp < 0x10000) || cp > 0x10ffff
            || (cp >= 0xd800 && cp <= 0xdfff)) return 0;
    }
    return 1;
}
static int valid_password(const unsigned char *s, size_t n)
{
    size_t i;
    if (n == 64) {
        for (i = 0; i < n; i++) if (hex_value(s[i]) < 0) return 0;
        return 1;
    }
    if (n < 8 || n > 63) return 0;
    for (i = 0; i < n; i++) if (s[i] < 0x20 || s[i] > 0x7e) return 0;
    return 1;
}
static int url_decode(const unsigned char *s, size_t n, unsigned char *out, size_t cap, size_t *used)
{
    size_t i, count = 0;
    for (i = 0; i < n; i++) {
        unsigned char c = s[i];
        if (c == '+') c = ' ';
        else if (c == '%') {
            int a, b;
            if (i+2 >= n || (a = hex_value(s[i+1])) < 0 || (b = hex_value(s[i+2])) < 0) return -1;
            c = (unsigned char)((a << 4) | b); i += 2;
        }
        if (!c || c == '\r' || c == '\n' || count >= cap) return -1;
        out[count++] = c;
    }
    out[count] = 0; *used = count; return 0;
}
static int parse_form(const unsigned char *body, size_t n, struct form *f)
{
    size_t start = 0;
    memset(f, 0, sizeof(*f));
    while (start < n) {
        size_t end = start, eq, keylen, used;
        unsigned bit;
        unsigned char key[17], *dest;
        size_t cap;
        while (end < n && body[end] != '&') end++;
        eq = start; while (eq < end && body[eq] != '=') eq++;
        if (eq == end || url_decode(body+start, eq-start, key, 16, &keylen) < 0) return -1;
        if (keylen == 4 && !memcmp(key, "csrf", 4)) { bit = 1; dest = (unsigned char *)f->csrf; cap = TOKEN_HEX; }
        else if (keylen == 4 && !memcmp(key, "ssid", 4)) { bit = 2; dest = f->ssid; cap = 32; }
        else if (keylen == 8 && !memcmp(key, "password", 8)) { bit = 4; dest = f->password; cap = 64; }
        else return -1;
        if ((f->fields & bit) || url_decode(body+eq+1, end-eq-1, dest, cap, &used) < 0) return -1;
        f->fields |= bit;
        if (bit == 2) f->ssid_len = used;
        if (bit == 4) f->password_len = used;
        if (end < n && end+1 == n) return -1;
        start = end+1;
    }
    return 0;
}
static int equal_token(const char *a, const char *b)
{
    unsigned diff = 0;
    size_t i;
    if (strlen(a) != TOKEN_HEX || strlen(b) != TOKEN_HEX) return 0;
    for (i = 0; i < TOKEN_HEX; i++) diff |= (unsigned char)a[i] ^ (unsigned char)b[i];
    return diff == 0;
}
#ifndef C2M_WEB_CORE_ONLY
static int save_credentials(struct service *s, const struct form *f)
{
    unsigned char psk[32];
    char ssid_hex[65], psk_hex[65], config[512];
    size_t i;
    int result, length;
    to_hex(f->ssid, f->ssid_len, ssid_hex);
    if (f->password_len == 64) {
        for (i = 0; i < 32; i++) psk[i] = (unsigned char)((hex_value(f->password[2*i]) << 4) | hex_value(f->password[2*i+1]));
    } else derive_psk(f->password, f->password_len, f->ssid, f->ssid_len, psk);
    to_hex(psk, 32, psk_hex);
    length = snprintf(config, sizeof(config), "# c2m-web staged WPA2 configuration; not applied automatically\n"
             "network={\n    ssid=%s\n    psk=%s\n    key_mgmt=WPA-PSK\n    proto=RSN\n}\n", ssid_hex, psk_hex);
    if (length < 0 || (size_t)length >= sizeof(config)) {
        erase(psk, sizeof(psk)); erase(psk_hex, sizeof(psk_hex)); erase(config, sizeof(config));
        return -1;
    }
    result = atomic_publish(s->config_fd, CONFIG_NAME, config, 0);
    erase(psk, sizeof(psk)); erase(psk_hex, sizeof(psk_hex)); erase(config, sizeof(config));
    return result;
}
static int ap_address(struct in_addr *address, struct in_addr *mask)
{
    int fd;
    struct ifreq iface;
    struct iwreq wireless;
    uint32_t hostmask, hostaddr;
    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return -1;
    memset(&wireless, 0, sizeof(wireless)); strcpy(wireless.ifr_name, "wlan0");
    if (ioctl(fd, SIOCGIWMODE, &wireless) < 0 || wireless.u.mode != IW_MODE_MASTER) goto fail;
    memset(&iface, 0, sizeof(iface)); strcpy(iface.ifr_name, "wlan0");
    if (ioctl(fd, SIOCGIFFLAGS, &iface) < 0 || !(iface.ifr_flags & IFF_UP)
        || (iface.ifr_flags & IFF_LOOPBACK)) goto fail;
    if (ioctl(fd, SIOCGIFADDR, &iface) < 0 || iface.ifr_addr.sa_family != AF_INET) goto fail;
    *address = ((struct sockaddr_in *)&iface.ifr_addr)->sin_addr;
    if (ioctl(fd, SIOCGIFNETMASK, &iface) < 0 || iface.ifr_netmask.sa_family != AF_INET) goto fail;
    *mask = ((struct sockaddr_in *)&iface.ifr_netmask)->sin_addr;
    hostaddr = ntohl(address->s_addr); hostmask = ntohl(mask->s_addr);
    /* Contiguous masks /1 through /30, no unspecified, loopback, multicast,
     * network or broadcast address. Reject a nonsensical AP configuration. */
    if (!hostmask || hostmask >= 0xfffffffeU || ((~hostmask + 1U) & ~hostmask)
        || !(hostaddr >> 24) || (hostaddr >> 24) == 127 || hostaddr >= 0xe0000000U
        || !(hostaddr & ~hostmask) || (hostaddr & ~hostmask) == ~hostmask) goto fail;
    close(fd); return 0;
fail:
    close(fd); return -1;
}
static int ap_still_valid(const struct service *s)
{
    struct in_addr address, mask;
    if (s->loopback) return 1;
    return ap_address(&address, &mask) == 0 && address.s_addr == s->address.s_addr && mask.s_addr == s->mask.s_addr;
}
static int64_t now_ms(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) < 0) return -1;
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static int read_sign_status(const struct service *s, struct sign_status *status)
{
    char text[C2M_WEB_MAX_BODY + 1];
    size_t used = 0;
    int fd;
    int64_t current;
    sign_unavailable(status);
    fd = open_status(s->sign_status_path);
    if (fd < 0) return -1;
    while (used < C2M_WEB_MAX_BODY) {
        ssize_t n = read(fd, text + used, C2M_WEB_MAX_BODY - used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { close(fd); erase(text, sizeof(text)); return -1; }
        if (!n) break;
        used += (size_t)n;
    }
    {
        char extra;
        ssize_t n = read(fd, &extra, 1);
        close(fd);
        if (n != 0 || memchr(text, 0, used)) { erase(text, sizeof(text)); return -1; }
    }
    text[used] = 0;
    current = now_ms();
    if (current < 0 || parse_sign_status(text, used, (uint64_t)current, status) < 0) {
        erase(text, sizeof(text)); sign_unavailable(status); return -1;
    }
    erase(text, sizeof(text)); return 0;
}
static int wait_ready(int fd, short events, int64_t deadline)
{
    struct pollfd p;
    int result;
    p.fd = fd; p.events = events; p.revents = 0;
    for (;;) {
        int64_t remain = deadline - now_ms();
        if (remain <= 0 || stopped) return -1;
        result = poll(&p, 1, remain > INT_MAX ? INT_MAX : (int)remain);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0 || (p.revents & (POLLERR | POLLNVAL))) return -1;
        return (p.revents & (events | POLLHUP)) ? 0 : -1;
    }
}
#endif
static int header_name(const char *s)
{
    static const char punct[] = "!#$%&'*+-.^_`|~";
    if (!*s) return 0;
    while (*s) {
        unsigned char c = (unsigned char)*s++;
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')
            || (c >= '0' && c <= '9') || strchr(punct, c))) return 0;
    }
    return 1;
}
static int copy_header(char *out, size_t cap, const char *value)
{
    if (strlen(value) >= cap || *out) return -1;
    strcpy(out, value); return 0;
}
static int parse_headers(char *head, struct request *r)
{
    char *line = head, *end, *first, *second;
    int host_seen = 0, origin_seen = 0, type_seen = 0, fetch_seen = 0;
    memset(r, 0, sizeof(*r));
    end = strstr(line, "\r\n");
    if (!end) return 400;
    *end = 0;
    first = strchr(line, ' '); if (!first) return 400; *first++ = 0;
    second = strchr(first, ' '); if (!second) return 400; *second++ = 0;
    if (strchr(second, ' ') || strlen(line) >= sizeof(r->method) || strlen(first) >= sizeof(r->path)) return 400;
    if (strcmp(second, "HTTP/1.1") && strcmp(second, "HTTP/1.0")) return 400;
    r->http11 = !strcmp(second, "HTTP/1.1");
    if (strcmp(line, "GET") && strcmp(line, "POST")) return 405;
    if (*first != '/' || !*line) return 400;
    strcpy(r->method, line); strcpy(r->path, first);
    line = end+2;
    while (*line) {
        char *colon, *value, *tail;
        unsigned char *p;
        end = strstr(line, "\r\n"); if (!end) return 400; *end = 0;
        if (!*line) { if (end[2]) return 400; break; }
        colon = strchr(line, ':'); if (!colon) return 400; *colon = 0;
        if (!header_name(line)) return 400;
        for (p = (unsigned char *)line; *p; p++) *p = (unsigned char)tolower(*p);
        value = colon+1;
        while (*value == ' ' || *value == '\t') value++;
        tail = value+strlen(value); while (tail > value && (tail[-1] == ' ' || tail[-1] == '\t')) *--tail = 0;
        for (p = (unsigned char *)value; *p; p++) if (*p < 0x20 || *p > 0x7e) return 400;
        if (!strcmp(line, "transfer-encoding")) return 400;
        if (!strcmp(line, "expect")) return 417;
        if (!strcmp(line, "content-length")) {
            size_t length = 0;
            if (r->has_length || !*value) return 400;
            for (p = (unsigned char *)value; *p; p++) {
                if (*p < '0' || *p > '9') return 400;
                length = length*10 + (*p-'0');
                if (length > C2M_WEB_MAX_BODY) return 413;
            }
            r->length = length; r->has_length = 1;
        } else if (!strcmp(line, "host")) {
            if (host_seen++ || !*value || copy_header(r->host, sizeof(r->host), value) < 0) return 400;
        } else if (!strcmp(line, "origin")) {
            if (origin_seen++ || !*value || copy_header(r->origin, sizeof(r->origin), value) < 0) return 400;
        } else if (!strcmp(line, "content-type")) {
            if (type_seen++ || !*value || copy_header(r->content_type, sizeof(r->content_type), value) < 0) return 400;
        } else if (!strcmp(line, "sec-fetch-site")) {
            if (fetch_seen++ || !*value || copy_header(r->fetch_site, sizeof(r->fetch_site), value) < 0) return 400;
        }
        line = end+2;
    }
    if (r->http11 && !host_seen) return 400;
    if (!strcmp(r->method, "POST") && !r->has_length) return 411;
    if (!strcmp(r->method, "GET") && r->length) return 400;
    return 0;
}
#ifndef C2M_WEB_CORE_ONLY
static int read_request(int fd, struct request *r)
{
    unsigned char buffer[C2M_WEB_MAX_HEADERS + C2M_WEB_MAX_BODY + 1];
    size_t used = 0, head_size = 0;
    int parsed = 0, result = 400;
    int64_t deadline = now_ms() + C2M_WEB_TIMEOUT_MS;
    memset(buffer, 0, sizeof(buffer)); memset(r, 0, sizeof(*r));
    for (;;) {
        ssize_t n;
        size_t i;
        if (wait_ready(fd, POLLIN, deadline) < 0) { result = 408; break; }
        n = recv(fd, buffer+used, sizeof(buffer)-1-used, MSG_DONTWAIT);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) { result = 400; break; }
        /* Raw NUL has no valid use in an HTTP header or URL-encoded form. */
        if (memchr(buffer+used, 0, (size_t)n)) { result = 400; break; }
        used += (size_t)n; buffer[used] = 0;
        if (!parsed) {
            for (i = 0; i+3 < used; i++) {
                if (!memcmp(buffer+i, "\r\n\r\n", 4)) { head_size = i+4; break; }
            }
            if (!head_size) {
                if (used >= C2M_WEB_MAX_HEADERS) { result = 431; break; }
                continue;
            }
            if (head_size > C2M_WEB_MAX_HEADERS) { result = 431; break; }
            /* Keep the final CRLF pair and terminate before the body. */
            {
                char header[C2M_WEB_MAX_HEADERS + 1];
                memcpy(header, buffer, head_size); header[head_size] = 0;
                result = parse_headers(header, r); erase(header, sizeof(header));
            }
            if (result) break;
            parsed = 1;
        }
        if (used-head_size > r->length) { result = 400; break; }
        if (used-head_size == r->length) {
            memcpy(r->body, buffer+head_size, r->length); r->body[r->length] = 0;
            result = 0; break;
        }
        if (used == sizeof(buffer)-1) { result = 413; break; }
    }
    erase(buffer, sizeof(buffer)); return result;
}
static int send_all(int fd, const char *p, size_t n, int64_t deadline)
{
    while (n) {
        ssize_t r;
        if (wait_ready(fd, POLLOUT, deadline) < 0) return -1;
        r = send(fd, p, n, MSG_DONTWAIT | MSG_NOSIGNAL);
        if (r < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (r <= 0) return -1;
        p += r; n -= (size_t)r;
    }
    return 0;
}
static const char *reason(int code)
{
    switch (code) {
    case 200: return "OK"; case 202: return "Accepted"; case 303: return "See Other";
    case 400: return "Bad Request"; case 403: return "Forbidden"; case 404: return "Not Found";
    case 405: return "Method Not Allowed"; case 408: return "Request Timeout";
    case 409: return "Conflict"; case 411: return "Length Required";
    case 413: return "Payload Too Large"; case 415: return "Unsupported Media Type";
    case 417: return "Expectation Failed"; case 431: return "Request Header Fields Too Large";
    case 503: return "Service Unavailable"; default: return "Internal Server Error";
    }
}
static void respond_policy(int fd, int code, const char *type, const char *extra,
                           const char *body, int signs_page)
{
    char header[1024];
    size_t n = strlen(body);
    int len;
    int64_t deadline = now_ms()+C2M_WEB_TIMEOUT_MS;
    len = snprintf(header, sizeof(header), "HTTP/1.1 %d %s\r\nContent-Type: %s\r\n"
        "Content-Length: %lu\r\nConnection: close\r\nCache-Control: no-store\r\n"
        /* Chromium serializes HTTP form Origin as null with no-referrer.
         * same-origin keeps legitimate POST origins, without cross-site leaks.
         * Do not accept Origin:null or weaken the Host/CSRF checks instead. */
        "X-Content-Type-Options: nosniff\r\nReferrer-Policy: same-origin\r\n"
        "Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'%s\r\n%s\r\n",
        code, reason(code), type, (unsigned long)n,
        signs_page ? "; script-src 'self'; connect-src 'self'" : "", extra ? extra : "");
    if (len < 0 || (size_t)len >= sizeof(header)) return;
    if (send_all(fd, header, (size_t)len, deadline) == 0) send_all(fd, body, n, deadline);
}
static void respond(int fd, int code, const char *type, const char *extra, const char *body)
{
    respond_policy(fd, code, type, extra, body, 0);
}
static void error_response(int fd, int code, const char *error)
{
    char body[128];
    snprintf(body, sizeof(body), "{\"ok\":false,\"error\":\"%s\"}\n", error);
    respond(fd, code, "application/json; charset=utf-8", NULL, body);
}
static int one_of(const char *value, const char *const *choices)
{
    while (*choices) if (!strcmp(value, *choices++)) return 1;
    return 0;
}
static void load_status(const struct service *s, struct status *status)
{
    static const char *const supports[] = {"yes", "no", "unknown", NULL};
    static const char *const states[] = {"unknown", "idle", "disconnected", "connecting", "associating", "connected", "associated_no_ip", "stopped", "failed", "unsupported", NULL};
    static const char *const errors[] = {"none", "unknown", "auth_failed", "no_config", "no_network", "dhcp_failed", "dhcp_helper_missing", "unsupported", "ap_unavailable", "controller_unavailable", "controller_error", "nl80211_unavailable", "ap_not_verified", "ap_nl80211_query_failed", "ap_name_missing_or_invalid", "ap_type_missing_or_invalid", "ap_frequency_missing_or_invalid", "preexisting_vif", "capability_missing_or_malformed", "capability_nl80211_query_failed", "capability_proof_unavailable", "ap_sta_combination_not_proven", "private_paths_or_supplicant_unavailable", "configuration_missing_or_invalid", "root_required_for_association", "private_runtime_unavailable", "vif_creation_failed_or_ambiguous", "supplicant_failed_or_unverified", "cleanup_unverified_manual_recovery_required", "ap_changed_or_unverifiable", "owned_station_lost", "association_timeout_or_unverified", "request_invalid_or_unsafe", NULL};
    static const char *const bt_values[] = {"unknown", "unavailable", "seen", "not_seen", "disabled", NULL};
    char text[C2M_WEB_MAX_BODY+1], *line, *save = NULL;
    int fd;
    size_t used = 0;
    memset(status, 0, sizeof(*status));
    strcpy(status->supported, "unknown"); strcpy(status->state, "unknown");
    strcpy(status->error, "unknown"); strcpy(status->bt, "unknown");
    fd = open_status(s->status_path);
    if (fd < 0) return;
    while (used < sizeof(text)-1) {
        ssize_t n = read(fd, text+used, sizeof(text)-1-used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { close(fd); erase(text, sizeof(text)); return; }
        if (!n) break;
        used += (size_t)n;
    }
    /* If the file grew beyond its checked size, ignore the entire snapshot. */
    {
        char extra;
        ssize_t n = read(fd, &extra, 1);
        close(fd);
        if (n != 0 || memchr(text, 0, used)) { erase(text, sizeof(text)); return; }
    }
    text[used] = 0; status->available = 1;
    line = strtok_r(text, "\n", &save);
    while (line) {
        char *eq = strchr(line, '=');
        if (eq) {
            char *value = eq+1;
            size_t n = strlen(value), i;
            *eq = 0;
            if (n && value[n-1] == '\r') value[--n] = 0;
            if (!strcmp(line, "sta_supported") && one_of(value, supports)) strcpy(status->supported, value);
            else if (!strcmp(line, "sta_state") && one_of(value, states)) strcpy(status->state, value);
            else if (!strcmp(line, "bt_presence") && one_of(value, bt_values)) strcpy(status->bt, value);
            else if (!strcmp(line, "last_error")) {
                /* Never reflect arbitrary controller error text, which could
                 * accidentally contain a passphrase. Only fixed error codes. */
                strcpy(status->error, one_of(value, errors) ? value : "controller_error");
            } else if (!strcmp(line, "sta_ipv4")) {
                struct in_addr address;
                if (inet_pton(AF_INET, value, &address) == 1) inet_ntop(AF_INET, &address, status->ipv4, sizeof(status->ipv4));
            } else if (!strcmp(line, "sta_ssid") && n <= 32) {
                /* ASCII display approximation; credentials are never read. */
                for (i = 0; i < n; i++) status->ssid[i] = ((unsigned char)value[i] >= 0x20 && (unsigned char)value[i] <= 0x7e) ? value[i] : '?';
                status->ssid[n] = 0;
            }
        }
        line = strtok_r(NULL, "\n", &save);
    }
    erase(text, sizeof(text));
}
static void escape_json(const char *in, char *out, size_t cap)
{
    size_t n = 0;
    while (*in && n+3 < cap) {
        unsigned char c = (unsigned char)*in++;
        if (c == '"' || c == '\\') out[n++] = '\\';
        out[n++] = (char)c;
    }
    out[n] = 0;
}
static void escape_html(const char *in, char *out, size_t cap)
{
    size_t n = 0;
    while (*in) {
        const char *escaped = NULL;
        size_t len;
        switch (*in) {
        case '&': escaped = "&amp;"; break; case '<': escaped = "&lt;"; break;
        case '>': escaped = "&gt;"; break; case '"': escaped = "&quot;"; break;
        case '\'': escaped = "&#39;"; break;
        }
        len = escaped ? strlen(escaped) : 1;
        if (n+len >= cap) break;
        if (escaped) memcpy(out+n, escaped, len); else out[n] = *in;
        n += len; in++;
    }
    out[n] = 0;
}
static void status_response(int fd, struct service *s)
{
    struct status status;
    char body[2048], ssid[260];
    load_status(s, &status); escape_json(status.ssid, ssid, sizeof(ssid));
    snprintf(body, sizeof(body), "{\"ap_active\":%s,\"ap_ipv4\":\"%s\",\"test_mode\":%s,"
        "\"config_saved\":%s,\"connect_pending\":%s,\"controller_status_available\":%s,"
        "\"sta_supported\":\"%s\",\"sta_state\":\"%s\",\"sta_ssid\":\"%s\","
        "\"sta_ipv4\":\"%s\",\"last_error\":\"%s\",\"bt_presence\":\"%s\"}\n",
        s->loopback ? "null" : "true", s->loopback ? "" : s->address_text,
        s->loopback ? "true" : "false", owned_file(s->config_fd, CONFIG_NAME) == 1 ? "true" : "false",
        owned_file(s->run_fd, REQUEST_NAME) == 1 ? "true" : "false", status.available ? "true" : "false",
        status.supported, status.state, ssid, status.ipv4, status.error, status.bt);
    respond(fd, 200, "application/json; charset=utf-8", NULL, body);
}
static void signs_response(int fd, const struct service *s)
{
    struct sign_status status;
    char body[640];
    int n;
    read_sign_status(s, &status);
    n = snprintf(body, sizeof(body), "{\"version\":1,\"source\":\"gps_offline\","
        "\"status_available\":%s,\"state\":\"%s\",\"gps_fresh\":%s,\"active\":%s,"
        "\"sequence\":%" PRIu32 ",\"code\":\"%s\",\"speed_kmh\":%u,\"distance_m\":%u,"
        "\"event_id\":%" PRIu32 ",\"monotonic_ms\":%" PRIu64 ",\"expires_in_ms\":%u}\n",
        status.available ? "true" : "false", sign_states[status.state],
        status.gps_fresh ? "true" : "false", status.active ? "true" : "false",
        status.sequence, sign_codes[status.code], status.speed, status.distance,
        status.event_id, status.monotonic_ms, status.expires);
    if (n < 0 || (size_t)n >= sizeof(body)) { error_response(fd, 500, "signs_error"); return; }
    respond(fd, 200, "application/json; charset=utf-8", NULL, body);
}
static void signs_page_response(int fd)
{
    static const char page[] =
        "<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>C2M D4 · Biển báo ngoại tuyến</title><style>"
        "body{font:18px system-ui,sans-serif;max-width:760px;margin:1em auto;padding:0 1em;color:#17212b}"
        "#warning{border:4px solid #ae1723;padding:1em;text-align:center}"
        "#sign{font-size:2em;font-weight:bold}#speed{display:block;font-size:4em;font-weight:bold}"
        "button{padding:1em;font:inherit}.note{padding:1em;background:#eef4ff}"
        "[hidden]{display:none!important}</style><script src=\"/signs.js\" defer></script>"
        "</head><body><nav><a href=\"/\">Cấu hình WiFi · D3</a> · "
        "<a href=\"/api/signs\">JSON biển báo</a></nav><h1>Biển báo ngoại tuyến · D4</h1>"
        "<p class=\"note\">Biển trong dữ liệu gần vị trí GPS — không xác nhận làn/hướng/giới hạn đang hiệu lực</p>"
        "<p id=\"fresh\" role=\"status\">Chưa có dữ liệu mới — không hiển thị cảnh báo.</p>"
        "<section id=\"warning\" hidden aria-live=\"polite\"><div id=\"sign\"></div>"
        "<span id=\"speed\"></span><p id=\"distance\"></p></section>"
        "<p id=\"empty\">Không có cảnh báo đang hiển thị.</p>"
        "<button id=\"sound\" type=\"button\" aria-pressed=\"false\">Bật tiếng bíp trên điện thoại/trình duyệt</button>"
        "<p>Âm thanh mặc định tắt, chỉ bật sau khi bấm nút; bíp ngắn tạo cục bộ, "
        "không giọng đọc/TTS. Âm thanh qua điện thoại/trình duyệt, KHÔNG qua loa camera. "
        "Chỉ dùng khi trang ở tiền cảnh; trình duyệt có thể chặn âm thanh.</p>"
        "<p>Chỉ tham khảo, không thay thế quan sát biển thực tế hoặc các biện pháp an toàn. "
        "Không nhìn hay thao tác trang khi lái xe. Dữ liệu GPS/cơ sở dữ liệu có thể sai hoặc thiếu. "
        "Trang không truy cập GPS của điện thoại; không kết nối Internet, không dùng CDN. "
        "Nếu mất cập nhật, cảnh báo tự xóa sau tối đa 3 giây; ẩn trang sẽ xóa ngay.</p>"
        "<noscript>Cần JavaScript để cập nhật. Không có cảnh báo trực tiếp khi JavaScript tắt.</noscript>"
        "</body></html>\n";
    respond_policy(fd, 200, "text/html; charset=utf-8", NULL, page, 1);
}
static void signs_script_response(int fd)
{
    /* Static script: no status text, credentials or per-device values embedded.
     * Only textContent with fixed labels and bounded numbers reaches the DOM. */
    static const char script[] =
        "'use strict';\n(() => {\n"
        "const el = id => document.getElementById(id);\n"
        "const states = Object.freeze({waiting_gps:'Chờ GPS',warming_up:'GPS đang ổn định',"
        "ready:'Sẵn sàng',stale:'Dữ liệu đã cũ',no_database:'Không có cơ sở dữ liệu',"
        "disabled:'Đã tắt',error:'Không có dữ liệu hợp lệ'});\n"
        "const labels = Object.freeze({none:'',speed_limit:'Biển giới hạn tốc độ',"
        "residential_start:'Bắt đầu khu dân cư',residential_end:'Hết khu dân cư'});\n"
        "let audio = null, enabled = false, tone = null, lastEvent = null, soundEpoch = 0, soundBaseline = false;\n"
        "let expiresMono = 0, expiresWall = 0, expiryTimer = 0, busy = false, generation = 0, controller = null;\n"
        "const integer = (v, lo, hi) => Number.isSafeInteger(v) && v >= lo && v <= hi;\n"
        "const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);\n"
        "function clearWarning(message) {\n"
        "  clearTimeout(expiryTimer); expiresMono = expiresWall = 0;\n"
        "  el('warning').hidden = true; el('sign').textContent = ''; el('speed').textContent = '';\n"
        "  el('distance').textContent = ''; el('empty').hidden = false; el('fresh').textContent = message;\n"
        "}\n"
        "function mute() {\n"
        "  enabled = false; soundBaseline = false; if (tone) { try { tone.stop(); } catch (_) {} tone = null; }\n"
        "  if (audio && audio.state === 'running') audio.suspend().catch(() => {});\n"
        "  el('sound').textContent = 'Bật tiếng bíp trên điện thoại/trình duyệt';\n"
        "  el('sound').setAttribute('aria-pressed', 'false');\n"
        "}\n"
        "el('sound').addEventListener('click', async () => {\n"
        "  if (enabled) { mute(); return; }\n"
        "  if (document.hidden) return; el('sound').disabled = true; const epoch = generation;\n"
        "  try {\n"
        "    const Audio = window.AudioContext || window.webkitAudioContext;\n"
        "    if (!Audio) throw new Error('unavailable');\n"
        "    if (!audio) audio = new Audio(); await audio.resume();\n"
        "    if (document.hidden || epoch !== generation || audio.state !== 'running') throw new Error('suspended');\n"
        "    soundEpoch++; soundBaseline = false; enabled = true;\n"
        "    el('sound').textContent = 'Tắt tiếng bíp trên điện thoại/trình duyệt';\n"
        "    el('sound').setAttribute('aria-pressed', 'true');\n"
        "  } catch (_) { mute(); el('sound').textContent = 'Âm thanh bị chặn — bấm để thử bật lại'; }\n"
        "  finally { el('sound').disabled = false; }\n"
        "});\n"
        "function beep() {\n"
        "  if (!enabled || document.hidden || !audio || audio.state !== 'running') return;\n"
        "  try {\n"
        "    const oscillator = audio.createOscillator(), gain = audio.createGain(), t = audio.currentTime;\n"
        "    oscillator.frequency.value = 880; gain.gain.setValueAtTime(0, t);\n"
        "    gain.gain.linearRampToValueAtTime(0.035, t + 0.015);\n"
        "    gain.gain.linearRampToValueAtTime(0, t + 0.15);\n"
        "    oscillator.connect(gain); gain.connect(audio.destination); tone = oscillator;\n"
        "    oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); if (tone === oscillator) tone = null; };\n"
        "    oscillator.start(t); oscillator.stop(t + 0.18);\n"
        "  } catch (_) { mute(); }\n"
        "}\n"
        "function valid(s) {\n"
        "  return s && s.version === 1 && s.source === 'gps_offline' && own(states, s.state) && own(labels, s.code)\n"
        "    && typeof s.status_available === 'boolean' && typeof s.gps_fresh === 'boolean' && typeof s.active === 'boolean'\n"
        "    && integer(s.sequence, 0, 4294967295) && integer(s.event_id, 0, 4294967295)\n"
        "    && integer(s.speed_kmh, 0, 130) && (s.speed_kmh === 0 || s.speed_kmh >= 10)\n"
        "    && integer(s.distance_m, 0, 2000) && integer(s.expires_in_ms, 0, 3000)\n"
        "    && integer(s.monotonic_ms, 0, Number.MAX_SAFE_INTEGER);\n"
        "}\n"
        "function expired() {\n"
        "  if (expiresMono && (performance.now() >= expiresMono || Date.now() >= expiresWall))\n"
        "    clearWarning('Dữ liệu đã cũ — đã xóa cảnh báo.');\n"
        "}\n"
        "async function poll() {\n"
        "  if (busy || document.hidden) return; busy = true;\n"
        "  const epoch = generation, audioEpoch = soundEpoch, started = performance.now(), wall = Date.now();\n"
        "  controller = new AbortController(); const current = controller;\n"
        "  const timeout = setTimeout(() => current.abort(), 1800);\n"
        "  try {\n"
        "    const response = await fetch('/api/signs', {method:'GET', mode:'same-origin', credentials:'omit',\n"
        "      cache:'no-store', redirect:'error', signal:current.signal});\n"
        "    if (!response.ok || !response.headers.get('content-type')?.startsWith('application/json')) throw new Error('response');\n"
        "    const s = await response.json();\n"
        "    if (epoch !== generation || document.hidden) return;\n"
        "    if (!valid(s)) throw new Error('schema');\n"
        "    const remaining = s.expires_in_ms - Math.max(performance.now() - started, Date.now() - wall, 0);\n"
        "    clearWarning(states[s.state] + ' — không có cảnh báo đang hiển thị.');\n"
        "    if (!s.status_available || !s.gps_fresh || s.state !== 'ready' || remaining <= 0) {\n"
        "      if (remaining <= 0 && s.status_available) el('fresh').textContent = 'Dữ liệu đã cũ — đã xóa cảnh báo.';\n"
        "      return;\n"
        "    }\n"
        /* Audio has its own epoch: pre-enable responses still render, but cannot
         * beep or arm sound. The first fresh post-enable poll is a silent baseline,
         * including when AudioContext.resume() or a foreground fetch was pending. */
        "    const audible = enabled && audioEpoch === soundEpoch && soundBaseline;\n"
        "    if (enabled && audioEpoch === soundEpoch && !soundBaseline) {\n"
        "      lastEvent = s.event_id; soundBaseline = true;\n"
        "    }\n"
        "    el('fresh').textContent = 'GPS mới theo nguồn ngoại tuyến — không phải xác minh độc lập.';\n"
        "    expiresMono = performance.now() + remaining; expiresWall = Date.now() + remaining;\n"
        "    expiryTimer = setTimeout(expired, Math.ceil(remaining));\n"
        "    if (!s.active || s.code === 'none' || (s.code === 'speed_limit' && !s.speed_kmh)) return;\n"
        "    el('sign').textContent = labels[s.code];\n"
        "    el('speed').textContent = s.code === 'speed_limit' ? String(s.speed_kmh) + ' km/h' : '';\n"
        "    el('distance').textContent = 'Khoảng cách trong dữ liệu: ' + String(s.distance_m) + ' m';\n"
        "    const isNew = lastEvent !== s.event_id; lastEvent = s.event_id;\n"
        "    el('empty').hidden = true; el('warning').hidden = false;\n"
        "    if (audible && isNew) beep();\n"
        "  } catch (_) {\n"
        "    if (epoch === generation) clearWarning('Mất cập nhật hoặc dữ liệu không hợp lệ — đã xóa cảnh báo.');\n"
        "  } finally { clearTimeout(timeout); if (controller === current) controller = null; busy = false; }\n"
        "}\n"
        "function pause() {\n"
        "  generation++; if (controller) controller.abort(); mute();\n"
        "  clearWarning('Trang đã ẩn hoặc vừa trở lại — chờ dữ liệu mới.');\n"
        "}\n"
        "document.addEventListener('visibilitychange', () => { pause(); if (!document.hidden) poll(); });\n"
        "window.addEventListener('pagehide', pause);\n"
        "window.addEventListener('pageshow', () => { clearWarning('Chờ dữ liệu mới.'); poll(); });\n"
        "setInterval(poll, 1000); setInterval(expired, 250); poll();\n"
        "})();\n";
    respond(fd, 200, "application/javascript; charset=utf-8", NULL, script);
}
static const char *notice_for(const char *path)
{
    if (!strcmp(path, "/?notice=saved")) return "Đã lưu cấu hình riêng tư. Chưa kết nối; hãy bấm Kết nối khi sẵn sàng.";
    if (!strcmp(path, "/?notice=queued")) return "Đã gửi yêu cầu tới bộ điều khiển. Đây không phải xác nhận đã kết nối.";
    if (!strcmp(path, "/?notice=forgotten")) return "Đã xóa cấu hình do dịch vụ lưu. Không thay đổi kết nối đang hoạt động.";
    return "";
}
static void page_response(int fd, struct service *s, const char *path)
{
    struct status status;
    char body[8192], ssid[800];
    int len;
    load_status(s, &status); escape_html(status.ssid, ssid, sizeof(ssid));
    len = snprintf(body, sizeof(body),
        "<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>C2M D3 · Cấu hình WiFi</title><style>body{font:16px system-ui,sans-serif;"
        "max-width:760px;margin:2em auto;padding:0 1em;color:#17212b}"
        "fieldset{margin:1em 0;padding:1em}label{display:block;margin:.8em 0}"
        "input{display:block;max-width:100%%;padding:.5em}button{padding:.7em 1em}"
        ".note{background:#eef4ff;padding:1em}dt{font-weight:bold}dd{margin-bottom:.5em}"
        "</style></head><body><h1>Cấu hình WiFi · D3</h1><p class=\"note\">%s</p>"
        "<p>%s</p><p>Lưu cấu hình không tự kết nối. Dịch vụ chỉ gửi yêu cầu; "
        "bộ điều khiển phải giữ điểm truy cập (AP) hoạt động khi thử kết nối STA. "
        "Khả năng AP + STA chưa được xác nhận nếu trạng thái là unknown.</p>"
        "<h2>Trạng thái do bộ điều khiển báo cáo</h2><dl>"
        "<dt>Tệp trạng thái</dt><dd>%s</dd><dt>Hỗ trợ STA</dt><dd>%s</dd>"
        "<dt>STA</dt><dd>%s</dd><dt>SSID đang kết nối</dt><dd>%s</dd>"
        "<dt>IPv4 STA</dt><dd>%s</dd><dt>Lỗi</dt><dd>%s</dd>"
        "<dt>Bluetooth hiện diện thụ động</dt><dd>%s</dd>"
        "<dt>Cấu hình đã lưu</dt><dd>%s</dd><dt>Yêu cầu kết nối chờ xử lý</dt><dd>%s</dd></dl>"
        "<p>Không có dữ liệu Bluetooth nghĩa là chưa biết; trang này không quét "
        "Bluetooth, không đọc nhật ký và không xác nhận có thiết bị.</p>"
        "<form method=\"post\" action=\"/api/wifi\"><fieldset><legend>Lưu WiFi WPA2</legend>"
        "<input type=\"hidden\" name=\"csrf\" value=\"%s\">"
        "<label>SSID (1–32 byte UTF-8)<input name=\"ssid\" required autocomplete=\"off\"></label>"
        "<label>Mật khẩu (8–63 ký tự ASCII, hoặc 64 ký tự hex)"
        "<input type=\"password\" name=\"password\" required minlength=\"8\" maxlength=\"64\" "
        "autocomplete=\"new-password\"></label><button type=\"submit\">Lưu, chưa kết nối</button>"
        "</fieldset></form><form method=\"post\" action=\"/api/connect\">"
        "<input type=\"hidden\" name=\"csrf\" value=\"%s\"><button type=\"submit\">"
        "Kết nối (giữ AP)</button></form><form method=\"post\" action=\"/api/forget\">"
        "<input type=\"hidden\" name=\"csrf\" value=\"%s\"><p><button type=\"submit\">"
        "Quên cấu hình đã lưu</button></p></form><p><a href=\"/\">Làm mới trạng thái</a> · "
        "<a href=\"/api/status\">JSON trạng thái</a> · <a href=\"/signs\">Biển báo ngoại tuyến · D4</a></p><p>Không có chức năng đặt lại, "
        "ghi flash, thay đổi ghi hình hoặc nvconf. HTTP không mã hóa; chỉ dùng "
        "trong AP đáng tin cậy, không công khai ra Internet.</p></body></html>\n",
        s->loopback ? "Chế độ thử trên localhost; chưa xác nhận AP của camera." : "Trang chỉ phục vụ tại IPv4 AP đã xác minh của wlan0; AP hiện đang hoạt động.",
        notice_for(path), status.available ? "Có dữ liệu (không phải xác minh độc lập)" : "Chưa có dữ liệu — trạng thái chưa biết",
        status.supported, status.state, ssid, status.ipv4, status.error, status.bt,
        owned_file(s->config_fd, CONFIG_NAME) == 1 ? "Có" : "Không",
        owned_file(s->run_fd, REQUEST_NAME) == 1 ? "Có" : "Không", s->token, s->token, s->token);
    if (len < 0 || (size_t)len >= sizeof(body)) { error_response(fd, 500, "page_error"); return; }
    respond(fd, 200, "text/html; charset=utf-8", NULL, body);
}
static int form_content_type(const char *value)
{
    return !strcmp(value, "application/x-www-form-urlencoded")
        || !strcmp(value, "application/x-www-form-urlencoded; charset=UTF-8")
        || !strcmp(value, "application/x-www-form-urlencoded; charset=utf-8");
}
static void handle_request(int fd, struct service *s)
{
    struct request request;
    struct form form;
    int result = read_request(fd, &request);
    memset(&form, 0, sizeof(form));
    if (result) { error_response(fd, result, "invalid_request"); goto done; }
    if ((request.host[0] && strcmp(request.host, s->host))
        || (request.origin[0] && strcmp(request.origin, s->origin))) {
        error_response(fd, 403, "origin_or_host_rejected"); goto done;
    }
    if (!ap_still_valid(s)) { error_response(fd, 503, "ap_unavailable"); stopped = 1; goto done; }
    if (!strcmp(request.method, "GET")) {
        if (!strcmp(request.path, "/") || *notice_for(request.path)) page_response(fd, s, request.path);
        else if (!strcmp(request.path, "/api/status")) status_response(fd, s);
        else if (!strcmp(request.path, "/signs") || !strcmp(request.path, "/api/signs") || !strcmp(request.path, "/signs.js")) {
            if (request.fetch_site[0] && strcmp(request.fetch_site, "same-origin") && strcmp(request.fetch_site, "none"))
                error_response(fd, 403, "cross_origin_rejected");
            else if (!strcmp(request.path, "/signs")) signs_page_response(fd);
            else if (!strcmp(request.path, "/api/signs")) signs_response(fd, s);
            else signs_script_response(fd);
        }
        else error_response(fd, 404, "not_found");
        goto done;
    }
    if (strcmp(request.path, "/api/wifi") && strcmp(request.path, "/api/connect") && strcmp(request.path, "/api/forget")) {
        error_response(fd, 404, "not_found"); goto done;
    }
    if (!form_content_type(request.content_type)) { error_response(fd, 415, "form_required"); goto done; }
    if ((request.fetch_site[0] && strcmp(request.fetch_site, "same-origin") && strcmp(request.fetch_site, "none"))) {
        error_response(fd, 403, "cross_origin_rejected"); goto done;
    }
    if (parse_form(request.body, request.length, &form) < 0) { error_response(fd, 400, "invalid_form"); goto done; }
    if (!(form.fields & 1) || !equal_token(form.csrf, s->token)) { error_response(fd, 403, "csrf_rejected"); goto done; }
    if (!strcmp(request.path, "/api/wifi")) {
        if (form.fields != 7 || !valid_utf8_ssid(form.ssid, form.ssid_len) || !valid_password(form.password, form.password_len)) {
            error_response(fd, 400, "invalid_credentials"); goto done;
        }
        if (owned_file(s->run_fd, REQUEST_NAME) != 0) {
            error_response(fd, 409, "connect_pending_or_unsafe"); goto done;
        }
        if (save_credentials(s, &form) < 0) { error_response(fd, 500, "save_failed"); goto done; }
        respond(fd, 303, "text/plain; charset=utf-8", "Location: /?notice=saved\r\n", "Saved, not connected.\n");
    } else {
        if (form.fields != 1) { error_response(fd, 400, "unexpected_fields"); goto done; }
        if (!strcmp(request.path, "/api/connect")) {
            if (owned_file(s->config_fd, CONFIG_NAME) != 1) { error_response(fd, 409, "no_safe_config"); goto done; }
            result = atomic_publish(s->run_fd, REQUEST_NAME, "version=1\naction=connect\n", 1);
            if (result) { error_response(fd, result == 1 ? 409 : 500, result == 1 ? "connect_pending" : "queue_failed"); goto done; }
            respond(fd, 303, "text/plain; charset=utf-8", "Location: /?notice=queued\r\n", "Request queued; connection unconfirmed.\n");
        } else {
            result = owned_file(s->config_fd, CONFIG_NAME);
            if (result < 0 || (result && unlinkat(s->config_fd, CONFIG_NAME, 0) < 0) || fsync(s->config_fd) < 0) {
                error_response(fd, 500, "forget_failed"); goto done;
            }
            respond(fd, 303, "text/plain; charset=utf-8", "Location: /?notice=forgotten\r\n", "Saved configuration removed; network unchanged.\n");
        }
    }
done:
    erase(&form, sizeof(form)); erase(&request, sizeof(request));
}
static void stop_signal(int sig)
{
    (void)sig; stopped = 1;
}
#endif
int c2m_web_self_test(void)
{
    static const char expected[] = "f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e";
    struct sha1 sha;
    struct form form;
    struct request request;
    struct sign_status sign;
    char sign_text[] = "version=1\nsource=gps_offline\nstate=ready\ngps_fresh=1\nactive=1\n"
        "sequence=9\ncode=speed_limit\nspeed_kmh=50\ndistance_m=100\nevent_id=4\nmonotonic_ms=1000\n";
    unsigned char output[32], decoded[33];
    char hex[65];
    size_t n;
    char header1[] = "GET / HTTP/1.1\r\nHost: 127.0.0.1:8099\r\n\r\n";
    char header2[] = "POST /api/wifi HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n";
    char header3[] = "POST /api/wifi HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n";
    sha1_init(&sha); sha1_update(&sha, "abc", 3); sha1_finish(&sha, output); to_hex(output, 20, hex);
    if (strcmp(hex, "a9993e364706816aba3e25717850c26c9cd0d89d")) return 1;
    derive_psk((const unsigned char *)"password", 8, (const unsigned char *)"IEEE", 4, output);
    to_hex(output, 32, hex); if (strcmp(hex, expected)) return 1;
    derive_psk((const unsigned char *)"ThisIsAPassword", 15,
               (const unsigned char *)"ThisIsASSID", 11, output);
    to_hex(output, 32, hex);
    if (strcmp(hex, "0dc0d6eb90555ed6419756b9a15ec3e3209b63df707dd508d14581f8982721af")) return 1;
    hmac_sha1((const unsigned char *)"Jefe", 4,
              (const unsigned char *)"what do ya want for nothing?", 28, output);
    to_hex(output, 20, hex);
    if (strcmp(hex, "effcdf6ae5eb2fa2d27416d5f184df9c259a7c79")) return 1;
    if (url_decode((const unsigned char *)"caf%C3%A9+WiFi", sizeof("caf%C3%A9+WiFi") - 1, decoded, 32, &n) < 0
        || !valid_utf8_ssid(decoded, n)) return 1;
    if (url_decode((const unsigned char *)"%00", 3, decoded, 32, &n) == 0) return 1;
    if (url_decode((const unsigned char *)"%0A", 3, decoded, 32, &n) == 0) return 1;
    if (parse_form((const unsigned char *)"csrf=a&csrf=b", 13, &form) == 0) return 1;
    if (parse_headers(header1, &request) || parse_headers(header2, &request) != 400
        || parse_headers(header3, &request) != 400) return 1;
    if (!valid_password((const unsigned char *)"a\"b\\cdef", 8)
        || valid_password((const unsigned char *)"short", 5)
        || valid_password((const unsigned char *)"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 64)) return 1;
    if (!equal_token(expected, expected) || equal_token(expected, "short")) return 1;
    if (parse_sign_status(sign_text, sizeof(sign_text) - 1, 3000, &sign) < 0
        || !sign.active || sign.code != SIGN_SPEED || sign.speed != 50) return 1;
    sign_text[0] = 'x';
    if (parse_sign_status(sign_text, sizeof(sign_text) - 1, 3000, &sign) == 0) return 1;
    if (valid_utf8_ssid((const unsigned char *)"\xc0\xaf", 2)
        || valid_utf8_ssid((const unsigned char *)"\xed\xa0\x80", 3)
        || valid_utf8_ssid((const unsigned char *)"\xf4\x90\x80\x80", 4)
        || valid_utf8_ssid((const unsigned char *)"bad\nssid", 8)) return 1;
    erase(output, sizeof(output)); erase(hex, sizeof(hex)); erase(&form, sizeof(form));
    erase(&request, sizeof(request));
    puts("c2m-web self-test: OK"); return 0;
}
#ifdef C2M_WEB_CORE_ONLY
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--self-test")) return c2m_web_self_test();
    fputs("Core-only build: use --self-test; no network service available.\n", stderr);
    return 1;
}
#else
static void usage(FILE *out)
{
    fputs("Usage: c2m-web [--bind 127.0.0.1] [--port 8099]\n"
          "  [--config-dir /customer/c2m-state] [--run-dir /tmp/c2m-d3]\n"
          "  [--status-file /tmp/c2m_wifi_status] [--sign-status-file /tmp/c2m_d4_status]\n"
          "  c2m-web --self-test\n"
          "Default binding requires validated AP mode and IPv4 on wlan0.\n"
          "Only the exact IPv4 loopback address is allowed as an explicit bind.\n", out);
}
int main(int argc, char **argv)
{
    struct service service;
    struct sockaddr_in address;
    struct stat config_stat, run_stat;
    struct sigaction action;
    unsigned char random[TOKEN_BYTES];
    const char *config = C2M_WEB_CONFIG_DIR, *run = C2M_WEB_RUN_DIR, *status = C2M_WEB_STATUS_FILE;
    const char *sign_status = C2M_WEB_SIGN_STATUS_FILE;
    int listener = -1, reuse = 1, i, exit_code = 1;
    memset(&service, 0, sizeof(service)); service.config_fd = service.run_fd = -1;
    service.port = C2M_WEB_DEFAULT_PORT;
    if (argc == 2 && !strcmp(argv[1], "--self-test")) return c2m_web_self_test();
    if (argc == 2 && !strcmp(argv[1], "--help")) { usage(stdout); return 0; }
    for (i = 1; i < argc; i += 2) {
        const char *value;
        if (i+1 >= argc) { usage(stderr); goto done; }
        value = argv[i+1];
        if (!strcmp(argv[i], "--bind")) {
            if (strcmp(value, "127.0.0.1")) { fputs("Only explicit loopback binding is permitted.\n", stderr); goto done; }
            service.loopback = 1;
        } else if (!strcmp(argv[i], "--port")) {
            char *end;
            long port;
            if (!*value || strspn(value, "0123456789") != strlen(value)) { usage(stderr); goto done; }
            errno = 0; port = strtol(value, &end, 10);
            if (errno || *end || port < 1 || port > 65535) { usage(stderr); goto done; }
            service.port = (unsigned short)port;
        } else if (!strcmp(argv[i], "--config-dir")) config = value;
        else if (!strcmp(argv[i], "--run-dir")) run = value;
        else if (!strcmp(argv[i], "--status-file")) status = value;
        else if (!strcmp(argv[i], "--sign-status-file")) sign_status = value;
        else { usage(stderr); goto done; }
    }
    if (status[0] != '/') { fputs("Status path must be absolute.\n", stderr); goto done; }
    if (sign_status[0] != '/') { fputs("Sign status path must be absolute.\n", stderr); goto done; }
    service.status_path = status; service.sign_status_path = sign_status;
    if (service.loopback) {
        inet_pton(AF_INET, "127.0.0.1", &service.address);
        inet_pton(AF_INET, "255.0.0.0", &service.mask);
    } else if (ap_address(&service.address, &service.mask) < 0) {
        fputs("Cannot validate wlan0 AP mode/address; refusing to listen.\n", stderr); goto done;
    }
    if (!inet_ntop(AF_INET, &service.address, service.address_text, sizeof(service.address_text))) goto done;
    snprintf(service.host, sizeof(service.host), "%s:%u", service.address_text, service.port);
    if (service.port == 80) snprintf(service.host, sizeof(service.host), "%s", service.address_text);
    snprintf(service.origin, sizeof(service.origin), "http://%s", service.host);
    service.config_fd = open_directory(config, 1); service.run_fd = open_directory(run, 1);
    if (service.config_fd < 0 || service.run_fd < 0
        || fstat(service.config_fd, &config_stat) < 0 || fstat(service.run_fd, &run_stat) < 0
        || (config_stat.st_dev == run_stat.st_dev && config_stat.st_ino == run_stat.st_ino)) {
        fputs("Config/run directories must be distinct, owned, private and free of symlinks.\n", stderr); goto done;
    }
    if (random_bytes(random, sizeof(random)) < 0) { fputs("Secure random source unavailable.\n", stderr); goto done; }
    to_hex(random, sizeof(random), service.token); erase(random, sizeof(random));
    memset(&action, 0, sizeof(action)); action.sa_handler = stop_signal; sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL); sigaction(SIGTERM, &action, NULL);
    signal(SIGPIPE, SIG_IGN);
    listener = socket(AF_INET, SOCK_STREAM, 0);
    if (listener < 0) goto done;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    fcntl(listener, F_SETFD, FD_CLOEXEC);
    memset(&address, 0, sizeof(address)); address.sin_family = AF_INET;
    address.sin_addr = service.address; address.sin_port = htons(service.port);
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) < 0 || listen(listener, 8) < 0) {
        fputs("Cannot bind private web listener.\n", stderr); goto done;
    }
    printf("c2m-web listening on %s%s\n", service.host, service.loopback ? " (host test mode)" : " (validated wlan0 AP)");
    fflush(stdout); exit_code = 0;
    while (!stopped) {
        struct pollfd p;
        struct sockaddr_in peer;
        socklen_t peer_len = sizeof(peer);
        int client, result;
        if (!ap_still_valid(&service)) { fputs("AP validation changed; stopping listener.\n", stderr); exit_code = 1; break; }
        p.fd = listener; p.events = POLLIN; p.revents = 0;
        result = poll(&p, 1, 1000);
        if (result < 0 && errno == EINTR) continue;
        if (result < 0) { exit_code = 1; break; }
        if (!result) continue;
        if (!(p.revents & POLLIN)) { exit_code = 1; break; }
        client = accept(listener, (struct sockaddr *)&peer, &peer_len);
        if (client < 0 && errno == EINTR) continue;
        if (client < 0) { exit_code = 1; break; }
        fcntl(client, F_SETFD, FD_CLOEXEC);
        if (peer.sin_family == AF_INET
            && ((peer.sin_addr.s_addr & service.mask.s_addr) == (service.address.s_addr & service.mask.s_addr))) {
            handle_request(client, &service);
        }
        close(client);
    }
done:
    if (listener >= 0) close(listener);
    if (service.config_fd >= 0) close(service.config_fd);
    if (service.run_fd >= 0) close(service.run_fd);
    erase(random, sizeof(random)); erase(service.token, sizeof(service.token));
    return exit_code;
}
#endif
