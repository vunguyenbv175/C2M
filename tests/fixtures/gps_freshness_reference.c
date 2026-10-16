/* Frozen freshness reference for D4 shadow-trace differential tests.
 *
 * Frozen from fw/d3/gps_snapshot.c as of commit f15d1b3
 * (f15d1b30ad0de808ec17ac1c72f7853b59a99c66).
 * Test-only fixture, NOT production. Production lives in fw/d3/gps_snapshot.c
 * and fw/d3/gps_snapshot.h with unchanged struct layouts and behavior.
 *
 * Symbols are renamed baseline_* (direct rename, equivalent to
 * -Dc2m_gps_freshness_init=baseline_freshness_init etc.) so this fixture can
 * be linked alongside production/shadow libraries for side-by-side
 * differential testing without symbol collision.
 *
 * Covers init + anchor + sample_in_range + update only. No decode, file I/O,
 * camera, network, keys, or deployment. Pure and allocation-free like prod.
 */
#include "gps_snapshot.h"

#include <math.h>
#include <string.h>

void baseline_freshness_init(struct c2m_gps_freshness *state)
{
    if (state != NULL)
        memset(state, 0, sizeof(*state));
}

static void baseline_freshness_anchor(struct c2m_gps_freshness *state,
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

static int baseline_sample_in_range(const struct c2m_gps_snapshot *sample)
{
    /* Defend the public state API against an uninitialized/manual sample.
     * Valid UTC window is 2000-01-01 through 2099-12-31 inclusive.
     * Subsecond raw is 0..999 unscaled 1-3 digit fraction (ms only when
     * 3 digits); never used to refresh a UTC second.
     */
    return sample != NULL && (sample->mask & C2M_GPS_RMC_MASK) &&
           sample->utc_seconds >= INT64_C(946684800) &&
           sample->utc_seconds <= INT64_C(4102444799) &&
           sample->subsecond_raw <= 999u &&
           isfinite(sample->latitude_deg) &&
           fabs(sample->latitude_deg) <= 90.0 &&
           isfinite(sample->longitude_deg) &&
           fabs(sample->longitude_deg) <= 180.0 &&
           isfinite(sample->speed_kmh) && sample->speed_kmh >= 0.0 &&
           sample->speed_kmh <= C2M_GPS_MAX_SPEED_KMH &&
           isfinite(sample->course_deg) && sample->course_deg >= 0.0 &&
           sample->course_deg < 360.0;
}

int baseline_freshness_update(struct c2m_gps_freshness *state,
                              const struct c2m_gps_snapshot *sample,
                              uint64_t monotonic_ms)
{
    uint64_t elapsed_ms, gps_ms, difference_ms, reference_elapsed_ms;

    if (state == NULL)
        return 0;
    if (!baseline_sample_in_range(sample)) {
        baseline_freshness_init(state);
        return 0;
    }
    if (!state->have_anchor || monotonic_ms < state->last_observation_ms) {
        baseline_freshness_anchor(state, sample->utc_seconds, monotonic_ms);
        return 0;
    }
    state->last_observation_ms = monotonic_ms;
    elapsed_ms = monotonic_ms - state->last_advance_ms;
    if (elapsed_ms >= C2M_GPS_STALE_MS ||
        sample->utc_seconds < state->last_utc_seconds) {
        baseline_freshness_anchor(state, sample->utc_seconds, monotonic_ms);
        return 0;
    }
    if (sample->utc_seconds == state->last_utc_seconds)
        return state->confirmed;
    if (elapsed_ms == 0) {
        baseline_freshness_anchor(state, sample->utc_seconds, monotonic_ms);
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
        baseline_freshness_anchor(state, sample->utc_seconds, monotonic_ms);
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
        baseline_freshness_anchor(state, sample->utc_seconds, monotonic_ms);
        return 0;
    }
    state->last_utc_seconds = sample->utc_seconds;
    state->last_advance_ms = monotonic_ms;
    state->confirmed = 1;
    return 1;
}
