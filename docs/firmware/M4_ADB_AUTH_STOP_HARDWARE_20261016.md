# M4 ADB identification: AUTH required, connection gate FAILED — 2026-10-16

## Exact result (not a UI test)

Source `95283f206765133417c00e7b24e67db0d2f5f09e`, manual ARM run
`38881250082` PASS. Host suite12 tests (one intentional no-real-probe skip),
including Linux successful fake-USB and failure-path shim. ARM pure self-test,
ELF/ABI, pinned stock-QEMU missing-USB/sentinel/actual-import gates passed.
QEMU did NOT test real hardware or real authentication.

- ELF11692B SHA256
  `e5f3ae5e9a3b601d5769e0a9f8e6143874a0aa9c8acc54aec0193ce1d6269b29`.
- Manifest1754B SHA256
  `a9f629a4cd630f6d2e8d7fc755f3d9e93688302aaec7993e4cbe449e27483bff`.
- Private vault `1a13a28c28ca32d8ac965a8741d9fd48d630edfa`.
- Local full source/bundle/runtime evidence/ELF readback PASS before pinning.

An initial16:39 preflight had SSH refused and stopped before upload or USB
transaction. No listener restart/extension. Owner then normally rebooted,
rejoined AP and reconfirmed stationary/healthy M4 in3D. Newly notified session
`m4_adb_identify_20261016_165949` passed fresh identity/finite window/native
three-leg preflight, staged exact RAM executable, then executed ONCE:

| Measurement | Observed |
| --- | --- |
| Identifier outcome |`authentication_required` /`auth_stop` |
| Received AUTH challenge payload |20B, contents never logged |
| Request |one CNXN,31B total,2 OUT transfers24+7 |
| Reply transfers |2 IN, no further reply sent |
| Actual measured native elapsed |7ms |
| Interface2 claim/release |both verified1 |
| Native exit / exact RAM cleanup |0 /verified |
| Self-test |PASS before native request |

This proves an ADB protocol responder, not authorized shell/readback/root,
M4 renderer version, widget capability or access bypass. NO AUTH response,
public/private key, service/shell OPEN, app installation, config/UI/firmware
change, guessed credential or second8080 application client was sent.

## Failed preservation gate and stop

Preflight at uptime59.00 had all three native M4 connections. Postflight at
64.33 retained8080 with the same client port, but neither24012 nor26012 was
ESTABLISHED. **Unchanged native-connection gate FAILED.** Cause UNKNOWN; do not
attribute it to ADB or to normal baseline without controlled evidence.

cardv PID640, ADAS2098/wrapper2096 and installed D4 PID952 unchanged in snapshots;
recording status1, actual segment metadata advanced, AP active, installed D4/DB
hash checks passed. Postflight and separate absent-RAM-directory check exit0.
These snapshots do not prove uninterrupted native scene delivery.

Owner subsequently reported M4 and original functions **still normal**. That
observation does not waive the connection gate or prove both ADAS legs recovered.
No follow-up camera check or second handshake was attempted; access stopped.
Later owner request to continue standard authorization is a NEW scope, not a
retry hidden inside this result.

## Evidence preservation

Raw native lifecycle stdout220B SHA256
`a9e4b4a0edb49f12389b6ed39a3d4a51766ec3d18a4f5952d97677113429d936`.
Private18-file manifest SHA256
`409519af129c2cc9d04309089669f422b8ba60fd4f534b00acc9018c8569efd6`.
No challenge/key/banner/vendor bytes are public.

## Next boundary

Standard ADB owner authorization may be assessed separately: dedicated laptop
key, private part never sent to camera/M4, one public-key approval request,
owner-visible one-time Allow if a dialog exists, no bypass or repeated attempts.
No firmware replacement is established as necessary. No speed/sign message or
extended UI trial has occurred; capability remains UNKNOWN, not unsupported.
