# C2M SD upgrade version gate — stock EN static audit

**Date:** 2026-10-13. **Scope:** historical stock image, host-only inspection.
Current camera environment and the failed B attempt's boot messages have NOT
been captured. This is not a device flash verdict.

## Why this audit matters

A and frozen B2 use the same update token, `20230803193750`. B attempts booted
normally with unchanged card files. The earlier inference that the A upgrade
removed the SD trigger from `bootcmd` was wrong: the stock U-Boot checks SD
eligibility **before** reading `bootcmd`. UART is not established as necessary
for another SD update.

The format prompt also occurred after the accepted A run, per local operator
evidence `C2M_HW_20261012/02_candidate_A/acceptance.md`, lines 12–13. It is not
an upgrade rejection code. Absence of `.bak` is likewise not an indicator of
U-Boot eligibility: the external Linux script creates configuration backups;
the audited U-Boot path does not create them.

## Verified input identities

Vendor bytes remain local/private; no firmware or credential material is
included here.

| Input | SHA256 |
|---|---|
| Stock EN TAR | `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c` |
| U-Boot uImage at inner offset `0x18000`, length `0x48a44` | `7c64be8cb848af856a9f107139ee90765be4c3c3bdcd4eb49563839b57304490` |
| XZ-decompressed U-Boot, 882,768 bytes | `0149b185064261ecde5bf3a61528936a712bcca9b9c85c5e50059a1cf773aa2f` |

The carved uImage was compared directly with the TAR member slice. Header
CRC `0x2bd5f7ab` and compressed-data CRC `0x6108048d` both verify. Decompressed
code offsets below are relative to that binary, **not** the compressed carve.
Linked/entry base is `0x23e00000`; the uImage header LOAD field is separately
`0x23f00000`.

Independent local evidence is retained at
`C:\Users\DrVu\AppData\Local\Temp\opencode\independent_uboot_audit_20261012\`:
`REPORT.md`, `audit_verified.txt`, `audit.py`, and `semantics.py`. This audit
used a limited A32 decoder plus raw instruction/literal resolution and
in-memory stepping of the parser/strcmp subset, not a complete boot emulator.

## Main-loop eligibility path

| Decompressed offset | Verified action |
|---|---|
| `0x1454` | `main_loop` entry, identified by its diagnostic literal |
| `0x14ac` | raw instruction `eb006e20`, BL to eligibility at `0x1cd34` |
| `0x14b4` | nonzero eligibility result skips the automatic `sdstar` choice |
| `0x14c4` / `0x14cc` | choose `sdstar` and invoke command runner on success |
| `0x14e4` | later call to boot settings lookup |
| `0x17a4` / `0x17a8` | lookup of environment `bootcmd` |

There are additional `sdautoupgrade` and direct-command routes. This finding
proves a separate compiled-in SD check, not a complete inventory of every
upgrade entry point or hardware prerequisite.

### Version selection and comparison

1. At `0x1cd70`, eligibility reads environment `sysVer`.
2. It rescans MMC and tries to load `sysVer.txt`.
3. **Only a load failure** causes fallback to the inner image's first `0x4000`
   bytes. A readable but malformed sidecar is rejected, not bypassed.
4. Parser `0x1abc0` skips blank/comment lines. The gate requires the first six
   bytes to equal `sysVer` and accepts a line length of 8–32. It copies the
   token beginning at line offset 7.
5. At `0x1ced4`, raw `eb01b74b` calls `0x8ac08`, a NUL-terminated bytewise
   `strcmp`, not a timestamp/numeric comparison.
6. Equality branches at `0x1cedc` to `CurVer = prvVer,no update` and returns 1.
   Either sign of an unequal comparison takes `ok update` and returns zero.

In-memory stepping of the original parser and strcmp confirmed both source
version lines yield `20230803193750`; unequal comparison signs both qualify.
The original inner token begins at offset `0x21` (33). The sidecar token begins
at offset 7. The 14-digit candidate `20261012000001` has the same width and
satisfies the observed parser constraints. Its date-shaped digits are an
update identity, not an interpreted build timestamp.

### Persistence

The `sdstar` handler is at `0x1bbe0` (command descriptor at `0xc7914`). It skips
the script's `sysVer` metadata line. Before executing a `reset` line, at
`0x1be28–0x1be3c` it sets environment `sysVer` from the selected token buffer
and runs `saveenv`.

This proves **attempted** persistence; those set/save return values are not
fully checked. If A saved its original token, the normal main-loop gate
rejects frozen B2 because the token is identical. That is the leading
explanation, not a captured runtime rejection.

## External script and checksum

The outer `adas_upgrade.sh` is 2,972 bytes, SHA256
`0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b`.
It checks MD5 of the **whole inner image** against `minieye_firmware.md5`.
It does not numerically compare `sysVer.txt`. Retry extraction must not
reintroduce stale bytes from a mismatched archive.

Its `.bak` files are configuration archives and matching checksum files, not
firmware rollback images. The script is different from the NAND ADAS-only
updater; neither replaces the independent U-Boot eligibility check.

## Authorized SD-only follow-up

Owner authorized a separately named B2 artifact and copying it to the
identified `C2M_FLASH_B` card. Retain frozen A/B1/B2. Change only:

- the 14 token bytes in the inner script;
- the matching sidecar token;
- the MD5 text derived from the complete modified inner image.

Keep all 11 partition loads, executable payloads, commands, offsets, lengths,
padding, unknown tail and `adas_upgrade.sh` byte-identical to frozen B2.
Record fresh hashes and validate independently. Do not relax the original
candidate builder/diff contract or silently replace its frozen hashes.

An unequal token enables the audited gate; it does not guarantee MMC/FAT
reads, safe power, successful flash writes, environment saving or B2 runtime
logging. The original script still performs a full firmware flash. After a
successful candidate-token save, A's old token is unequal and passes this
equality check, but that alone does not prove rollback or recovery succeeds.
