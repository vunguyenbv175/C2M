#!/bin/sh
# C2M D3 passive Wi-Fi / Bluetooth inventory. No mode changes or pairing.
# Run on the camera with authorization; keep output private.
# POSIX/BusyBox shell. Optional tools may be missing.

section() { printf '\n=== %s ===\n' "$1"; }
run() {
    printf '$ %s\n' "$*"
    if command -v "$1" >/dev/null 2>&1; then
        "$@" 2>&1 || printf '(command unavailable/failed)\n'
    else
        printf '(not installed)\n'
    fi
}
section "kernel"
run uname -a
section "network link state"
run ip -o link show
run ip -4 addr show
run ip route show
section "wifi radio capabilities"
run iw dev
run iw list
section "wireless counters"
if [ -r /proc/net/wireless ]; then cat /proc/net/wireless; else echo "(unavailable)"; fi
section "relevant loaded modules"
if [ -r /proc/modules ]; then
    grep -Ei '8821|88.*cs|cfg80211|bluetooth|hci_uart|btusb|rtk_bt' /proc/modules || echo "(none matched)"
else
    echo "(unavailable)"
fi
section "wireless processes (names/status for research)"
if command -v ps >/dev/null 2>&1; then
    # This may include arguments and identifiers; save privately, do not post raw.
    ps 2>/dev/null | grep -Ei 'hostapd|wpa_supplicant|udhcp|bluetoothd|hciattach|rtk_hci' |
        cut -c 1-160 || :
else
    echo "(ps unavailable)"
fi
section "HCI device presence"
if [ -d /sys/class/bluetooth ]; then
    for p in /sys/class/bluetooth/*; do
        [ -e "$p" ] && printf 'HCI class entry: %s\n' "$p"
    done
else
    echo "(no /sys/class/bluetooth)"
fi
run hciconfig -a
section "UART tty nodes (names only)"
for p in /dev/ttyS* /dev/ttyAMA* /dev/ttyUSB*; do
    [ -e "$p" ] && printf '%s\n' "$p"
done
section "Wi-Fi/BT relevant boot logs (last 40 matching lines)"
if command -v dmesg >/dev/null 2>&1; then
    dmesg 2>/dev/null | grep -Ei '8821|cfg80211|wlan|bluetooth|hci|realtek|rtl' | tail -n 40 || :
fi
section "END: passive inventory, no network configuration changed"
