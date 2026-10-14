/* Host-only GPS/database advisory replay; NOT vision TSR or a device daemon.
 * Usage: c2m-warner --replay <regular NMEA file> -s <db> [-l <log>]
 * No serial, stdin, audio, display, FIFO, or live-device integration.
 */
#ifndef _WIN32
#define _XOPEN_SOURCE 700
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <sys/stat.h>
#include <fcntl.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#else
#include <unistd.h>
#endif
#include "warner.h"
#include "nmea.h"
#include "db.h"

#define LOG_LIMIT (64u * 1024u)

#ifdef _WIN32
typedef struct _stat64 file_stat_t;
#define file_stat(fd, st) _fstat64((fd), (st))
#define file_fd(f) _fileno(f)
#define regular_file(st) (((st).st_mode & _S_IFMT) == _S_IFREG)
#else
typedef struct stat file_stat_t;
#define file_stat(fd, st) fstat((fd), (st))
#define file_fd(f) fileno(f)
#define regular_file(st) S_ISREG((st).st_mode)
#endif

static void usage(FILE *out) {
    fprintf(out, "Usage: c2m-warner --replay <regular NMEA file> -s <db> [-l <log>]\n"
                 "HOST/REPLAY SIMULATION only; live-device capability is BLOCKED.\n");
}

/* Reject device paths before opening anything. POSIX canonical paths are also
 * checked below, so /tmp/../dev/... and symlinked parents cannot bypass this. */
static int forbidden_path(const char *path) {
    if (!path || !*path || !strcmp(path, "-")) return 1;
    if (!strncmp(path, "/dev", 4) && (path[4] == '/' || path[4] == '\0')) return 1;
#ifdef _WIN32
    {
        const char *p = path;
        const char *colon = strchr(path, ':');
        /* No alternate data streams, drive aliases, or reserved console names. */
        if (colon && (colon != path + 1 ||
                      !((path[0] >= 'A' && path[0] <= 'Z') ||
                        (path[0] >= 'a' && path[0] <= 'z')) || strchr(colon + 1, ':'))) return 1;
        /* No UNC/network paths or Windows device namespaces. */
        if ((p[0] == '\\' || p[0] == '/') &&
            (p[1] == '\\' || p[1] == '/')) return 1;
        while (*p) {
            const char *start;
            size_t n;
            while (*p == '/' || *p == '\\') p++;
            start = p;
            while (*p && *p != '/' && *p != '\\') p++;
            n = strcspn(start, ". /\\");
            if ((n == 3 && (!_strnicmp(start, "CON", 3) ||
                            !_strnicmp(start, "PRN", 3) ||
                            !_strnicmp(start, "AUX", 3) ||
                            !_strnicmp(start, "NUL", 3))) ||
                (n == 4 && (!_strnicmp(start, "COM", 3) ||
                            !_strnicmp(start, "LPT", 3)) &&
                 start[3] >= '0' && start[3] <= '9')) return 1;
        }
    }
#endif
    return 0;
}

/* Final-component symlinks/reparse points are rejected. Validate the actual
 * opened descriptor, not just the pathname; never open a FIFO in blocking mode.
 * Logs are append-only, with no truncation of existing user files. */
