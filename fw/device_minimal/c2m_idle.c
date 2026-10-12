/* c2m-idle — MINIMAL device binary + best-effort SD diagnostics (B2).
 *
 * Behaviour contract (only):
 *   start -> print version -> best-effort /tmp/c2m_idle.marker
 *        -> best-effort SD diag log -> sleep loop.
 *
 * SD diag layout (all steps best-effort; ANY failure leaves the daemon
 * running with stock behaviour untouched):
 *   <DIAG_DIR>/boot.seq      decimal boot counter (ring 0..RING-1)
 *   <DIAG_DIR>/boot-<i>.log  START + HEARTBEAT lines, capped per file
 *   <DIAG_DIR>/boot-fb.log   shared fallback when the counter is unusable
 * START carries version/pid/boot-id/uptime/marker-result.
 * HEARTBEAT carries uptime + sequence number every BEAT_EVERY wakes.
 * No network, no M4 transmit, no camera, no ADAS, no config writes.
 * No serials, keys, credentials or memory dumps are ever logged.
 * Label: HOST-CROSS-BUILT, NOT device-tested (until B2 acceptance).
 */
#include <stdio.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>

#ifndef C2M_IDLE_VERSION
#define C2M_IDLE_VERSION "0.2.0-sdlog1"
#endif
#ifndef C2M_MARKER_PATH
#define C2M_MARKER_PATH "/tmp/c2m_idle.marker"
#endif
#ifndef C2M_DIAG_DIR
#define C2M_DIAG_DIR "/mnt/mmc/C2M_DIAG"
#endif
#ifndef C2M_BOOTID_PATH
#define C2M_BOOTID_PATH "/proc/sys/kernel/random/boot_id"
#endif
#ifndef C2M_UPTIME_PATH
#define C2M_UPTIME_PATH "/proc/uptime"
#endif
#ifndef C2M_SLEEP_SEC
#define C2M_SLEEP_SEC 60
#endif
#ifndef C2M_BEAT_EVERY
#define C2M_BEAT_EVERY 5
#endif
#ifndef C2M_DIAG_RING
#define C2M_DIAG_RING 8
#endif
#ifndef C2M_DIAG_CAP_BYTES
#define C2M_DIAG_CAP_BYTES 65536UL
#endif

/* Tiny local string helpers: avoids versioned libc string symbols. */
static unsigned long s_len(const char *s) {
    const char *p = s;
    while (*p) ++p;
    return (unsigned long)(p - s);
}

static void s_copy(char *d, unsigned long cap, const char *s) {
    unsigned long i = 0;
    if (cap == 0) return;
    while (i + 1 < cap && s[i]) { d[i] = s[i]; ++i; }
    d[i] = 0;
}

static void s_cat(char *d, unsigned long cap, const char *s) {
    unsigned long n = s_len(d);
    if (n + 1 >= cap) return;
    s_copy(d + n, cap - n, s);
}

static void u_dec(char *d, unsigned long cap, unsigned long v) {
    char tmp[32];
    int n = 0;
    if (v == 0) tmp[n++] = '0';
    else {
        while (v && n < 31) { tmp[n++] = (char)('0' + (v % 10)); v /= 10; }
    }
    {
        unsigned long i = 0;
        while (n > 0 && i + 1 < cap) { d[i++] = tmp[--n]; }
        d[i] = 0;
    }
}

/* Read up to cap-1 bytes; returns bytes read, 0 on any failure. */
static unsigned long read_file(const char *path, char *buf, unsigned long cap) {
    FILE *f;
    unsigned long n = 0;
    size_t r;
    if (cap == 0) return 0;
    f = fopen(path, "r");
    if (!f) return 0;
    r = fread(buf, 1, (size_t)(cap - 1), f);
    n = (unsigned long)r;
    buf[n] = 0;
    fclose(f);
    return n;
}

/* Leading decimal value; *ok=0 when no digits present. */
static unsigned long parse_dec(const char *s, int *ok) {
    unsigned long v = 0;
    int digits = 0;
    while (*s >= '0' && *s <= '9') { v = v * 10 + (unsigned long)(*s - '0'); ++s; ++digits; }
    *ok = digits > 0;
    return v;
}

struct Diag {
    FILE *f;
    unsigned long bytes;
    int on;
};

static void diag_write(struct Diag *d, const char *line) {
    int r;
    if (!d->on || !d->f) return;
    r = fprintf(d->f, "%s", line);
    if (r < 0) { fclose(d->f); d->f = 0; d->on = 0; return; }
    d->bytes += (unsigned long)r;
    fflush(d->f);
    if (d->bytes > (unsigned long)C2M_DIAG_CAP_BYTES) {
        fclose(d->f);
        d->f = 0;
        d->on = 0;
    }
}

