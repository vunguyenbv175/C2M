#!/bin/sh
# Candidate F boot voice advisory. Detached, one-shot, fail-closed.
#
# Plays the owner-requested Vietnamese greeting through cardv's own stock
# `audioplay 1 dev0 <absolute wav>` FIFO command, then plays exactly one light
# reminder:
#   dark   -> Light_Dark_TurnOn.wav   ("Bật đèn xe")
#   bright -> Light_Bright_TurnOff.wav ("Tắt đèn khi trời sáng")
#
# Default light source: the stock C2M display day/night schedule
# (06:00:01..17:59:59, the same boundary used by SendDisplayModeToScreenv).
# The camera exposes no shell-readable ambient sensor state.  c2m-light is an
# optional, read-only stock-ISP AE helper; it is NOT called unless the owner
# has manually validated it on the device and created
# /customer/c2m/AE_LIGHT_ENABLE.  Until then the stock schedule is used so
# the advisory still works and no second ISP client is opened at boot.
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
_ae_enable="$_dir/AE_LIGHT_ENABLE"
_threshold=500

_status_write() {
    printf '%s\n' "$1" > "$_status" 2>/dev/null
}

_clock_state() {
    _h=$(date +%H 2>/dev/null) || return 1
    _m=$(date +%M 2>/dev/null) || return 1
    _s=$(date +%S 2>/dev/null) || return 1
    case "$_h$_m$_s" in
        ''|*[!0-9]*) return 1 ;;
    esac
    case "$_h" in
        06)
            # Stock day window starts at 06:00:01, not 06:00:00.
            if [ "$_m" = 00 ] && [ "$_s" = 00 ]; then
                printf 'dark\n'
            else
                printf 'bright\n'
            fi
            ;;
        0[7-9]|1[0-7])
            printf 'bright\n'
            ;;
        *)
            printf 'dark\n'
            ;;
    esac
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

# Optional AE path, intended for a manually validated build only.  Bounded so
# a broken vendor library can never hold the detached hook forever.  The
# helper is a separate process; it is never started unless the explicit
# AE_LIGHT_ENABLE marker was created after a hardware test.
_state=
_source=
_detail=
if [ -f "$_ae_enable" ] && [ ! -L "$_ae_enable" ] &&
   [ -x "$_light_bin" ] && [ ! -L "$_light_bin" ] &&
   command -v timeout >/dev/null 2>&1; then
    _reading=$(timeout 10 "$_light_bin" --threshold "$_threshold" 2>/dev/null)
    case "$_reading" in
        state=dark*)
            _state=dark
            _source=ae
            _detail=$_reading
            ;;
        state=bright*)
            _state=bright
            _source=ae
            _detail=$_reading
            ;;
    esac
fi

if [ -z "$_state" ]; then
    _state=$(_clock_state 2>/dev/null)
    case "$_state" in
        dark|bright)
            _source=theme
            _detail="schedule=06:00:01-17:59:59"
            ;;
        *)
            _status_write "greeting=played light=unknown"
            exit 0
            ;;
    esac
fi

case "$_state" in
    dark) _advisory="$_dark_wav" ;;
    bright) _advisory="$_bright_wav" ;;
    *)
        _status_write "greeting=played light=invalid detail=$_detail"
        exit 0
        ;;
esac

_play "$_advisory" || {
    _status_write "greeting=played light=$_state source=$_source detail=$_detail advisory=play-failed"
    exit 0
}
_status_write "greeting=played light=$_state source=$_source detail=$_detail advisory=played"
exit 0
