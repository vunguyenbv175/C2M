#!/bin/sh
# Isolated D4 advisory. c2m-signs itself has no stock playback, IPC, UART or
# network control. The optional separate sign_voice.sh bridge consumes only
# the fixed D4 status and uses cardv's FIFO for a bounded spoken advisory.
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
# Optional C2M speaker bridge; it is a separate process and cannot delay D4.
if [ -f /customer/c2m/sign_voice.sh ] &&
   [ ! -L /customer/c2m/sign_voice.sh ] &&
   [ -r /customer/c2m/sign_voice.sh ]; then
    if command -v nice >/dev/null 2>&1; then
        nice -n 10 /bin/sh /customer/c2m/sign_voice.sh >/dev/null 2>&1 &
    else
        /bin/sh /customer/c2m/sign_voice.sh >/dev/null 2>&1 &
    fi
fi
exit 0
