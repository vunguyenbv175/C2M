# Wi-Fi / Bluetooth live follow-up — 2026-10-18

## Authorization and scope

Owner requested continued connectivity work, preserving stock AP/M4/GPS, and selected DeepSeek V4.1 Flash Free for newly launched subagents. Read-only camera inventory and local static research were performed in this stage. No Wi-Fi mode switch, scan, VIF creation, module reload, association, credential change, GPIO/rfkill write, UART attach or Bluetooth pairing has been performed.

## Wi-Fi: a more concrete installed-driver limitation

Live `/proc/net/rtl8821cs/drv_cfg` reports:

```text
Kernel Version: 4.9.227
Driver Version: v5.14.2-28-g6011b0372.20220328
CFG80211
CONFIG_IFACE_NUMBER = 1
```

The reported compile configuration does not include a concurrent-mode line. Runtime interface inventory has only `lo`, `usb0`, `wlan0`; `/sys/class/ieee80211` has `phy0`. Driver version/build-time report matches the RTL8821CS target already studied. `if2name` exists as a module parameter, but its presence alone does not override the explicit one-interface build report.

Live D3 status remains:

```text
ap_active=true
config_saved=false
connect_pending=false
sta_supported=unknown
sta_state=unknown
last_error=capability_combinations_empty
bt_presence=not_seen
```

**Interpretation:** this is direct evidence of a single-interface installed build, not proof the silicon cannot support concurrent AP+STA, nor permission to force-create an interface. Public Realtek source corroborates `dump_drv_cfg()` printing `CONFIG_IFACE_NUMBER` and conditionally printing `CONFIG_CONCURRENT_MODE`; drv_conf selects1 without concurrency and normally2 with it. Exact installed-module VIF tracing now independently confirms the limit: `dump_drv_cfg` passes literal1 at0x006e8a; the adapter pool has one pointer slot; `dvobj_get_unregisterd_adapter` checks only that slot. With wlan0 already registered, the accepted STATION/AP/P2P add path in `cfg80211_rtw_add_virtual_intf` cannot obtain a free adapter and returns `ERR_PTR(-ENODEV)`. No VIF-creation request was issued to test this. The function accepts station type in principle, but its compiled adapter pool cannot host a second instance; the mere existence of its symbol was not concurrency proof. The prior exact-module review in [RTL8821CS_CONCURRENCY_STATIC_20261016.md](RTL8821CS_CONCURRENCY_STATIC_20261016.md) had not established a numeric adapter limit; the explicit runtime build report is new evidence.

The `if2name` module parameter is unconditional in the inspected public source, so its presence does not prove concurrent mode. Gated virtual-interface parameters were not observed in the live inventory. The Linux4.9 nl80211 path can emit an empty combinations nest when `n_iface_combinations` is zero, consistent with the observed zero-byte attribute; that does not justify changing the controller to force creation.

No runtime UI, `iw` command or module parameter has been demonstrated to turn this single-interface build into concurrent AP+STA. The next engineering path is a matching-source **offline driver candidate**, retaining the original module and preparing an AP-independent recovery route before any eventual test. Matching version text alone does not establish the SigmaStar kernel ABI/configuration. Public Realtek source families inspected include `milkv-duo/duo-buildroot-sdk` (osdrv/extdrv/wireless/realtek/rtl8821cs) and references to `zouxf/linux-rockchip` (drivers/net/wireless/rockchip_wlan/rtl8821cs); these are contextual references, **not a verified source pin for the installed exact version**. A later attempted pin of `git.neardi.com/rockchip/linux/kernel@808d6627f5cd48c123b7e3114429fd126a9abe43` failed: the host was not resolvable in that research environment and no source bytes/commit were independently verified. Do not cite the candidate commit as confirmed or silently substitute a5.12 source tree. That was the state of the first failed pin attempt. A subsequent broader search retrieved the standalone `leavs/rtl8821cs` archive at `d0336d198c7dc050fd5a14c6ae6ac3c74d7112f2`; its archive/version-header hashes and exact installed-version string were independently checked. See [source provenance](RTL8821CS_SOURCE_PROVENANCE_20261018.md). Matching public source version is now available for research, but exact camera-platform patches/configuration and kernel ABI remain unproven; this is not a ready module or hardware acceptance.

Keep the current controller's conservative UNKNOWN/refusal behavior until a safe concurrency path is established. Do not silently replace it with stock AP-XOR-STA scripts: those would sacrifice the AP used by the app and current maintenance connection.

## Bluetooth: missing stack exposure; protect existing UART users

Live observations:

