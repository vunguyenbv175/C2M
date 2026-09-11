/* c2m-idle — MINIMAL device binary (Sprint 1 FLASH-READY).
 *
 * Behaviour contract (only):
 *   start -> print version -> best-effort /tmp/c2m_idle.marker -> sleep loop.
 * No network, no M4 transmit, no camera, no ADAS, no config writes.
 * Label: HOST-CROSS-BUILT, NOT device-tested.
 */
#include <stdio.h>
#include <unistd.h>

#ifndef C2M_IDLE_VERSION
#define C2M_IDLE_VERSION "0.1.0-sprint1"
#endif

int main(void) {
    printf("c2m-idle %s\n", C2M_IDLE_VERSION);
    fflush(stdout);
    FILE *f = fopen("/tmp/c2m_idle.marker", "w");
    if (f) {
        fprintf(f, "c2m-idle %s\n", C2M_IDLE_VERSION);
        fclose(f);
    }
    for (;;) {
        sleep(60);
    }
    return 0;
}
