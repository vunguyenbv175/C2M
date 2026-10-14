#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif

#include "gps_snapshot.h"

#include <float.h>
#include <limits.h>
#include <math.h>
#include <string.h>

#ifdef __linux__
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

/* Never overlay a native C structure on the vendor bytes: padding,
 * alignment, byte order and time_t width would change the wire contract.
 */
static uint32_t read_u32_le(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static double read_double_le(const uint8_t *p)
{
    uint64_t bits = (uint64_t)read_u32_le(p) |
                    ((uint64_t)read_u32_le(p + 4) << 32);
    double value = 0.0;
    /* Decode is disabled below on non-IEEE-binary64 hosts. */
    if (sizeof(value) == sizeof(bits))
        memcpy(&value, &bits, sizeof(bits));
    return value;
}

static int fail_decode(struct c2m_gps_snapshot *out, int result)
{
    if (out != NULL)
        memset(out, 0, sizeof(*out));
    return result;
}

static int leap_year(unsigned year)
{
    return year % 4u == 0u && (year % 100u != 0u || year % 400u == 0u);
}

static int decode_utc(const uint8_t *p, int64_t *seconds)
{
    static const unsigned month_days[12] = {
        31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31
    };
    unsigned year = read_u32_le(p + 0x04);
    unsigned month = read_u32_le(p + 0x08);
    unsigned day = read_u32_le(p + 0x0c);
    unsigned hour = read_u32_le(p + 0x10);
    unsigned minute = read_u32_le(p + 0x14);
    unsigned second = read_u32_le(p + 0x18);
    unsigned days_in_month, y, m;
    int64_t days = 0;

    /* nmeaTIME stores year since 1900 and zero-based month. The RMC
     * parser adds 100 for yy<=89; do NOT interpret this as full-year UTC.
     */
    if (year < 100u || year > 199u || month > 11u ||
        hour > 23u || minute > 59u || second > 59u ||
        read_u32_le(p + 0x1c) > 99u)
        return 0;
    year += 1900u;
    days_in_month = month_days[month];
    if (month == 1u && leap_year(year))
        ++days_in_month;
    if (day == 0u || day > days_in_month)
        return 0;

    for (y = 1970u; y < year; ++y)
        days += leap_year(y) ? 366 : 365;
    for (m = 0; m < month; ++m) {
        days += month_days[m];
        if (m == 1u && leap_year(year))
            ++days;
    }
    days += day - 1u;
    *seconds = days * INT64_C(86400) + hour * INT64_C(3600) +
               minute * INT64_C(60) + second;
    return 1;
}

static int decode_ddmm(double raw, unsigned bound, double *degrees_out)
{
    double magnitude, minutes, degrees;
    unsigned whole_degrees;

    if (!isfinite(raw))
        return 0;
    magnitude = fabs(raw);
    if (magnitude > (double)bound * 100.0)
        return 0;
    /* The bounded conversion to unsigned truncates only the degree part.
     * cardv's conversion applies hemisphere sign but leaves NMEA DDMM.
     */
    whole_degrees = (unsigned)(magnitude / 100.0);
    minutes = magnitude - (double)whole_degrees * 100.0;
    if (minutes < 0.0 || minutes >= 60.0 || whole_degrees > bound ||
        (whole_degrees == bound && minutes != 0.0))
        return 0;
    degrees = (double)whole_degrees + minutes / 60.0;
    *degrees_out = signbit(raw) ? -degrees : degrees;
    return 1;
}

int c2m_gps_decode(const uint8_t *bytes, size_t size,
                   struct c2m_gps_snapshot *out)
{
    struct c2m_gps_snapshot value;
    uint32_t signal, fix;

    if (out == NULL)
        return C2M_GPS_INVALID;
    if (bytes == NULL || size != C2M_GPS_RECORD_BYTES || CHAR_BIT != 8 ||
        sizeof(double) != 8 || DBL_MANT_DIG != 53 || DBL_MAX_EXP != 1024)
        return fail_decode(out, C2M_GPS_INVALID);
    memset(&value, 0, sizeof(value));
    value.mask = read_u32_le(bytes);
    signal = read_u32_le(bytes + 0x20);
    fix = read_u32_le(bytes + 0x24);
    /* Both vendor fields are signed int32. Reject the negative bit pattern
     * without an implementation-defined unsigned-to-signed conversion.
     */
    if (!(value.mask & C2M_GPS_RMC_MASK) || signal == 0 ||
        signal > INT32_MAX || fix < 2u || fix > INT32_MAX ||
        !decode_utc(bytes, &value.utc_seconds))
        return fail_decode(out, C2M_GPS_INVALID);
    value.hundredths = read_u32_le(bytes + 0x1c);
    if (!decode_ddmm(read_double_le(bytes + 0x40), 90u,
                     &value.latitude_deg) ||
        !decode_ddmm(read_double_le(bytes + 0x48), 180u,
                     &value.longitude_deg))
        return fail_decode(out, C2M_GPS_INVALID);
    value.speed_kmh = read_double_le(bytes + 0x58);
    value.course_deg = read_double_le(bytes + 0x60);
    if (!isfinite(value.speed_kmh) || value.speed_kmh < 0.0 ||
        value.speed_kmh > C2M_GPS_MAX_SPEED_KMH ||
        !isfinite(value.course_deg) || value.course_deg < 0.0 ||
        value.course_deg >= 360.0)
        return fail_decode(out, C2M_GPS_INVALID);
    value.heading_usable = value.speed_kmh >= C2M_GPS_MIN_HEADING_KMH;
    *out = value;
    return C2M_GPS_OK;
}

int c2m_gps_read(const char *path, struct c2m_gps_snapshot *out)
{
#ifdef __linux__
    uint8_t first[C2M_GPS_RECORD_BYTES], second[C2M_GPS_RECORD_BYTES];
    struct stat before, after;
    ssize_t count;
    int fd, result = C2M_GPS_IO_ERROR;

    if (out == NULL)
        return C2M_GPS_INVALID;
    memset(out, 0, sizeof(*out));
    if (path == NULL || path[0] == '\0')
        return C2M_GPS_INVALID;
    /* O_NONBLOCK ensures FIFO/device paths cannot stall before fstat.
     * O_NOFOLLOW rejects the final symlink; directory ancestry must be
     * trusted by the caller (as with the vendor /tmp/car_info path).
     */
    fd = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0)
        return C2M_GPS_IO_ERROR;
    if (fstat(fd, &before) != 0)
        goto done;
    if (!S_ISREG(before.st_mode) ||
        before.st_size < (off_t)C2M_GPS_MIN_FILE_BYTES ||
        before.st_size > (off_t)C2M_GPS_MAX_FILE_BYTES) {
        result = C2M_GPS_INVALID;
        goto done;
    }
    do {
        count = pread(fd, first, sizeof(first), (off_t)C2M_GPS_FILE_OFFSET);
    } while (count < 0 && errno == EINTR);
    if (count < 0)
        goto done;
    if (count != (ssize_t)sizeof(first)) {
        result = C2M_GPS_INVALID;
        goto done;
    }
    do {
        count = pread(fd, second, sizeof(second), (off_t)C2M_GPS_FILE_OFFSET);
    } while (count < 0 && errno == EINTR);
    if (count < 0)
        goto done;
    if (count != (ssize_t)sizeof(second)) {
        result = C2M_GPS_INVALID;
        goto done;
    }
    if (memcmp(first, second, sizeof(first)) != 0) {
        result = C2M_GPS_UNSTABLE;
        goto done;
    }
    if (fstat(fd, &after) != 0)
        goto done;
    if (!S_ISREG(after.st_mode) || after.st_size != before.st_size ||
        after.st_size < (off_t)C2M_GPS_MIN_FILE_BYTES ||
        after.st_size > (off_t)C2M_GPS_MAX_FILE_BYTES) {
        result = C2M_GPS_UNSTABLE;
        goto done;
    }
    /* mtime is deliberately not inspected: it says nothing about whether
     * a GPS UTC second is advancing, and can change for unrelated fields.
     */
    result = c2m_gps_decode(first, sizeof(first), out);
done:
    /* Do not retry close on EINTR: the descriptor may already be closed. */
    if (close(fd) != 0 && result == C2M_GPS_OK)
        result = C2M_GPS_IO_ERROR;
    if (result != C2M_GPS_OK)
        memset(out, 0, sizeof(*out));
    return result;
#else
    (void)path;
    return fail_decode(out, out == NULL ? C2M_GPS_INVALID : C2M_GPS_UNSUPPORTED);
#endif
}

