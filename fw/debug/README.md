# fw/debug debug bundle build note

Scope: full debug bundle build-only: `dropbear`, `dropbearkey`,
`c2m-debug` (supervisor), `debug_boot.sh` + reports/objects in `--out DIR`.
No exact deploy; parent deploys to `/customer/c2m` separately.

Default D4 SSH supervisor lifetime is **120 minutes (7200 seconds) from serve start**.
D5-VI uses the separate `build_dropbear.sh --lifetime` edition: `window_sec=0`,
`lifetime=boot`, no listener deadline. AP-loss/signal/child-exit still stops the
owned listener, without automatic restart. The600s idle-session bound remains.
This is a compile-time policy (`C2M_DEBUG_WINDOW_SEC`), not a production CLI
extension. AP-only bind, owner Ed25519 key, AP-loss shutdown and automatic
expiry remain enforced. The existing camera runs its old 20-minute binary until
a separately gated updated binary/package is deployed; repo changes alone do
not extend a live session.
Run this script after the D4 build; parent assembles all assets.

Root-only: supervisor serves root only; Dropbear is compiled
`DROPBEAR_SVR_MULTIUSER=1` plus the reviewed same-UID source patch so only the server UID (root) can authenticate.

## Pin

- `dropbear-2026.94`
- `https://matt.ucc.asn.au/dropbear/releases/dropbear-2026.94.tar.bz2`
- `sha256 e098034a843699200c8c977a991fff73159735bf795d5f72ef672c41a6b1ae81`
- Script verifies hash before extract. Public upstream only.

Purpose: replace stock OpenSSH 5.6p1 (ancient) for fast WiFi debug on own
abandoned camera. After one flash, RAM upload/run via laptop ssh.

## ABI method

Proven `fw/d3/build_supplicant.sh` pattern for upstream:

- `-include compat_prefix.h` with `_GNU_SOURCE`, `sys/stat.h`,
  `sys/types.h`, `time.h` before `fw/d3/compat.h`.
- `CFLAGS`: `-Os -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard`
  `-fno-stack-protector -fno-pie -D_TIME_BITS=32 -U_FILE_OFFSET_BITS`
  `-D_FORTIFY_SOURCE=0`.
- Custom `_start` copied from `fw/device_minimal/start.S` with
  `c2m_init_arrays` hook; `fw/d3/init_arrays.c` linked in.
- `LDFLAGS`: `-nostartfiles -no-pie start.o init_arrays.o`
  `-Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3 -Wl,-z,noexecstack`.
- Avoids `GLIBC_2.34` startup (`__libc_start_main` pinned `GLIBC_2.4`
  in own object).

Supervisor (own TU) uses the `fw/d4/build.sh` wrapper pattern instead:

- Generated `$out/objects/supervisor_compat.c`: strip the static
  `#define _POSIX_C_SOURCE` / `#define _DEFAULT_SOURCE` / `#define
  _GNU_SOURCE` lines from `fw/debug/supervisor.c`, then prepend
  `_POSIX_C_SOURCE` + `_DEFAULT_SOURCE` + `_GNU_SOURCE` and all libc
  headers actually used (`arpa/inet.h`, `ctype.h`, `errno.h`, `fcntl.h`,
  `inttypes.h`, `limits.h`, `net/if.h`, `netinet/in.h`, `poll.h`, `pwd.h`,
  `signal.h`, `stdint.h`, `stdio.h`, `stdlib.h`, `string.h`, `sys/file.h`,
  `sys/ioctl.h`, `sys/socket.h`, `sys/stat.h`, `sys/types.h`,
  `sys/wait.h`, `time.h`, `unistd.h`, plus `linux/wireless.h` under
  `__linux__`) BEFORE `#include "compat.h"` (`-I fw/d3 -I fw/debug`).
- Compile `-std=c99 -Os -Wall -Wextra -Werror` with the same arch /
  `_TIME_BITS=32` / no-protector / no-pie flags. `_TIME_BITS` 32-bit time
  symbols (`clock_gettime` etc.) are pinned old-style by `compat.h`; the
  ELF gate proves max need.
- Link `fw/device_minimal/start.S` + `supervisor.o` with `-nostartfiles
  -no-pie --dynamic-linker=/lib/ld-linux-armhf.so.3 --no-undefined
  -z,noexecstack` (no `init_arrays.o`: own code has no static-archive
  constructors; no `-lm`: no math use).

## Configure (proven only)

Script greps `./configure --help` and uses only found options:

- Required: `--host=arm-linux-gnueabihf --disable-harden --disable-zlib`
  `--enable-bundled-libtom`.
