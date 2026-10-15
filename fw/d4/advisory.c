/* Experimental NEARBY-area advisory, not legal speed or in-area state. */
#include "advisory.h"
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void clear_active(struct c2m_d4_advisory *c)
{
    c->active_sign = -1;
    c->active_id = 0;
    c->active_since_ms = 0;
}

void c2m_d4_init(struct c2m_d4_advisory *c, const warner_sign_t *signs,
                 int count, struct c2m_d4_cooldown *cooldowns)
{
    if (!c) return;
    memset(c, 0, sizeof(*c));
    if (signs && cooldowns && count > 0 && count <= 40000) {
        c->signs = signs;
        c->count = count;
        c->cooldowns = cooldowns;
        memset(cooldowns, 0, (size_t)count * sizeof(*cooldowns));
    }
    clear_active(c);
    c2m_gps_freshness_init(&c->freshness);
}

static enum c2m_d4_code sign_code(const warner_sign_t *s)
{
    if (!memcmp(s->type, "R.420", 6)) return C2M_D4_RESIDENTIAL_START;
    if (!memcmp(s->type, "R.421", 6)) return C2M_D4_RESIDENTIAL_END;
    return C2M_D4_NONE;
}

static int eligible(const warner_sign_t *s,
                    const struct c2m_gps_snapshot *gps, double radius,
                    double *distance)
{
    double d, bearing, delta, lon_delta, cos_lat;
    /* COMPLETE semantic filter before distance/nearest selection: no numeric
     * speed inference, P.127, unknown application direction, or free text. */
    if (sign_code(s) == C2M_D4_NONE || !isfinite(s->heading_deg) ||
        s->heading_deg < 0.0 || s->heading_deg >= 360.0 ||
        !isfinite(s->lat) || fabs(s->lat) > 90.0 ||
        !isfinite(s->lon) || fabs(s->lon) > 180.0) return 0;
    delta = fabs(warner_angle_diff(s->heading_deg, gps->course_deg));
    if (!isfinite(delta) || delta > 45.0) return 0;
    if (fabs(s->lat - gps->latitude_deg) > radius / 110000.0) return 0;
    cos_lat = cos(gps->latitude_deg * 0.01745329251994329577);
    lon_delta = fabs(s->lon - gps->longitude_deg);
    if (lon_delta > 180.0) lon_delta = 360.0 - lon_delta;
    if (cos_lat > 0.01 && lon_delta > radius / (110000.0 * cos_lat)) return 0;
    d = warner_haversine_m(gps->latitude_deg, gps->longitude_deg, s->lat, s->lon);
    if (!isfinite(d) || d < 0.5 || d > radius) return 0;
    bearing = warner_bearing_deg(gps->latitude_deg, gps->longitude_deg, s->lat, s->lon);
    delta = fabs(warner_angle_diff(bearing, gps->course_deg));
    if (!isfinite(delta) || delta > 30.0) return 0;
    *distance = d;
    return 1;
}

