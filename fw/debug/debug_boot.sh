#!/bin/sh
# Dedicated debug SSH launcher. Single-shot, low priority, fail-closed.
# Called from a standalone provision hook; never edit fw/d3 boot files here.
# Creates NOTHING: the supervisor's safe_dir owns its private run/config
# leaves (exact 0700); stock ancestors are never chmodded or created here.
# There is intentionally no once-guard and no retry loop: the supervisor's
# locked run dir (supervisor.lock) is the duplicate guard (a second copy
# exits already_running), and the supervisor itself retries AP readiness
# for 60 s inside its 20-minute window. A repeat hook call just re-execs
# into that lock. The supervisor enforces AP-only binding
# (192.168.1.1:2222 on wlan0, SO_BINDTODEVICE via -l wlan0) and key-only
# root auth. No routes, firewall rules, passwd/shadow/ssh changes,
# process-killer invocations, shells, or radio reconfiguration happen here.
umask 077

_bin=/customer/c2m/c2m-debug
_dropbear=/customer/c2m/dropbear
_dropbearkey=/customer/c2m/dropbearkey
_owner=/customer/c2m/debug_owner.pub
_nss=/customer/c2m/libnss_files.so.2

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

# Use only the pinned private copy of the stock glibc NSS module. Never
# include the stock group-writable /customer/ssh/lib directory.
[ -f "$_nss" ] && [ ! -L "$_nss" ] || exit 0
export LD_LIBRARY_PATH=/customer/c2m:/lib

# Detached low-priority supervisor. It re-validates everything, generates
# the persistent hostkey on first boot only, and stops after 20 minutes.
if command -v nice >/dev/null 2>&1; then
    nice -n 10 "$_bin" --serve >/dev/null 2>&1 &
else
    "$_bin" --serve >/dev/null 2>&1 &
fi
exit 0