static FILE *open_regular(const char *path, int append) {
    file_stat_t st;
    int fd;
    FILE *f;
    if (forbidden_path(path)) { errno = EINVAL; return NULL; }
#ifdef _WIN32
    {
        DWORD attributes = GetFileAttributesA(path);
        DWORD creation = OPEN_EXISTING;
        BY_HANDLE_FILE_INFORMATION info;
        HANDLE h;
        if (attributes == INVALID_FILE_ATTRIBUTES) {
            DWORD error = GetLastError();
            if (!append || error != ERROR_FILE_NOT_FOUND) {
                errno = ENOENT;
                return NULL;
            }
            creation = CREATE_NEW;
        } else if (attributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)) {
            errno = EINVAL;
            return NULL;
        }
        h = CreateFileA(path, append ? GENERIC_WRITE : GENERIC_READ,
                        FILE_SHARE_READ, NULL, creation,
                        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, NULL);
        if (h == INVALID_HANDLE_VALUE) { errno = EACCES; return NULL; }
        if (GetFileType(h) != FILE_TYPE_DISK ||
            !GetFileInformationByHandle(h, &info) ||
            (info.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT))) {
            CloseHandle(h);
            errno = EINVAL;
            return NULL;
        }
        fd = _open_osfhandle((intptr_t)h, _O_BINARY | (append ? _O_WRONLY | _O_APPEND : _O_RDONLY));
        if (fd < 0) { CloseHandle(h); return NULL; }
    }
#else
    {
        struct stat before;
        int exists = lstat(path, &before) == 0;
        int flags = (append ? O_WRONLY | O_APPEND : O_RDONLY) | O_NONBLOCK;
        char *resolved;
        if (!exists && (!append || errno != ENOENT)) return NULL;
        if (exists && !S_ISREG(before.st_mode)) { errno = EINVAL; return NULL; }
        if (exists) {
            resolved = realpath(path, NULL);
        } else {
            /* Resolve a new log's parent before creating it, including /dev
             * aliases. O_EXCL prevents a raced-in existing file being opened. */
            char *parent = strdup(path);
            char *slash;
            if (!parent) return NULL;
            slash = strrchr(parent, '/');
            if (!slash) strcpy(parent, ".");
            else if (slash == parent) slash[1] = '\0';
            else *slash = '\0';
            resolved = realpath(parent, NULL);
            free(parent);
            flags |= O_CREAT | O_EXCL;
        }
        if (!resolved) return NULL;
        if (forbidden_path(resolved)) { free(resolved); errno = EINVAL; return NULL; }
        free(resolved);
#ifdef O_NOFOLLOW
        flags |= O_NOFOLLOW;
#endif
        fd = open(path, flags, 0600);
        if (fd < 0) return NULL;
        if (file_stat(fd, &st) != 0 || !regular_file(st) ||
            (exists && (st.st_dev != before.st_dev || st.st_ino != before.st_ino))) {
            close(fd);
            errno = EINVAL;
            return NULL;
        }
        if (append) {
            /* Cooperating replay processes must not share the log budget. */
            struct flock lock;
            memset(&lock, 0, sizeof(lock));
            lock.l_type = F_WRLCK;
            lock.l_whence = SEEK_SET;
            if (fcntl(fd, F_SETLK, &lock) != 0) { close(fd); return NULL; }
        }
    }
#endif
    if (file_stat(fd, &st) != 0 || !regular_file(st)) {
#ifdef _WIN32
        _close(fd);
#else
        close(fd);
#endif
        errno = EINVAL;
        return NULL;
    }
#ifdef _WIN32
    f = _fdopen(fd, append ? "ab" : "rb");
#else
    f = fdopen(fd, append ? "ab" : "rb");
#endif
    if (!f) {
#ifdef _WIN32
        _close(fd);
#else
        close(fd);
#endif
    }
    return f;
}

static int same_file(FILE *a, FILE *b) {
#ifdef _WIN32
    BY_HANDLE_FILE_INFORMATION x, y;
    if (!GetFileInformationByHandle((HANDLE)_get_osfhandle(file_fd(a)), &x) ||
        !GetFileInformationByHandle((HANDLE)_get_osfhandle(file_fd(b)), &y)) return -1;
    return x.dwVolumeSerialNumber == y.dwVolumeSerialNumber &&
           x.nFileIndexHigh == y.nFileIndexHigh && x.nFileIndexLow == y.nFileIndexLow;
#else
    file_stat_t x, y;
    if (file_stat(file_fd(a), &x) != 0 || file_stat(file_fd(b), &y) != 0) return -1;
    return x.st_dev == y.st_dev && x.st_ino == y.st_ino;
#endif
}

