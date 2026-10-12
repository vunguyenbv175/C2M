/* glibc_compat.h — bind every libc reference of c2m-idle to a symbol version
 * that exists in the EN stock glibc 2.30 baseline (measured: stock cardv max
 * need is GLIBC_2.29; baseline cap enforced by check_elf.py --max-glibc 2.30).
 *
 * Why: the clean-runner cross toolchain ships a NEWER glibc whose default
 * symbol versions (e.g. __libc_start_main@GLIBC_2.34 after the libpthread
 * merge) would exceed the on-device loader. Explicit .symver pins force the
 * linker to bind the OLD version nodes, which still exist in both the
 * link-time libc and the stock 2.30 libc. The ELF gate independently proves
 * max need <= 2.30 — these pins are claims, the gate is the proof.
 *
 * Scope: ONLY the symbols reachable from fw/device_minimal/c2m_idle.c
 * (stdio file ops incl. fortified _chk variants + fopen64, sleep,
 * mkdir/getpid/fread/memset + libgcc soft-div's raise for %//,
 * + C startup). Any new libc call MUST get a pin
 * here first, or the gate fails the build (fail-closed).
 *
 * Deliberately ABSENT (CI-proven 2026-10-12, see toolchain file):
 * - time(): Ubuntu's armhf toolchain redirects it to __time64@GLIBC_2.34
 *   (missing on the 2.30 device -> would crash there, not just fail the
 *   gate). Diag ordering uses uptime + boot counter + card mtimes instead.
 * - stack protector: __stack_chk_guard binds its version node from ld-linux
 *   itself, keeping DT_NEEDED on the loader. Disabled in the dyn toolchain
 *   (-fno-stack-protector); the daemon has no hostile input surface.
 * here first, or the gate fails the build (fail-closed).
 */
#ifndef __ASSEMBLER__
#pragma once

/* C startup is handled by start.S (-nostartfiles): the toolchain's default
 * crt1.o would bind __libc_start_main@GLIBC_2.34, which the 2.30 device
 * loader rejects. start.S references the GLIBC_2.4 node from its own object
 * (the only place .symver can rebind it). This header pins the symbols
 * referenced by c2m_idle.c itself. */
__asm__(".symver printf,printf@GLIBC_2.4");
__asm__(".symver fprintf,fprintf@GLIBC_2.4");
__asm__(".symver fflush,fflush@GLIBC_2.4");
__asm__(".symver fopen,fopen@GLIBC_2.4");
__asm__(".symver fclose,fclose@GLIBC_2.4");
__asm__(".symver sleep,sleep@GLIBC_2.4");
__asm__(".symver fread,fread@GLIBC_2.4");
__asm__(".symver mkdir,mkdir@GLIBC_2.4");
__asm__(".symver getpid,getpid@GLIBC_2.4");
__asm__(".symver memset,memset@GLIBC_2.4");
__asm__(".symver raise,raise@GLIBC_2.4");
/* Ubuntu enables -D_FORTIFY_SOURCE by default: printf/fprintf become the
 * _chk variants and fopen becomes fopen64. Pin the REAL references. */
__asm__(".symver __printf_chk,__printf_chk@GLIBC_2.4");
__asm__(".symver __fprintf_chk,__fprintf_chk@GLIBC_2.4");
__asm__(".symver fopen64,fopen64@GLIBC_2.4");
/* Ubuntu enables -fstack-protector by default; bind its helper old-style. */
__asm__(".symver __stack_chk_fail,__stack_chk_fail@GLIBC_2.4");
#endif /* __ASSEMBLER__ */