- No `/sys/class/bluetooth`.
- No Bluetooth/HCI/RFCOMM/L2CAP protocol in the bounded protocol inventory.
- No kernel symbol names matching the inspected HCI/BT/RFCOMM/L2CAP/SCO/serdev prefixes in `/proc/kallsyms`.
- No `/proc/config.gz`; exact CONFIG_BT state cannot be inferred solely from that absence.
- Passive boot probe completed: `NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE`, no firmware/helper/transport observed.
- Driver SDIO identity is Realtek vendor `0x024c`, device `0xc821`; this does not prove board-level BT UART wiring.

The SoC's tty driver is named `ms_uart` (`/proc/tty/driver/ms_uart`, not the usual `serial`). Ports0–4 are listed. Ports1/2 show ongoing RX traffic; **cardv holds both `/dev/ttyS1` and `/dev/ttyS2` open**. Do not open, configure or attach Bluetooth to either. Ports3/4 having zero counters does not prove spare connected Bluetooth wiring.

**Interpretation:** Bluetooth is not operational in the present stack; no physical-absence verdict is justified. Static VI kernel/partition/DT analysis found no shipped BT core/transport modules, firmware or userspace setup and no declared Bluetooth UART/reset binding. DT identifies `MERCURY6 SZDEMO BGA2` / `sstar,mercury6`, with five serial aliases, consistent with the live tty inventory. Cardv-held serial1/serial2 are GPS-critical; idle serial3/serial4 do not prove connected Bluetooth pins.

A live positive-control check read94,644 kernel symbol rows successfully: `__netlink_kernel_create` is present; inspected BT/HCI/L2CAP/SCO/RFCOMM prefixes have0 matches, and the separate rfkill-prefix count is0. This strengthens the finding that no active built-in/loaded Bluetooth stack is exposed. Exact `CONFIG_BT=n` versus modular-but-not-shipped remains unverified because the build config is unavailable; absence of `/proc/config.gz` alone does not prove CONFIG_IKCONFIG is disabled. Static raw-string absence is corroborating, not by itself proof.

Bluetooth therefore needs matching kernel support/modules, firmware/helper and a proven free wired UART/enable path; adding only BlueZ or calling hciattach cannot supply those missing layers. Board wiring requires schematic/module/pin evidence or a separately reviewed physical investigation. No kernel/DT change is prepared or installed.

## Existing diagnostics

The owner-approved continuous SD logger remains active with successful card writes. It records safe resource/process/network state but does not enable Wi-Fi concurrency or Bluetooth, nor read UART payloads. See [continuous diagnostic deployment](../runtime/CONTINUOUS_DIAGNOSTICS_20261018.md).

## DHCP / Internet is a separate unfinished layer

`fw/d3/wifi_control.c` deliberately reports `dhcp_helper=missing` and transitions verified same-channel WPA association only to `associated_no_ip`. No controller-owned DHCP lease/address/route/DNS implementation exists yet. The camera BusyBox applet inventory includes `udhcpc`; only explicit `--help` was invoked, never bare `udhcpc` (which could start an acquisition).

A future implementation must be gated behind proven AP+STA, the controller-owned secondary interface and unchanged AP/channel. It needs strict lease validation, ownership-checked process lifecycle, bounded attempts and cleanup scoped to that interface. Do not reuse the stock AP-XOR-STA scripts, write nvconf, rewrite global DNS, or replace routes blindly. A subnet overlapping the AP or M4/USB network must be rejected or explicitly isolated; a lease alone is not Internet acceptance. Policy routing and per-feature resolver behavior require design/tests before claiming Internet works. No DHCP code or association was deployed in this stage.

## Matching-build feasibility result

Static DT identifies Mercury6 / SSC8838G, not Infinity6E. Both firmware DTBs identify `MERCURY6 SZDEMO BGA2`, `sstar,mercury6`, two Cortex-A53 CPUs. Do not select an Infinity6E SDK by resemblance of firmware/toolchain names.

The inspected Wi-Fi module reports kernel vermagic `4.9.227 SMP preempt mod_unload ARMv7 thumb2 p2v8`, depends on cfg80211/mmc_core and has no `__versions` section. Lack of symbol-version CRCs does **not** prove ABI compatibility or make Module.symvers/export metadata universally irrelevant: matching export availability, generated headers and vendor structure layout still matter. A generic4.9.227 build that matches vermagic and undefined symbol names is only a candidate, not a safe-to-load result.

No matching Mercury6 vendor kernel tree/config/build environment has been located locally. Public source research found corresponding Realtek version references, but it did not obtain a verified matching vendor SDK. Failure to locate a public source is a search outcome, **not proof none exists**. Toolchain mirrors without trusted provenance/checksums must not be executed merely to unblock a build.