- Optional if present: `--disable-shadow` (keep syslog compiled so `-E` is accepted).
  `--disable-lastlog --disable-utmp --disable-utmpx --disable-wtmp`
  `--disable-wtmpx --disable-loginfunc --disable-pututline`
  `--disable-pututxline --disable-openpty`.
- `LTM_CFLAGS` carries arch/prefix plus absolute `-I$src -I$src/src` and
  `-DLOCALOPTIONS_H_EXISTS`, so bundled math code includes the same
  password-disabled local policy even though its sub-make ignores `CPPFLAGS`;
  script fails if `libtommath/Makefile` lacks
  `armv7-a`/`compat_prefix`/`$src/src`. The absolute src include is required
  because bundled `libtommath` builds inside `libtommath/` with only
  `LTM_CFLAGS` (its `%.o` rule ignores `CPPFLAGS`) while upstream
  `tommath_class.h` tails `#include "dbmalloc.h"` from Dropbear `src/`
  (CI r38738994826 failed at `bn_cutoffs.o` without it). Those dirs hold only
  Dropbear headers, no stock libc override.
- `make` log must show `compat_prefix` for both `libtommath` and
  `libtomcrypt`, else fail.
- `ac_cv_func_crypt=no ac_cv_lib_crypt_crypt=no`: no host `-lcrypt`
  (password auth compiled out).

## localoptions.h (official defines only)

Off: `SVR_PASSWORD_AUTH`, `SVR_PAM_AUTH`, `SVR_SHADOW_AUTH`,
`CLI_PASSWORD_AUTH`, `SVR/CLI_AGENTFWD`, `X11FWD`,
`SVR/CLI_LOCALTCPFWD`, `SVR/CLI_REMOTETCPFWD`,
`SVR_LOCALSTREAMFWD`, `SVR_REMOTESTREAMFWD`,
`CLI_PROXYCMD`, `CLI_NETCAT`, `SFTPSERVER`, `CLI_COMPRESSION`.

On: `SVR_PUBKEY_AUTH`, `ED25519`, `ECDSA`, `ECDH`, `CURVE25519`,
`CHACHA20POLY1305`, `AES128/256`, `SHA2_256_HMAC`, `DH_GROUP14_SHA256`.

Root-only: keep `SVR_MULTIUSER 1` (normal Linux kernel support), then apply
`tools/fw/patch_debug_dropbear.py`. Its one-line restriction removes root's
permission to authenticate as other UIDs; account, shell, key/signature and
privilege-dropping checks remain intact. Without it, root-run `-D <run dir>`
could authorize the owner key for other accounts. `SVR_DROP_PRIVS` remains on.
A valid root passwd entry/shell is still required (read-only, never modified).

No auth bypass, no default keys. The same patch also permits just the exact
`/tmp` ancestor layouts checked by the supervisor: root-owned sticky `/tmp`,
or stock EN `0775 1001:1001`. The private root-owned0700 debug directory,
key file and all other path components retain upstream permission checks.
The vendor UID trust is an existing firmware assumption, not a new hardened
multi-user security boundary; no global chmod changes are made.

The firmware pipeline additionally copies the exact stock glibc2.30
`libnss_files.so.2` (361400 bytes, SHA-256
`381a2aa8348259f1722aa09a90c4345a4460a94350d60b1df6782b3dc23ebffd`)
to `/customer/c2m` as0644. The rootfs alone lacks an NSS module for normal
account lookups. Only the fixed loader path `/customer/c2m:/lib` is used;
no stock library, passwd or shadow edits and no custom account parser.

Build: `make PROGRAMS='dropbear dropbearkey'`.

## Compiled macro proof (before make)

`config.h` holds only configure probes; Dropbear option values never land
there. The script builds `default_options_guard.h`, then runs the real
preprocessor over the official header chain:

```sh
arm-linux-gnueabihf-gcc -dM -E -DLOCALOPTIONS_H_EXISTS -I. -Isrc $flags \
    -x c macro_probe.c  # macro_probe.c contains: #include "options.h"
```

`options.h` pulls `config.h`, `localoptions.h`, and the post-default
computed values, so `-dM` output is what the compiler will see. The script
records sanitized snapshots (`reports/dropbear-macros-full.txt`,
`reports/dropbear-macros.txt` = `DROPBEAR_*` lines only) and asserts:

- `0`: `SVR_PASSWORD_AUTH`, `SVR_PAM_AUTH`,
  `SVR/CLI_AGENTFWD`, `X11FWD`, `SVR/CLI_LOCALTCPFWD`,
  `SVR/CLI_REMOTETCPFWD`, `SVR_LOCALSTREAMFWD`, `SVR_REMOTESTREAMFWD`,
  `CLI_PROXYCMD`, `CLI_NETCAT`, `SFTPSERVER`;
