# FLASH-READY Sprint 2 — Candidate B tooling (FLASH-READY / NOT YET FLASH-PROVEN)

Golden baseline unchanged: `V2023.08.03.1_C2M_U_FR_WIFI_EN.tar`
(`3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c`).
No hardware claims. Candidate C and product features untouched.

## 1. SYSROOT RESULT (P0 — PROVEN, preferred over Ubuntu-static)

Outcome: a **dynamic stock-ABI binary is feasible and proven in product CI**
— the static binary is kept only as a bring-up fallback.

- `tools/fw/build_sysroot.py` → `docs/firmware/SYSROOT_MANIFEST.json`:
  loader `lib/ld-linux-armhf.so.3` → `ld-2.30.so`
  (`dd2f57c2…`), `libc.so.6` → `libc-2.30.so` (`3b2cc951…`),
  `libm`, `libpthread`, `libgcc_s` hashes recorded; **crt objects and libc
  headers are ABSENT from the firmware** (absence proven by full cpio scan),
  so a literal `--sysroot` link is impossible — documented, not worked around.
- Instead: runner cross toolchain + `fw/device_minimal/glibc_compat.h`
  (`.symver` pins every reachable symbol to GLIBC_2.4 nodes) +
  `fw/device_minimal/start.S` (freestanding `_start`; the toolchain `crt1.o`
  would otherwise bind `__libc_start_main@GLIBC_2.34`, which no TU-local pin
  can rebind — the one subtle point, fixed honestly rather than waived).
- CI `arm-dyn` GREEN: ET_EXEC, interp `/lib/ld-linux-armhf.so.3`,
  NEEDED exactly `[libc.so.6]`, **max GLIBC need `GLIBC_2.4`** (cap 2.30),
  attrs v7-A/VFPv3-D16/VFP-args with **NO Advanced_SIMD tag at all**
  (dynamic links bake in no libc objects — cleaner than static).
- The inherited static-libc SIMD risk is therefore GONE on the preferred
  path (not hidden: static path keeps the TU-proof mechanism + recorded tag).
- Candidate-B payload = the `arm-dyn` binary.

## 2. UBIFS TOOLCHAIN (P1)

- IPs: `tools/fw/ubifs_manifest.py` (full manifest: type/mode/uid/gid/size/
  sha/target/mtime; `--compare` semantic, fail-closed),
  `tools/fw/ubifs_extract_tree.py` (full tree, modes/mtimes/symlinks,
  fallback report), `tools/fw/ubifs_geometry.py` (superblock parse),
  `tools/fw/rebuild_customer.sh` (Linux driver: tool/version record, root +
  no-fallback gates, `mkfs.ubifs`, manifest compare).
- Mature upstream tools only for the write path (`mkfs.ubifs` from mtd-utils,
  versions recorded per run). No invented UBIFS writer.
- Geometry (measured, `docs/firmware/CUSTOMER_GEOMETRY.json`):
  `min_io=2048, leb_size=126976, leb_cnt=313, max_leb=638, compr=lzo,
  fmt=4, fanout=8` with `313*126976 = 0x25E7000` exactly the image size.
  mkfs args: `-m 2048 -e 126976 -c 638 -x lzo`.
- Stock manifest committed: `docs/firmware/CUSTOMER_MANIFEST_EN.json`
  (227 entries: 197 reg, 28 dir, 2 symlinks; uid/gid uniformly 1001).
- Corrected two real extractor bugs found by cross-checking: INO field map
  is +8 vs mainline (vendor layout: size@48, nlink@92, uid@96, gid@100,
  mode@104 — proven on 3+ inodes incl. the 11 MB adas and the `0x41fd` dir
  mode), and the 2 symlinks (`/wifi/*_config.bin` → `/config/*`, target
  inline, `data_len@112`) were previously invisible.

## 3. NO-OP REBUILD EVIDENCE (P1)

- Extraction direction proven locally: manifest + full tree + adas SHA
  (`0dcc6982…`) exact through the new bulk-LZO path.
