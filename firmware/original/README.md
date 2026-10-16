# Original C2M Firmware Images

Place the two vendor-provided firmware TAR files in this directory **without modifying or repacking them**.

## Golden working firmware

```text
File: V2023.08.03.1_C2M_U_FR_WIFI_EN.tar
Role: GOLDEN / ADAS confirmed working on the user's physical C2M
Size: ~56 MiB
SHA-256: 3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c
sysVer: 20230803193750
```

## Vietnam firmware (D5-VI base; hardware behavior unverified)

```text
File: V2023.09.20.1_C2M_U_FR_WIFI_VI.tar
Role: vendor Vietnam localization / owner-requested D5 base; prior ADAS observation may be settings-related
Size: ~56 MiB
SHA-256: f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa
sysVer: 20230920185743
```

## Required repository paths

```text
firmware/original/V2023.08.03.1_C2M_U_FR_WIFI_EN.tar
firmware/original/V2023.09.20.1_C2M_U_FR_WIFI_VI.tar
```

Do not rename them: the reverse-engineering scripts and documentation should use these canonical names.

## Integrity

Run:

```sh
sha256sum firmware/original/*.tar
```

and compare with the hashes above before any carve, diff or flash operation.

EN remains the historically known-working runtime baseline. On 2026-10-16 the owner clarified the earlier VI ADAS observation may have reflected unfamiliar settings, not a firmware defect, and requested full-VI-based D5. That is an explicit base choice, not proof that newer is better or VI is incompatible. D5 package validation and later hardware acceptance are separate.