- `1`: `SVR_PUBKEY_AUTH`, `SVR_MULTIUSER`, `ED25519`, `CHACHA20POLY1305`;
- negative controls reject `SVR_PASSWORD_AUTH 1`, `SVR_PAM_AUTH 1`,
  `SVR_MULTIUSER 0` is rejected; source gate requires `C2M_DEBUG_SAME_UID_ONLY`.

Any mismatch fails the build before `make`. Password-roundtrip rejection
on live targets is covered separately by parent CI native tests.

## Fail-closed logging

`#!/bin/sh` + `set -eu`, no `cmd | tee` pipes anywhere: under `set -e`
a pipeline returns only the last command's status, hiding configure/make/
gate/QEMU failures. Every capture is `> report 2>&1 || { cat report;
exit 1; }` followed by `cat report`. `make` additionally requires both
target files to exist, and the CFLAGS check is a pipe-free `awk` scan
(every cross-compile line must carry `compat_prefix`).

QEMU exit policy (rc recorded next to each log): `dropbear -V` must exit
0 and print `2026.94`; `dropbear -h` must exit 0 or 1 and list `-D`
plus `-l`; `dropbearkey -h` must exit 0 (successful help);
keygen/`-y`/`--self-test` must exit 0. No `|| true` suppression.

## Random

Default Dropbear randomness kept (no `SIMPLERANDOM` override):
`getrandom()` is `GLIBC_2.25`, inside the stock 2.30 baseline. The script
records `config.h` random lines to `reports/config-random.txt`; the ELF
gate caps max `GLIBC_*` need at 2.30.

## Outputs (`--out DIR`)

- `dropbear`, `dropbearkey`, `c2m-debug`, `debug_boot.sh` (755).
- `dropbear.LICENSE`/`COPYING`, `dropbear_SOURCE.json`,
  `dropbear.sha256` (dropbear pair), `debug.sha256` (supervisor pair).
- `reports/`: `configure-help.txt`, `configure-opts.txt`,
  `configure.log`, `config-random.txt`, `guard.log`,
  `dropbear-macros-full.txt`, `dropbear-macros-err.txt`,
  `dropbear-macros.txt`, `build.log`, `prefix-check.txt`,
  `dropbear-dynsyms.txt`, `dropbearkey-dynsyms.txt`,
  `c2m-debug-dynsyms.txt`, `dropbear-glibc.txt`,
  `check_elf-*.txt`, `dropbear-V.txt`, `dropbear-h.txt`,
  `dropbear-h-rc.txt`, `dropbearkey-h.txt`, `dropbearkey-h-rc.txt`,
  `dropbearkey-gen.txt`, `dropbearkey-y.txt`, `c2m-debug-glibc.txt`,
  `check_elf-c2m-debug.txt`, `c2m-debug-selftest.txt`.
- `objects/`: `start.o`, `init_arrays.o`, `compat_prefix.h`,
  `localoptions.h`, `supervisor_compat.c`, `supervisor.o`,
  `*.versions.txt`.

`debug_boot.sh` is copied verbatim from `fw/debug/debug_boot.sh`.

## Proofs

- `readelf --dyn-syms | grep GLIBC_` sorted, logged (all three binaries).
- `fw/device_minimal/check_elf.py --allow-dynamic` on all three binaries
  (default allow: `libc.so.6`, `libm.so.6`, `libgcc_s.so.1`; max 2.30).
- QEMU stock sysroot (`--sysroot ROOT`, needs
  `$ROOT/lib/ld-linux-armhf.so.3`):
  `dropbear -V` exits 0 and contains `2026.94`; `dropbear -h` exits 0/1
  and contains `-D` (authorized_keys dir, 2025.89+) and `-l` (bind device,
  e.g. `wlan0`); `dropbearkey -h` exits 0 (successful help);
  `dropbearkey -t ed25519 -f tmp` then `-f tmp -y` yields `ssh-ed25519`;
  `c2m-debug --self-test` exits 0 and prints `PASS ...` /
  `c2m-debug self-test: OK` (pure, no I/O fixtures, no `--serve` in build).
- Smoke keys stay in `work/dropbear-upstream/smoke-keys`, never in `--out`.
- Host `test_debug_supervisor` (fixtures/loopback) is finished by the
  server agent, not this build script.

## Usage

Run from repo root:

```sh
sh fw/debug/build_dropbear.sh --out DIR --sysroot STOCK_ROOTFS
```

Host tools allowed: `curl`, cross `arm-linux-gnueabihf-*`, `qemu-arm-static`,
`python3`, `make`. No camera needed. No commit/push by this script.
