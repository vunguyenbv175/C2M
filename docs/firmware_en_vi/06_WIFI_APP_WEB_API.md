# 06 — Wi-Fi, Stock App, Web and Network

## Stock design

The firmware contains both AP and STA scripts.

`apsta_switch.sh` explicitly switches modes:

```text
AP -> stop AP -> start STA
STA -> stop STA -> start AP
```

Therefore the **stock software design is AP XOR STA**, not simultaneous AP+STA.

This does not prove the RTL8821CS hardware/driver cannot do concurrency.

## Driver

The customer image contains:

```text
wifi/lib/8821cs.ko
cfg80211.ko
iw
hostapd
wpa_supplicant config
```

The enhancement project may later test concurrent virtual interfaces, but stock behavior must be preserved first.

## AP mode

`ap.sh`:
- brings `wlan0` up,
- assigns AP address,
- starts `udhcpd`,
- starts `hostapd`.

## STA mode

`sta.sh`:
- loads cfg80211 / Wi-Fi module,
- configures wpa_supplicant,
- runs DHCP,
- stores STA address with `nvconf`,
- starts goahead.

## Stock app compatibility

Keep stock app behavior untouched during early enhancement.

Do not modify:
- discovery,
- SSID rules,
- DHCP assumptions,
- stock web/CGI ports,
- clip indexing,
- recording file layout.

## EN vs VI CGI delta

Default CGI config changes:

```text
EN: Camera.Menu.SpeedUnit=MPH
VI: Camera.Menu.SpeedUnit=KM/H
```

Both still have:

```text
Camera.Menu.SpeedLimit=OFF
Camera.Menu.SpeedCamAlert=OFF
Camera.Menu.Edog=ON
```

This proves `_VI` includes region-specific defaults, but these menu fields are not equivalent to ADAS `--enable_tsr`.

## G-sensor CGI delta

`CGI_PROCESS.sh` changes one write:

```text
EN:
nvconf set 0 Camera.Menu.GSensorSensitivity $1

VI:
nvconf set 0 Camera.Menu.GSensor $1
```

The default/config schema should be traced to ensure this rename is consistent across producer and consumer code.

## Enhanced web architecture

Recommended:

```text
stock app -> untouched stock services

browser/PWA -> new independent c2m-web service
```

Initial web scope:

```text
status
settings
diagnostics
logs
firmware/model/data update
```

Avoid claiming port 8088 or any other port until the live device socket map is captured.
