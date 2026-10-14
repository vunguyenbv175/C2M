/* Freestanding third-party startup: honor constructors linked from static
 * libnl. Do not assume a NULL-init glibc2.30 entry will run executable arrays.
 * Called by __libc_start_main AFTER libc startup, BEFORE upstream main. */
typedef void (*init_fn)(int, char **, char **);
extern init_fn __init_array_start[];
extern init_fn __init_array_end[];
void c2m_init_arrays(int argc, char **argv, char **envp) {
    init_fn *p;
    for (p = __init_array_start; p < __init_array_end; ++p)
        (*p)(argc, argv, envp);
}
