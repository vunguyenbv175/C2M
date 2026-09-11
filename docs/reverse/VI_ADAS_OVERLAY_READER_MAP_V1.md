# VI ADAS Overlay Reader Map + License / Custom-State V1

**Mode:** static, read-only. No firmware modification, no flash.
**Inputs:** `build/fw_bin_en/adas` (`0dcc6982…`), `build/fw_bin_vi/adas` (`997b71c2…`),
`build/fw_bin_en/cardv` / `build/fw_bin_vi/cardv` (hashes per upstream report).
**Tool limits:** Windows, no `readelf`/`llvm-objdump`/ARM `objdump`; `capstone` 5.0.7 only.
All counts/offsets are pure-Python byte-exact. `READER` attribution below the string
layer (exact BL xref) is marked UNKNOWN where it needs disassembly; string-layer
presence/count is CONFIRMED. Prior `BITANSWER_LICENSE_PATH_V1.md`,
`ADAS_OVERLAY_STRUCTURE_V1.md`, `ADAS_INTERSTITIAL_GAPS_V1.md`,
`VI_ADAS_PACKAGE_METADATA_V2.md` are cited, not redone.

## 1. Verdicts

```text
OVERLAY_METADATA: PARTIAL (model blobs + flag tail have CONFIRMED readers;
7 interstitial gaps: NO_READER_FOUND — downgraded)
LICENSE_STATE: INPUT_DEPENDENT (implementation STATICALLY_SAME on compared paths;
identical code can diverge on release-specific/device-specific inputs — concrete
dependencies listed in section 4)
```

## 2. Overlay geometry (re-verified this run)

`tools/fw/elf_overlay_report.py` (pure-Python, NOBITS-excluded):

```text
EN: file 11636008, overlay_start 0x172b1c, overlay_size 10117644, sha c395db15…
VI: file 11653870, overlay_start 0x172b1c, overlay_size 10135506, sha 6becae4d…
VI-EN = +17862 = sum(7 gap deltas) — re-confirmed
tail: 3602 B packaged flags, 121/121 keys, only m0 differs (see compat report)
entropy ~7.9767 both (prior; not recomputed here — cite ADAS_OVERLAY_STRUCTURE_V1)
```

Gap deltas (prior, cited): `+1312/+4514/+9350/-1974/+1084/+1220/+2356 = +17862`.

## 3. Reader search method

Searched both `adas` binaries for interstitial/overlay reader vocabulary:

```text
/proc/self/exe, mmap, munmap, mprotect, lseek, pread, pwrite,
open, fopen, fread, readlink, AES, Decrypt, FLAGS_m0, GetKey, UpdateFromEnv,
DecryptNum, Bit_* , SetCustomInfo, GetPlatformUuidStr, .bitanswer.volume,
model_root_dir, license_root_path, switch_file/calib_file/produce_file
```

plus `cardv` for confinement (`/proc/self/exe/AES/BitAnswer` should be 0 in cardv
if validation is adas-side). Tool: `lastmile_scan.py` (byte-exact).

## 4. Overlay read map

`OFFSET` = representative string offset (not the overlay data offset itself — data offsets
are in `EVIDENCE_ADAS_GAP_GEOMETRY.json`, cited). `READER` = owning subsystem at string
layer; exact BL xref needs `llvm-objdump` → UNKNOWN. `PURPOSE` = proven vs hypothesized.
Ranges with no reader are downgraded at the bottom.