static void disable_log(FILE **logf, const char *reason) {
    fprintf(stderr, "c2m-warner: optional log disabled (%s)\n", reason);
    fclose(*logf);
    *logf = NULL;
}

static void log_line(FILE **logf, const char *line) {
    file_stat_t st;
    size_t length;
    if (!*logf) return;
    length = strlen(line);
    /* Count existing bytes on every append, including previous runs. Never
     * truncate an oversized pre-existing file or write a partial log record. */
    if (file_stat(file_fd(*logf), &st) != 0 || st.st_size < 0) {
        disable_log(logf, "cannot inspect size");
    } else if ((uint64_t)st.st_size > LOG_LIMIT ||
               length > LOG_LIMIT - (uint64_t)st.st_size) {
        disable_log(logf, "64 KiB cap reached");
    } else if (fwrite(line, 1, length, *logf) != length || fflush(*logf) != 0) {
        disable_log(logf, "write/flush failure");
    }
}

/* SIMULATION clock only: the parser currently supplies time-of-day, not a
 * verified date. Reject missing, repeated, or backwards times; no invented
 * nudges. Infer rollover ONLY from the last minute to the first minute of a
 * day. Even that inference cannot establish real-world chronology. */
typedef struct {
    double last_tod;
    double day_base;
} replay_clock_t;

static int replay_now(replay_clock_t *clock, double tod, double *now) {
    if (!isfinite(tod) || tod < 0.0 || tod >= 86400.0) return 0;
    if (clock->last_tod >= 0.0 && tod <= clock->last_tod) {
        if (clock->last_tod < 86340.0 || tod >= 60.0) return 0;
        clock->day_base += 86400.0;
    }
    clock->last_tod = tod;
    *now = clock->day_base + tod;
    return 1;
}

