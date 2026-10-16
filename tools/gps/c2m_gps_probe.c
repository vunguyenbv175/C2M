/* tools/gps/c2m_gps_probe.c - RAM-only read-only GPS decode status sampler.
 *
 * Fixed /tmp/car_info only (C2M_GPS_DEFAULT_PATH). No path overrides, no
 * status-file writes, no UART, no network, no shell. Reuses the production
 * decoder and freshness gate (fw/d3/gps_snapshot.c + gps_snapshot.h).
 *
 * Observer role: diagnose whether the installed D4 producer sees advancing
 * GPS without killing or restarting it. This tool only performs the same
 * regular-file read the producer does; it never opens UART or vendor IPC.
 *
 * Privacy: structural decode status only. Coordinates, speed, course,
 * subsecond fraction and UTC values are NEVER printed. Per-sample output is
 * exactly `sample=N result=<name> fresh=<0/1>` plus fixed header/summary.
 *
 * Bounds (fixed, no overrides):
 *   samples 10, interval 500 ms, freshness is the production
 *   c2m_gps_freshness_update gate (2.5 s stale window, 3 s delta tolerance,
 *   two strictly advancing UTC seconds required).
 *
 * CLI (explicit, fixed):
 *   --observe    10 read-only samples at 500 ms from the fixed path
 *   --self-test  pure synthetic fixtures only (no files, clock, env)
 *   --help       usage
 * Any other arity or flag exits 2. No user file overrides exist.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "gps_snapshot.h"

#ifdef __linux__
#include <errno.h>
#include <time.h>
#endif

#define C2M_GPS_PROBE_VERSION "c2m-gps-probe-v1"
#define C2M_GPS_PROBE_SAMPLES 10
#define C2M_GPS_PROBE_INTERVAL_MS 500

static const char *c2m_probe_result_name(int result)
{
    switch (result) {
    case C2M_GPS_OK:
        return "ok";
    case C2M_GPS_INVALID:
        return "invalid";
    case C2M_GPS_IO_ERROR:
        return "io_error";
    case C2M_GPS_UNSTABLE:
        return "unstable";
    case C2M_GPS_UNSUPPORTED:
        return "unsupported";
    default:
        return "unknown";
    }
}

static void c2m_probe_usage(FILE *out)
{
    fputs("Usage: c2m-gps-probe --help | --self-test | --observe\n"
          "RAM-only read-only GPS decode status sampler.\n"
          "Fixed path: /tmp/car_info (C2M_GPS_DEFAULT_PATH, no overrides).\n"
          "Fixed bounds: 10 samples at 500 ms; production freshness gate.\n"
          "No coordinates, speed, course, UTC, status writes, UART or network.\n",
          out);
}

static void c2m_probe_put_u32(uint8_t *dst, uint32_t value)
{
    dst[0] = (uint8_t)value;
    dst[1] = (uint8_t)(value >> 8);
    dst[2] = (uint8_t)(value >> 16);
    dst[3] = (uint8_t)(value >> 24);
}

static void c2m_probe_put_double(uint8_t *dst, double value)
{
    uint64_t bits = 0;
    if (sizeof(value) == sizeof(bits))
        memcpy(&bits, &value, sizeof(bits));
    c2m_probe_put_u32(dst, (uint32_t)bits);
    c2m_probe_put_u32(dst + 4, (uint32_t)(bits >> 32));
}

/* Build one synthetic nmeaINFO record. Second varies; all else fixed valid. */
static void c2m_probe_make_record(uint8_t *dst, uint32_t second)
{
    memset(dst, 0, C2M_GPS_RECORD_BYTES);
    c2m_probe_put_u32(dst + 0x00, C2M_GPS_RMC_MASK);
    c2m_probe_put_u32(dst + 0x04, 124);
    c2m_probe_put_u32(dst + 0x08, 1);
    c2m_probe_put_u32(dst + 0x0c, 29);
    c2m_probe_put_u32(dst + 0x18, second);
    c2m_probe_put_u32(dst + 0x20, 1);
    c2m_probe_put_u32(dst + 0x24, 2);
    c2m_probe_put_double(dst + 0x40, -1230.0);
    c2m_probe_put_double(dst + 0x48, 4530.0);
    c2m_probe_put_double(dst + 0x58, 5.0);
    c2m_probe_put_double(dst + 0x60, 359.5);
}

