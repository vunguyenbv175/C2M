#!/bin/sh
# Candidate F boot voice advisory. Detached, one-shot, fail-closed.
#
# Plays the owner-requested Vietnamese greeting through cardv's own stock
# `audioplay 1 dev0 <absolute wav>` FIFO command, then reads the ambient
# light estimate from c2m-light (stock ISP AE LVx10, read-only) and plays
# exactly one light reminder:
#   dark   -> Light_Dark_TurnOn.wav   ("Bật đèn xe")
#   bright -> Light_Bright_TurnOff.wav ("Tắt đèn khi trời sáng")
#
# This script NEVER changes a car circuit.  The camera has no verified
# headlight output; the wavs are spoken reminders only.
#
# Called detached before the stock mount-wait block from wifi/rcInsDriver.sh;
# it must never delay or fail the stock boot path.
umask 077

_dir=/customer/c2m
_fifo=/tmp/cardv_fifo
_status=/tmp/c2m_voice_status
_once=/tmp/c2m-voice-start.once
_greeting="$_dir/Boot_Greeting.wav"
_dark_wav="$_dir/Light_Dark_TurnOn.wav"
_bright_wav="$_dir/Light_Bright_TurnOff.wav"
_light_bin="$_dir/c2m-light"
_threshold=500

_status_write() {
    printf '%s\n' "$1" > "$_status" 2>/dev/null
}

# One attempt per boot; /tmp is a tmpfs boot artifact.
[ ! -e "$_once" ] && [ ! -L "$_once" ] || exit 0
mkdir "$_once" 2>/dev/null || exit 0

[ -f "$_greeting" ] && [ ! -L "$_greeting" ] || {
    _status_write "greeting=missing"
    exit 0
}

# The FIFO is created by stock cardv.  Wait for it without blocking boot.
_n=0
while [ "$_n" -lt 15 ]; do
    if [ -p "$_fifo" ]; then
        break
    fi
    sleep 1
    _n=$((_n + 1))
done
if [ ! -p "$_fifo" ]; then
    _status_write "fifo=missing"
    exit 0
fi

# A dead cardv can leave the FIFO inode behind without a reader; never hang
# forever on the write.  `timeout` is a stock BusyBox applet; when unavailable
# the write falls back to the stock scripts' plain redirect.
_fifo_write() {
    if command -v timeout >/dev/null 2>&1; then
        timeout 5 sh -c 'printf "audioplay 1 dev0 %s\n" "$1" > "$2"' sh "$1" "$2"
    else
        printf 'audioplay 1 dev0 %s\n' "$1" > "$2"
    fi
}

_play() {
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    _fifo_write "$1" "$_fifo" 2>/dev/null || return 1
    return 0
}

_play "$_greeting" || {
    _status_write "greeting=play-failed"
    exit 0
}
_status_write "greeting=played"

# The greeting is about 2.0 s at 24 kHz; give the decoder a clean gap before
# the light query and the advisory.
sleep 3

if [ ! -x "$_light_bin" ] || [ -L "$_light_bin" ]; then
    _status_write "greeting=played light=unavailable"
    exit 0
fi
_reading=$("$_light_bin" --threshold "$_threshold" 2>/dev/null)
if [ $? -ne 0 ]; then
    _status_write "greeting=played light=unknown"
    exit 0
fi

case "$_reading" in
    state=dark*)
        _advisory="$_dark_wav"
        _state=dark
        ;;
    state=bright*)
        _advisory="$_bright_wav"
        _state=bright
        ;;
    *)
        _status_write "greeting=played light=invalid output=$_reading"
        exit 0
        ;;
esac

_play "$_advisory" || {
    _status_write "greeting=played light=$_reading advisory=play-failed"
    exit 0
}
_status_write "greeting=played light=$_reading advisory=played"
exit 0
