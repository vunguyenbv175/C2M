/* Minimal NMEA RMC parser. */
#include "nmea.h"
#include <string.h>
#include <stdlib.h>

static int hexval(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static double nmea_to_deg(const char *s) {
    /* ddmm.mmmm (lat) or dddmm.mmmm (lon); sign applied by caller */
    const char *dot = strchr(s, '.');
    int intpart = atoi(s);
    int deg = intpart / 100;
    double minutes = (intpart % 100) + (dot ? atof(dot) : 0.0);
    return deg + minutes / 60.0;
}

int nmea_parse_rmc(const char *line, nmea_fix_t *out) {
    char buf[256], *f[16], *q;
    int nf = 0;
    unsigned char cs = 0;
    const char *p, *star;

    out->valid = 0;
    if (!line || line[0] != '$') return 0;
    /* talker: GP/GN/BD + RMC */
    if (strlen(line) < 6 || memcmp(line + 3, "RMC", 3) != 0) return 0;

    /* verify checksum if present */
    star = strchr(line, '*');
    if (star && strlen(star) >= 3) {
        int hi = hexval(star[1]), lo = hexval(star[2]);
        if (hi < 0 || lo < 0) return 0;
        for (p = line + 1; p < star; p++) cs ^= (unsigned char)*p;
        if (cs != (unsigned char)((hi << 4) | lo)) return 0;
    }

    strncpy(buf, line, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    if ((q = strchr(buf, '*')) != NULL) *q = '\0';
    for (q = strtok(buf, ","); q && nf < 16; q = strtok(NULL, ","))
        f[nf++] = q;
    /* $xRMC,time,status,lat,N/S,lon,E/W,speed_knots,course,date,... */
    if (nf < 9 || f[2][0] != 'A') return 0;   /* status A = valid */

    {
        double lat = nmea_to_deg(f[3]);
        double lon = nmea_to_deg(f[5]);
        if (f[4][0] == 'S') lat = -lat;
        if (f[6][0] == 'W') lon = -lon;
        out->lat = lat;
        out->lon = lon;
        out->speed_kmh = atof(f[7]) * 1.852;
        out->course_deg = atof(f[8]);
        /* RMC field 1: UTC hhmmss.ss */
        out->tod_s = -1.0;
        if (nf > 1 && strlen(f[1]) >= 6) {
            int hh = (f[1][0] - '0') * 10 + (f[1][1] - '0');
            int mm = (f[1][2] - '0') * 10 + (f[1][3] - '0');
            double ss = atof(f[1] + 4);
            if (hh >= 0 && hh < 24 && mm >= 0 && mm < 60 && ss >= 0 && ss < 61)
                out->tod_s = hh * 3600.0 + mm * 60.0 + ss;
        }
        out->valid = 1;
    }
    return 1;
}
