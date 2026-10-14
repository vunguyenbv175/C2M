# D3 implementation — current work, not hardware-validated

Owner requested pulling ChatGPT D3 design and implementation, then added:
passive Bluetooth presence check, concurrent AP+STA priority, and a Wi-Fi
configuration page. Imported `feature/d3-tsr-events-20261014` through b97a531.

## Real new components (no mock transport)

- Native Vietnamese web configuration service `fw/d3/web.c`, separate port
  8099, validated AP address on wlan0 only. Stock GoAhead/app is unchanged.
  Save WPA2 network, explicitly request connection, forget saved network,
  inspect controller status. Host-only loopback mode is explicit. No recorder,
  reset, upgrade or nvconf endpoints.
- Random per-process CSRF protection, exact Host/Origin, bounded HTTP requests,
  private mode-0700 directories and atomically published mode-0600 config.
  SSID hex + derived WPA2 PSK; passwords are not command-line/log/API output.
  HTTP is local/plaintext: use only trusted camera AP, not a public endpoint.
- Native Wi-Fi controller `fw/d3/wifi_control.c`. Uses nl80211 actual interface
  combination advertisement, requires one AP and managed interface in the
  SAME combination. Creates only its own `c2msta0`, same radio/channel as AP,
  never invokes stock exclusive mode switch or takes wlan0 down. No automatic
  association on boot. Association is not yet an Internet claim: DHCP support
  is explicitly missing in this first source checkpoint.
- AP+STA advertisement is a permission gate, NOT successful concurrent radio
  operation. Missing/malformed proof blocks rather than switching to STA-only.
  One-channel constraint requires upstream hotspot/router on camera AP channel.
- EN has `sta.sh` references but no supplicant executable was found in the
  inspected rootfs/customer inventory. D3 builds its own pinned upstream
  WPA2/nl80211 supplicant (2.12) with static libnl; stock hostapd untouched.
  Build/stock-loader tests must pass before it is a usable package.
- Passive Bluetooth presence probe after mount. Saves
  `C2M_DIAG/bluetooth-D3.txt`. HCI presence is reported as kernel exposure, not
  successful radio/physical-board test. Missing HCI is not hardware absence.
  No pairing, scans, UART attach, radio activation or module changes.
- D2 TSR flags and exact C Vietnamese audio remain unchanged. No new detector,
  screen adapter, GPS database/audio warning daemon is claimed in this source.

## GPS static correction (important)

Independently disassembled EN cardv and libIPC_msg: the previous informal GPS
report had wrong file offset and coordinate interpretation. The actual writer
at Thumb 0x76234 copies 0x1c0 bytes to carInfo+0x330 and passes file offset
0x330, length 0x1c8 to IPC_CarInfo_Write_PartInfo. Reader uses only known
0x1c0 bytes at offset 0x330, not offset zero. The latitude/longitude doubles
are signed NMEA DDMM, NOT decimal degrees; explicit conversion is needed.
RMC year is since 1900, month is zero-based. Speed is km/h.

`fw/d3/gps_snapshot.c` provides bounded read-only pread/double-read, strict
calendar/DDMM/fix validation and monotonic advancing-UTC freshness tests.
This is reusable code, not deployed GPS advisory yet. It never opens UART or
calls vendor read/write IPC helpers. Private instruction evidence is in
`build/d3-contract-review/`; no firmware bytes are committed.

## Build status and preservation

Manual pipeline `firmware-candidateD3.yml` reuses pinned EN/C audio, no-op and
mutated customer gates, ELF ABI and stock-rootfs QEMU gates, new Linux web and
controller tests, passive probe under exact BusyBox, deep full-package diff.
Gates are fail-closed. Firmware and dependencies stay in private vault;
public artifacts are explicit reports/hashes/source only.

D3 installs flat `/customer/c2m` services plus D2 profile and existing idle.
Private settings are under `/customer/minieye/config/.c2m-d3/`, which is inside
stock updater's backed-up/restored config path; never `/config` edits.
Existing vendor UID1001/mode0775 config ancestors remain unchanged and part of
stock trust boundary. D3 owns only root-private child and temporary run dir.

Token `20261014000005` reserved, not on-card/flash-proven. Recording card must
NOT receive updater payload. No camera, UART, FIFO or recording-card write has
been authorized/performed by this D3 work. D2 field status shows applied config,
not successful TSR recognition.

Acceptance pending: completed ARM/supplicant/Linux gates, owner flash approval
on correct 32GB flash card, web access while stock app/recording work, actual
Bluetooth presence report, guarded concurrent association then verified IP/
Internet, native TSR detection/output. No database points as legal speed state.
