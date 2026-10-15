#!/bin/sh
# Isolated D4 advisory. No stock playback, IPC, UART or network control.
# Called detached after D3 service launch; never delay the stock boot hook.
umask 077
_once=/tmp/c2m-d4-start.once
[ ! -e "$_once" ] && [ ! -L "$_once" ] || exit 0
mkdir "$_once" 2>/dev/null || exit 0
[ -f /customer/c2m/c2m-signs ] && [ ! -L /customer/c2m/c2m-signs ] || exit 0
[ -x /customer/c2m/c2m-signs ] || exit 0
# The daemon handles missing/invalid GPS or private DB by publishing inactive.
# It never opens the SD card, and all high-frequency status writes stay in tmp.
if command -v nice >/dev/null 2>&1; then
    nice -n 10 /customer/c2m/c2m-signs --serve >/dev/null 2>&1 &
else
    /customer/c2m/c2m-signs --serve >/dev/null 2>&1 &
fi
exit 0
