# tools/wifi ARM build — RAM-only `c2m-nlprobe` (diagnostic only)

`build_nlprobe_arm.sh` cross-builds the unmodified
`tools/wifi/c2m_nlprobe.c` for RAM-only stock-userspace execution. It does
not edit production GPS/D4 or `c2m_nlprobe.c`; the compat wrapper is
generated under `--out`.

## Pattern (exact `fw/d4/build.sh` + `fw/d3/build.sh`)

* Generated wrapper with ALL system headers before `fw/d3/compat.h`
  (source `_POSIX`/`_DEFAULT`/`_GNU` duplicates stripped to keep
  `-Werror` clean).
* `arm-linux-gnueabihf-gcc -std=c99 -Os -Wall -Wextra -Werror`
  `-march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard`
  `-D_TIME_BITS=32 -U_FILE_OFFSET_BITS -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0`
  `-fno-stack-protector -fno-pie -I fw/d3`.
* Link `-nostartfiles -no-pie`
  `-Wl,--dynamic-linker=/lib/ld-linux-armhf.so.3`
  `-Wl,--no-undefined -Wl,-z,noexecstack fw/device_minimal/start.S`.
* ELF gate `python3 fw/device_minimal/check_elf.py --allow-dynamic`
  (ARMv7-A hard-float VFPv3-D16, old startup, glibc<=2.30).
* Actual `qemu-arm-static -L SYSROOT` pure `--self-test` and `--help`.
* Fail-closed: `set -eu`, no pipes hiding exit; every capture is
  redirect-or-fail (`> log 2>&1 || { cat log; exit 1; }`).
* Saves logs/versions/hashes.

## Usage (repo root, parent manual workflow)

```sh
sh tools/wifi/build_nlprobe_arm.sh --out /tmp/nlprobe-arm --sysroot work/sysroot
```

Artifacts: `c2m-nlprobe`, `nlprobe-selftest-arm.txt`,
`nlprobe-help-arm.txt`, `objects/c2m-nlprobe.versions.txt`,
`objects/toolchain_version.txt`, `nlprobe_arm_hashes.txt`.

## Host validation (no ARM toolchain needed)

```sh
python3 tools/wifi/test_build_nlprobe_arm.py -v
python3 tools/wifi/test_c2m_nlprobe.py -v
```

Portable `--self-test` only is validated here. Linux compile/QEMU and
stock-loader gates run in parent CI. See `tools/wifi/README.md` for the
delayed on-camera `/tmp`-only procedure (never upload host binaries).
