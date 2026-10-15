# C2M Bluetooth capability — evidence boundary — 2026-10-15

## Current conclusion

The golden camera firmware bundles a **Realtek RTL8821C-series WLAN driver**,
file `/wifi/lib/8821cs.ko`, with a hash-verified manifest entry. This is high-
confidence evidence that the camera image targets RTL8821CS-family Wi-Fi
hardware. RTL8821CS silicon is a Wi-Fi + Bluetooth-capable family: Wi-Fi uses
SDIO and Bluetooth uses a separate HS-UART controller.

It is **not** proof that the owner's physical board has the Bluetooth side of a
combo module populated, wired, enabled, or supported by the deployed boot
configuration. The module filename and family capability cannot establish
board routing or a working HCI device.

## Evidence from the camera image

- Customer manifest: `docs/firmware/CUSTOMER_MANIFEST_EN.json:3229–3240`.
- `/wifi/lib/8821cs.ko`: 2,899,872 bytes;
  SHA-256 `81323242c6fa1e60296921395063a2124ed2a8af330ac5568cfa5e20d80734cc`.
- Static module inspection found RTL8821C HAL symbols, the
  `drivers/net/wireless/realtek/rtl8821CS/` source path, and SDIO modaliases.
  It identifies the Wi-Fi SDIO driver, not a Bluetooth transport driver.
- The extracted customer inventory contains no separate Bluetooth `.ko`, HCI
  UART driver, `rtl_bt`/`.hcd` Bluetooth firmware, or `hciattach`/BlueZ setup
  path. This is strong evidence that the shipped image has no demonstrated
  Bluetooth software bring-up path.
- The Wi-Fi boot chain loads the selected Wi-Fi module through
  `/customer/wifi/rcInsDriver.sh`; this does not initialize Bluetooth.

The [RTL8821CS manufacturer's product description](https://www.realtek.com/Product/Index?id=588&cate_id=194),
checked 2026-10-15, identifies the family as supporting Bluetooth 4.2 over HS-UART. That establishes chipset capability,
not the C2M board's module variant, BT-disable pin, UART wiring, firmware,
or runtime state.

## Runtime evidence

The latest private passive diagnostic says:

```text
verdict=NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE
radio_test=NOT_PERFORMED
state_changes=NONE
```

It observed no HCI, Bluetooth rfkill entry, named Bluetooth device-tree node,
or standard Bluetooth user-space tools within the bounded read-only probe.
No scan, pairing, RF activation, driver load, UART attach, or settings change
was performed. Therefore:

- **Bluetooth usable now:** not demonstrated; treat as unavailable.
- **Physical Bluetooth chip definitely absent:** not established.
- **RTL8821CS-family Wi-Fi target in the image:** high confidence.
- **Bluetooth on the exact board:** possible, but board wiring/module variant
  remains unknown.

## What would close the question

The least-invasive decisive evidence is an owner-supplied photo or board/module
marking, or a board schematic/part number proving whether the RTL8821CS combo
module and its BT UART pins are populated and connected. A future owner-
approved read-only camera inspection could additionally compare the device-tree
UART/SDIO nodes and boot logs, but must not open a UART owned by `cardv`, load
modules, run `hciattach`, scan, pair, or transmit RF without a separate gate.

Until that evidence exists, C2M features must not depend on Bluetooth. Use the
already-proven camera AP/HTTP path or offline behavior instead.

## Owner-approved next-flash investigation

Owner has no board photos/documentation and requested testing on the next
firmware flash. Prepare an expanded passive probe in the next D4 candidate;
no separate diagnostic-only flash is required or proposed. Existing D3 boot
integration saves the report to private `/tmp/c2m-d3/bluetooth.txt` and, after
the recording volume is mounted, `C2M_DIAG/bluetooth-D3.txt`.

The expanded report must distinguish **bundled Wi-Fi driver**, **runtime
Wi-Fi/SDIO exposure**, **Bluetooth transport/software context**, and **HCI
presence**. Probe header `C2M_D3_PASSIVE_BLUETOOTH_V2` distinguishes it from
the earlier V1 card captures; file name and HCI verdict strings remain compatible
with the existing D3 status consumer. No hardware-absence verdict is inferred
from missing files. Runtime SDIO vendor/device IDs may be reported only after
strict fixed-width hexadecimal validation: these identify a chip family, not
a unique device or board-level Bluetooth wiring. No raw modalias/uevent data
is dumped. All reads and output are bounded; no credentials, MAC addresses,
serial numbers, GPS positions, database contents or raw device data are included.

This approval does not justify guessed Bluetooth initialization on an unknown
UART. Do not load a module, toggle rfkill/GPIO, run an attach helper, scan,
pair or transmit RF in the boot probe. If an HCI interface already exists,
report it without bringing it up; an active functional test remains a separate
step after the transport and stock GPS ownership are verified. If the next
boot still exposes no HCI, record the result as inconclusive for board wiring,
not as a promise that every physical question can be settled by flashing.

Next-flash acceptance:

1. Owner flashes the otherwise-approved D4 candidate using correctly identified
   updater media; preserve the recording card, recording/app/AP and ADAS.
2. Let normal boot complete. Retrieve the private report read-only through
   an authorized route; identify its probe version and completed status.
3. Compare driver/SDIO evidence with the bundled RTL8821CS target. Preserve
   HCI-present versus no-HCI distinctions independently from chipset capability.
4. If stock recording/GPS/ADAS regresses, stop; Bluetooth investigation is not
   grounds to disable a stock service or recalibrate/reset configuration.
