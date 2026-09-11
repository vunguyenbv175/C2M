/* start.S — freestanding _start for the dynamic stock-ABI build.
 *
 * ABI reference (adapted, not blind-copied): upstream glibc 2.30
 * sysdeps/arm/start.S, non-PIC path. The startup contract it defines:
 *   - on entry a1 holds the loader-provided rtld_fini (how the dynamic
 *     linker arranges DT_FINI for preloaded shared objects);
 *   - sp points at argc, followed by argv/envp;
 *   - __libc_start_main(main, argc, argv, init, fini, rtld_fini, stack_end)
 *     with the last three passed on the stack in that order;
 *   - outermost frame/link cleared (fp/lr = 0);
 *   - 8-byte call-boundary alignment preserved (Tag_ABI align8 24/25).
 *
 * Why freestanding at all: the runner toolchain's default crt1.o references
 * __libc_start_main WITHOUT a version, so the linker binds the DEFAULT node
 * (__libc_start_main@GLIBC_2.34 after the libpthread merge), which the
 * on-device glibc 2.30 rejects. A TU-local .symver cannot rebind another
 * object's reference, hence -nostartfiles + this file, which references the
 * pinned GLIBC_2.4 node from its own object (the ELF gate proves max need).
 *
 * Deliberate deviations from upstream (documented, each gated):
 *   - init/fini = NULL: -nostartfiles excludes __libc_csu_init/fini and our
 *     TU has no constructors/destructors (nothing to run; fini array empty).
 *   - abort fallback kept (upstream does the same) with a 2.4 pin.
 */
    .syntax unified
    /* Tag_ABI_align8_needed/preserved + v7-A/VFPv3-D16/VFP-args, matching the
       measured stock attributes (tools/fw/arm_attributes.py); NO SIMD. */
    .eabi_attribute 24, 1
    .eabi_attribute 25, 1
    .eabi_attribute 6, 10
    .eabi_attribute 7, 65
    .eabi_attribute 8, 1
    .eabi_attribute 9, 2
    .eabi_attribute 10, 4
    .eabi_attribute 28, 1
    .text
    .global _start
    .type _start, %function
_start:
    /* Protect against unhandled exceptions. */
    .fnstart
    /* Clear frame pointer and link register: outermost frame. */
    mov fp, #0
    mov lr, #0

    /* Pop argc off the stack, argv stays at sp. */
    pop {a2}
    mov a3, sp

    /* Push stack_end, then the loader-provided rtld_fini (PRESERVED from a1:
       must be pushed before a1 is reused for main). */
    push {a3}
    push {a1}

    /* init/fini NULL (see header note); a1 now free for main. */
    mov a4, #0
    push {a4}
    ldr a1, =main

    /* __libc_start_main (main, argc, argv, init, fini, rtld_fini, stack_end).
       Stack (ascending): fini, rtld_fini, stack_end. sp is 8-aligned here:
       entry sp0 - 4 (pop) + 12 (3 pushes) = sp0 + 8. */
    bl __libc_start_main

    /* Should never get here. */
    bl abort
    .cantunwind
    .fnend
    .size _start, .-_start

/* Non-executable stack: without this the link warns (no crt object left to
   declare it once -nostartfiles drops the toolchain startup files). */
    .section .note.GNU-stack,"",%progbits

/* Pinned in THIS object so these references bind the 2.30-era nodes. */
    .symver __libc_start_main,__libc_start_main@GLIBC_2.4
    .symver abort,abort@GLIBC_2.4
