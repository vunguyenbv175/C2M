#!/bin/sh
# Isolated D3 services. Called in the existing bounded background mount waiter.
# Never switch stock Wi-Fi modes, load modules, open UARTs or control cardv.
# Settings stay in the stock-updater-preserved config directory, privately.
umask 077
_run=/tmp/c2m-d3
_cfg=/customer/minieye/config/.c2m-d3
_log=/mnt/mmc/C2M_DIAG

# Refuse foreign objects; repeat hook execution cannot start duplicate services.
[ ! -e /tmp/c2m-d3-start.once ] && [ ! -L /tmp/c2m-d3-start.once ] || exit 0
mkdir /tmp/c2m-d3-start.once 2>/dev/null || exit 0
[ ! -L "$_run" ] && [ ! -L "$_cfg" ] || exit 0
[ -d /customer/minieye/config ] && [ ! -L /customer/minieye/config ] || exit 0
mkdir -p "$_run" "$_cfg" || exit 0
chmod 700 "$_run" "$_cfg" || exit 0

# Presence-only inventory. Do not invoke hciattach/hciconfig/rfkill or radio up.
/bin/sh /customer/c2m/connectivity_probe.sh > "$_run/bluetooth.txt" 2>/dev/null
if grep -qs ' /mnt/mmc ' /proc/mounts; then
    [ ! -L "$_log" ] && mkdir -p "$_log" &&
        [ ! -L "$_log/bluetooth-D3.txt" ] &&
        cp "$_run/bluetooth.txt" "$_log/bluetooth-D3.txt"
fi

# No automatic STA association on boot. Controller waits for an explicit web
# connect request; it must prove concurrent capability and retain stock AP.
# The bundled supplicant is required; absent executable means explicit status,
# never a call to the stock AP<->STA exclusive switch.
/customer/c2m/c2m-wifi --serve --config-dir "$_cfg" --run-dir "$_run" \
    --supplicant /customer/c2m/wpa_supplicant \
    --status-file /tmp/c2m_wifi_status >/dev/null 2>&1 &

# The web server binds only after validating wlan0 AP mode/address. Retry only
# our listener while AP startup settles; never restart or reconfigure AP.
( _n=0
  while [ "$_n" -lt 30 ]; do
      /customer/c2m/c2m-web --config-dir "$_cfg" --run-dir "$_run" \
          --status-file /tmp/c2m_wifi_status && break
      _n=$((_n + 1))
      sleep 2
  done
) >/dev/null 2>&1 &
exit 0