static void diag_init(struct Diag *d, const char *version, int marker_ok) {
    /* Stack buffers only; every step below tolerates failure. */
    char dir[256], seqp[256], path[256], line[256], num[32];
    char bootid[72], upt[48];
    unsigned long seq = 0, uptime = 0;
    int ok = 0, i;
    FILE *sf;
    d->f = 0;
    d->bytes = 0;
    d->on = 0;
    s_copy(dir, sizeof(dir), C2M_DIAG_DIR);
#ifdef _WIN32
    mkdir(dir); /* host-test shape; device uses the POSIX branch below */
#else
    mkdir(dir, 0755); /* ignore rc: absent/unwritable SD disables diag only */
#endif
    s_copy(seqp, sizeof(seqp), dir);
    s_cat(seqp, sizeof(seqp), "/boot.seq");
    if (read_file(seqp, num, sizeof(num)) > 0) {
        seq = parse_dec(num, &ok);
    }
    s_copy(path, sizeof(path), dir);
    {
        /* Ring slot always: first boot (no counter yet) uses slot 0 and
         * starts the counter at 1. Bounded by design in all cases. */
        unsigned long idx = 0, next = 1;
        if (ok) {
            idx = seq % (unsigned long)C2M_DIAG_RING;
            next = seq + 1;
        }
        s_cat(path, sizeof(path), "/boot-");
        u_dec(num, sizeof(num), idx);
        s_cat(path, sizeof(path), num);
        s_cat(path, sizeof(path), ".log");
        d->f = fopen(path, "w"); /* ring slot: truncate, bounded by design */
        if (d->f) {
            sf = fopen(seqp, "w");
            if (sf) {
                fprintf(sf, "%lu\n", next);
                fclose(sf);
            }
        } else {
            s_copy(path, sizeof(path), dir);
            s_cat(path, sizeof(path), "/boot-fb.log");
            d->f = fopen(path, "a"); /* last resort, still capped */
        }
    }
    if (!d->f) return;
    d->on = 1;
    /* boot id: first 8 hex chars, else "noid". */
    for (i = 0; i < 72; ++i) bootid[i] = 0;
    if (read_file(C2M_BOOTID_PATH, bootid, sizeof(bootid)) > 0) {
        char clean[16];
        int n = 0, k = 0;
        while (bootid[k] && n < 8) {
            char c = bootid[k++];
            if ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) clean[n++] = c;
        }
        clean[n] = 0;
        if (n > 0) s_copy(bootid, sizeof(bootid), clean);
        else s_copy(bootid, sizeof(bootid), "noid");
    } else {
        s_copy(bootid, sizeof(bootid), "noid");
    }
    /* uptime: seconds before '.'. */
    if (read_file(C2M_UPTIME_PATH, upt, sizeof(upt)) > 0) {
        uptime = parse_dec(upt, &ok);
        if (!ok) uptime = 0;
    }
    line[0] = 0;
    s_cat(line, sizeof(line), "START v=");
    s_cat(line, sizeof(line), version);
    s_cat(line, sizeof(line), " pid=");
    u_dec(num, sizeof(num), (unsigned long)getpid());
    s_cat(line, sizeof(line), num);
    s_cat(line, sizeof(line), " boot=");
    s_cat(line, sizeof(line), bootid);
    s_cat(line, sizeof(line), " uptime=");
    u_dec(num, sizeof(num), uptime);
    s_cat(line, sizeof(line), num);
    s_cat(line, sizeof(line), " marker=");
    s_cat(line, sizeof(line), marker_ok ? "ok" : "fail");
    s_cat(line, sizeof(line), "\n");
    diag_write(d, line);
}

static void diag_beat(struct Diag *d, unsigned long n) {
    char upt[48], line[128], num[32];
    unsigned long uptime = 0;
    int ok = 0;
    if (read_file(C2M_UPTIME_PATH, upt, sizeof(upt)) > 0) {
        uptime = parse_dec(upt, &ok);
        if (!ok) uptime = 0;
    }
    line[0] = 0;
    s_cat(line, sizeof(line), "HB uptime=");
    u_dec(num, sizeof(num), uptime);
    s_cat(line, sizeof(line), num);
    s_cat(line, sizeof(line), " n=");
    u_dec(num, sizeof(num), n);
    s_cat(line, sizeof(line), num);
    s_cat(line, sizeof(line), "\n");
    diag_write(d, line);
}

int main(void) {
    struct Diag dg;
    int marker_ok = 0;
    unsigned long wake = 0, beats = 0;
    FILE *f;
    printf("c2m-idle %s\n", C2M_IDLE_VERSION);
    fflush(stdout);
    f = fopen(C2M_MARKER_PATH, "w");
    if (f) {
        fprintf(f, "c2m-idle %s\n", C2M_IDLE_VERSION);
        fclose(f);
        marker_ok = 1;
    }
    diag_init(&dg, C2M_IDLE_VERSION, marker_ok);
    for (;;) {
        sleep(C2M_SLEEP_SEC);
        ++wake;
        if (wake % (unsigned long)C2M_BEAT_EVERY == 0) {
            ++beats;
            diag_beat(&dg, beats);
        }
    }
    return 0;
}