static int c2m_probe_check(const char *name, int actual, int expected)
{
    if (actual != expected) {
        printf("FAIL %s: %d != %d\n", name, actual, expected);
        return 1;
    }
    printf("PASS %s\n", name);
    return 0;
}

/* Pure self-test: synthetic bytes + freshness state only. No files, no
 * clock, no environment, no coordinates printed. */
static int c2m_probe_self_test(void)
{
    uint8_t first[C2M_GPS_RECORD_BYTES];
    uint8_t second[C2M_GPS_RECORD_BYTES];
    uint8_t bad[C2M_GPS_RECORD_BYTES];
    struct c2m_gps_snapshot one;
    struct c2m_gps_snapshot two;
    struct c2m_gps_snapshot tmp;
    struct c2m_gps_freshness state;
    int failures = 0;

    printf("gps_probe=%s\n", C2M_GPS_PROBE_VERSION);
    printf("path_fixed=%s\n", C2M_GPS_DEFAULT_PATH);
    printf("samples_fixed=%d\n", C2M_GPS_PROBE_SAMPLES);
    printf("interval_ms_fixed=%d\n", C2M_GPS_PROBE_INTERVAL_MS);

    failures += c2m_probe_check("bounds_samples_fixed",
        C2M_GPS_PROBE_SAMPLES, 10);
    failures += c2m_probe_check("bounds_interval_fixed",
        C2M_GPS_PROBE_INTERVAL_MS, 500);

    c2m_probe_make_record(first, 0);
    c2m_probe_make_record(second, 1);
    /* Exercise the actual corrected vendor fraction range, not just zero. */
    c2m_probe_put_u32(first + 0x1c, 100);
    c2m_probe_put_u32(second + 0x1c, 200);
    memset(bad, 0, sizeof(bad));

    failures += c2m_probe_check("decode_valid_ok",
        c2m_gps_decode(first, sizeof(first), &one), C2M_GPS_OK);
    failures += c2m_probe_check("decode_second_ok",
        c2m_gps_decode(second, sizeof(second), &two), C2M_GPS_OK);
    failures += c2m_probe_check("decode_zero_rejected",
        c2m_gps_decode(bad, sizeof(bad), &tmp), C2M_GPS_INVALID);
    failures += c2m_probe_check("decode_short_rejected",
        c2m_gps_decode(first, sizeof(first) - 1, &tmp), C2M_GPS_INVALID);
    memcpy(bad, first, sizeof(bad));
    c2m_probe_put_u32(bad + 0x1c, 999);
    failures += c2m_probe_check("decode_raw999_accepted",
        c2m_gps_decode(bad, sizeof(bad), &tmp), C2M_GPS_OK);
    c2m_probe_put_u32(bad + 0x1c, 1000);
    failures += c2m_probe_check("decode_raw1000_rejected",
        c2m_gps_decode(bad, sizeof(bad), &tmp), C2M_GPS_INVALID);
    failures += c2m_probe_check("result_names_stable",
        (int)(strcmp(c2m_probe_result_name(C2M_GPS_OK), "ok") == 0 &&
              strcmp(c2m_probe_result_name(C2M_GPS_INVALID), "invalid") == 0 &&
              strcmp(c2m_probe_result_name(C2M_GPS_IO_ERROR), "io_error") == 0 &&
              strcmp(c2m_probe_result_name(C2M_GPS_UNSTABLE), "unstable") == 0), 1);

    /* Production gate: two advancing seconds confirm; staleness clears. */
    c2m_gps_freshness_init(&state);
    failures += c2m_probe_check("fresh_first_unconfirmed",
        c2m_gps_freshness_update(&state, &one, 1000), 0);
    failures += c2m_probe_check("fresh_advance_confirmed",
        c2m_gps_freshness_update(&state, &two, 2000), 1);
    failures += c2m_probe_check("fresh_repeat_holds",
        c2m_gps_freshness_update(&state, &two, 4499), 1);
    failures += c2m_probe_check("fresh_stale_gate",
        c2m_gps_freshness_update(&state, &two, 4500), 0);
    failures += c2m_probe_check("fresh_failure_resets",
        c2m_gps_freshness_update(&state, NULL, 4600), 0);

    /* Reacquire after reset requires two fresh advances again. */
    c2m_probe_make_record(first, 2);
    c2m_probe_make_record(second, 3);
    failures += c2m_probe_check("fresh_reacquire_first",
        c2m_gps_decode(first, sizeof(first), &one) == C2M_GPS_OK ?
        c2m_gps_freshness_update(&state, &one, 5000) : 99, 0);
    failures += c2m_probe_check("fresh_reacquire_second",
        c2m_gps_decode(second, sizeof(second), &two) == C2M_GPS_OK ?
        c2m_gps_freshness_update(&state, &two, 6000) : 99, 1);

    printf("self_test=%s\n", failures ? "failed" : "passed");
    return failures ? 1 : 0;
}

