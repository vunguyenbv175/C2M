#ifndef C2M_D4_ADVISORY_H
#define C2M_D4_ADVISORY_H

#include <stddef.h>
#include <stdint.h>
#include "warner.h"
#include "gps_snapshot.h"

#define C2M_D4_DEFAULT_DB "/customer/c2m/signs-d4.bin"
#define C2M_D4_DEFAULT_STATUS "/tmp/c2m_d4_status"
/* Five seconds locally plus the web's 3-second hard TTL stays <=8 seconds
 * even when the producer stops/fails just before clearing the heartbeat. */
#define C2M_D4_HOLD_MS UINT64_C(5000)
#define C2M_D4_COOLDOWN_MS UINT64_C(120000)
#define C2M_D4_STATUS_BYTES 512

enum c2m_d4_state {
    C2M_D4_WAITING_GPS, C2M_D4_WARMING_UP, C2M_D4_READY, C2M_D4_STALE,
    C2M_D4_NO_DATABASE, C2M_D4_DISABLED, C2M_D4_ERROR
};
enum c2m_d4_code {
    C2M_D4_NONE, C2M_D4_RESIDENTIAL_START, C2M_D4_RESIDENTIAL_END
};
struct c2m_d4_status {
    enum c2m_d4_state state;
    enum c2m_d4_code code;
    uint32_t sequence, event_id;
    uint64_t monotonic_ms;
    unsigned gps_fresh, active, distance_m;
};
struct c2m_d4_cooldown {
    uint64_t delivered_ms;
    int used;
};
struct c2m_d4_advisory {
    const warner_sign_t *signs;
    int count;
    struct c2m_d4_cooldown *cooldowns; /* caller-owned count entries */
    struct c2m_gps_freshness freshness;
    int seen_gps, stale_seen;
    int active_sign;
    uint64_t active_since_ms, last_ms;
    uint32_t event_counter, active_id, sequence;
    int have_time, pending, pending_new, pending_sign;
    struct c2m_d4_status proposed;
};

/* Pure core. No files, output, timers, threads, or warner_update lifecycle.
 * A NULL/invalid DB is safe. Cooldown memory is cleared by init. */
void c2m_d4_init(struct c2m_d4_advisory *core, const warner_sign_t *signs,
                 int count, struct c2m_d4_cooldown *cooldowns);
void c2m_d4_prepare(struct c2m_d4_advisory *core,
                    const struct c2m_gps_snapshot *sample, uint64_t now_ms,
                    int database_ok, int disabled, struct c2m_d4_status *out);
/* Must follow every prepare. Only a successfully atomically published status
 * commits event ID, hold start, sequence, and per-sign cooldown. On failure an
 * existing hold is cleared, and un-delivered candidates remain retryable. */
void c2m_d4_published(struct c2m_d4_advisory *core, int success);
/* Fixed, ASCII, LF-only web contract; never contains coordinates or labels.
 * Returns bytes (excluding NUL), or -1. Numeric speed is ALWAYS zero. */
int c2m_d4_format_status(const struct c2m_d4_status *status,
                         char *buffer, size_t capacity);
int c2m_d4_self_test(void);

#endif
