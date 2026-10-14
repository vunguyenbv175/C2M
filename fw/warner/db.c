/* Strict bounded offline sign database loader. No partial-prefix acceptance. */
#include "db.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define REC_SIZE 100
#define MAX_SIGNS 40000U /* deployment memory bound, not format maximum */

static int utf8_string(const unsigned char *s, size_t size) {
    size_t i = 0;
    while (i < size && s[i]) {
        unsigned char c = s[i++];
        int extra, j;
        unsigned int code, minimum;
        if (c < 0x80) {
            if (c < 0x20 || c == 0x7f) return 0; /* no control/log injection */
            continue;
        }
        if (c >= 0xc2 && c <= 0xdf) { extra = 1; code = c & 0x1f; minimum = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { extra = 2; code = c & 0x0f; minimum = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { extra = 3; code = c & 0x07; minimum = 0x10000; }
        else return 0;
        if (i + (size_t)extra >= size) return 0;
        for (j = 0; j < extra; j++) {
            unsigned char next = s[i++];
            if ((next & 0xc0) != 0x80) return 0;
            code = (code << 6) | (next & 0x3f);
        }
        if (code < minimum || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return 0;
    }
    return i < size && s[i] == 0;
}

warner_sign_t *signdb_load(const char *path, int *n_out) {
    FILE *f;
    unsigned char hdr[12], rec[REC_SIZE];
    unsigned int n, i;
    long size;
    warner_sign_t *signs = NULL;
    const unsigned int endian = 1;
    if (!n_out) return NULL;
    *n_out = 0;
    if (!path || sizeof(double) != 8 || sizeof(float) != 4 ||
        *((const unsigned char *)&endian) != 1) return NULL;
    f = fopen(path, "rb");
    if (!f) return NULL;
    if (fread(hdr, 1, sizeof(hdr), f) != sizeof(hdr) ||
        memcmp(hdr, "C2MSDB01", 8) != 0) goto fail;
    n = (unsigned int)hdr[8] | ((unsigned int)hdr[9] << 8) |
        ((unsigned int)hdr[10] << 16) | ((unsigned int)hdr[11] << 24);
    if (n == 0 || n > MAX_SIGNS) goto fail;
    /* Check exact length before allocation; appended or truncated data fails. */
    if (fseek(f, 0, SEEK_END) || (size = ftell(f)) < 0 ||
        size != 12L + (long)n * REC_SIZE || fseek(f, 12, SEEK_SET)) goto fail;
    signs = (warner_sign_t *)calloc(n, sizeof(warner_sign_t));
    if (!signs) goto fail;
    for (i = 0; i < n; i++) {
        float heading;
        if (fread(rec, 1, REC_SIZE, f) != REC_SIZE) goto fail;
        memcpy(&signs[i].lat, rec, 8);
        memcpy(&signs[i].lon, rec + 8, 8);
        memcpy(&heading, rec + 16, 4);
        if (!isfinite(signs[i].lat) || signs[i].lat < -90 || signs[i].lat > 90 ||
            !isfinite(signs[i].lon) || signs[i].lon < -180 || signs[i].lon > 180 ||
            !isfinite(heading) || (heading != -999 && (heading < 0 || heading > 360))) goto fail;
        if (!utf8_string(rec + 20, WARNER_TYPE_LEN) ||
            !utf8_string(rec + 36, WARNER_LABEL_LEN) || rec[20] == 0) goto fail;
        signs[i].heading_deg = heading == 360 ? 0 : heading;
        memcpy(signs[i].type, rec + 20, WARNER_TYPE_LEN);
        memcpy(signs[i].label, rec + 36, WARNER_LABEL_LEN);
    }
    if (ferror(f) || fgetc(f) != EOF || ferror(f)) goto fail;
    fclose(f);
    *n_out = (int)n;
    return signs;
fail:
    fclose(f);
    free(signs);
    return NULL;
}

void signdb_free(warner_sign_t *signs) {
    free(signs);
}
