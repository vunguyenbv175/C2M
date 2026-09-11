# Owner Review — ProMax / VietMap Protocol Deep Reverse V2

Reviewed source commit: `c4733ad4784a7f12c2839b9a70c0e63084424037`

## Verdict

**PASS for research quality / PARTIAL for live VietMap protocol recovery.**

The V2 pass materially improves the product direction and supersedes the earlier V1 recommendation that centered an external ESP32 bridge. Static evidence supports a direct Android companion -> existing C2M Wi-Fi -> isolated navigation service architecture as the default path. An external ESP32 is **NOT JUSTIFIED** unless later runtime evidence proves a BLE-only dependency that cannot reasonably be translated on the phone side.

The live VietMap value-plane is **not recovered**. Management BLE (`FFF0/FFF1/FFF2/FFF3`) is confirmed, while the `8a7e0001/2/3` navigation block plus `dev/want/can/transport=ble` vocabulary provides high-confidence navigation intent but not yet a proven live characteristic role/property/handler/value encoding.

## Accepted findings

1. ProMax family images are correctly separated into ESP32, ESP32-C3, ESP32-S3, Adapter ESP32, and XL ESP32-S3 variants using image headers/entries and deterministic inventory tooling.
2. `FFF0` management plane is directly supported by Web-Bluetooth code and firmware evidence.
3. The navigation handshake vocabulary is strong evidence for a pre-normalized semantic navigation feed: `nav, spd, lim, trn, dst, exit, st, eta, rmin, rkm, avg, avgL, alrs, lan`, with capability names `speed, limit, turn, street, eta, avgzone, alerts` and `transport=ble`.
4. Live navigation values/encoding are absent from the inspected static images and remain UNKNOWN.
5. Classic Bluetooth SPP, ProMax classic Wi-Fi navigation, and cloud relay are appropriately downgraded/excluded by current evidence.
6. The existing ProMax `firmware_adapter.bin` is not proven to be a runtime VietMap navigation bridge. Therefore it must not be used as justification for adding an ESP32 to C2M.
7. Preferred C2M product architecture is Android companion -> C2M Wi-Fi/AP -> neutral `NavigationState` -> `DisplayState` -> M4 adapter, with Linux framebuffer/OSD only as fallback after M4 capability gates.

## Owner corrections / guardrails

- Do not describe the complete phone-to-HUD navigation transport as fully `CONFIRMED BLE GATT`. Use: **management BLE CONFIRMED; navigation BLE intent HIGH-CONFIDENCE; live navigation characteristic roles/properties/value plane UNKNOWN**.
- Do not implement the recovered `want` field names as if they are the live wire schema. They are handshake/subscription vocabulary only.
- Do not create an ESP32 bridge unless all external-hardware gates are independently proven.
- Do not write to stock M4 yet. L0/L1 passive decoding and responsibility mapping remain prerequisites.
- Keep Candidate A/B frozen and unrelated to VietMap work.

## Product decision

Baseline architecture accepted:

`Android companion -> C2M Wi-Fi (new isolated port) -> NavigationProvider -> neutral NavigationState -> DisplayState arbiter -> M4Adapter -> stock M4`

Safety properties:

- phone input is untrusted;
- stale data expires;
- navigation never writes ADAS safety state;
- ADAS warning priority is above navigation;
- enhancement failure cannot stop stock camera/recording/ADAS;
- kill-switch returns to stock-only display behavior.

## Next highest-value experiment

Accept the proposed non-hardware experiment first: build a **PC/host protocol emulator and neutral navigation-state harness** that replays only the recovered handshake (`ping/pong/dev/want/can`) and synthetic `nav/1` semantic fixtures into a shadow `DisplayState`, with **zero C2M display writes**.

Purpose: validate the vendor-neutral C2M architecture independently of the still-unknown VietMap live packet encoding. This prevents product progress from being blocked on cloning the ProMax BLE wire protocol.

In parallel but lower priority, deeper Xtensa/RISC-V disassembly may continue to recover the `8a7e` GATT handler table and live value-plane. Hardware sniffing remains useful later, not mandatory now.

## Status

- C2M HUD feasibility: **MEDIUM overall / HIGH for offline HUD path**
- VietMap protocol: **PARTIALLY RECOVERED**
- External ESP32: **NOT JUSTIFIED**
- Hardware sniffing: **USEFUL LATER**
- Candidate A/B: **UNCHANGED / FROZEN**
