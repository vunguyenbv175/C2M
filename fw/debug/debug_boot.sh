#!/bin/sh
# Dedicated debug SSH launcher. Detached, low priority, fail-closed.
# Called from a standalone provision hook; never edit fw/d3 boot files here.
# Does nothing when the owner key or Dropbear assets are missing/invalid.
# The supervisor enforces the 20-minute listener window, AP-only binding
# (192.168.1.1:2222 on wlan0, SO_BINDTODEVICE via -l wlan0) and key-only
# root auth. No routes, firewall rules, passwd/shadow/ssh changes,
# pkill/killall, shells, or radio reconfiguration happen here.
umask 077
_once=/tmp/c2m-debug-start.once
[ ! -e "$_once" ] && [ ! -L "$_once" ] || exit 0
mkdir "$_once" 2>/dev/null || exit 0

_bin=/customer/c2m/c2m-debug
_dropbear=/customer/c2m/dropbear
_dropbearkey=/customer/c2m/dropbearkey
_owner=/customer/c2m/debug_owner.pub
_run=/tmp/c2m-debug
_cfg=/customer/minieye/config/.c2m-debug

# Fixed production assets only; refuse links and non-executables.
[ -f "$_bin" ] && [ ! -L "$_bin" ] || exit 0
[ -x "$_bin" ] || exit 0
[ -f "$_dropbear" ] && [ ! -L "$_dropbear" ] || exit 0
[ -x "$_dropbear" ] || exit 0
[ -f "$_dropbearkey" ] && [ ! -L "$_dropbearkey" ] || exit 0
[ -x "$_dropbearkey" ] || exit 0
# Owner key must exist and look like a single ssh-ed25519 line.
# Full validation happens in the supervisor; this is only a presence gate.
[ -f "$_owner" ] && [ ! -L "$_owner" ] || exit 0
grep -qs '^ssh-ed25519 [A-Za-z0-9+/]\{68\}\( [!-~]\{1,256\}\)\?$' "$_owner" || exit 0

# Private dirs only; never create ancestors or follow links.
[ ! -L "$_run" ] || exit 0
[ ! -L "$_cfg" ] || exit 0
[ -d /customer/minieye/config ] && [ ! -L /customer/minieye/config ] || exit 0
mkdir -p "$_run" "$_cfg" 2>/dev/null || exit 0
chmod 700 "$_run" "$_cfg" 2>/dev/null || exit 0

# Detached low-priority supervisor. It re-validates everything, generates
# the persistent hostkey on first boot only, and stops after 20 minutes.
if command -v nice >/dev/null 2>&1; then
    nice -n 10 "$_bin" --serve >/dev/null 2>&1 &
else
    "$_bin" --serve >/dev/null 2>&1 &
fi
exit 0
