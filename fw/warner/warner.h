/* c2m-warner — on-device offline traffic-sign Warner for C2M (SSC8838G).
 *
 * No phone, no network. Reads NMEA GPS, matches against an offline sign
 * database, emits alerts. Designed to run as a small daemon launched by
 * the SD-card boot hook (same mechanism as candidate C).
 *
 * Target: armv7-a, hard-float (see fw/device_minimal/toolchain-armhf-dyn.cmake).
 * Also builds natively for host testing: gcc -o warner_host main.c warner.c nmea.c db.c -lm
 */
#ifndef WARNER_H
#define WARNER_H

#define WARNER_TYPE_LEN 16
#define WARNER_LABEL_LEN 64

typedef struct {
    double lat;
    double lon;
    float heading_deg;   /* direction the sign applies to; -999 = unknown */
    char type[WARNER_TYPE_LEN];
    char label[WARNER_LABEL_LEN];
} warner_sign_t;

typedef struct {
    int sign_index;      /* index into db array */
    double distance_m;
    double eta_s;
    double bearing_deg;
} warner_alert_t;

typedef struct {
    const warner_sign_t *signs;
    int n_signs;
    /* tuning (mirrors Python prototype) */
    double lookahead_s;      /* default 8.0 */
    double min_warn_m;       /* default 150 */
    double max_warn_m;       /* default 600 */
    double bearing_tol_deg;  /* default 30 */
    double sign_heading_tol; /* default 45 */
    double cooldown_s;       /* default 120 */
    /* state */
    double *last_alert;      /* per-sign last alert time, -1 = never */
} warner_t;

void warner_init(warner_t *w, const warner_sign_t *signs, int n_signs);

/* Attach caller-owned per-sign timestamp storage (n_signs doubles).
 * If never attached, cooldown is disabled. */
void warner_set_state(warner_t *w, double *last_alert);

/* Replay-only advisory selection: returns nearest directional DB matches.
 * Unknown-heading signs and movement below 5 km/h are suppressed.
 * now_s is ordered replay time, NOT proof of live GPS freshness. Cooldown
 * currently commits selection; a future live backend must commit delivery. */
int warner_update(warner_t *w, double lat, double lon, double heading_deg,
                  double speed_kmh, double now_s,
                  warner_alert_t *out, int max_alerts);

/* geodesic helpers (also unit-testable) */
double warner_haversine_m(double lat1, double lon1, double lat2, double lon2);
double warner_bearing_deg(double lat1, double lon1, double lat2, double lon2);
double warner_angle_diff(double a, double b);

#endif
