# ProMax Xtensa Ghidra final V6 — tooling verdict: STATIC_TOOLING_BLOCKED

ANALYSIS-ONLY. No C2M firmware modified. No BLE emulation/transmission/sniffing.
No Candidate C. No broad scans repeated. No V1–V5 findings reproduced — cited only.

Ground truth: V5 `b8b3cb8f44e353f597df389ddba387b06372c248`,
owner review `4943cb7a4e72521aa953b95a8ab3c6cca14ffe3d`, recovery LEVEL 2 PARTIAL.

## 1. Environment (exact, verified this pass)

```text
Ghidra version:                 NONE (not installed; see §3)
Xtensa processor module:        NONE (see §3)
Java version:                   NONE (`java` not on PATH; winget Temurin-17 install
                                FAILED — installer hosted on github.com, same
                                egress block as §3; confirms JDK/Ghidra share one
                                unreachable distribution point)
Language/compiler spec:         n/a (no image ever loaded)
Image mapping:                  n/a
Rizin (prior env, untouched):   0.9.1 windows-x86-64 (V5 baseline, not re-run)
Python:                         3.12.0 (used only for hashing/extraction)
```

## 2. Firmware targets — PINNED REVISIONS VERIFIED PRESENT (read-only)

Source: on-machine bare mirrors `D:\CODE\backups\kimdung-promax{,-xl}.git`
(read-only `git show`; nothing extracted into the repo; nothing modified).

```text
Classic  firmware/firmware.bin  @ fd581971ac86475763e1ac0380e9f5cb8c0630e6
         sha256 790605ea…7b1f4b  bytes 4194304  MATCHES promax_image_inventory.json
XL       firmware/guition_ota_v1.bin @ f678b2c25b90df0989fa0ae2bf9e954b3de662ac
         sha256 4d0f62af…09033372  bytes 5916912  MATCHES promax_image_inventory.json
History swept: 41 classic + 33 XL revisions hashed; exactly one hit each (above).
```

Methodology correction (recorded honestly): an initial PowerShell-redirect
extraction produced wrong sizes/hashes (8.4/11.9 MB — UTF-16 stream corruption).
Byte-exact re-extraction via Python subprocess confirmed the MATCHes above.
The earlier "MISMATCH" reading was tooling error, not firmware drift.
Working copies live ONLY in `Temp\promax_v6\` (outside the repo, uncommitted).

## 3. Ghidra install attempt — FAILED on three independent grounds

1. **No distribution channel.** `github.com:443` unreachable from this sandbox
   (curl timeout, all GitHub hosts; ICMP passes, TCP/443 blocked). Ghidra
   publishes only via GitHub releases. `winget search ghidra` → no package.
   `webfetch` returns text/markdown only — cannot transfer a ~450 MB binary.
2. **No Java runtime.** `java` absent; a JDK alone enables nothing without (1).
3. **Xtensa-module maturity unverifiable here.** Official ChangeHistory shows a
   bundled Xtensa module exists in recent Ghidra (Xtensa fixes in 11.x/12.x),
   and community `yath/ghidra-xtensa` (111★, 35 commits, self-declared bugs,
   windowed-register/MAC16/loop TODOs) is the documented ESP32 alternative —
   but NEITHER could be obtained or smoke-tested (windowed-ABI `entry/call8`
   decode is exactly what this task needs), so no reliability claim is made.

Per §2 of the task order: **`STATIC_TOOLING_BLOCKED` — STOP.**
No silent Rizin fallback was performed (a further Rizin window pass is
explicitly out of scope; full-`aaa` already exceeded practical timeout in V5).

## 4. Per-section outcome (§§4–16: all Ghidra-dependent items)

Classic DROM anchors (`0x3FC82824`, `0x3FC803DF`), XL anchors
(`0x42000168–9C`, `0x42000948`, `0x42000BB4`, `0x42167668`), BLE registration
chain, callback binding, parser entry, key mapping, settings-vs-live decision
(§10 A/B/C/D), `rate:4`, dev/want/can negotiation, turn/lane/alert enums,
display chain, stale timeout: **NO NEW CODE-BACKED EVIDENCE — all prior
verdicts stand unchanged** (see the three companion V6 docs + JSON).

## 5. Stop declaration

No genuinely new code-backed protocol semantics were recovered this pass
(none could be — analyzer never obtained).
**`PROMAX_STATIC_ANALYSIS_EXHAUSTED = YES`.** No V7 broad static pass.
Next evidence must come from targeted BLE capture, runtime instrumentation,
or controlled replay (§21 order).