int main(int argc, char **argv) {
    const char *replaypath = NULL, *dbpath = NULL, *logpath = NULL;
    int i, n_signs = 0, result = 0;
    warner_sign_t *signs = NULL;
    warner_t w;
    double *state = NULL;
    warner_alert_t alerts[16];
    FILE *input = NULL, *logf = NULL;
    char line[512], event[256];
    size_t llen = 0;
    int discard = 0, c;
    replay_clock_t clock = { -1.0, 0.0 };
    unsigned long accepted = 0, rejected_time = 0;

    for (i = 1; i < argc; i++) {
        const char **option = NULL;
        if (!strcmp(argv[i], "--replay")) option = &replaypath;
        else if (!strcmp(argv[i], "-s")) option = &dbpath;
        else if (!strcmp(argv[i], "-l")) option = &logpath;
        if (!option || *option || i + 1 >= argc || !*argv[i + 1] || argv[i + 1][0] == '-') {
            fprintf(stderr, "c2m-warner: unknown, duplicate, or incomplete argument: %s\n", argv[i]);
            usage(stderr);
            return 2;
        }
        *option = argv[++i];
    }
    if (!replaypath || !dbpath || forbidden_path(dbpath)) { usage(stderr); return 2; }

    fprintf(stderr, "c2m-warner: HOST/REPLAY SIMULATION; live-device capability BLOCKED\n");
    input = open_regular(replaypath, 0);
    if (!input) {
        fprintf(stderr, "c2m-warner: replay must be a readable regular, non-symlink file: %s\n", strerror(errno));
        return 1;
    }
    /* Preflight the database too, so a FIFO/device cannot block the loader.
     * Database format and content validation remain signdb_load's contract. */
    {
        FILE *dbcheck = open_regular(dbpath, 0);
        if (!dbcheck) {
            fprintf(stderr, "c2m-warner: database must be a readable regular, non-symlink file\n");
            result = 1;
            goto cleanup;
        }
        fclose(dbcheck);
    }
    signs = signdb_load(dbpath, &n_signs);
    if (!signs || n_signs <= 0) {
        fprintf(stderr, "c2m-warner: cannot load sign database\n");
        result = 1;
        goto cleanup;
    }
    if ((size_t)n_signs > SIZE_MAX / sizeof(*state) ||
        !(state = (double *)calloc((size_t)n_signs, sizeof(*state)))) {
        fprintf(stderr, "c2m-warner: cannot allocate per-sign state\n");
        result = 1;
        goto cleanup;
    }
    warner_init(&w, signs, n_signs);
    warner_set_state(&w, state);

    if (logpath) {
        logf = open_regular(logpath, 1);
        if (!logf) fprintf(stderr, "c2m-warner: optional log unavailable: %s\n", strerror(errno));
        else {
            /* Never append into the replay or database through a path alias. */
            FILE *dbcheck = open_regular(dbpath, 0);
            if (same_file(input, logf) != 0 || !dbcheck || same_file(dbcheck, logf) != 0)
                disable_log(&logf, "log aliases input/database, or identity check failed");
            if (dbcheck) fclose(dbcheck);
            /* No buffered retry on fclose after a failed fwrite/fflush. */
            if (logf && setvbuf(logf, NULL, _IONBF, 0) != 0) disable_log(&logf, "cannot disable buffering");
            snprintf(event, sizeof(event), "SIMULATION start: %d signs; no live I/O\n", n_signs);
            log_line(&logf, event);
        }
    }

    for (;;) {
        c = fgetc(input);
        if (c == EOF && ferror(input)) {
            fprintf(stderr, "c2m-warner: replay read failure\n");
            result = 1;
            break;
        }
        if (c == EOF || c == '\n' || c == '\r') {
            if (!discard && llen > 0) {
                nmea_fix_t fix;
                line[llen] = '\0';
                if (nmea_parse_rmc(line, &fix) && fix.valid) {
                    double now;
                    if (!replay_now(&clock, fix.tod_s, &now)) rejected_time++;
                    else {
                        int k, na;
                        accepted++;
                        na = warner_update(&w, fix.lat, fix.lon, fix.course_deg,
                                           fix.speed_kmh, now, alerts, 16);
                        for (k = 0; k < na; k++) {
                            const warner_sign_t *s = &signs[alerts[k].sign_index];
                            /* Privacy: no GPS coordinates, input paths, or
                             * potentially location-bearing DB labels in log. */
                            snprintf(event, sizeof(event),
                                     "SIMULATION ALERT sign=%d t=%.1f dist=%.0fm eta=%.0fs\n",
                                     alerts[k].sign_index, now, alerts[k].distance_m, alerts[k].eta_s);
                            log_line(&logf, event);
                            if (printf("SIMULATION ALERT %.*s (%.*s) %.0fm\n",
                                       WARNER_LABEL_LEN - 1, s->label, WARNER_TYPE_LEN - 1,
                                       s->type, alerts[k].distance_m) < 0 || fflush(stdout) != 0) {
                                fprintf(stderr, "c2m-warner: stdout write failure\n");
                                result = 1;
                                goto cleanup;
                            }
                        }
                    }
                }
            }
            llen = 0;
            discard = 0;
            if (c == EOF) break;
        } else if (!discard) {
            if (c < 32 || c > 126 || llen >= sizeof(line) - 1) {
                discard = 1; /* Skip the WHOLE invalid line, never parse its tail. */
                llen = 0;
            } else line[llen++] = (char)c;
        }
    }
    snprintf(event, sizeof(event), "SIMULATION end: accepted=%lu rejected_time=%lu\n", accepted, rejected_time);
    log_line(&logf, event);
    fprintf(stderr, "c2m-warner: replay finished; accepted=%lu rejected_time=%lu\n", accepted, rejected_time);

cleanup:
    if (logf && fclose(logf) != 0) fprintf(stderr, "c2m-warner: optional log close failure\n");
    if (input && fclose(input) != 0) result = 1;
    free(state);
    signdb_free(signs);
    return result;
}
