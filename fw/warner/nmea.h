/* Minimal NMEA RMC parser: $GPRMC/$GNRMC/$BDRMC -> fix, lat, lon, speed, course.
 * Returns 1 on a complete valid fix, 0 otherwise. Checksum is REQUIRED;
 * empty fields, invalid coordinates/time/speed/course fail closed. */
#ifndef NMEA_H
#define NMEA_H

typedef struct {
    int valid;
    double lat;
    double lon;
    double speed_kmh;
    double course_deg;
    double tod_s;   /* UTC seconds since midnight from RMC; -1 if absent */
} nmea_fix_t;

int nmea_parse_rmc(const char *line, nmea_fix_t *out);

#endif
