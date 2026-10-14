#ifndef C2M_D3_COMPAT_H
#define C2M_D3_COMPAT_H
/* Included after system headers by build.sh. ARM32 stat() exported directly
 * by new libc is GLIBC_2.33; stock 2.30 exposes its versioned xstat ABI.
 * We use time32/off32 explicitly and independently gate all final imports.
 * __clock_gettime64 etc must never silently reach the stock loader. */
#if defined(__arm__) && defined(__GLIBC__)
#include <sys/stat.h>
#include <sys/types.h>
#include <stdlib.h>
/* glibc 2.38 C23 redirects. Our numeric inputs use explicit decimal/hex,
 * not C23 0b prefixes; bind the same integer conversions available on 2.30. */
__asm__(".symver __isoc23_strtol,strtol@GLIBC_2.4");
__asm__(".symver __isoc23_strtoul,strtoul@GLIBC_2.4");
__asm__(".symver __isoc23_strtoll,strtoll@GLIBC_2.4");
__asm__(".symver __isoc23_strtoull,strtoull@GLIBC_2.4");
__asm__(".symver __isoc23_sscanf,__isoc99_sscanf@GLIBC_2.7");
__asm__(".symver __isoc23_fscanf,__isoc99_fscanf@GLIBC_2.7");
__asm__(".symver __isoc23_scanf,__isoc99_scanf@GLIBC_2.7");
extern int __xstat(int, const char *, struct stat *);
extern int __lxstat(int, const char *, struct stat *);
extern int __fxstat(int, int, struct stat *);
extern int __fxstatat(int, int, const char *, struct stat *, int);
__asm__(".symver __xstat,__xstat@GLIBC_2.4");
__asm__(".symver __lxstat,__lxstat@GLIBC_2.4");
__asm__(".symver __fxstat,__fxstat@GLIBC_2.4");
__asm__(".symver __fxstatat,__fxstatat@GLIBC_2.4");
static inline int c2m_stat(const char *p, struct stat *s) { return __xstat(3, p, s); }
static inline int c2m_lstat(const char *p, struct stat *s) { return __lxstat(3, p, s); }
static inline int c2m_fstat(int f, struct stat *s) { return __fxstat(3, f, s); }
static inline int c2m_fstatat(int f, const char *p, struct stat *s, int flags) { return __fxstatat(3, f, p, s, flags); }
#define stat(...) c2m_stat(__VA_ARGS__)
#define lstat(...) c2m_lstat(__VA_ARGS__)
#define fstat(...) c2m_fstat(__VA_ARGS__)
#define fstatat(...) c2m_fstatat(__VA_ARGS__)
__asm__(".symver clock_gettime,clock_gettime@GLIBC_2.17");
#endif
#endif
