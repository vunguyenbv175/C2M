/* c2m-warner daemon: NMEA GPS in -> offline sign Warner -> alert log.
 *
 * Usage: c2m-warner [-d /dev/ttyS1] [-b 9600] [-s signs.bin] [-l /tmp/c2m_warner.log]
 *
 * Alert output v1: log lines. Sound/display hooks are marked HOOK and left
 * for device bring-up (cardv fifo command format needs runtime verification).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <termios.h>
#include "warner.h"
#include "nmea.h"
#include "db.h"

static int open_serial(const char *dev, int baud) {
    int fd = open(dev, O_RDONLY | O_NOCTTY | O_NONBLOCK);
    struct termios t;
    speed_t sp;
    if (fd < 0) return -1;
    if (tcgetattr(fd, &t) != 0) {
        /* not a tty (e.g. test input file): use as-is */
        return fd;
    }
    cfmakeraw(&t);
    switch (baud) {
    case 4800: sp = B4800; break;
    case 38400: sp = B38400; break;
    case 115200: sp = B115200; break;
    default: sp = B9600; break;
    }
    cfsetispeed(&t, sp);
    t.c_cc[VMIN] = 0;
    t.c_cc[VTIME] = 10; /* 1s read timeout */
    if (tcsetattr(fd, TCSANOW, &t) != 0) { close(fd); return -1; }
    return fd;
}

/* Monotonic clock driven by GPS time (RMC hhmmss), not libc: the toolchain
 * redirects clock_gettime/gettimeofday to __*_time64@GLIBC_2.34, absent on
 * the 2.30 device loader. Handles midnight wrap; nudged forward if GPS
 * time ever steps back (reacquire). Good enough for cooldown timing. */
static double gps_day_base = 0.0;
static double gps_last_t = -1.0;

static double gps_now_s(double tod_s) {
    double t;
    if (tod_s < 0) {
        /* no GPS time: advance slowly from last known */
        return gps_last_t < 0 ? 0.0 : gps_last_t + 1.0;
    }
    if (gps_last_t >= 0) {
        double last_tod = gps_last_t - gps_day_base;
        if (tod_s < last_tod - 43200.0) gps_day_base += 86400.0; /* midnight */
    }
    t = gps_day_base + tod_s;
    if (t <= gps_last_t) t = gps_last_t + 0.2;
    gps_last_t = t;
    return t;
}

int main(int argc, char **argv) {
    const char *dev = "/dev/ttyS1";
    const char *dbpath = "/customer/c2m-warner/signs.bin";
    const char *logpath = "/tmp/c2m_warner.log";
    int baud = 9600, i;
    int fd, n_signs = 0;
    warner_sign_t *signs;
    warner_t w;
    double *state;
    warner_alert_t alerts[16];
    FILE *logf;
    char line[512];
    int llen = 0;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-d") && i + 1 < argc) dev = argv[++i];
        else if (!strcmp(argv[i], "-b") && i + 1 < argc) baud = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-s") && i + 1 < argc) dbpath = argv[++i];
        else if (!strcmp(argv[i], "-l") && i + 1 < argc) logpath = argv[++i];
    }

    signs = signdb_load(dbpath, &n_signs);
    if (!signs || n_signs <= 0) {
        fprintf(stderr, "c2m-warner: cannot load sign db %s\n", dbpath);
        return 1;
    }
    state = (double *)calloc((size_t)n_signs, sizeof(double));
    warner_init(&w, signs, n_signs);
    warner_set_state(&w, state);

    logf = fopen(logpath, "a");
    if (logf) {
        fprintf(logf, "c2m-warner start: %d signs, gps=%s@%d\n", n_signs, dev, baud);
        fflush(logf);
    }

    fd = open_serial(dev, baud);
    if (fd < 0) {
        fprintf(stderr, "c2m-warner: cannot open %s: %s\n", dev, strerror(errno));
        if (logf) fprintf(logf, "WARN: cannot open %s: %s\n", dev, strerror(errno));
        /* keep running: GPS may appear later; retry loop below */
    }

    for (;;) {
        ssize_t r;
        char c;
        if (fd < 0) {
            sleep(5);
            fd = open_serial(dev, baud);
            continue;
        }
        r = read(fd, &c, 1);
        if (r <= 0) continue; /* timeout */
        if (c == '\n' || c == '\r') {
            if (llen > 0) {
                nmea_fix_t fix;
                line[llen] = '\0';
                if (nmea_parse_rmc(line, &fix) && fix.valid) {
                    double t = gps_now_s(fix.tod_s);
                    int na, k;
                    /* every valid RMC is evaluated (real GPS emits ~1 Hz);
                     * per-sign cooldown in warner_update() prevents spam */
                    na = warner_update(&w, fix.lat, fix.lon,
                                       fix.course_deg, fix.speed_kmh, t,
                                       alerts, 16);
                        for (k = 0; k < na; k++) {
                            const warner_sign_t *s =
                                &signs[alerts[k].sign_index];
                            /* HOOK: trigger sound/display here once the
                             * cardv fifo command format is verified. */
                            if (logf) {
                                fprintf(logf,
                                        "ALERT t=%.0f %s (%s) dist=%.0fm eta=%.0fs "
                                        "pos=%.6f,%.6f hdg=%.0f spd=%.0fkm/h\n",
                                        t, s->label, s->type,
                                        alerts[k].distance_m, alerts[k].eta_s,
                                        fix.lat, fix.lon,
                                        fix.course_deg, fix.speed_kmh);
                                fflush(logf);
                            }
                            printf("ALERT %s (%s) %.0fm\n",
                                   s->label, s->type, alerts[k].distance_m);
                            fflush(stdout);
                        }
                    }
                }
                llen = 0;
        } else if (llen < (int)sizeof(line) - 1) {
            line[llen++] = c;
        } else {
            llen = 0; /* overlong line: resync */
        }
    }
    return 0;
}
