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
