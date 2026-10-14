/* Host unit test: geo math + NMEA parser + warner logic.
 * gcc -o test_warner test_warner.c warner.c nmea.c -lm && ./test_warner
 */
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <math.h>
#include "warner.h"
#include "nmea.h"

static int fails = 0;
#define CHECK(cond, msg) do { \
    if (!(cond)) { printf("FAIL: %s\n", msg); fails++; } \
} while (0)

int main(void) {
    /* geo */
    double d = warner_haversine_m(10.7720, 106.6900, 10.7720, 106.6990);
    CHECK(fabs(d - 983.0) < 5.0, "haversine ~983m");
    CHECK(fabs(warner_bearing_deg(10.7720, 106.6900, 10.7720, 106.6990) - 90.0) < 1.0,
          "bearing east = 90");
    CHECK(fabs(warner_angle_diff(10, 350) - 20.0) < 1e-9, "angle diff wrap");

    /* nmea: $GPRMC,084522,A,1046.32,N,10641.40,E,21.6,90.0,141026,,,A*63
       -> 10.7720N, 106.6900E, 21.6 knots = 40.0 km/h, course 90 */
    {
        nmea_fix_t fix;
        /* checksum computed for this exact sentence */
        const char *rmc = "$GPRMC,084522,A,1046.32,N,10641.40,E,21.6,90.0,141026,,,A";
        char line[128];
        unsigned char cs = 0;
        const char *p;
        for (p = rmc + 1; *p; p++) cs ^= (unsigned char)*p;
        snprintf(line, sizeof(line), "%s*%02X", rmc, cs);
        CHECK(nmea_parse_rmc(line, &fix) == 1 && fix.valid, "rmc valid");
        CHECK(fabs(fix.lat - 10.772) < 1e-4, "rmc lat");
        CHECK(fabs(fix.lon - 106.690) < 1e-4, "rmc lon");
        CHECK(fabs(fix.speed_kmh - 40.0) < 0.5, "rmc speed");
        CHECK(fabs(fix.course_deg - 90.0) < 0.5, "rmc course");
        CHECK(fabs(fix.tod_s - (8 * 3600 + 45 * 60 + 22)) < 0.5, "rmc tod");
        /* bad checksum rejected */
        snprintf(line, sizeof(line), "%s*00", rmc);
        CHECK(nmea_parse_rmc(line, &fix) == 0, "rmc bad checksum rejected");
        /* void fix rejected */
        snprintf(line, sizeof(line), "$GPRMC,084522,V,1046.32,N,10641.40,E,0,0,141026,,,A");
        for (p = line + 1, cs = 0; *p && *p != '*'; p++) cs ^= (unsigned char)*p;
        snprintf(line, sizeof(line), "$GPRMC,084522,V,1046.32,N,10641.40,E,0,0,141026,,,A*%02X", cs);
        CHECK(nmea_parse_rmc(line, &fix) == 0, "rmc void rejected");
    }

    /* warner: 2 signs ahead, 3 to ignore */
    {
        warner_sign_t signs[5];
        warner_t w;
        double state[5];
        warner_alert_t out[8];
        int na;
        double lat = 10.7720, lon = 106.6900, t = 1000.0;
        memset(signs, 0, sizeof(signs));
        /* helper: place sign d meters east */
        #define EAST(d) (106.6900 + (d) / (111320.0 * cos(10.7720 * 3.14159265 / 180.0)))
        signs[0].lat = 10.7720; signs[0].lon = EAST(300);
        strcpy(signs[0].type, "P.127"); strcpy(signs[0].label, "60");
        signs[0].heading_deg = 90;
        signs[1].lat = 10.7720; signs[1].lon = EAST(500);
        strcpy(signs[1].type, "W.207"); strcpy(signs[1].label, "X");
        signs[1].heading_deg = 90;
        signs[2].lat = 10.7720; signs[2].lon = EAST(-100); /* behind */
        strcpy(signs[2].type, "P.127"); signs[2].heading_deg = 90;
        signs[3].lat = 10.7720 - 200 / 111320.0; signs[3].lon = 106.6900; /* south */
        strcpy(signs[3].type, "P.131a"); signs[3].heading_deg = 90;
        signs[4].lat = 10.7720; signs[4].lon = EAST(300); /* opposite dir */
        strcpy(signs[4].type, "P.102"); signs[4].heading_deg = 270;

        warner_init(&w, signs, 5);
        warner_set_state(&w, state);
        na = warner_update(&w, lat, lon, 90.0, 40.0, t, out, 8);
        CHECK(na == 0, "no alert at 300m (lookahead 150m)");
        /* move to 140m before sign0 */
        na = warner_update(&w, 10.7720, EAST(160), 90.0, 40.0, t + 14, out, 8);
        CHECK(na == 1 && out[0].sign_index == 0, "alert sign0 at ~140m");
        CHECK(fabs(out[0].distance_m - 140.0) < 3.0, "distance ~140m");
        /* cooldown: same spot again -> no repeat */
        na = warner_update(&w, 10.7720, EAST(160), 90.0, 40.0, t + 15, out, 8);
        CHECK(na == 0, "cooldown suppresses repeat");
        /* drive on: sign1 alerts, others never do */
        na = warner_update(&w, 10.7720, EAST(360), 90.0, 40.0, t + 200, out, 8);
        CHECK(na == 1 && out[0].sign_index == 1, "alert sign1 later");
    }

    if (fails == 0) printf("ALL TESTS PASSED\n");
    return fails ? 1 : 0;
}
