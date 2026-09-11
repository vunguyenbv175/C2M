# ProMax live-protocol version diff V1 (41-version bisect, mandatory §29)

Mirror: `promax.git` @ `fd581971ac86475763e1ac0380e9f5cb8c0630e6`. All 41
commits touching `firmware/firmware.bin` scanned (oldest→newest); string-set
diff on the two introducing transitions.

## Timeline (nav stack lands in Aug 2026, days before analysis)

| # | Date | Commit | Title | 8a7e | bare unix | pong | dev | DTBK |
|---|---|---|---|---|---|---|---|---|
| 0 | 2024-12-02 | 12b2f577 | wip | — | — | — | — | — |
| 1 | 2024-12-03 | 528f34a4 | up 7.11 | — | — | — | — | FIRST |
| … | … | … | … | — | — | — | — | present |
| 38 | 2026-08-21 | 60ab7b32 | daily | FIRST | — | — | — | present |
| 39 | 2026-08-30 | f2aaa831 | daily | ✓ | FIRST | FIRST | FIRST (named **Promax XL**) | present |
| 40 | 2026-08-31 | fd581971 | daily (HEAD) | ✓ | ✓ | ✓ | ✓ (renamed **Promax**) | present |

`ObdBleTask`: absent from ALL 41 classic versions (variant-gated to C3/S3).

## Introducing diffs

8a7e-transition (`085c7fb6` → `60ab7b32`, size unchanged 4194304):
added `8a7e0001/2/3`, transient `nav       : %d` + `spd       : %d` log
formats (sole integer-handling evidence, MEDIUM-transient), DTBK churn
(`MAPVIET`→`WAZE` default), JPEG-XMP churn. No dev/pong/unix yet — UUIDs
landed BEFORE the handshake.

unix/pong-transition (`60ab7b32` → `f2aaa831`): added `"t":"ping"`,
`unix`, `alrs`, full `dev` JSON (**named Promax XL inside the classic
image**), `{"v":1,"t":"pong"}`; REMOVED the `nav/spd : %d` log strings.
HEAD then renames dev to `Promax`.

## Reading

The nav stack is ~10 days old, assembled across 3 dailies (UUIDs →
handshake+live-keys → rename), with debug-log churn in between. There is no
stable spec to clone; any C2M-side ProMax-protocol emulation would chase a
moving target. Handshake `want` (incl `st/avgL/lan`) was written before/independently
of the bare parser table (which lacks those three) — consistent with
spec-ahead-of-implementation or a second object, but neither is proven.
