#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include "advisory.h"
#include "db.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __linux__
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define DB_MAX_BYTES 4000012L
#define PATH_BYTES 4096
#define NAME_BYTES 256
static volatile sig_atomic_t stopping;
struct checked_path {
    int dir;
    char leaf[NAME_BYTES];
};
struct database {
    struct checked_path path;
    FILE *stream;
    struct stat identity;
    warner_sign_t *signs;
    int count, valid;
};

static void on_signal(int sig) { (void)sig; stopping = 1; }

static int milliseconds(uint64_t *out)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0 ||
        (uint64_t)t.tv_sec > UINT64_MAX / UINT64_C(1000)) return -1;
    *out = (uint64_t)t.tv_sec * UINT64_C(1000) + (uint64_t)t.tv_nsec / UINT64_C(1000000);
    return 0;
}

static int directory_ok(const struct stat *s, const char *prefix, int fixture)
{
    mode_t mode = s->st_mode & 07777;
    if (!S_ISDIR(s->st_mode)) return 0;
    /* The only writable shared ancestry exception is sticky, root /tmp.
     * Its children still need no-follow/type/owner checks. */
    if (!strcmp(prefix, "/tmp")) return s->st_uid == 0 && mode == 01777;
    if (s->st_uid == 0 && !(mode & 0022)) return 1;
    if (s->st_uid == 1001 && mode == 0755 &&
        (!strcmp(prefix, "/customer") || !strcmp(prefix, "/customer/c2m"))) return 1;
    return fixture && s->st_uid == geteuid() && !(mode & 0022);
}


/* Walk every directory component using descriptor-relative, no-follow opens.
 * All returned descriptors are pinned; no shell, realpath, or symlink escape.
 * Host fixture paths allow the invoking UID, never writable ancestry. */