void c2m_gps_freshness_init(struct c2m_gps_freshness *state)
{
    if (state != NULL)
        memset(state, 0, sizeof(*state));
}

static void freshness_anchor(struct c2m_gps_freshness *state,
                             int64_t utc_seconds, uint64_t monotonic_ms)
{
    state->last_utc_seconds = utc_seconds;
    state->last_advance_ms = monotonic_ms;
    state->last_observation_ms = monotonic_ms;
    state->reference_utc_seconds = utc_seconds;
    state->reference_ms = monotonic_ms;
    state->have_anchor = 1;
    state->confirmed = 0;
}

static int sample_in_range(const struct c2m_gps_snapshot *sample)
{
    /* Defend the public state API against an uninitialized/manual sample.
     * Valid UTC window is 2000-01-01 through 2099-12-31 inclusive.
     */
    return sample != NULL && (sample->mask & C2M_GPS_RMC_MASK) &&
           sample->utc_seconds >= INT64_C(946684800) &&
           sample->utc_seconds <= INT64_C(4102444799) &&
           sample->hundredths <= 99u &&
           isfinite(sample->latitude_deg) &&
           fabs(sample->latitude_deg) <= 90.0 &&
           isfinite(sample->longitude_deg) &&
           fabs(sample->longitude_deg) <= 180.0 &&
           isfinite(sample->speed_kmh) && sample->speed_kmh >= 0.0 &&
           sample->speed_kmh <= C2M_GPS_MAX_SPEED_KMH &&
           isfinite(sample->course_deg) && sample->course_deg >= 0.0 &&
           sample->course_deg < 360.0;
}

