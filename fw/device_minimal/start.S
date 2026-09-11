/* start.S — freestanding _start for the dynamic stock-ABI build.
 *
 * Why this exists (evidence, not style): the runner toolchain's default
 * crt1.o references __libc_start_main WITHOUT a version, so the linker binds
 * the DEFAULT node (__libc_start_main@GLIBC_2.34 after the libpthread merge),
 * which the on-device glibc 2.30 cannot satisfy. .symver pins in a C TU
 * cannot rebind another object's reference, so the only honest fix is to
 * drop the toolchain startup files (-nostartfiles) and enter through our
 * own _start, which references the pinned GLIBC_2.4 node (proven by the
 * ELF gate's dyn.glibc row, not by this comment).
 *
 * Contract: argc/argv/envp from the initial stack, init/fini/NULL (our TU
 * has no constructors/destructors), rtld_fini NULL (correct for ET_EXEC;
 * the loader registers _dl_fini itself), stack_end = initial sp.
 */
    .syntax unified
    .text
    .global _start
    .type _start, %function
    /* Self-describing attributes: v7-A / Thumb-2 / VFPv3-D16 / VFP-args,
       NO Advanced SIMD (matches tools/fw/arm_attributes.py stock decode). */
    .eabi_attribute 6, 10
    .eabi_attribute 7, 65
    .eabi_attribute 8, 1
    .eabi_attribute 9, 2
    .eabi_attribute 10, 4
    .eabi_attribute 28, 1
_start:
    mov fp, #0
    mov r4, sp                  /* save stack_end */
    ldr r1, [sp], #4            /* argc, sp now -> argv */
    mov r2, sp                  /* argv */
    ldr r0, =main
    mov r3, #0                  /* init = NULL */
    mov r5, #0
    push {r4}                   /* stack_end */
    push {r5}                   /* rtld_fini = NULL */
    push {r5}                   /* fini = NULL */
    bl __libc_start_main
    bl abort                    /* unreachable; pinned below */
    .size _start, .-_start

    /* Pinned in THIS object so the reference binds the 2.30-era node. */
    .symver __libc_start_main,__libc_start_main@GLIBC_2.4
    .symver abort,abort@GLIBC_2.4
