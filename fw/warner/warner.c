/* Warner core: (lat, lon, heading, speed) -> alerts for signs ahead. */
#include "warner.h"
#include <math.h>
#include <stddef.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define EARTH_R 6371000.0
#define UNKNOWN_HEADING -999.0

double warner_haversine_m(double lat1, double lon1, double lat2, double lon2) {
    double p1 = lat1 * M_PI / 180.0, p2 = lat2 * M_PI / 180.0;
    double dp = (lat2 - lat1) * M_PI / 180.0;
    double dl = (lon2 - lon1) * M_PI / 180.0;
    double a = sin(dp / 2) * sin(dp / 2) +
               cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2);
    return 2 * EARTH_R * asin(sqrt(a));
}

double warner_bearing_deg(double lat1, double lon1, double lat2, double lon2) {
    double p1 = lat1 * M_PI / 180.0, p2 = lat2 * M_PI / 180.0;
    double dl = (lon2 - lon1) * M_PI / 180.0;
    double x = sin(dl) * cos(p2);
    double y = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl);
    double b = atan2(x, y) * 180.0 / M_PI;
    return b < 0 ? b + 360.0 : b;
}

double warner_angle_diff(double a, double b) {
    double d = a - b;
    /* wrap to [-180, 180] without fmod (keeps glibc need <= 2.30) */
    while (d > 180.0) d -= 360.0;
    while (d <= -180.0) d += 360.0;
    return d;
}

void warner_init(warner_t *w, const warner_sign_t *signs, int n_signs) {
    w->signs = signs;
    w->n_signs = n_signs;
    w->lookahead_s = 8.0;
    w->min_warn_m = 150.0;
    w->max_warn_m = 600.0;
    w->bearing_tol_deg = 30.0;
    w->sign_heading_tol = 45.0;
    w->cooldown_s = 120.0;
    w->last_alert = NULL; /* caller provides storage via warner_set_state() */
}

/* Optional: attach caller-owned per-sign timestamp storage (n_signs doubles).
 * If not attached, cooldown is disabled. */
void warner_set_state(warner_t *w, double *last_alert) {
    int i;
    w->last_alert = last_alert;
    for (i = 0; i < w->n_signs; i++) last_alert[i] = -1.0;
}

int warner_update(warner_t *w, double lat, double lon, double heading_deg,
                  double speed_kmh, double now_s,
                  warner_alert_t *out, int max_alerts) {
    double v_ms = speed_kmh / 3.6;
    double radius = v_ms * w->lookahead_s;
    int n = 0, i, j;
    if (radius < w->min_warn_m) radius = w->min_warn_m;
    if (radius > w->max_warn_m) radius = w->max_warn_m;
    if (v_ms < 1.0) v_ms = 1.0;

    for (i = 0; i < w->n_signs && n < max_alerts; i++) {
        const warner_sign_t *s = &w->signs[i];
        double dist = warner_haversine_m(lat, lon, s->lat, s->lon);
        double brg, ad;
        if (dist > radius) continue;
        brg = warner_bearing_deg(lat, lon, s->lat, s->lon);
        ad = warner_angle_diff(brg, heading_deg);
        if (ad < 0) ad = -ad;
        if (ad > w->bearing_tol_deg) continue;          /* behind / off-side */
        if (s->heading_deg != UNKNOWN_HEADING) {
            double hd = warner_angle_diff(s->heading_deg, heading_deg);
            if (hd < 0) hd = -hd;
            if (hd > w->sign_heading_tol) continue;     /* opposite direction */
        }
        if (w->last_alert) {
            double last = w->last_alert[i];
            if (last >= 0 && now_s - last < w->cooldown_s) continue;
            w->last_alert[i] = now_s;
        }
        out[n].sign_index = i;
        out[n].distance_m = dist;
        out[n].eta_s = dist / v_ms;
        out[n].bearing_deg = brg;
        n++;
    }
    /* insertion sort by distance (n is small) */
    for (i = 1; i < n; i++) {
        warner_alert_t t = out[i];
        for (j = i; j > 0 && out[j - 1].distance_m > t.distance_m; j--)
            out[j] = out[j - 1];
        out[j] = t;
    }
    return n;
}