int c2m_gps_freshness_update(struct c2m_gps_freshness *state,
                           const struct c2m_gps_snapshot *sample,
                           uint64_t monotonic_ms)
{
    uint64_t elapsed_ms, gps_ms, difference_ms, reference_elapsed_ms;

    if (state == NULL)
        return 0;
    if (!sample_in_range(sample)) {
        c2m_gps_freshness_init(state);
        return 0;
    }
    if (!state->have_anchor || monotonic_ms < state->last_observation_ms) {
        freshness_anchor(state, sample->utc_seconds, monotonic_ms);
        return 0;
    }
    state->last_observation_ms = monotonic_ms;
    elapsed_ms = monotonic_ms - state->last_advance_ms;
    if (elapsed_ms >= C2M_GPS_STALE_MS ||
        sample->utc_seconds < state->last_utc_seconds) {
        freshness_anchor(state, sample->utc_seconds, monotonic_ms);
        return 0;
    }
    if (sample->utc_seconds == state->last_utc_seconds)
        return state->confirmed;
    if (elapsed_ms == 0) {
        freshness_anchor(state, sample->utc_seconds, monotonic_ms);
        return 0;
    }
    /* Both UTC values are range-checked, so subtraction/multiplication
     * cannot overflow. GPS subseconds/coordinates do not renew freshness.
     */
    gps_ms = (uint64_t)(sample->utc_seconds - state->last_utc_seconds) *
             UINT64_C(1000);
    difference_ms = gps_ms > elapsed_ms ? gps_ms - elapsed_ms :
                                         elapsed_ms - gps_ms;
    if (difference_ms > C2M_GPS_DELTA_TOLERANCE_MS) {
        freshness_anchor(state, sample->utc_seconds, monotonic_ms);
        return 0;
    }
    /* Check the whole acquisition period too: a replay advancing one GPS
     * second every few milliseconds must not pass forever just because
     * each individual delta falls within the quantization tolerance.
     */
    reference_elapsed_ms = monotonic_ms - state->reference_ms;
    gps_ms = (uint64_t)(sample->utc_seconds - state->reference_utc_seconds) *
             UINT64_C(1000);
    difference_ms = gps_ms > reference_elapsed_ms ?
                    gps_ms - reference_elapsed_ms :
                    reference_elapsed_ms - gps_ms;
    if (difference_ms > C2M_GPS_DELTA_TOLERANCE_MS) {
        freshness_anchor(state, sample->utc_seconds, monotonic_ms);
        return 0;
    }
    state->last_utc_seconds = sample->utc_seconds;
    state->last_advance_ms = monotonic_ms;
    state->confirmed = 1;
    return 1;
}

