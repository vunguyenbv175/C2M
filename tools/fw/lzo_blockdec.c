/* lzo1x-block decompressor helper for C2M UBIFS extraction (repo template;
 * NOT GPL itself — but it must be compiled together with upstream minilzo.c,
 * which is GPL-licensed; minilzo sources are downloaded at tool time, never
 * vendored in this repo).
 *
 * Build: gcc -O2 -o build/lzo_blockdec[.exe] tools/fw/lzo_blockdec.c <minilzo.c>
 *        -I <minilzo-dir> -I <lzo-include>/lzo
 * Protocol: reads blocks from stdin: [u32 le comp_len][u32 le out_len][comp_len bytes]...
 * writes raw decompressed bytes to stdout. Exits nonzero on any failure.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#include "minilzo.h"

static int read_all(uint8_t *b, size_t n) {
    size_t got = 0;
    while (got < n) {
        size_t r = fread(b + got, 1, n - got, stdin);
        if (r == 0) return (got == 0 && n > 0 && feof(stdin)) ? 1 : -1;
        got += r;
    }
    return 0;
}

int main(void) {
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    if (lzo_init() != LZO_E_OK) {
        fprintf(stderr, "lzo_init failed\n");
        return 1;
    }
    for (;;) {
        uint8_t hdr[8];
        int rc = read_all(hdr, 8);
        if (rc == 1) return 0; /* clean EOF */
        if (rc != 0) {
            fprintf(stderr, "short header\n");
            return 1;
        }
        uint32_t clen = (uint32_t)hdr[0] | ((uint32_t)hdr[1] << 8) |
                        ((uint32_t)hdr[2] << 16) | ((uint32_t)hdr[3] << 24);
        uint32_t olen = (uint32_t)hdr[4] | ((uint32_t)hdr[5] << 8) |
                        ((uint32_t)hdr[6] << 16) | ((uint32_t)hdr[7] << 24);
        if (clen > (1u << 24) || olen > (1u << 24)) {
            fprintf(stderr, "insane lens\n");
            return 1;
        }
        uint8_t *in = (uint8_t *)malloc(clen ? clen : 1);
        uint8_t *out = (uint8_t *)malloc(olen ? olen : 1);
        if (!in || !out) {
            fprintf(stderr, "oom\n");
            return 1;
        }
        if (read_all(in, clen) != 0) {
            fprintf(stderr, "short body\n");
            return 1;
        }
        lzo_uint out_len = olen;
        int r = lzo1x_decompress_safe(in, clen, out, &out_len, NULL);
        if (r != LZO_E_OK || out_len != olen) {
            fprintf(stderr, "decompress failed r=%d %u!=%u\n", r,
                    (unsigned)out_len, (unsigned)olen);
            return 1;
        }
        if (olen && fwrite(out, 1, olen, stdout) != olen) {
            fprintf(stderr, "write failed\n");
            return 1;
        }
        free(in);
        free(out);
    }
}
