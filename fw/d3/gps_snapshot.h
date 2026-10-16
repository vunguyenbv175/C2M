#ifndef C2M_D3_GPS_SNAPSHOT_H
#define C2M_D3_GPS_SNAPSHOT_H

#include <stddef.h>
#include <stdint.h>

/* EN cardv contract: WriteGpsInfoForCardvUI copies 0x1c0 bytes of
 * little-endian nmeaINFO into carInfo+0x330, then writes 0x1c8 bytes at
 * FILE offset 0x330. Decode only the copied 0x1c0-byte GPS region, not the
 * extra eight bytes or the start of car_info. This is not a vendor IPC API.
 */
#define C2M_GPS_DEFAULT_PATH "/tmp/car_info"
#define C2M_GPS_FILE_OFFSET 0x330u
#define C2M_GPS_RECORD_BYTES 0x1c0u
#define C2M_GPS_MIN_FILE_BYTES 0x4f0u
#define C2M_GPS_MAX_FILE_BYTES (2u * 1024u * 1024u)
/* nmeaPACKTYPE_GPRMC is the mask VALUE 8, not bit index 8. */
#define C2M_GPS_RMC_MASK UINT32_C(0x0008)
#define C2M_GPS_MIN_HEADING_KMH 5.0
#define C2M_GPS_MAX_SPEED_KMH 300.0
#define C2M_GPS_STALE_MS UINT64_C(2500)
#define C2M_GPS_DELTA_TOLERANCE_MS UINT64_C(3000)

enum c2m_gps_result {
    C2M_GPS_OK = 0,
    C2M_GPS_INVALID = -1,
    C2M_GPS_IO_ERROR = -2,
    C2M_GPS_UNSTABLE = -3,
    C2M_GPS_UNSUPPORTED = -4
};

struct c2m_gps_snapshot {
    int64_t utc_seconds;       /* Unix UTC seconds; no local timezone/time_t. */
    uint32_t subsecond_raw;    /* 0..999 unscaled 1-3 digit fraction; not used to refresh a UTC second. */
    uint32_t mask;
    double latitude_deg;      /* Converted from SIGNED NMEA DDMM, not radians. */
    double longitude_deg;
    double speed_kmh;         /* Already km/h in nmeaINFO; do not multiply. */
    double course_deg;        /* [0,360), even at rest; not necessarily usable. */
    int heading_usable;       /* Speed in [5,300]; also require freshness below. */
};

/* Pure, allocation-free decoder. Requires exactly C2M_GPS_RECORD_BYTES.
 * RMC, signal>0, fix>=2, UTC 2000..2099, valid calendar/subseconds, finite
 * signed DDMM coordinates, speed [0,300], and course [0,360) are mandatory.
 * Subseconds at GPS-record-relative 0x1c (nmeaINFO+0x1c; absolute file
 * 0x34c = 0x330+0x1c) are 0..999 unscaled 1-3 digit fraction (milliseconds
 * only when 3 digits; see _nmea_parse_time 0xe0099 with "%2d%2d%2d.%d",
 * no scaling). Returns OK or INVALID. All failures clear *out
 * when out is non-NULL.
 * A decoded sample alone is NOT proof of freshness or a heading candidate.
 */
int c2m_gps_decode(const uint8_t *bytes, size_t size,
                   struct c2m_gps_snapshot *out);

/* Read-only Linux adapter. The caller supplies the path explicitly.
 * Opens O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC, checks a bounded regular
 * file, and requires two identical, exact pread()s of the GPS region.
 * No writes, UART, vendor IPC, mtime-based freshness, or location logging.
 * Equal reads cannot prove atomicity of the vendor's in-place writer; the
 * decoder and advancing-timestamp gate are additional fail-closed checks.
 * Non-Linux builds return UNSUPPORTED without touching the filesystem.
 */
int c2m_gps_read(const char *path, struct c2m_gps_snapshot *out);

struct c2m_gps_freshness {
    int64_t last_utc_seconds;
    uint64_t last_advance_ms;
    uint64_t last_observation_ms;
    int64_t reference_utc_seconds;
    uint64_t reference_ms;
    int have_anchor;
    int confirmed;
};

void c2m_gps_freshness_init(struct c2m_gps_freshness *state);

/* Feed each poll, including failures (sample=NULL). monotonic_ms must be
 * from the caller's monotonic clock, NOT wall time or file mtime. Returns 1
 * only after two strictly increasing GPS UTC-second observations agree
 * with elapsed monotonic time within 3 seconds. Repeated seconds do not
 * refresh the clock, regardless of coordinates/subseconds; at age >=2.5s
 * they are invalid. Stale gaps, clock regressions, UTC jumps/regressions,
 * and failed polls require a new two-sample confirmation. This function
 * is pure and has no timer/thread; callers must poll before using a sample.
 * Pass only successfully decoded samples. Heading candidates additionally
 * require sample->heading_usable (speed >=5 km/h).
 */
int c2m_gps_freshness_update(struct c2m_gps_freshness *state,
                           const struct c2m_gps_snapshot *sample,
                           uint64_t monotonic_ms);

/* Standalone synthetic CLI: cc -std=c99 -Wall -Wextra
 *   -DC2M_GPS_SELFTEST gps_snapshot.c -lm -o gps-selftest
 *   ./gps-selftest --self-test
 * It never opens C2M_GPS_DEFAULT_PATH or prints coordinates.
 */

#endif