| OVERLAY RANGE (data) | EN size → VI size | READER (string layer) | PURPOSE | DIFFERENCE EN/VI | Confidence |
|---|---|---|---|---|---|
| `d0` model blob | identical size+sha (prior) | `FLAGS_m0 @ 0x25622 both` → `GetKey @ 0x25aa4,0x44415 both` → `UpdateFromEnv @ 0x27997` → `DecryptNum @ 0x3a879` → `AES x40 / Decrypt x10` (all counts SAME) | model directory + AES-128 decrypt + slice | none (blobs byte-identical, `m0` self-consistent) | READER_CONFIRMED (prior + string SAME) |
| `v_a` model blob | identical | same as above | same | none | READER_CONFIRMED |
| `v_t` model blob | identical | same as above | same | none | READER_CONFIRMED |
| `p_r` model blob | identical | same as above | same | none | READER_CONFIRMED |
| `road` model blob | identical | same as above | same | none | READER_CONFIRMED |
| `tl` model blob | identical | same as above | same | none | READER_CONFIRMED |
| 3602 B flag tail `@ EN 0xb17f16 / VI 0xb1c4dc` | 121 keys both, only `m0` value differs | `FLAGS_switch_file/calib_file/produce_file/license_root_path` + `cliargs.cpp` descriptors `@ 0x157fxx` + `license_service.cpp` `@ 0x1619d8/0x161970` | gflags defaults (`--switch_file=…/adas_de.flag` etc., contexts identical per `ctx_scan.py`) | `+0x45c6` shift only | READER_CONFIRMED |
| gap0 `ELF-end→d0` +1312 | 7394 → 8706 | none found | hypothesized protection/package metadata — NO PROOF | size only | NO_READER_FOUND → DOWNGRADED |
| gap1 `d0→v_a` +4514 | 16790 → 21304 | none found | same | size only | NO_READER_FOUND → DOWNGRADED |
| gap2 `v_a→v_t` +9350 | 7624 → 16974 | none found | same | size only | NO_READER_FOUND → DOWNGRADED |
| gap3 `v_t→p_r` −1974 | 17384 → 15410 | none found | same (only shrinking gap) | size only | NO_READER_FOUND → DOWNGRADED |
| gap4 `p_r→road` +1084 | 14532 → 15616 | none found | same | size only | NO_READER_FOUND → DOWNGRADED |
| gap5 `road→tl` +1220 | 20660 → 21880 | none found | same | size only | NO_READER_FOUND → DOWNGRADED |
| gap6 `tl→flags` +2356 | 6746 → 9102 | none found | same | size only | NO_READER_FOUND → DOWNGRADED |

Supporting string evidence (this run, byte-exact):

```text
adas /proc/self/exe: EN 1 @ 0x161b9c / VI 1 @ 0x161b34 (SAME count, -0x68 string shift)
adas .bitanswer.volume: EN 1 @ 0x161fc8 / VI 1 @ 0x161f60 (SAME)
adas mmap/munmap/mprotect/pread/pwrite: 0/0 both (no direct mapping vocabulary)
adas lseek: 1 @ 0x2339d both (SAME .text offset — not a new VI reader)
adas open/fopen/fread/readlink: 29/1/2/1 both (SAME)
adas AES 40 / Decrypt 10 / FLAGS_m0 1 @ 0x25622 / GetKey 2 / UpdateFromEnv 1 /
  DecryptNum 1 / CheckOutSn 3 / CheckOutFeatures 2 / Bit_Login 2 / Bit_ReadFeature 1 /
  Bit_SetRootPath 1 / SetCustomInfo 2 / GetPlatformUuidStr 1 — ALL SAME counts,
  .text offsets identical (e.g. FLAGS_m0 0x25622 both, GetKey 0x25aa4 both)
cardv /proc/self/exe/AES/Decrypt/FLAGS_m0/Bit_*: 0 both (confinement: validation is adas-side)
cardv mmap 6 / munmap 2 / lseek 2 / open 118 / pthread_create 8 — SAME both
```

Prior byte-identity (cited, not redone): `Bit_SetRootPath @ EN 0x1659ac / VI 0x165994
size 52 identical sha`; `Bit_Login 140 B`, `Bit_ReadFeature 148 B`, `Bit_CheckOutSn 274 B`,
`Bit_CheckOutFeatures 292 B`, dispatcher 180 B — all byte-identical; exe-dir helper
`@ EN 0x116430 / VI 0x116418 size 106 identical`; `.bitanswer.volume` builder semantics
same; `/proc/self/exe` helper only does `readlink`+NUL-terminate (does NOT hash exe).

Interpretation: the *only* proven overlay consumers are the model loader (via `m0`)
and the flag-tail reader. No second plaintext offset field pointing into gaps was found
(prior + re-confirmed: `m0` is the sole directory). `/proc/self/exe` is directory
discovery, not whole-exe validation. Unexamined indirect dispatch through BitAnswer
function tables remains UNKNOWN, but without a new string/xref delta there is no static
basis to promote gaps above runtime integration. All seven gaps are therefore
DOWNGRADED as causal suspects until a reader/xref/log is proven.

## 5. BitAnswer / license runtime inputs — can identical code diverge?

YES. Concrete input dependencies (all proven present at string layer, identical code):

