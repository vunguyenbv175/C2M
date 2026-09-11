# Owner Review — ProMax Xtensa V5

Reviewed commit: `b8b3cb8f44e353f597df389ddba387b06372c248`

## Verdict

**PASS — targeted Xtensa method established**  
**PARTIAL — 8a7e registration structure strengthened**  
**NO LEVEL ADVANCE — protocol recovery remains LEVEL 2 partial**

## Accepted findings

1. Rizin/rz-asm Xtensa decoding is materially established and validated on known ESP32 entry patterns.
2. XL IROM head is a real descriptor/init table rather than executable code.
3. The tuple `8a7e0002 ↔ 0xFFF1 ↔ CODE 0x42167668` inside that descriptor table is the strongest code-backed 8a7e registration evidence to date.
4. Nearby Xtensa code is consistent with BLE/GATT object initialization and 16-bit identifier comparison.
5. This is sufficient to upgrade **registration-structure evidence** from PARTIAL to **STRONG PARTIAL**, but not sufficient to label service/RX/TX roles, properties, permissions, CCCD/MTU, write/notify direction, or callbacks.
6. Bare-key consumer neighborhoods are now better classified as settings/persistence/notification plumbing; therefore the bare-key table must NOT be treated as a proven live-navigation parser/state table.
7. Classic ESP32 analysis is honestly blocked by the current xref method; zero pointer hits are method failure, not absence evidence.
8. Emulator gate remains correctly held. No fabricated live packets or field types were introduced.
9. Hardware sniff remains `USEFUL_LATER`, not `JUSTIFIED_NOW`.

## Guardrails

Do not claim:

```text
8a7e0001 = service
8a7e0002 = RX
8a7e0003 = TX
```

or any permutation until code or runtime evidence binds UUIDs to properties/callbacks/direction.

Do not infer live field types or NavigationState mappings from `unix/nav/spd/lim/...` key-table presence alone.

Do not extend `nav_protocol_emulator.py` with validated live frames until direction + field types are proven.

## Static stop policy

No further broad Rizin/window/census pass is authorized. Information gain is now too low.

Exactly one static path remains worthwhile:

```text
Ghidra/IDA-quality whole-program Xtensa analysis
→ classic DROM/IROM mapped correctly
→ xrefs to 8a7e + bare-key anchors
→ registration function
→ callback binding
→ parser flow
```

If that environment cannot be established or still fails to bind the callbacks/parser, declare:

```text
PROMAX_STATIC_ANALYSIS_EXHAUSTED
```

and wait for a targeted BLE runtime capture when hardware/app access is available.

## Architecture impact

None.

Accepted product direction remains:

```text
Android companion
→ C2M Wi-Fi
→ NavigationProvider / NavigationState
→ DisplayState
→ M4Adapter
```

The project should not clone the ProMax BLE protocol as a prerequisite for C2M navigation/HUD.

## Final owner decision

**PASS / CONTINUE ONLY WITH ONE WHOLE-PROGRAM XTENSA PASS OR STOP STATIC.**
