/* Strict, bounded NMEA RMC parser. Missing/invalid fields fail closed. */
#include "nmea.h"
#include <string.h>
#include <stdlib.h>
#include <math.h>

static int hexval(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static int decimal(const char *s, double *out) {
    const char *p = s;
    char *end;
    int digits = 0, dots = 0;
    if (!s || !*s) return 0;
    while (*p) {
        if (*p >= '0' && *p <= '9') digits++;
        else if (*p == '.' && ++dots == 1) { /* one decimal point */ }
        else return 0;
        p++;
    }
    if (!digits || s[0] == '.' || p[-1] == '.') return 0;
    *out = strtod(s, &end);
    return *end == '\0' && isfinite(*out);
}

static int coordinate(const char *s, int degree_digits, double limit,
                      double *out) {
    int i, deg = 0;
    double minutes;
    if (strlen(s) < (size_t)(degree_digits + 2)) return 0;
    for (i = 0; i < degree_digits; i++) {
        if (s[i] < '0' || s[i] > '9') return 0;
        deg = deg * 10 + s[i] - '0';
    }
    if (s[degree_digits] < '0' || s[degree_digits] > '9' ||
        s[degree_digits + 1] < '0' || s[degree_digits + 1] > '9') return 0;
    if (s[degree_digits + 2] != '\0' && s[degree_digits + 2] != '.') return 0;
    if (!decimal(s + degree_digits, &minutes) || minutes >= 60.0) return 0;
    *out = deg + minutes / 60.0;
    return *out <= limit;
}

int nmea_parse_rmc(const char *line, nmea_fix_t *out) {
    char buf[256], *field[20], *p;
    const char *star;
    size_t length, payload_length, i;
    int nf = 0, hi, lo, hh, mm;
    unsigned char cs = 0;
    double lat, lon, knots, course, seconds;
    if (!out) return 0;
    memset(out, 0, sizeof(*out));
    out->tod_s = -1.0;
    if (!line || line[0] != '$') return 0;
    length = strlen(line);
    if (length >= sizeof(buf) || length < 10) return 0;
    /* Exact talker/type and required delimiter, not arbitrary xxRMC text. */
    if ((memcmp(line + 1, "GP", 2) && memcmp(line + 1, "GN", 2) &&
         memcmp(line + 1, "BD", 2)) || memcmp(line + 3, "RMC,", 4)) return 0;
    star = strchr(line, '*');
    if (!star || strlen(star) != 3) return 0;
    hi = hexval(star[1]); lo = hexval(star[2]);
    if (hi < 0 || lo < 0) return 0;
    for (i = 1; line + i < star; i++) cs ^= (unsigned char)line[i];
    if (cs != (unsigned char)((hi << 4) | lo)) return 0;
    payload_length = (size_t)(star - line);
    memcpy(buf, line, payload_length);
    buf[payload_length] = '\0';
    /* Preserve empty fields. strtok would shift mandatory RMC field indices. */
    field[nf++] = buf;
    for (p = buf; *p; p++) {
        if (*p == ',') {
            *p = '\0';
            if (nf >= (int)(sizeof(field) / sizeof(field[0]))) return 0;
            field[nf++] = p + 1;
        }
    }
    if (nf < 10 || strcmp(field[2], "A") != 0) return 0;
    if (!coordinate(field[3], 2, 90.0, &lat) ||
        !coordinate(field[5], 3, 180.0, &lon)) return 0;
    if (strcmp(field[4], "N") && strcmp(field[4], "S")) return 0;
    if (strcmp(field[6], "E") && strcmp(field[6], "W")) return 0;
    if (!decimal(field[7], &knots) || knots * 1.852 > 300.0 ||
        !decimal(field[8], &course) || course >= 360.0) return 0;
    if (strlen(field[1]) < 6) return 0;
    for (i = 0; i < 6; i++) if (field[1][i] < '0' || field[1][i] > '9') return 0;
    if (field[1][6] != '\0' && field[1][6] != '.') return 0;
    if (!decimal(field[1] + 4, &seconds) || seconds >= 60.0) return 0;
    hh = (field[1][0] - '0') * 10 + field[1][1] - '0';
    mm = (field[1][2] - '0') * 10 + field[1][3] - '0';
    if (hh >= 24 || mm >= 60) return 0;
    /* Reject explicit no-fix mode even when status incorrectly says A. */
    if (nf > 12 && strcmp(field[12], "N") == 0) return 0;
    out->lat = strcmp(field[4], "S") == 0 ? -lat : lat;
    out->lon = strcmp(field[6], "W") == 0 ? -lon : lon;
    out->speed_kmh = knots * 1.852;
    out->course_deg = course;
    out->tod_s = hh * 3600.0 + mm * 60.0 + seconds;
    out->valid = 1;
    return 1;
}