static int checked_parent(const char *path, int fixture, struct checked_path *out)
{
    char copy[PATH_BYTES], prefix[PATH_BYTES];
    char *part, *slash;
    size_t len, used = 0;
    struct stat st;
    int dir = -1, next;
    out->dir = -1;
    out->leaf[0] = 0;
    if (!path || path[0] != '/' || (len = strlen(path)) >= sizeof(copy) || len < 2) return -1;
    memcpy(copy, path + 1, len);
    prefix[0] = 0;
    dir = open("/", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (dir < 0 || fstat(dir, &st) || !directory_ok(&st, "/", fixture)) goto fail;
    part = copy;
    for (;;) {
        size_t n;
        slash = strchr(part, '/');
        if (slash) *slash = 0;
        n = strlen(part);
        if (!n || n >= NAME_BYTES || !strcmp(part, ".") || !strcmp(part, "..")) goto fail;
        if (!slash) {
            memcpy(out->leaf, part, n + 1);
            out->dir = dir;
            return 0;
        }
        if (used + n + 1 >= sizeof(prefix)) goto fail;
        prefix[used++] = '/';
        memcpy(prefix + used, part, n + 1);
        used += n;
        next = openat(dir, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
        if (next < 0) goto fail;
        close(dir);
        dir = next;
        if (fstat(dir, &st) || !directory_ok(&st, prefix, fixture)) goto fail;
        part = slash + 1;
    }
fail:
    if (dir >= 0) close(dir);
    return -1;
}

static int data_owner_ok(const struct stat *st, int fixture)
{
    return (st->st_uid == 0 || st->st_uid == 1001 ||
            (fixture && st->st_uid == geteuid())) && !(st->st_mode & 0022);
}

static int db_stat_ok(const struct stat *s, int fixture)
{
    return S_ISREG(s->st_mode) && s->st_nlink == 1 && data_owner_ok(s, fixture) &&
           s->st_size >= 112 && s->st_size <= (off_t)DB_MAX_BYTES;
}

static int same_file(const struct stat *a, const struct stat *b)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
           a->st_uid == b->st_uid && a->st_gid == b->st_gid &&
           a->st_mode == b->st_mode && a->st_nlink == b->st_nlink &&
           a->st_size == b->st_size &&
           a->st_mtim.tv_sec == b->st_mtim.tv_sec && a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
           a->st_ctim.tv_sec == b->st_ctim.tv_sec && a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}

static void database_open(struct database *db, const char *path, int fixture)
{
    struct stat after, named;
    int fd;
    memset(db, 0, sizeof(*db));
    db->path.dir = -1;
    if (checked_parent(path, fixture, &db->path)) return;
    fd = openat(db->path.dir, db->path.leaf, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) return;
    if (fstat(fd, &db->identity) || !db_stat_ok(&db->identity, fixture)) {
        close(fd); return;
    }
    db->stream = fdopen(fd, "rb");
    if (!db->stream) { close(fd); return; }
    db->signs = signdb_load_stream(db->stream, &db->count);
    if (!db->signs || fstat(fd, &after) || !same_file(&db->identity, &after) ||
        fstatat(db->path.dir, db->path.leaf, &named, AT_SYMLINK_NOFOLLOW) ||
        !same_file(&db->identity, &named)) return;
    db->valid = 1;
}

static int database_unchanged(struct database *db, const char *path, int fixture)
{
    struct stat now, named, parent, original;
    struct checked_path current;
    if (!db->valid) return 0;
    /* Metadata only: never reload/reopen/read the DB. Replacement or in-place
     * mutation invalidates this process permanently (restart to load again). */
    if (checked_parent(path, fixture, &current)) { db->valid = 0; return 0; }
    if (fstat(current.dir, &parent) || fstat(db->path.dir, &original) ||
        parent.st_dev != original.st_dev || parent.st_ino != original.st_ino ||
        fstat(fileno(db->stream), &now) || !same_file(&db->identity, &now) ||
        fstatat(current.dir, current.leaf, &named, AT_SYMLINK_NOFOLLOW) ||
        !db_stat_ok(&named, fixture) || !same_file(&db->identity, &named)) db->valid = 0;
    close(current.dir);
    return db->valid;
}

static void database_close(struct database *db)
{
    if (db->stream) fclose(db->stream);
    if (db->path.dir >= 0) close(db->path.dir);
    signdb_free(db->signs);
}

static int target_ok(const struct checked_path *p)
{
    struct stat st;
    if (fstatat(p->dir, p->leaf, &st, AT_SYMLINK_NOFOLLOW)) return errno == ENOENT;
    /* Private tmp status belongs to this producer UID, not package/user data.
     * Refuse to replace any link or unexpected object, even by rename. */
    return S_ISREG(st.st_mode) && st.st_nlink == 1 && st.st_uid == geteuid() &&
           (st.st_mode & 07777) == 0600 && st.st_size >= 0 && st.st_size <= C2M_D4_STATUS_BYTES;
}

static int write_status(const char *path, int fixture, const struct c2m_d4_status *status)
{
    struct checked_path p;
    char text[C2M_D4_STATUS_BYTES], temporary[NAME_BYTES];
    struct stat st, named;
    int len, fd = -1, result = -1;
    unsigned attempt;
    len = c2m_d4_format_status(status, text, sizeof(text));
    if (len < 0 || checked_parent(path, fixture, &p)) return -1;
    if (!target_ok(&p)) goto done;
    for (attempt = 0; attempt < 8; ++attempt) {
        int n = snprintf(temporary, sizeof(temporary), ".c2m-d4-%ld-%" PRIu32 "-%u.tmp",
                         (long)getpid(), status->sequence, attempt);
        if (n < 0 || (size_t)n >= sizeof(temporary)) goto done;
        fd = openat(p.dir, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW |
                    O_NONBLOCK | O_CLOEXEC, 0600);
        if (fd >= 0) break;
        if (errno != EEXIST) goto done;
    }
    if (fd < 0) goto done;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_nlink != 1 ||
        st.st_uid != geteuid() || (st.st_mode & 07777) != 0600) goto cleanup;
    {
        size_t pos = 0;
        while (pos < (size_t)len) {
            ssize_t n = write(fd, text + pos, (size_t)len - pos);
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0) goto cleanup;
            pos += (size_t)n;
        }
    }
    if (fstat(fd, &st) || st.st_size != (off_t)len || st.st_nlink != 1 ||
        fstatat(p.dir, temporary, &named, AT_SYMLINK_NOFOLLOW) ||
        st.st_dev != named.st_dev || st.st_ino != named.st_ino ||
        !target_ok(&p)) goto cleanup;
    /* tmpfs heartbeat: no per-fix media log, fsync, or persistence needed. */
    if (close(fd)) { fd = -1; goto cleanup; }
    fd = -1;
    if (renameat(p.dir, temporary, p.dir, p.leaf)) goto cleanup;
    result = 0;
    goto done;