#ifdef C2M_GPS_SELFTEST
#include <stdio.h>

static void test_put_u32(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

static void test_put_double(uint8_t *p, double value)
{
    uint64_t bits = 0;
    if (sizeof(value) == sizeof(bits))
        memcpy(&bits, &value, sizeof(bits));
    test_put_u32(p, (uint32_t)bits);
    test_put_u32(p + 4, (uint32_t)(bits >> 32));
}

static int gps_self_test(void)
{
    uint8_t bytes[C2M_GPS_RECORD_BYTES];
    struct c2m_gps_snapshot sample;
    struct c2m_gps_freshness state;
    memset(bytes, 0, sizeof(bytes));
    test_put_u32(bytes, C2M_GPS_RMC_MASK);
    test_put_u32(bytes + 0x04, 124); /* Synthetic 2024-02-29, UTC midnight. */
    test_put_u32(bytes + 0x08, 1);
    test_put_u32(bytes + 0x0c, 29);
    test_put_u32(bytes + 0x20, 1);
    test_put_u32(bytes + 0x24, 2);
    test_put_double(bytes + 0x40, -1230.0);
    test_put_double(bytes + 0x48, 4530.0);
    test_put_double(bytes + 0x58, 5.0);
    test_put_double(bytes + 0x60, 359.5);
    if (c2m_gps_decode(bytes, sizeof(bytes), &sample) != C2M_GPS_OK ||
        sample.utc_seconds != INT64_C(1709164800) ||
        sample.latitude_deg != -12.5 || sample.longitude_deg != 45.5 ||
        sample.speed_kmh != 5.0 || !sample.heading_usable)
        return 1;
    c2m_gps_freshness_init(&state);
    if (c2m_gps_freshness_update(&state, &sample, 1000) != 0)
        return 1;
    ++sample.utc_seconds;
    if (c2m_gps_freshness_update(&state, &sample, 2000) != 1 ||
        c2m_gps_freshness_update(&state, &sample, 4499) != 1 ||
        c2m_gps_freshness_update(&state, &sample, 4500) != 0)
        return 1;
    test_put_u32(bytes, 0);
    if (c2m_gps_decode(bytes, sizeof(bytes), &sample) != C2M_GPS_INVALID ||
        sample.utc_seconds != 0 || sample.heading_usable != 0)
        return 1;
    test_put_u32(bytes, C2M_GPS_RMC_MASK);
    test_put_u32(bytes + 0x04, 123); /* Non-leap February 29 is invalid. */
    if (c2m_gps_decode(bytes, sizeof(bytes), &sample) != C2M_GPS_INVALID)
        return 1;
    return 0;
}

int main(int argc, char **argv)
{
    int result;
    if (argc != 2 || strcmp(argv[1], "--self-test") != 0) {
        fputs("usage: gps-selftest --self-test\n", stderr);
        return 2;
    }
    result = gps_self_test();
    puts(result ? "gps snapshot synthetic self-test: FAIL" :
                  "gps snapshot synthetic self-test: OK");
    return result;
}
#endif
