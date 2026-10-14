/* Compact offline sign database loader. */
#include "db.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REC_SIZE 100

warner_sign_t *signdb_load(const char *path, int *n_out) {
    FILE *f = fopen(path, "rb");
    unsigned char hdr[12];
    unsigned int n, i;
    unsigned char *rec;
    warner_sign_t *signs;

    *n_out = 0;
    if (!f) return NULL;
    if (fread(hdr, 1, 12, f) != 12 || memcmp(hdr, "C2MSDB01", 8) != 0) {
        fclose(f);
        return NULL;
    }
    n = (unsigned int)hdr[8] | ((unsigned int)hdr[9] << 8) |
        ((unsigned int)hdr[10] << 16) | ((unsigned int)hdr[11] << 24);
    if (n == 0 || n > 100000) { fclose(f); return NULL; }

    signs = (warner_sign_t *)calloc(n, sizeof(warner_sign_t));
    rec = (unsigned char *)malloc(REC_SIZE);
    if (!signs || !rec) { fclose(f); free(signs); free(rec); return NULL; }
    for (i = 0; i < n; i++) {
        float heading;
        if (fread(rec, 1, REC_SIZE, f) != REC_SIZE) break;
        memcpy(&signs[i].lat, rec, 8);
        memcpy(&signs[i].lon, rec + 8, 8);
        memcpy(&heading, rec + 16, 4);
        signs[i].heading_deg = heading;
        memcpy(signs[i].type, rec + 20, WARNER_TYPE_LEN);
        memcpy(signs[i].label, rec + 36, WARNER_LABEL_LEN);
        signs[i].type[WARNER_TYPE_LEN - 1] = '\0';
        signs[i].label[WARNER_LABEL_LEN - 1] = '\0';
    }
    free(rec);
    fclose(f);
    *n_out = (int)i;
    return signs;
}

void signdb_free(warner_sign_t *signs) {
    free(signs);
}
