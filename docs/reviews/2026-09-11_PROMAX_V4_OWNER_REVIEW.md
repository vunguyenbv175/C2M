# ProMax/VietMap V4 Owner Review

Reviewed commit: `c31415c2df5b8a1463da041679c4a119a912870d`

## Verdict

**PARTIAL / CONTINUE ONE FOCUSED OFFLINE DISASSEMBLY PASS**

V4 materially improves the evidence base but does not satisfy the main V4 objective because no Xtensa-capable disassembler was actually used. The result therefore remains **LEVEL 2 partial with a LEVEL 1 GATT-role gap**.

## Accepted findings

1. The executable memory maps for classic ESP32 and XL ESP32-S3 are now reconstructed with `esptool` and can support address-correct disassembly.
2. XL contains real data-pointer clusters linking 8a7e UUID material, numeric `0xFFF0`, code pointers, and DRAM pointers. This upgrades the XL registration evidence from string adjacency to **PARTIAL registration-structure evidence**.
3. The recovered bare live-key table is consumed by XL code through multiple IROM pointer/literal clusters. This is strong evidence that the `unix/nav/spd/lim/trn/dst/exit/eta/rmin/rkm/avg/alrs/hi` table participates in runtime code rather than being dead text.
4. The 41-version history differential is high-value: the nav stack appeared across three August 2026 daily builds (`8a7e` first, then `unix/pong/dev`, then product rename). This establishes that the implementation is recent and still evolving.
5. The emulator guardrail is correct: live fixtures remain unvalidated because field types and direction are still unproven.

## Not accepted / still open

- 8a7e service/characteristic hierarchy: UNKNOWN.
- RX/TX direction: UNKNOWN.
- GATT properties/permissions/CCCD/MTU: UNKNOWN.
- Callback addresses and write/notify handlers: UNKNOWN.
- JSON parser control flow: not recovered.
- Key -> type/state-offset/default/range mapping: not recovered.
- Turn/lane/alert enums: not recovered.
- `rate:4`, stale timeout, `hi`, and `st/avgL/lan` semantics: UNKNOWN.
- Direct VietMap vs companion source: UNKNOWN.

The absence of these results is expected because the requested Xtensa disassembly step was not executed. Pointer scanning is useful evidence, but it is not a substitute for naming and tracing the code targets at the recovered addresses.

## Owner decision

Do **not** sniff hardware yet. Static work is not exhausted because the strongest remaining path is now unusually well-targeted: load the recovered ESP32/S3 segments into an Xtensa-capable disassembler and resolve the exact code targets already identified by V4.

The next pass must be narrow and tool-driven. It should first establish a working Xtensa disassembly environment, then analyze only the following anchor addresses/clusters:

- Classic DROM bare-key table VA `0x3FC82824`
- Classic 8a7e UUID VA around `0x3FC803DF`
- XL 8a7e setup structure around IROM VA `0x42000168-0x4200019C`
- XL live-key consumer clusters around `0x42000948` and `0x42000BB4`

The pass should stop after recovering or definitively failing to recover: service/char roles, callbacks, parser entry, key-type/state mappings, and display consumer chain.

## Current product implication

The accepted product architecture remains unchanged: C2M should use a neutral Android-companion -> Wi-Fi -> `NavigationState` path. Native cloning of the ProMax BLE protocol is not required for the first C2M HUD implementation and must not block that architecture.