#ifdef __linux__
static int c2m_probe_now_ms(uint64_t *out)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
        return -1;
    if (now.tv_sec < 0)
        return -1;
    if ((uint64_t)now.tv_sec > UINT64_MAX / UINT64_C(1000))
        return -1;
    *out = (uint64_t)now.tv_sec * UINT64_C(1000) +
           (uint64_t)now.tv_nsec / UINT64_C(1000000);
    return 0;
}

static void c2m_probe_sleep_ms(void)
{
    struct timespec delay;
    delay.tv_sec = 0;
    delay.tv_nsec = (long)C2M_GPS_PROBE_INTERVAL_MS * 1000000L;
    while (nanosleep(&delay, &delay) != 0 && errno == EINTR) {
    }
}

/* Fixed bounded observer: 10 read-only samples at 500 ms. No writes. */
static int c2m_probe_run(void)
{
    struct c2m_gps_freshness state;
    int index;
    int final_fresh = 0;

    printf("gps_probe=%s\n", C2M_GPS_PROBE_VERSION);
    printf("path_fixed=%s\n", C2M_GPS_DEFAULT_PATH);
    printf("samples_fixed=%d interval_ms_fixed=%d\n",
        C2M_GPS_PROBE_SAMPLES, C2M_GPS_PROBE_INTERVAL_MS);
    c2m_gps_freshness_init(&state);
    for (index = 0; index < C2M_GPS_PROBE_SAMPLES; ++index) {
        struct c2m_gps_snapshot sample;
        const struct c2m_gps_snapshot *fed = NULL;
        uint64_t now = 0;
        int result;
        int fresh;
        memset(&sample, 0, sizeof(sample));
        result = c2m_gps_read(C2M_GPS_DEFAULT_PATH, &sample);
        if (result == C2M_GPS_OK)
            fed = &sample;
        if (c2m_probe_now_ms(&now) != 0)
            return 1;
        fresh = c2m_gps_freshness_update(&state, fed, now);
        final_fresh = fresh;
        printf("sample=%d result=%s fresh=%d\n",
            index + 1, c2m_probe_result_name(result), fresh ? 1 : 0);
        if (index + 1 < C2M_GPS_PROBE_SAMPLES)
            c2m_probe_sleep_ms();
    }
    printf("summary samples=%d fresh_final=%d\n",
        C2M_GPS_PROBE_SAMPLES, final_fresh ? 1 : 0);
    return 0;
}
#endif

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        c2m_probe_usage(stdout);
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--self-test") == 0)
        return c2m_probe_self_test();
    if (argc == 2 && strcmp(argv[1], "--observe") == 0) {
#ifdef __linux__
        return c2m_probe_run();
#else
        fputs("observe unsupported on this platform\n", stderr);
        return 3;
#endif
    }
    c2m_probe_usage(stderr);
    return 2;
}
