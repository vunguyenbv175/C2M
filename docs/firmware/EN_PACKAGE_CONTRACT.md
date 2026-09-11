# EN Package Contract — re-derived from original vendor TAR

Source TAR SHA-256: `3a703522df31f8accd58069850be0a01c2ac5ecbf12af1705ccb4904cd465f8c` (58368000 bytes)

## Outer TAR members (order-significant)

| order | name | size | mode | mtime | header@ | data@ | sha256 |
|---|---|---|---|---|---|---|---|
| 0 | `SigmastarUpgradeSD_SSC8838G.bin` | 58359832 | 0o664 | 1691062673 | 0x0 | 0x200 | `e3f2443294f71588…` |
| 1 | `sysVer.txt` | 26 | 0o664 | 1691062670 | 0x37a8400 | 0x37a8600 | `7cc0796927d1a85e…` |
| 2 | `minieye_firmware.md5` | 66 | 0o664 | 1691062674 | 0x37a8800 | 0x37a8a00 | `fca994b683f6f2d9…` |
| 3 | `adas_upgrade.sh` | 2972 | 0o775 | 1691062673 | 0x37a8c00 | 0x37a8e00 | `0e18c91fd95f2a2c…` |

Trailing zero bytes after last member data: 1536 (3x512 zero blocks; preserved verbatim by the splicing repacker).

## sysVer / MD5 relationship

sysVer.txt: `b'sysVer 20230803193750\nend\n'`

minieye_firmware.md5: `8e69fe4511366ed86b892bf413916187  SigmastarUpgradeSD_SSC8838G.bin`

EXACT-MATCH: minieye_firmware.md5 lists 8e69fe4511366ed86b892bf413916187; md5(inner .bin) = 8e69fe4511366ed86b892bf413916187; match=True

## Inner upgrade image

Size 58359832 bytes, SHA-256 `e3f2443294f71588…` (full hash in JSON), MD5 `8e69fe4511366ed86b892bf413916187`.

U-Boot script: 2622 bytes + 1x `\n` trailer, then 0xFF pad to 0x4000 (first payload).

### Payloads

| section | offset | size | end | sha256 |
|---|---|---|---|---|
| cis.es#0 | 0x4000 | 0x5c00 | 0x9c00 | `70a587437182018a…` |
| cis.es#1 | 0xa000 | 0x200 | 0xa200 | `5fedff9f36704ec2…` |
| ipl.es#0 | 0xb000 | 0x6180 | 0x11180 | `78d4ba339b4ba5f8…` |
| ipl_cust.es#0 | 0x12000 | 0x5eb0 | 0x17eb0 | `6f892733ff63d449…` |
| uboot.es#0 | 0x18000 | 0x48a44 | 0x60a44 | `7c64be8cb848af85…` |
| kernel.es#0 | 0x61000 | 0x22691f | 0x28791f | `c1fa8f7363615f1d…` |
| rootfs.es#0 | 0x288000 | 0x841d6b | 0xac9d6b | `1dcc3e954910661a…` |
| miservice.es#0 | 0xaca000 | 0x193000 | 0xc5d000 | `358c01a9e9455a8d…` |
| customer.es#0 | 0xc5d000 | 0x25e7000 | 0x3244000 | `b4dabc4d789c758d…` |
| misc.es#0 | 0x3244000 | 0x200000 | 0x3444000 | `c9bbb3850500aae6…` |
| oneed_cust.es#0 | 0x3444000 | 0x364000 | 0x37a8000 | `f982f15e2d18dc25…` |

### Gaps / padding

- `0xa3f..0x4000` (13761 B): fill=0xFF
- `0x9c00..0xa000` (1024 B): fill=0xFF
- `0xa200..0xb000` (3584 B): fill=0xFF
- `0x11180..0x12000` (3712 B): fill=0xFF
- `0x17eb0..0x18000` (336 B): fill=0xFF
- `0x60a44..0x61000` (1468 B): fill=0xFF
- `0x28791f..0x288000` (1761 B): fill=0xFF
- `0xac9d6b..0xaca000` (661 B): fill=0xFF

### UNKNOWN tail (24 B @ 0x37a8000)

hex `31323334353637380a232046696c6520506172746974696f` ascii `'12345678\n# File Partitio'` — preserved verbatim, never interpreted.

## Partition / write map

- `CIS` <- cis.es loads (0x4000/0xA000): writecis
- `KEY_CUST/MISC/ADAS_CUST/ubi0` <- set_partition.es (no fatload): mtdparts + saveenv
- `IPL0` <- ipl.es: nand erase.part + nand write.e
- `IPL_CUST0/IPL_CUST1` <- ipl_cust.es: nand erase.part + nand write.e x2
- `UBOOT0/UBOOT1` <- uboot.es: nand erase.part + nand write.e x2
- `KERNEL/RECOVERY` <- kernel.es: nand erase.part + nand write.e x2
- `rootfs` <- rootfs.es: nand erase.part + nand write.e
- `ubi0 (erase)` <- ubi0.es section (no fatload): nand erase.part ubi0
- `ubi0:miservice` <- miservice.es: ubi create + ubi write
- `ubi0:customer` <- customer.es: ubi create + ubi write
- `MISC` <- misc.es: nand erase.part + nand write.e
- `ubi0:oneed_cust` <- oneed_cust.es: ubi create + ubi write

## Byte accounting

script 2623 + payload 58330878 + 0xFF pad 26307 + UNKNOWN tail 24 = 58359832 (check=True)