void c2m_d4_prepare(struct c2m_d4_advisory *c,
                    const struct c2m_gps_snapshot *gps, uint64_t now,
                    int database_ok, int disabled, struct c2m_d4_status *out)
{
    struct c2m_d4_status s;
    int fresh, had_anchor, was_confirmed, regression;
    int chosen = -1, i;
    double radius, nearest = 2001.0, distance = 0.0;
    if (!c || !out) return;
    /* Caller failed to acknowledge a publication: it was NOT delivery. */
    if (c->pending) c2m_d4_published(c, 0);
    memset(&s, 0, sizeof(s));
    s.state = C2M_D4_WAITING_GPS;
    s.monotonic_ms = now;
    s.sequence = c->sequence == UINT32_MAX ? UINT32_MAX : c->sequence + 1;
    regression = c->have_time && now < c->last_ms;
    c->last_ms = now;
    c->have_time = 1;
    had_anchor = c->freshness.have_anchor;
    was_confirmed = c->freshness.confirmed;
    if (had_anchor && !regression &&
        now - c->freshness.last_advance_ms >= C2M_GPS_STALE_MS) c->stale_seen = 1;
    fresh = c2m_gps_freshness_update(&c->freshness, gps, now);
    if (c->freshness.have_anchor) c->seen_gps = 1;
    if ((had_anchor && !c->freshness.have_anchor) ||
        (was_confirmed && !fresh)) c->stale_seen = 1;
    if (fresh) c->stale_seen = 0;
    s.gps_fresh = (unsigned)fresh;
    if (c->seen_gps) s.state = c->stale_seen ? C2M_D4_STALE : C2M_D4_WARMING_UP;
    if (fresh) s.state = C2M_D4_READY;
    if (!database_ok || !c->signs || !c->cooldowns || c->count <= 0)
        s.state = C2M_D4_NO_DATABASE;
    if (disabled || c->sequence >= UINT32_MAX - 1) s.state = C2M_D4_DISABLED;
    if (regression) {
        s.state = C2M_D4_ERROR;
        s.gps_fresh = 0;
        c2m_gps_freshness_init(&c->freshness);
    }
    c->pending_new = 0;
    if (s.state != C2M_D4_READY || !gps || !gps->heading_usable ||
        gps->speed_kmh < C2M_GPS_MIN_HEADING_KMH) {
        clear_active(c);
        goto done;
    }
    radius = gps->speed_kmh / 3.6 * 8.0;
    if (radius < 150.0) radius = 150.0;
    if (radius > 600.0) radius = 600.0;
    if (c->active_sign >= 0) {
        if (now - c->active_since_ms < C2M_D4_HOLD_MS &&
            eligible(&c->signs[c->active_sign], gps, radius, &distance)) {
            chosen = c->active_sign;
            s.event_id = c->active_id;
            goto selected;
        }
        clear_active(c);
    }
    if (c->event_counter == UINT32_MAX) {
        s.state = C2M_D4_DISABLED;
        goto done;
    }
    for (i = 0; i < c->count; ++i) {
        const struct c2m_d4_cooldown *cd = &c->cooldowns[i];
        if (cd->used && (now < cd->delivered_ms ||
                        now - cd->delivered_ms < C2M_D4_COOLDOWN_MS)) continue;
        if (!eligible(&c->signs[i], gps, radius, &distance)) continue;
        if (distance < nearest) { nearest = distance; chosen = i; }
    }
    if (chosen < 0) goto done;
    distance = nearest;
    s.event_id = c->event_counter + 1;
    c->pending_new = 1;
selected:
    s.active = 1;
    s.code = sign_code(&c->signs[chosen]);
    s.distance_m = (unsigned)(distance + 0.5);
    c->pending_sign = chosen;
done:
    c->proposed = s;
    c->pending = 1;
    *out = s;
}

void c2m_d4_published(struct c2m_d4_advisory *c, int success)
{
    if (!c || !c->pending) return;
    if (success) {
        c->sequence = c->proposed.sequence;
        if (c->pending_new && c->proposed.active) {
            c->active_sign = c->pending_sign;
            c->active_id = c->proposed.event_id;
            c->event_counter = c->active_id;
            c->active_since_ms = c->proposed.monotonic_ms;
            c->cooldowns[c->active_sign].used = 1;
            c->cooldowns[c->active_sign].delivered_ms = c->active_since_ms;
        }
    } else {
        clear_active(c);
    }
    c->pending = 0;
    c->pending_new = 0;
}

int c2m_d4_format_status(const struct c2m_d4_status *s, char *buf, size_t cap)
{
    static const char *const states[] = {
        "waiting_gps", "warming_up", "ready", "stale", "no_database", "disabled", "error"
    };
    static const char *const codes[] = { "none", "residential_start", "residential_end" };
    int n;
    if (!s || !buf || cap == 0 || (unsigned)s->state > C2M_D4_ERROR ||
        (unsigned)s->code > C2M_D4_RESIDENTIAL_END || s->gps_fresh > 1 ||
        s->active > 1 || s->distance_m > 2000 ||
        (s->active && (s->state != C2M_D4_READY || !s->gps_fresh ||
                       s->code == C2M_D4_NONE || !s->event_id)) ||
        (!s->active && (s->code != C2M_D4_NONE || s->event_id || s->distance_m))) return -1;
    n = snprintf(buf, cap, "version=1\nsource=gps_offline\nstate=%s\ngps_fresh=%u\n"
                 "active=%u\nsequence=%" PRIu32 "\ncode=%s\nspeed_kmh=0\n"
                 "distance_m=%u\nevent_id=%" PRIu32 "\nmonotonic_ms=%" PRIu64 "\n",
                 states[s->state], s->gps_fresh, s->active, s->sequence,
                 codes[s->code], s->distance_m, s->event_id, s->monotonic_ms);
    return n < 0 || (size_t)n >= cap ? -1 : n;
}

