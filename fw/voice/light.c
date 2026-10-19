/*
 * c2m-light - read-only ambient light estimate from the stock ISP AE engine.
 *
 * Stock cardv already calls MI_ISP_AE_QueryExposureInfo(0, 0, &info) and
 * consumes info+0x230 as "LVx10" (its cardv_detect_FCamAEToPWM path compares
 * that value with 500 and maps LVx10/10 to a backlight level).  This helper
 * reuses only that read-only query; it never changes AE, backlight, screen
 * theme or any stock state.
 *
 * It is a MANUAL hardware-validation tool, not the default boot source.  The
 * boot hook uses the stock display day/night schedule unless the owner has
 * validated this helper and created /customer/c2m/AE_LIGHT_ENABLE.  A second
 * ISP client is intentionally not opened automatically at boot.
 *
 * libmi_isp.so has no DT_NEEDED entries for the vendor support libraries; it
 * expects the executable to have loaded libmi_sys.so, libcam_os_wrapper.so
 * and libcus3a.so into the global symbol scope first.  Load them explicitly so
 * dlopen(libmi_isp.so, RTLD_NOW) can resolve its undefined vendor symbols.
 *
 * Output is one line on stdout:
 *   state=dark lv=-123 samples=5 threshold=500
 *   state=bright lv=812 samples=5 threshold=500
 *
 * No valid sample (missing library, API error, implausible value) prints a
 * diagnostic on stderr, writes nothing on stdout and exits 2.  The boot hook
 * treats that as "fall back to the stock schedule", never as a guessed state.
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define LIGHT_VERSION "c2m-light 0.2.0"
#define INFO_BYTES 0x404u
#define LV_OFFSET 0x230u
#define DEFAULT_THRESHOLD 500
#define DEFAULT_SAMPLES 5
#define DEFAULT_INTERVAL_MS 200
#define MAX_SAMPLES 9
#define MIN_LV (-1000)
#define MAX_LV 100000

typedef int (*query_fn)(int, int, void *);

static int parse_int(const char *text, int minimum, int maximum, int *out) {
    char *end = NULL;
    long value;

    if (text == NULL || *text == '\0') {
        return 1;
    }
    value = strtol(text, &end, 10);
    if (end == text || *end != '\0' || value < minimum || value > maximum) {
        return 1;
    }
    *out = (int)value;
    return 0;
}

static void usage(FILE *stream) {
    fprintf(stream,
            "usage: c2m-light [--threshold N] [--samples N] [--interval-ms N]\n"
            "                 [--lib PATH]\n"
            "       c2m-light --self-test\n"
            "  Emits state=dark|state=bright plus the median LVx10 sample.\n"
            "  Exit 0 with a state, 2 when ambient light is unknown.\n");
}

int main(int argc, char **argv) {
    int threshold = DEFAULT_THRESHOLD;
    int samples = DEFAULT_SAMPLES;
    int interval_ms = DEFAULT_INTERVAL_MS;
    int self_test = 0;
    int i;
    int values[MAX_SAMPLES];
    int count = 0;
    int median;
    const char *state;
    const char *library_name = "libmi_isp.so";
    void *library;
    query_fn query;
    const char *error;

    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--self-test") == 0) {
            self_test = 1;
        } else if (strcmp(argv[i], "--help") == 0) {
            usage(stdout);
            return 0;
        } else if (strcmp(argv[i], "--threshold") == 0 && i + 1 < argc) {
            if (parse_int(argv[++i], 0, MAX_LV, &threshold) != 0) {
                fprintf(stderr, "c2m-light: invalid --threshold\n");
                return 2;
            }
        } else if (strcmp(argv[i], "--samples") == 0 && i + 1 < argc) {
            if (parse_int(argv[++i], 1, MAX_SAMPLES, &samples) != 0) {
                fprintf(stderr, "c2m-light: invalid --samples\n");
                return 2;
            }
        } else if (strcmp(argv[i], "--interval-ms") == 0 && i + 1 < argc) {
            if (parse_int(argv[++i], 0, 5000, &interval_ms) != 0) {
                fprintf(stderr, "c2m-light: invalid --interval-ms\n");
                return 2;
            }
        } else if (strcmp(argv[i], "--lib") == 0 && i + 1 < argc) {
            library_name = argv[++i];
            if (*library_name == '\0') {
                fprintf(stderr, "c2m-light: invalid --lib\n");
                return 2;
            }
        } else {
            fprintf(stderr, "c2m-light: unknown argument: %s\n", argv[i]);
            usage(stderr);
            return 2;
        }
    }

    if (self_test) {
        puts(LIGHT_VERSION);
        return 0;
    }
    if (samples < 1 || samples > MAX_SAMPLES) {
        fprintf(stderr, "c2m-light: invalid sample count\n");
        return 2;
    }

    if (strcmp(library_name, "libmi_isp.so") == 0) {
        static const char *const vendor_deps[] = {
            "libmi_sys.so",
            "libcam_os_wrapper.so",
            "libcus3a.so"
        };
        size_t dep;

        for (dep = 0; dep < sizeof(vendor_deps) / sizeof(vendor_deps[0]); dep++) {
            void *handle = dlopen(vendor_deps[dep], RTLD_NOW | RTLD_GLOBAL);
            if (handle == NULL) {
                error = dlerror();
                fprintf(stderr, "c2m-light: cannot preload %s: %s\n",
                        vendor_deps[dep], error != NULL ? error : "unknown error");
                return 2;
            }
        }
    }

    library = dlopen(library_name, RTLD_NOW | RTLD_GLOBAL);
    if (library == NULL) {
        error = dlerror();
        fprintf(stderr, "c2m-light: cannot open %s: %s\n",
                library_name, error != NULL ? error : "unknown error");
        return 2;
    }
    *(void **)(&query) = dlsym(library, "MI_ISP_AE_QueryExposureInfo");
    if (query == NULL) {
        error = dlerror();
        fprintf(stderr, "c2m-light: MI_ISP_AE_QueryExposureInfo unavailable: %s\n",
                error != NULL ? error : "unknown error");
        dlclose(library);
        return 2;
    }

    for (i = 0; i < samples; i++) {
        unsigned char info[INFO_BYTES];
        int32_t lv;
        int rc;

        memset(info, 0, sizeof(info));
        rc = query(0, 0, info);
        memcpy(&lv, info + LV_OFFSET, sizeof(lv));
        if (rc == 0 && lv >= MIN_LV && lv <= MAX_LV) {
            values[count++] = (int)lv;
        }
        if (i + 1 < samples && interval_ms > 0) {
            struct timespec delay;
            delay.tv_sec = interval_ms / 1000;
            delay.tv_nsec = (long)(interval_ms % 1000) * 1000000L;
            (void)nanosleep(&delay, NULL);
        }
    }
    dlclose(library);

    if (count == 0) {
        fprintf(stderr, "c2m-light: no valid AE exposure sample\n");
        return 2;
    }

    /* Small fixed-size insertion sort; the median rejects a single bad frame. */
    for (i = 1; i < count; i++) {
        int value = values[i];
        int j = i - 1;
        while (j >= 0 && values[j] > value) {
            values[j + 1] = values[j];
            j--;
        }
        values[j + 1] = value;
    }
    median = values[count / 2];
    state = median >= threshold ? "bright" : "dark";
    printf("state=%s lv=%d samples=%d threshold=%d\n",
           state, median, count, threshold);
    return 0;
}
