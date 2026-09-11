# 02 — Boot, Kernel and Rootfs Differential

## Summary

The rootfs comparison is unusually informative:

```text
EN rootfs files: 528
VI rootfs files: 528
identical:       526
different:         2
```

Different files:

```text
bootconfig/bin/cardv
bootconfig/modules/4.9.227/sc7a20.ko
```

This means the VI release did **not** broadly replace the userspace OS.

## U-Boot

### EN

```text
timestamp: Mon Jul 31 12:04:40 2023
size: 297540 bytes
SHA-256: 7c64be8cb848af856a9f107139ee90765be4c3c3bdcd4eb49563839b57304490
```

### VI

```text
timestamp: Mon Aug 21 03:09:01 2023
size: 297540 bytes
SHA-256: 0e1e13409beaf77e680f5c9c5221ab21d796164dc926715e649ac52457102fd9
```

The load and entry addresses remain unchanged.

## Kernel

### EN

```text
timestamp: Mon Jul 31 12:08:22 2023
payload size: 2,255,135 bytes
SHA-256: c1fa8f7363615f1dc7d91f3308608d336fee6d89f5dcfe48e826bf4a399f5030
```

### VI

```text
timestamp: Wed Sep 20 08:38:27 2023
payload size: 2,255,137 bytes
SHA-256: 8261589e10474885277d59fea0a2ad02e079a5b94661a2f4f8f869be29364314
```

Both identify as Linux/ARM uImage, load/entry `0x20008000`.

## `cardv`

Both files are exactly 1,225,780 bytes, but have different Build IDs.

```text
EN BuildID: c668e5183db60fb7963c5bc14353aad581476345
VI BuildID: f3bcc090b8d2badd1b2146cf6abbe2dc17ef1a10
```

The source path embedded in EN references:

```text
/home/zac/work/project/c2m/...
```

VI references:

```text
/home/zac/project/c2m/...
```

### Important symbol delta

EN-only:

```text
Is_Gps_info(unsigned char*)
nmea_satinfo(...)
nema_calc_checksum(...)
g_zkw_gps_module
Camera.Menu.GSensorSensitivity
```

VI-only:

```text
nmea_BDGSV2info_na(...)
SendGPSSpeedToScreen(int)
Camera.Menu.GSensor
```

VI also contains additional power-control strings:

```text
echo 1 > /sys/devices/soc0/soc/soc:adc-keys/poweroff_ctrl
echo 3 > /sys/devices/soc0/soc/soc:adc-keys/poweroff_mode
system restar
```

### Why `cardv` matters to the ADAS regression

Both builds expose important screen and ADAS integration functions:

```text
SendADASInfoToScreen()
SendGPSInfoToScreen()
SendWifiStatusToScreen()
SendDisplayModeToScreen()
SendStorageInfoToScreen()
SendAudioRecordStatusToScreen()
SendBacklightLevelInfoToScreen()
DeviceSendMsgToScreenTask()
```

VI additionally exposes:

```text
SendGPSSpeedToScreen(int)
```

Thus `cardv` is not merely the recorder. It participates in device state, GPS and screen integration.

**Regression hypothesis:** an interface or timing change between VI `cardv` and the otherwise-similar ADAS stack may contribute to “ADAS not working”.

## SC7A20 accelerometer module

Both identify as:

```text
sc7a20 3-Axis Accelerometer driver
Silan Microelectronics
vermagic=4.9.227 SMP preempt mod_unload ARMv7 thumb2 p2v8
```

The binary differs:

```text
EN size 24196
VI size 24204
```

ADAS contains IMU-dependent logic (`use_imu_move=true`, harsh-warning/drive-state libraries). Therefore this module should be included in regression capture, but it is not yet proven causal.

## Customer kernel modules

A group of 4.9.227 modules are rebuilt/changed in VI, including:

```text
cdc_ether.ko
cfg80211.ko
ehci-hcd.ko
fat.ko
kdrv_sdmmc.ko
mii.ko
mmc_block.ko
mmc_core.ko
nls_utf8.ko
ntfs.ko
rndis_host.ko
usb-common.ko
usbcore.ko
usbnet.ko
vfat.ko
```

Their vermagic remains compatible with 4.9.227.

Do not assume the code changed materially just from the binary hash; some differences may be rebuild metadata/modversions. If a specific module becomes a suspect, compare `.text` and relocation contents with an ARM-aware ELF tool.

## Rootfs security observations

Common to both versions:

```text
busybox telnetd
interactive shell in inittab
root password hash
usb0 rule in mdev.conf
```

These should be preserved during reverse engineering and hardened only after stock-app/M4 dependencies are understood.