/* Synthetic core tests: no production paths/data or I/O. */
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
int c2m_d4_self_test(void)
{
    struct c2m_d4_advisory c;
    struct c2m_d4_cooldown cds[7];
    struct c2m_d4_status s;
    struct c2m_gps_snapshot g;
    warner_sign_t signs[7];
    char text[C2M_D4_STATUS_BYTES];
    int i;
    memset(&g, 0, sizeof(g));
    g.mask = C2M_GPS_RMC_MASK; g.utc_seconds = INT64_C(1709164800);
    g.speed_kmh = 36.0; g.heading_usable = 1;
    memset(signs, 0, sizeof(signs));
    for (i = 0; i < 7; ++i) {
        signs[i].lat = 0.0001 * (i + 1);
        memcpy(signs[i].type, "R.420", 6);
    }
    memcpy(signs[0].type, "P.127", 6); /* nearer but forbidden */
    signs[1].heading_deg = -999.0f; /* never both directions */
    signs[2].heading_deg = 180.0f;
    signs[3].lon = 0.001; /* outside point corridor */
    memcpy(signs[4].type, "R.421", 6); /* nearest ELIGIBLE */
    c2m_d4_init(&c, signs, 7, cds);
    c2m_d4_prepare(&c, NULL, 0, 1, 0, &s);
    CHECK(s.state == C2M_D4_WAITING_GPS && !s.active);
    c2m_d4_published(&c, 1);
    c2m_d4_prepare(&c, &g, 1000, 1, 0, &s);
    CHECK(s.state == C2M_D4_WARMING_UP && !s.active);
    c2m_d4_published(&c, 1);
    ++g.utc_seconds;
    c2m_d4_prepare(&c, &g, 2000, 1, 0, &s);
    CHECK(s.active && s.code == C2M_D4_RESIDENTIAL_END && s.event_id == 1);
    CHECK(c2m_d4_format_status(&s, text, sizeof(text)) > 0);
    CHECK(strstr(text, "speed_kmh=0\n") && !strstr(text, "lat"));
    c2m_d4_published(&c, 0);
    CHECK(!cds[4].used && c.event_counter == 0 && c.sequence == 2);
    c2m_d4_prepare(&c, &g, 2100, 1, 0, &s);
    CHECK(s.active && s.event_id == 1);
    c2m_d4_published(&c, 1);
    CHECK(cds[4].used && c.active_since_ms == 2100);
    /* Same event on every heartbeat, no new cooldown commit. */
    for (i = 3; i <= 6; ++i) {
        ++g.utc_seconds;
        c2m_d4_prepare(&c, &g, (uint64_t)i * 1000, 1, 0, &s);
        CHECK(s.active && s.event_id == 1 && s.code == C2M_D4_RESIDENTIAL_END);
        c2m_d4_published(&c, 1);
        CHECK(cds[4].delivered_ms == 2100);
    }
    ++g.utc_seconds;
    c2m_d4_prepare(&c, &g, 7100, 1, 0, &s);
    CHECK(s.active && s.event_id == 2 && s.code == C2M_D4_RESIDENTIAL_START);
    c2m_d4_published(&c, 1);
    g.course_deg = 180;
    c2m_d4_prepare(&c, &g, 7200, 1, 0, &s);
    CHECK(!s.active); /* out of corridor/turned */
    c2m_d4_published(&c, 1);
    g.course_deg = 0;
    c2m_d4_prepare(&c, &g, 9600, 1, 0, &s);
    CHECK(!s.active && !s.gps_fresh && s.state == C2M_D4_STALE);
    c2m_d4_published(&c, 1);
    c2m_d4_prepare(&c, NULL, 13000, 0, 0, &s);
    CHECK(s.state == C2M_D4_NO_DATABASE && !s.active);
    c2m_d4_published(&c, 1);
    c2m_d4_prepare(&c, NULL, 14000, 1, 1, &s);
    CHECK(s.state == C2M_D4_DISABLED && !s.active);
    c2m_d4_published(&c, 1);
    c2m_d4_prepare(&c, &g, 13000, 1, 0, &s);
    CHECK(s.state == C2M_D4_ERROR && !s.active);
    c2m_d4_published(&c, 1);
    /* Freshness must reacquire after every failure; stopped is never active. */
    c2m_d4_init(&c, signs + 4, 1, cds);
    c2m_d4_prepare(&c, &g, 1000, 1, 0, &s); c2m_d4_published(&c, 1);
    ++g.utc_seconds;
    c2m_d4_prepare(&c, &g, 2000, 1, 0, &s); c2m_d4_published(&c, 1);
    CHECK(s.active);
    g.speed_kmh = 4.99; g.heading_usable = 0;
    c2m_d4_prepare(&c, &g, 2100, 1, 0, &s);
    CHECK(!s.active && s.state == C2M_D4_READY);
    c2m_d4_published(&c, 1);
    g.speed_kmh = 36; g.heading_usable = 1;
    c2m_d4_prepare(&c, &g, 2200, 1, 0, &s);
    CHECK(!s.active); /* cooldown even after stopped */
    c2m_d4_published(&c, 1);
    c.event_counter = UINT32_MAX;
    c2m_d4_prepare(&c, &g, 2300, 1, 0, &s);
    CHECK(!s.active && s.state == C2M_D4_DISABLED);
    c2m_d4_published(&c, 1);
    c.sequence = UINT32_MAX - 1;
    c2m_d4_prepare(&c, &g, 2400, 1, 0, &s);
    CHECK(s.sequence == UINT32_MAX && s.state == C2M_D4_DISABLED);
    c2m_d4_published(&c, 1);
    c2m_d4_prepare(&c, &g, 2500, 1, 0, &s);
    CHECK(s.sequence == UINT32_MAX && !s.active);
    c2m_d4_published(&c, 1);
    /* Clear immediately on passing, missing/changed DB, or a failed poll.
     * A lost hold does not undo its delivered per-sign cooldown. */
    c2m_d4_init(&c, signs + 4, 1, cds);
    c2m_d4_prepare(&c, &g, 1000, 1, 0, &s); c2m_d4_published(&c, 1);
    ++g.utc_seconds;
    c2m_d4_prepare(&c, &g, 2000, 1, 0, &s); c2m_d4_published(&c, 1);
    CHECK(s.active);
    g.latitude_deg = 0.0006;
    c2m_d4_prepare(&c, &g, 2100, 1, 0, &s);
    CHECK(!s.active); c2m_d4_published(&c, 1);
    g.latitude_deg = 0.0;
    c2m_d4_prepare(&c, &g, 2200, 1, 0, &s);
    CHECK(!s.active); c2m_d4_published(&c, 1);
    /* Reanchor after a long gap, then at exactly 120 seconds cooldown ends. */
    c2m_d4_prepare(&c, &g, 121000, 1, 0, &s);
    CHECK(!s.active); c2m_d4_published(&c, 1);
    ++g.utc_seconds;
    c2m_d4_prepare(&c, &g, 122000, 1, 0, &s);
    CHECK(s.active && s.event_id == 2); c2m_d4_published(&c, 1);
    c2m_d4_prepare(&c, &g, 122100, 0, 0, &s);
    CHECK(!s.active && s.state == C2M_D4_NO_DATABASE); c2m_d4_published(&c, 1);
    c2m_d4_prepare(&c, NULL, 122200, 1, 0, &s);
    CHECK(!s.active && !s.gps_fresh); c2m_d4_published(&c, 1);
    ++g.utc_seconds;
    c2m_d4_prepare(&c, &g, 123000, 1, 0, &s);
    CHECK(!s.active && !s.gps_fresh); c2m_d4_published(&c, 1);
    ++g.utc_seconds;
    c2m_d4_prepare(&c, &g, 124000, 1, 0, &s);
    CHECK(!s.active && s.gps_fresh); c2m_d4_published(&c, 1);
    /* 150..600 m radius, 30-degree point/45-degree application corridors,
     * and compass wrap; unknown direction cannot shadow an eligible sign. */
    g.latitude_deg = 0; g.longitude_deg = 0; g.course_deg = 359;
    g.speed_kmh = 300;
    signs[4].lat = 0.004; signs[4].heading_deg = 1;
    c2m_d4_init(&c, signs + 4, 1, cds);
    c2m_d4_prepare(&c, &g, 1000, 1, 0, &s); c2m_d4_published(&c, 1);
    ++g.utc_seconds;
    c2m_d4_prepare(&c, &g, 2000, 1, 0, &s);
    CHECK(s.active && s.distance_m > 400 && s.distance_m < 600);
    c2m_d4_published(&c, 1);
    signs[4].lat = 0.006;
    c2m_d4_prepare(&c, &g, 2100, 1, 0, &s);
    CHECK(!s.active); c2m_d4_published(&c, 1);
    signs[4].lat = 0.0005; signs[4].heading_deg = 46;
    c2m_d4_prepare(&c, &g, 2200, 1, 0, &s);
    CHECK(!s.active); c2m_d4_published(&c, 1);
    return 0;
}
