/* Native hostile-input regressions; no device access. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "warner.h"
#include "nmea.h"
#include "db.h"

static int failures = 0;
#define CHECK(test) do { if (!(test)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #test); failures++; } } while (0)

static int parse(const char *payload, nmea_fix_t *fix) {
    char line[512];
    unsigned char cs = 0;
    const char *p;
    for (p = payload + 1; *p; p++) cs ^= (unsigned char)*p;
    snprintf(line, sizeof(line), "%s*%02X", payload, cs);
    return nmea_parse_rmc(line, fix);
}

static void parser_tests(void) {
    nmea_fix_t fix;
    const char *bad[] = {
        "$GPRMC,084522,A,1046.32,N,10641.40,E,,90.0,141026,,,A",
        "$GPRMC,084522,A,1046.32,N,10641.40,E,21.6,,141026,,,A",
        "$GPRMC,084522,A,1046.32,X,10641.40,E,21.6,90.0,141026,,,A",
        "$GPRMC,084522,A,1060.32,N,10641.40,E,21.6,90.0,141026,,,A",
        "$GPRMC,084522,A,9046.32,N,10641.40,E,21.6,90.0,141026,,,A",
        "$GPRMC,084522,A,1046.32,N,18141.40,E,21.6,90.0,141026,,,A",
        "$GPRMC,084522,A,1046.32,N,10641.40,E,nan,90.0,141026,,,A",
        "$GPRMC,084522,A,1046.32,N,10641.40,E,21.6,inf,141026,,,A",
        "$GPRMC,084522,A,1046.32,N,10641.40,E,-1,90.0,141026,,,A",
        "$GPRMC,084522,A,1046.32,N,10641.40,E,21.6,360,141026,,,A",
        "$GPRMC,246000,A,1046.32,N,10641.40,E,21.6,90.0,141026,,,A",
        "$GPRMC,0845000,A,1046.32,N,10641.40,E,21.6,90.0,141026,,,A",
        "$GPRMC,084522,A,1046.32,N,10641.40,E,21.6,90.0,141026,,,N",
        "$ZZRMC,084522,A,1046.32,N,10641.40,E,21.6,90.0,141026,,,A"
    };
    size_t i;
    CHECK(parse("$GNRMC,084522,A,1046.32,N,10641.40,E,21.6,90.0,141026,,,A", &fix));
    CHECK(fix.valid && fabs(fix.speed_kmh - 40) < 0.5);
    for (i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) { CHECK(!parse(bad[i], &fix)); CHECK(!fix.valid); }
    CHECK(!nmea_parse_rmc("$GPRMC,084522,A,1046.32,N,10641.40,E,21.6,90.0,141026,,,A", &fix));
    CHECK(!nmea_parse_rmc("$GPRMC,084522,A*", &fix));
    CHECK(!nmea_parse_rmc("$GPRMC,084522,A*0", &fix));
    CHECK(!nmea_parse_rmc(NULL, &fix));
    CHECK(!nmea_parse_rmc("$GPRMC", NULL));
}

static void matcher_tests(void) {
    warner_t w;
    warner_sign_t signs[17];
    warner_alert_t out[16];
    double state[17];
    int i, n;
    memset(signs, 0, sizeof(signs));
    for (i = 0; i < 17; i++) {
        signs[i].lat = 10;
        signs[i].lon = 106 + (i == 16 ? 5 : 100) / (111320.0 * cos(10 * 3.141592653589793 / 180));
        signs[i].heading_deg = 90;
    }
    warner_init(&w, signs, 17); warner_set_state(&w, state);
    n = warner_update(&w, 10, 106, 90, 40, 1, out, 16);
    CHECK(n == 16 && out[0].sign_index == 16);
    CHECK(state[15] == -1); /* omitted sign did not consume cooldown */
    CHECK(warner_update(&w, 10, 106, 90, 0, 200, out, 16) == 0);
    CHECK(warner_update(&w, 10, 106, INFINITY, 40, 200, out, 16) == 0);
    CHECK(warner_update(&w, NAN, 106, 90, 40, 200, out, 16) == 0);
    CHECK(isnan(warner_angle_diff(INFINITY, 90)));
    CHECK(isnan(warner_angle_diff(1e300, 90)));
    CHECK(warner_update(NULL, 10, 106, 90, 40, 200, out, 16) == 0);
    warner_set_state(&w, NULL);
    for (i = 0; i < 17; i++) signs[i].heading_deg = -999;
    CHECK(warner_update(&w, 10, 106, 90, 40, 200, out, 16) == 0);
}

static void write_database(const char *path, unsigned declared, int count, double latitude, int trailing) {
    unsigned char header[12] = {'C','2','M','S','D','B','0','1',0,0,0,0};
    unsigned char record[100] = {0};
    double longitude = 106;
    float heading = 360;
    FILE *f;
    int i;
    header[8] = (unsigned char)declared;
    header[9] = (unsigned char)(declared >> 8);
    header[10] = (unsigned char)(declared >> 16);
    header[11] = (unsigned char)(declared >> 24);
    memcpy(record, &latitude, 8); memcpy(record + 8, &longitude, 8); memcpy(record + 16, &heading, 4);
    memcpy(record + 20, "P.127", 6); memcpy(record + 36, "60", 3);
    f = fopen(path, "wb"); CHECK(f != NULL); if (!f) return;
    fwrite(header, 1, 12, f);
    for (i = 0; i < count; i++) fwrite(record, 1, 100, f);
    if (trailing) fputc(1, f);
    fclose(f);
}

static void db_tests(const char *path) {
    warner_sign_t *signs;
    int n;
    write_database(path, 1, 1, 10, 0);
    signs = signdb_load(path, &n); CHECK(signs && n == 1);
    if (signs) CHECK(signs[0].heading_deg == 0);
    signdb_free(signs);
    write_database(path, 2, 1, 10, 0); signs = signdb_load(path, &n); CHECK(!signs && n == 0); signdb_free(signs);
    write_database(path, 1, 1, NAN, 0); signs = signdb_load(path, &n); CHECK(!signs && n == 0); signdb_free(signs);
    write_database(path, 1, 1, 10, 1); signs = signdb_load(path, &n); CHECK(!signs && n == 0); signdb_free(signs);
    write_database(path, 40001, 0, 10, 0); signs = signdb_load(path, &n); CHECK(!signs && n == 0); signdb_free(signs);
    CHECK(!signdb_load(path, NULL));
    remove(path);
}

int main(int argc, char **argv) {
    parser_tests(); matcher_tests();
    if (argc != 2) { fprintf(stderr, "provide private temporary DB path\n"); return 2; }
    db_tests(argv[1]);
    if (!failures) printf("warner guards: PASS\n");
    return failures ? 1 : 0;
}
