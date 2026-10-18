# RTL8821CS baseline/concurrent profile preparation — 2026-10-18

## Status

**Offline configuration preparation passed; no kernel module compiled or deployed.** These checks use the host preprocessor and source checks, not the camera kernel build. They do not prove driver ABI, radio concurrency, performance or AP retention.

Source pin and hashes: [source provenance](RTL8821CS_SOURCE_PROVENANCE_20261018.md), primary `leavs/rtl8821cs@d0336d198c7dc050fd5a14c6ae6ac3c74d7112f2`.

## Configurations derived

| Profile | Concurrent macro | Derived interface count | Purpose |
|---|---|---|---|
| baseline | absent | 1 | Compare selected observed features against current driver |
| concurrent | enabled | 2 | Separate research profile for same-channel AP+STA |
| wext | absent | 1 | Iteration-6 legacy-WEXT gate emulation (driver-side `-DCONFIG_WIRELESS_EXT` only; added 2026-10-19) |

Both disable the downloaded source's default RK3188 platform block, which would otherwise inject Rockchip/Android and concurrency flags. The replacement C2M profile explicitly selects little-endian cfg80211/STA events. It must not inherit a Rockchip shutdown path on the SigmaStar board.

The intended additional concurrency flag is:

```text
-DCONFIG_CONCURRENT_MODE
```

`CONFIG_IFACE_NUMBER` is derived by the source headers, not manually faked. Host preprocessing produces1 for baseline and2 for concurrent. This only demonstrates those macro relationships.

Selected live-report parity checks pass for SDIO, cfg80211, power-saving/IPS/LPS, PHY-file loading, transmit-power settings, adaptivity settings, scatter/gather, busy-scan period16000, TPT and TX aggregation. Matching these visible settings does **not** prove every hidden camera-platform option or downstream patch matches.

P2P, monitor, Android and USB/PCI/GSPI are absent from these proposed profiles. Those exclusions are profile policy; absence of a printed macro in a live report alone does not prove every such feature is absent in the original module.

## Same-channel boundary

The inspected source's concurrency combinations use:

```text
num_different_channels = 1
max_interfaces = CONFIG_IFACE_NUMBER
```

The combinations block is gated by single-wiphy and at least two interfaces. Thus the proposed path is **same-channel AP+STA**, not independent-channel concurrency. This constraint also has to be enforced by connection policy and validated on hardware later.

## Verification performed

The parent reran the prepared host-preprocessor/source gates: **65/65 passed**. The preparation also reported both Makefile patches pass `git apply --check` against the pinned source. No source was compiled into a kernel module by these gates, and no live VIF/association request was made.

## Next build gate

A compatible kernel build environment must provide validated generated headers/config, release identity, ARM architecture settings and export metadata. Merely defining the right release string or obtaining a matching vermagic does not validate vendor structure layouts. Build and assess the baseline before the concurrency variant, use the offline ABI comparison tool, and retain an AP-independent recovery path before any future live load.

No `8821cs.ko`, kernel image, downloaded source tree or unverified compiler executable is committed with this document. Current camera driver remains unchanged.