| Input | Path / format (static) | Validation / fallback / error (static) | Why identical code diverges |
|---|---|---|---|
| `license_root_path` | `--license_root_path=/customer/minieye/config` (tail both) + `FLAGS_license_root_path` + `license_service.cpp` ref | `Bit_SetRootPath` dispatch `0x2a` both; fallback/error immediates UNKNOWN | different dir contents → different login/feature results with same code |
| Executable directory | `readlink(/proc/self/exe)` → dirname helper (byte-identical) → builds `.bitanswer.volume` path | NUL-terminate on success; failure path UNKNOWN | different install path → different volume path with same code |
| `.bitanswer.volume` | builder present both (`0x161fc8/0x161f60`); no ordinary direct BL caller found (prior) — indirect dispatch UNKNOWN | UNKNOWN whether used on this SKU | presence/absence of volume file changes behavior without code change |
| `GetPlatformUuidStr` + `SetCustomInfo` | symbols present 1–2× both; UUID/custom-info blobs live under preserved config root | return-code handling UNKNOWN | per-device UUID/serial/deviceID differences → different `Bit_Login` outcome |
| `Bit_Login / Bit_ReadFeature / Bit_CheckOutSn / Bit_CheckOutFeatures` | byte-identical impls (prior); `CheckOutSn 3× / CheckOutFeatures 2×` string refs SAME | success stores state / failure increments? (wrapper shape same; immediates UNKNOWN) | same code + different license/feature blobs → different feature set |
| `adas_de/calib_de/produce_de.flag` + `persist_flag_file_base64` | `/customer/minieye/config/*` (16 refs SAME) | `run.sh` decode + MD5-compare + `--enable_vehicle=false` exit (identical) | preserved device files differ → different gates with same binary |
| Indirect feature dispatch | `feature` 5×, `custom` 20×, `license` 17× both (same) | selected feature values via indirect tables UNKNOWN | same dispatcher + different table inputs → different enablement |

Answer: `STATICALLY_SAME code ≠ IDENTICAL runtime license state`. The vendor updater
preserves `/customer/minieye/config` (+ `/config/cgi_config.bin`, `/config/net_config.bin`),
so EN-era device blobs meet the VI binary at runtime. Identical `Bit_*` code fed
different UUID/license/feature/volume blobs can legitimately return different
login/feature/checkout codes and suppress ADAS while display/preview works. No secrets
were extracted; device blobs remain UNKNOWN (needs sanitized return-code capture).

## 6. Build-ID / version / sysVer / expiry / SKU / language / region coupling

```text
adas build-id note string "build-id" @ 0x172579 both (SAME; GNU note identity)
adas sysVer/expiry/SKU/language/region/vietnam/VI_VN/en_US: 0 both (no coupling strings)
adas version: 10 both; build: 1 both; custom 20 / license 17 / feature 5 — SAME both
cardv sysVer: 4 both (templates, e.g. EN 0xf02f5… vs VI shifted — same count)
cardv language: 4 both (EN 0xf1b1d… vs VI shifted — same count, no new language gate)
cardv build: 3 both; version: 15 both; custom: 24 both; region/SKU/expiry/vietnam: 0 both
sysVer.txt outer: 20230803193750 vs 20230920185743 (proven, but TAR metadata, not a code gate)
```

No `expiry`/`SKU`/`region`/`vietnam`/`VI_VN` ASCII coupling was found in either binary.
`language` count is SAME (no new VI language gate at string layer). `sysVer` templates in
`cardv` are SAME count. Build-ID note offset identical. A hidden integer SKU/region
compare without ASCII anchor cannot be excluded → UNKNOWN, but no static coupling is
proven. Do NOT claim region-lock without a reader + runtime input.

## 7. Reproduction

```powershell
python C:\Users\Admin\AppData\Local\Temp\opencode\lastmile_scan.py
python C:\Users\Admin\AppData\Local\Temp\opencode\ctx_scan.py
python tools/fw/elf_overlay_report.py build/fw_bin_en/adas build/fw_bin_vi/adas
python tools/fw/extract_tail_flags.py build/fw_bin_en/adas build/fw_bin_vi/adas
```

Prior (cited): `BITANSWER_LICENSE_PATH_V1.md` byte-compare; `overlay_anchor_map.py`
(306/309 anchors identical); `adas_gap_report.py` per-gap entropy.

## 8. Conclusion

Promote nothing from gaps without a reader. The overlay/license static surface is now
PARTIAL (models+tail proven, gaps readerless) and INPUT_DEPENDENT (same code, different
state can diverge). The discriminating evidence is runtime: sanitized `Bit_Login` /
`ReadFeature` / `CheckOut*` return codes + UUID/custom-info presence (hashes only) +
`.bitanswer.volume` existence on EN vs VI, plus the reversible EN-base + VI-`adas`
launch log.
