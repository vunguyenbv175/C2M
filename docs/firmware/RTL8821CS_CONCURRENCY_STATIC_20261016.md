# Exact RTL8821CS module: concurrency evidence limits — 2026-10-16

## Identity and method

Installed Wi-Fi module `/customer/wifi/lib/8821cs.ko` was hashed in the bounded
read-only hardware session. Matching private module bytes were extracted
in-memory from an already-local customer image, without camera access,
downloads, module loading or public binary output.

- Size:2899872 bytes.
- SHA-256:`81323242c6fa1e60296921395063a2124ed2a8af330ac5568cfa5e20d80734cc`.
- ARM relocatable ELF; kernel vermagic reports4.9.227/ARMv7/thumb2.
- This hash matches the EN customer manifest and the privately inspected local
  VI-image module. The local source container is not a substitute for the hash.
- Static inspection: ELF symbol/string tables and Thumb disassembly of the
  named functions below. No private module/image bytes are included here.

## Positive evidence, not concurrency acceptance

The exact module defines these functions (Thumb symbol values):

| Function | Value | Bytes |
| --- | ---: | ---: |
| `cfg80211_rtw_add_virtual_intf` | `0x75a45` | 960 |
| `cfg80211_rtw_del_virtual_intf` | `0x75981` | 196 |
| `rtw_wiphy_alloc` | `0x7a1a1` | 664 |
| `rtw_wiphy_register` | `0x7a439` | 204 |

It also has cfg80211 AP/connection operations and multi-interface helper
symbols. Parameters include a documented second-interface name `if2name`.
This proves that VIF/multi-interface-related code exists, not that the board's
active build accepts concurrent AP+managed interfaces, supports two channels,
or preserves recording/AP during association. Generic P2P/multi-interface
helpers can exist without the required AP+STA combination.

## Missing advertisement and negative-evidence limits

The exact module's inspected string/symbol tables did not name
`CONFIG_CONCURRENT_MODE`, `rtw_cfg80211_iface_combination` or an interface-
combination structure. Absence of names does not prove a compile-time feature
was disabled: macros can disappear during compilation and data may be unnamed.
No numeric maximum of concurrent virtual adapters was proven from this review.

More decisive runtime evidence is in `RAM_OBSERVERS_HARDWARE_20261016.md`:

- Actual `wlan0` is AP on5180MHz, phy0.
- Single and ordinary dump GET_WIPHY include an explicitly zero-byte
  `INTERFACE_COMBINATIONS` attribute, not a complete valid AP+STA proof.
- The first split dump was truncated and cannot prove absence. A later exact
  verified probe completed all59 target replies without text truncation or
  parse error and again saw one zero-byte combination attribute; see
  `D4_SHADOW_HARDWARE_20261016.md`. This is complete advertisement evidence,
  not physical hardware impossibility or safe VIF-creation proof.
- Only `lo`, `usb0`, `wlan0` interface names were observed.

The stock scripts use one `wlan0` and explicitly stop AP before starting STA
(and the reverse). This is **stock AP XOR STA policy**, not proof that hardware
concurrency is impossible. Do not run those scripts to obtain STA at the cost
of the working AP.

## 2026-10-18 follow-up: exact installed build is single-interface

The numeric-limit uncertainty above is superseded for this exact module build by new live and static evidence; see [connectivity follow-up](CONNECTIVITY_LIVE_FOLLOWUP_20261018.md).

- Live `drv_cfg` explicitly reports `CONFIG_IFACE_NUMBER = 1`.
- Exact module `dump_drv_cfg` passes literal1 at0x006e8a.
- The compiled adapter pool has one pointer slot. Its free-adapter helper checks only index0; wlan0 already occupies and registers that adapter.
- `cfg80211_rtw_add_virtual_intf` does accept STATION/AP/P2P types, but requires an unregistered adapter. With the only slot in use it returns `ERR_PTR(-ENODEV)`; `if2name` cannot create another slot.
- `rtw_wiphy_alloc` advertises interface types but leaves concurrency-combination data absent/zero, consistent with the empty runtime combinations attribute.
- This was established by read-only observation and static analysis, **not by issuing a VIF-create or mode-switch request**.

Thus a second simultaneous AP/STA interface is not supported by the **installed build**. It still does not disprove concurrent operation in another correctly built driver, or establish board-level RF/BT behavior. A matching driver/kernel build and an AP-independent recovery route are prerequisites before any future candidate test.

## Original conclusion and next gate (historical)

**At the time of the original review, AP+STA remained unproven, not disproven.** The current safe controller must
keep UNKNOWN and refuse interface creation/association when advertisement is
empty or unadvertised. Source diagnostic errors now distinguish those cases
from malformed framing only after validating the complete target response,
without authorizing any new Wi-Fi action. General Linux/Chrome CI
`38834222285` passed on source `7832fd5` including empty/missing/wrong-PHY/
duplicate/truncated cases. This source clarification is not installed on the
camera and is not a target-driver or AP+STA association test.

Potential next static work is to trace exact wiphy-field initialization and
VIF type/adapter limits using this hash and kernel4.9 layout. Only a proven
safe path plus explicit owner-controlled test plan could justify a later
state-changing test. No forced VIF, module parameter rewrite, module reload,
firmware/driver replacement, AP switch, scan, DHCP or route change was made.
Bluetooth co-existence parameter names are not HCI/transport/RF proof.