A rebuilt single-interface baseline must be assessed before enabling concurrency. Exact reproducibility is currently blocked; a reconstructed vanilla-kernel config could be useful for offline research but leaves vendor ABI risk and is **not authorized for live module loading**. No candidate module has been built, installed or accepted on the camera in this stage. An AP-independent recovery method remains required before a future driver test.

## Active offline engineering follow-up

Work continues after the dead-source-link result; it is not an abandonment decision:

- Accessible source with the exact installed version string was pinned and downloaded; [source provenance](RTL8821CS_SOURCE_PROVENANCE_20261018.md). A different version is still only a labeled research alternative, never an unnoticed replacement. Mercury6/TIRAMISU documentation and public userspace SDK are identified, but matching vendor kernel headers/config are not yet obtained.
- Baseline/concurrent driver profiles passed65/65 host-preprocessor/source gates, deriving interface counts1/2 and same-channel combinations. See [profile preparation](RTL8821CS_BUILD_PROFILES_20261018.md). These are not compiled kernel modules or ABI/hardware acceptance.
- `tools/fw/module_abi_report.py` now extracts allowlisted ARM relocatable-module metadata and compares candidates without loading them. Its stock run reproduced the pinned module SHA,219 undefined symbols, cfg80211/mmc_core dependencies and vermagic. Matching metadata always reports **load safety NOT ESTABLISHED**; it cannot validate vendor structure layout or recoverability. Five offline comparison/report tests pass, including missing-metadata inequality and a synthetic ARM module with symbol-version metadata.
- A pure DHCP lease-validation component now exists at `fw/d3/dhcp_lease.c/.h`, with22 passing host tests in `tests/test_d3_dhcp_lease.py`. It validates IPv4/mask/router/DNS/lease bounds and protected-subnet overlap, with no I/O or network commands. It is **not integrated into the controller or deployed**, and does not provide DHCP/Internet by itself. Independent edge-case review found a raw protected-subnet normalization bypass and broad-subnet/DNS edge cases. These were fixed: caller-supplied protected masks are validated and host bits normalized; forbidden subnet intersections and local network/broadcast DNS are rejected. The22-test suite passes with those regressions. This does not exercise a DHCP client or authorize network integration/deployment.
- Continuous diagnostics remained live at sample1129 (~94 minutes from its first continuous sample), card_result0 and ~2.0MB card log. ADAS/lane and main recorder PIDs remained the same at that spot check. This is not driver/concurrency acceptance.

## Later offline builds and renewed powered-camera check

Actual public-source baseline/concurrent builds passed in iterations1/2; see [lab results](RTL8821CS_OFFLINE_LAB_20261018.md). These use upstream4.9.227/reconstructed config and remain NO_LOAD. Iteration2 has all219 stock undefined symbols plus `__memzero`; selected lock sizes match stock evidence but vendor ABI remains unvalidated. Iteration3 object/COMMON accounting was pushed as `3454cb6` and started [run39106160974](https://github.com/vunguyenbv175/C2M/actions/runs/39106160974); result pending inspection.

The owner requested renewed Wi-Fi work while the camera was powered. Read-only live inventory again reports interface count1, wlan0 up and logger running/card_result0. A bounded read of /proc/kallsyms found names for all219 stock undefined references but **no `__memzero`**, and no `__ksymtab___memzero` marker. This is a concrete unresolved-symbol blocker for the upstream-built research module, not a reason to force loading.171 of220 checked export markers were visible; many missing markers belong to already-loaded cfg80211/mmc_core modules, so marker absence must not be equated automatically with absence of all those working exports. Kernel addresses/raw inventory were not published. Upstream ARM exports `__memzero`, but the live vendor kernel does not expose that name in the checked inventory; upstream export evidence must not be substituted for target evidence.

No VIF, association, radio-mode change, driver unload/reload, firmware flash or camera config write occurred in this renewed check.

## Next gates

1. Inspect iteration3 object/COMMON accounting against the stock table; do not infer missing features from .bss size alone.
2. Resolve the extra `__memzero` dependency against verified vendor source/header evidence; do not suppress unresolved checks or force metadata.
3. Obtain/validate matching kernel config/generated headers/layout and establish AP-independent recovery before any separately reviewed driver test. The installed adapter-limit trace is complete; no need to attempt forced VIF creation.
4. Determine Bluetooth kernel availability and transport routing without touching cardv-owned UARTs.
5. No driver/kernel/firmware replacement should be presented as ready before ABI, rollback, AP retention and hardware acceptance checks.
