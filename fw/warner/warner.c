/* Replay matcher: coordinates/course/speed -> nearest directional DB alerts.
 * This is GPS advisory selection, NOT a camera TSR detector or audio backend.
 */
#include "warner.h"
#include <math.h>
#include <stddef.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
#define EARTH_R 6371000.0
#define UNKNOWN_HEADING -999.0
#define MIN_MOVING_KMH 5.0

static int valid_position(double lat, double lon) {
    return isfinite(lat) && isfinite(lon) && lat >= -90 && lat <= 90 &&
           lon >= -180 && lon <= 180;
}

static int valid_heading(double heading) {
    return isfinite(heading) && heading >= 0 && heading < 360;
}

double warner_haversine_m(double lat1, double lon1, double lat2, double lon2) {
    double p1, p2, dp, dl, a;
    if (!valid_position(lat1, lon1) || !valid_position(lat2, lon2)) return NAN;
    p1 = lat1 * M_PI / 180.0; p2 = lat2 * M_PI / 180.0;
    dp = (lat2 - lat1) * M_PI / 180.0;
    dl = (lon2 - lon1) * M_PI / 180.0;
    a = sin(dp / 2) * sin(dp / 2) + cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2);
    if (a < 0) a = 0;
    if (a > 1) a = 1;
    return 2 * EARTH_R * asin(sqrt(a));
}

double warner_bearing_deg(double lat1, double lon1, double lat2, double lon2) {
    double p1, p2, dl, x, y, bearing;
    if (!valid_position(lat1, lon1) || !valid_position(lat2, lon2)) return NAN;
    p1 = lat1 * M_PI / 180.0; p2 = lat2 * M_PI / 180.0;
    dl = (lon2 - lon1) * M_PI / 180.0;
    x = sin(dl) * cos(p2);
    y = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl);
    bearing = atan2(x, y) * 180.0 / M_PI;
    return bearing < 0 ? bearing + 360.0 : bearing;
}

double warner_angle_diff(double a, double b) {
    double d;
    /* The matcher accepts only bounded angles; never loop on Inf/huge input. */
    if (!isfinite(a) || !isfinite(b) || a < 0 || a > 360 || b < 0 || b > 360) return NAN;
    d = a - b;
    if (d > 180) d -= 360;
    if (d <= -180) d += 360;
    return d;
}

void warner_init(warner_t *w, const warner_sign_t *signs, int n_signs) {
    if (!w) return;
    w->signs = signs;
    w->n_signs = n_signs;
    w->lookahead_s = 8.0;
    w->min_warn_m = 150.0;
    w->max_warn_m = 600.0;
    w->bearing_tol_deg = 30.0;
    w->sign_heading_tol = 45.0;
    w->cooldown_s = 120.0;
    w->last_alert = NULL;
}

void warner_set_state(warner_t *w, double *last_alert) {
    int i;
    if (!w) return;
    w->last_alert = last_alert;
    if (!last_alert) return;
    for (i = 0; i < w->n_signs; i++) last_alert[i] = -1.0;
}

int warner_update(warner_t *w, double lat, double lon, double heading_deg,
                  double speed_kmh, double now_s,
                  warner_alert_t *out, int max_alerts) {
    double radius, v_ms, lat_bound, lon_bound, c;
    int n = 0, i;
    if (!w || !w->signs || w->n_signs <= 0 || w->n_signs > 40000 || !out || max_alerts <= 0 ||
        !valid_position(lat, lon) || !valid_heading(heading_deg) ||
        !isfinite(speed_kmh) || speed_kmh < MIN_MOVING_KMH || speed_kmh > 300 ||
        !isfinite(now_s) || now_s < 0 || !isfinite(w->lookahead_s) || w->lookahead_s <= 0 ||
        !isfinite(w->min_warn_m) || !isfinite(w->max_warn_m) ||
        w->min_warn_m < 0 || w->max_warn_m < w->min_warn_m || w->max_warn_m > 2000 ||
        !isfinite(w->cooldown_s) || w->cooldown_s < 0 ||
        !isfinite(w->bearing_tol_deg) || w->bearing_tol_deg < 0 || w->bearing_tol_deg > 180 ||
        !isfinite(w->sign_heading_tol) || w->sign_heading_tol < 0 || w->sign_heading_tol > 180) return 0;
    v_ms = speed_kmh / 3.6;
    radius = v_ms * w->lookahead_s;
    if (radius < w->min_warn_m) radius = w->min_warn_m;
    if (radius > w->max_warn_m) radius = w->max_warn_m;
    /* Conservative prefilter; geodesic tests follow. Prevent full-DB trig. */
    lat_bound = radius / 110000.0;
    c = cos(lat * M_PI / 180.0);
    lon_bound = c > 0.01 ? radius / (110000.0 * c) : 180.0;
    for (i = 0; i < w->n_signs; i++) {
        const warner_sign_t *s = &w->signs[i];
        double dist, bearing, delta, lon_delta;
        int j;
        if (!valid_position(s->lat, s->lon) || !valid_heading(s->heading_deg)) continue;
        /* Unknown application heading is not eligible for automatic warning. */
        if (s->heading_deg == UNKNOWN_HEADING) continue;
        if (fabs(s->lat - lat) > lat_bound) continue;
        lon_delta = fabs(s->lon - lon);
        if (lon_delta > 180) lon_delta = 360 - lon_delta;
        if (lon_delta > lon_bound) continue;
        dist = warner_haversine_m(lat, lon, s->lat, s->lon);
        if (!isfinite(dist) || dist > radius || dist < 0.5) continue;
        bearing = warner_bearing_deg(lat, lon, s->lat, s->lon);
        delta = fabs(warner_angle_diff(bearing, heading_deg));
        if (!isfinite(delta) || delta > w->bearing_tol_deg) continue;
        delta = fabs(warner_angle_diff(s->heading_deg, heading_deg));
        if (!isfinite(delta) || delta > w->sign_heading_tol) continue;
        if (w->last_alert) {
            double last = w->last_alert[i];
            if (!isfinite(last) || (last >= 0 && now_s - last < w->cooldown_s)) continue;
        }
        /* Select nearest max_alerts across the complete eligible set. */
        if (n == max_alerts && dist >= out[n - 1].distance_m) continue;
        if (n < max_alerts) n++;
        for (j = n - 1; j > 0 && out[j - 1].distance_m > dist; j--) out[j] = out[j - 1];
        out[j].sign_index = i;
        out[j].distance_m = dist;
        out[j].eta_s = dist / v_ms;
        out[j].bearing_deg = bearing;
    }
    /* Replay selection bookkeeping only. Live output MUST move this update
     * to successful delivery; no live backend is enabled by this prototype. */
    if (w->last_alert) for (i = 0; i < n; i++) w->last_alert[out[i].sign_index] = now_s;
    return n;
}
