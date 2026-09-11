# 01 — Package and Flash Layout

## Status

**CONFIRMED by direct static analysis.**

## Package identity

### EN

```text
filename: V2023.08.03.1_C2M_U_FR_WIFI_EN.tar
SHA-256: 3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c
sysVer: 20230803193750
inner upgrade MD5: 8e69fe4511366ed86b892bf413916187
```

### VI

```text
filename: V2023.09.20.1_C2M_U_FR_WIFI_VI.tar
SHA-256: f28cad049bf27437f4245ff489a784c679a20c1d867c4a63b6bcfb081b8d3cfa
sysVer: 20230920185743
inner upgrade MD5: ab5245740c2c7860b44d7d8adbf89ec6
```

Both TAR packages contain the same four logical items:

```text
SigmastarUpgradeSD_SSC8838G.bin
sysVer.txt
minieye_firmware.md5
adas_upgrade.sh
```

`adas_upgrade.sh` SHA-256 is identical in both packages:

```text
0e18c91fd95f2a2cdf64637448d8540e946ae5bb2e37627d8bbd6bef7f7da05b
```

## Flash script layout

Both upgrade images use the same fixed-offset SigmaStar script/container approach.

Common payload layout:

```text
CIS
set_partition
IPL
IPL_CUST
U-Boot
kernel
rootfs
ubi0 erase/create
miservice
customer
MISC
oneed_cust
set_config
```

The stock updater is broad/destructive:

```text
nand erase.part IPL0
nand erase.part IPL_CUST0
nand erase.part IPL_CUST1
nand erase.part UBOOT0
nand erase.part UBOOT1
nand erase.part KERNEL
nand erase.part RECOVERY
nand erase.part rootfs
nand erase.part ubi0
nand erase.part MISC
```

Therefore it must **not** be reused as the normal update mechanism for C2M Enhanced features.

## Important identical low-level payloads

The following exact payload hashes match EN and VI:

```text
CIS       70a587437182018af328c50fdb7d94663311857bbc14e849cb21c08913584e70
IPL       78d4ba339b4ba5f892e9a3d5ade44a9125932188acd5e73d093fadba365a2e2e
IPL_CUST  6f892733ff63d4493b8465bfe6a044043ebde25d8f79ba2af1d4aceb5ffb8a6e
```

This strongly argues against a board-init/IPL difference being the cause of the observed EN-good / VI-bad ADAS behavior.

## Partition payload size differences

```text
kernel:
EN 0x22691f
VI 0x226921

rootfs:
EN 0x841d6b
VI 0x841177

oneed_cust:
EN 0x364000
VI 0x326000
```

`customer` and `miservice` allocated/write sizes are unchanged.

## Persistent config behavior

The updater explicitly backs up/restores:

```text
/customer/minieye/config
/config/cgi_config.bin
/config/net_config.bin
```

This is a critical regression-analysis fact.

On the same physical unit, flashing VI and EN does not inherently replace those persistent per-device files.

## VI bootarg delta

EN bootargs include the common memory/NPU/CMA layout.

VI adds:

```text
mmap_reserved=fb,miu=0,sz=0x800000,max_start_off=0x3F000000,max_end_off=0x3F800000
```

Interpretation:

- **CONFIRMED:** VI reserves an additional 8 MiB region labelled `fb`.
- **HIGH-CONFIDENCE:** this is framebuffer/display-related.
- **UNKNOWN:** whether this change is required specifically by M4, local display plumbing, or another rendering path.

Coding agent must treat this as an important VI delta rather than noise.

## Update safety recommendation

For development:

```text
Never flash the full vendor image just to test:
- web UI
- road DB
- AI model
- M4 parser
- voice files
- config
```

Create modular, rollback-capable customer-layer updates instead.