cleanup:
    if (fd >= 0) close(fd);
    /* Directory is checked/pinned; remove only the temporary we created. */
    unlinkat(p.dir, temporary, 0);
done:
    close(p.dir);
    return result;
}

static int gps_parent_ok(const char *path, int fixture)
{
    struct checked_path p;
    if (checked_parent(path, fixture, &p)) return 0;
    close(p.dir);
    return 1;
}

static int serve(const char *db_path, const char *gps_path, const char *status_path,
                 int fixture)
{
    struct database db;
    struct c2m_d4_advisory core;
    struct c2m_d4_cooldown *cooldowns = NULL;
    struct c2m_d4_status status;
    struct c2m_gps_snapshot gps;
    struct sigaction action;
    uint64_t now = 0;
    int gps_result, ok, rc = 0;
    struct timespec delay;
    /* Boot launcher provides low priority; do not control other processes. */
    memset(&action, 0, sizeof(action));
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) return 1;
    database_open(&db, db_path, fixture);
    if (db.valid) {
        cooldowns = (struct c2m_d4_cooldown *)calloc((size_t)db.count, sizeof(*cooldowns));
        if (!cooldowns) db.valid = 0;
    }
    c2m_d4_init(&core, db.signs, db.count, cooldowns);
    while (!stopping) {
        if (milliseconds(&now)) { rc = 1; break; }
        ok = database_unchanged(&db, db_path, fixture);
        gps_result = C2M_GPS_IO_ERROR;
        if (gps_parent_ok(gps_path, fixture)) gps_result = c2m_gps_read(gps_path, &gps);
        c2m_d4_prepare(&core, gps_result == C2M_GPS_OK ? &gps : NULL, now, ok, 0, &status);
        c2m_d4_published(&core, write_status(status_path, fixture, &status) == 0);
        /* One bounded read/selection and atomic /tmp heartbeat per second.
         * Relative sleeping deliberately avoids catch-up bursts. */
        delay.tv_sec = 1; delay.tv_nsec = 0;
        while (!stopping && nanosleep(&delay, &delay) && errno == EINTR) { }
    }
    /* Signals clear the currently displayed event, with no new cooldown. */
    if (!milliseconds(&now)) {
        c2m_d4_prepare(&core, NULL, now, db.valid, 1, &status);
        if (write_status(status_path, fixture, &status)) rc = 1;
        else c2m_d4_published(&core, 1);
    }
    free(cooldowns);
    database_close(&db);
    return rc;
}
#endif

static void usage(void)
{
    puts("usage: c2m-d4 --self-test | --help | --serve [--db ABS --gps-file ABS --status-file ABS]\n"
         "Experimental offline GPS NEARBY-area advisory only; no legal speed or audio.\n"
         "Default: fixed package DB, read-only /tmp/car_info, private /tmp status.\n"
         "Absolute path overrides are solely for host synthetic fixtures.");
}

int main(int argc, char **argv)
{
    const char *db = C2M_D4_DEFAULT_DB, *gps = C2M_GPS_DEFAULT_PATH;
    const char *status = C2M_D4_DEFAULT_STATUS;
    unsigned overrides = 0;
    int i, result;
    if (argc == 2 && !strcmp(argv[1], "--help")) { usage(); return 0; }
    if (argc == 2 && !strcmp(argv[1], "--self-test")) {
        result = c2m_d4_self_test();
        puts(result ? "D4 synthetic advisory self-test: FAIL" : "D4 synthetic advisory self-test: OK");
        return result ? 1 : 0;
    }
    if (argc < 2 || strcmp(argv[1], "--serve")) { usage(); return 2; }
    for (i = 2; i < argc; i += 2) {
        unsigned bit;
        const char **destination;
        if (!strcmp(argv[i], "--db")) { bit = 1; destination = &db; }
        else if (!strcmp(argv[i], "--gps-file")) { bit = 2; destination = &gps; }
        else if (!strcmp(argv[i], "--status-file")) { bit = 4; destination = &status; }
        else return 2;
        if (i + 1 >= argc || argv[i + 1][0] != '/' || (overrides & bit)) return 2;
        overrides |= bit;
        *destination = argv[i + 1];
    }
    /* Never combine host fixtures with any camera default path. */
    if (overrides && overrides != 7) return 2;
#ifdef __linux__
    return serve(db, gps, status, overrides != 0);
#else
    (void)db; (void)gps; (void)status;
    fputs("D4 serve unsupported on this platform\n", stderr);
    return 3;
#endif
}