- The `mkfs.ubifs` EXECUTION needs Linux (dev box has no WSL/Docker/
  mtd-utils — verified absent, not assumed): it runs via
  `tools/fw/rebuild_customer.sh --mode noop` (fail-closed gates) or the
  manual workflow `firmware-candidateB.yml` (apt-pinned tools, TAR gate,
  evidence-only artifacts). No-op acceptance = `manifest --compare` zero
  diffs (ctime/atime/nlink excluded by design — a fresh UBIFS cannot
  preserve them; mtime/mode/uid/gid/content must match).
- NOT claimed as executed: the report states exactly which half is proven
  (extract/manifest/geometry/assemble/compare) and which single step awaits
  Linux (one `mkfs` + compare, fully scripted).

## 4. EXACT CANDIDATE-B SEMANTIC DIFF (P2/P3 design + dry-run proof)

- Mutation (`tools/fw/mutate_customer.py`, base-hash gated, no double-hook):
  ADD `/c2m/c2m-idle` (mode 0755, `arm-dyn` binary) + APPEND one line
  `/customer/c2m/c2m-idle &` at EOF of `/wifi/rcInsDriver.sh`. Nothing else.
- Assembly (`tools/fw/build_candidates.py --customer-b`): new layout keeps
  all pre-customer offsets, shifts misc/oneed by the customer delta,
  regenerates fatload/ubi-write numerics, fresh MD5, raw-header TAR assembly
  (headers differ from golden ONLY in size/chksum — proven by construction).
- Validation: B-contract re-derived → `validate --deep` → `candidate_diff.py`
  allowlist (only customer.es + derived offsets/script/MD5 may differ;
  all other payload SHAs, UNKNOWN tail, cardv/adas PASS required).
- Dry-run on REAL EN data (customer enlarged by 4096 dummy bytes, output
  discarded): `validate_B_deep` = VALID (33 checks), `candidate_diff` =
  ALLOWLIST-OK with exactly fatload lines [8,9,10] (customer/misc/oneed)
  changed. The machinery is proven; only genuine `customer_B.es` is missing.

## 5. PACKAGE HASHES

- A: `EN_REPACK_GOLDEN.tar` = `3a703522…` (byte-identical golden, re-proven
  in the dry-run).
- B: no final hashes yet (awaits the Linux `mkfs` run); recipe + expected
  diff shape above. Nothing fabricated, nothing committed.

## 6. PROTECTED-COMPONENT HASHES (unchanged, enforced)

cardv `344b4a3f…`, adas `0dcc6982…`, kernel `c1fa8f73…`(es),
rootfs `1dcc3e95…`(es) — all re-verified through the fixed extractor;
`candidate_diff` BLOCKS any B build that touches them.

## 7. REMAINING UNKNOWNS

- mkfs.ubifs output LEB packing/size for our tree (bounded: ≤ 80 MB volume;
  layout code handles any size; script regenerates).
- New-file mtimes inside rebuilt customer.es (build-time; INFO-only in
  `verify_b_manifest`, never compared).
- `_start` runtime behaviour (no hardware execution yet — the gate proves
  ABI, not execution).
- Boot-timing of the rcInsDriver hook; watchdog interactions (HW checklist).
- 24 B UNKNOWN tail (still preserved verbatim), outer TAR magic encoding
  (documented), U-Boot MD5 pre-check (unknown as before).

## 8. HARDWARE TEST PROCEDURE

`docs/firmware/FLASH_HW_CHECKLIST.md` (Phase A stock-proof, then Phase B
idle-proof incl. marker file, 5x reboot, kill-daemon, 24 h soak) +
one-command build (`build_candidates.py`, A anywhere / B on Linux).
`firmware-candidateB.yml` produces both images' evidence on demand.

## 9. CI / NEGATIVE TESTS

Product CI stays green and firmware-free: `tests/test_candidate_b.py` proves
synthetically — manifest diffs (content/mode/add/remove), mutate guards
(tampered base, double-hook), `verify_b_manifest` OK + extra-path BLOCK,
allowlist OK + kernel/tail/deep-verdict BLOCKs, inner-assembler overlap
rejection, TAR golden/package round-trips. Local `--strict` green.

## 10. NEXT HIGHEST-VALUE TASK

Run the ready chain on Linux (one `firmware-candidateB.yml` dispatch with
TARs, or `rebuild_customer.sh` + `build_candidates.py` on a bench box) →
flash A → flash B per checklist. Do NOT start Candidate C or features
before a Phase-B PASS.
