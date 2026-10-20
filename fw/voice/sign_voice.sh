#!/bin/sh
# D4 offline area-sign C2M speaker advisory. Detached, fail-closed.
#
# Reads the fixed, sanitized /tmp/c2m_d4_status snapshot produced by c2m-signs.
# Plays at most one owner-supplied Vietnamese WAV per new D4 event_id through
# cardv's stock FIFO:
#
#   audioplay 0 dev0 /customer/c2m/Sign_Residential_Start.wav
#   audioplay 0 dev0 /customer/c2m/Sign_Residential_End.wav
#
# Flag 0 is deliberately the waiting form: a sign advisory is lower priority
# than stock ADAS audio and must not cut the shared decoder.  The trade-off is
# that the advisory can be delayed until the current stock playback finishes.
# The D4 scope does not claim an atomic priority broker; no advertising,
# vehicle control, CAN, UART, network, ISP/AE access or second GPS reader is
# used here.  The WAVs are spoken reminders only, not legal sign confirmation.
#
# The camera's BusyBox v1.20.2 timeout takes `-t SECS`; this script uses the
# same bounded syntax detection as boot_voice.sh and never blocks forever.
umask 077

_dir=/customer/c2m
_fifo=/tmp/cardv_fifo
_status=/tmp/c2m_d4_status
_voice_status=/tmp/c2m_sign_voice_status
_voice_log=/tmp/c2m_sign_voice.log
_lock=/tmp/c2m-sign-voice.lock
_start_wav="$_dir/Sign_Residential_Start.wav"
_end_wav="$_dir/Sign_Residential_End.wav"
_stale_s=3
_interval=1

# ---------------------------------------------------------------------------
# One instance only; remove a stale lock left by SIGKILL.
# ---------------------------------------------------------------------------
_acquire_lock() {
    if [ -d "$_lock" ] && [ ! -L "$_lock" ]; then
        _oldpid=$(cat "$_lock/pid" 2>/dev/null)
        case "$_oldpid" in
            ''|*[!0-9]*) _oldpid=0 ;;
        esac
        if [ "$_oldpid" -gt 0 ] && kill -0 "$_oldpid" 2>/dev/null; then
            return 1
        fi
        rm -rf "$_lock" 2>/dev/null
    fi
    [ ! -e "$_lock" ] && [ ! -L "$_lock" ] || return 1
    mkdir "$_lock" 2>/dev/null || return 1
    printf '%s\n' "$$" > "$_lock/pid" 2>/dev/null
    return 0
}

_acquire_lock || exit 0
trap 'rm -rf "$_lock" 2>/dev/null' 0
trap 'rm -rf "$_lock" 2>/dev/null; exit 0' 1 2 15

# ---------------------------------------------------------------------------
# Bounded FIFO write: BusyBox `timeout -t SECS`, coreutils `timeout SECS`.
# ---------------------------------------------------------------------------
_timeout_style=unknown
_timeout_init() {
    if ! command -v timeout >/dev/null 2>&1; then
        _timeout_style=none
        return 0
    fi
    if timeout -t 1 true >/dev/null 2>&1; then
        _timeout_style=busybox
    elif timeout 1 true >/dev/null 2>&1; then
        _timeout_style=coreutils
    else
        _timeout_style=none
    fi
}

_timeout_run() {
    _tr_secs=$1
    shift
    case "$_timeout_style" in
        busybox)
            timeout -t "$_tr_secs" "$@"
            ;;
        coreutils)
            timeout "$_tr_secs" "$@"
            ;;
        *)
            "$@" &
            _tr_pid=$!
            _tr_n=0
            while [ "$_tr_n" -lt "$_tr_secs" ]; do
                kill -0 "$_tr_pid" 2>/dev/null || break
                sleep 1
                _tr_n=$((_tr_n + 1))
            done
            if kill -0 "$_tr_pid" 2>/dev/null; then
                kill "$_tr_pid" 2>/dev/null
                wait "$_tr_pid" 2>/dev/null
                return 124
            fi
            wait "$_tr_pid" 2>/dev/null
            return $?
            ;;
    esac
}

_timeout_init

# ---------------------------------------------------------------------------
# Fixed status/log output.  Never include coordinates or raw status rows.
# ---------------------------------------------------------------------------
_emit() {
    _stamp=$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null)
    [ -n "$_stamp" ] || _stamp=unknown
    printf '%s %s\n' "$_stamp" "$1" > "$_voice_status" 2>/dev/null
    printf '%s %s\n' "$_stamp" "$1" >> "$_voice_log" 2>/dev/null
}

_emit "monitor=started"

# Read one exact fixed-key field from the D4 snapshot.  Keys are literals in
# this script; no status text is evaluated as shell code.
_field() {
    sed -n "s/^$1=//p" "$_status" 2>/dev/null | head -n 1
}

_age_s() {
    _now=$(date +%s 2>/dev/null) || return 1
    _mtime=$(stat -c %Y "$_status" 2>/dev/null) || return 1
    case "$_now$_mtime" in
        ''|*[!0-9]*) return 1 ;;
    esac
    [ "$_now" -ge "$_mtime" ] || return 1
    printf '%s\n' "$((_now - _mtime))"
}

_event_wav() {
    case "$1" in
        residential_start) printf '%s\n' "$_start_wav" ;;
        residential_end) printf '%s\n' "$_end_wav" ;;
        *) return 1 ;;
    esac
}

_play() {
    _wav=$1
    [ -f "$_wav" ] && [ ! -L "$_wav" ] || return 1
    [ -p "$_fifo" ] || return 1
    _timeout_run 5 sh -c 'printf "audioplay 0 dev0 %s\n" "$1" > "$2"' \
        sh "$_wav" "$_fifo" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Poll only the fixed D4 snapshot.  Active is cleared by D4 on stop/stale/
# no-DB; this script does not keep a latched warning after the producer goes
# away.  A new event_id is the only trigger, so the 5 s D4 hold cannot repeat
# the same phrase.
# ---------------------------------------------------------------------------
_last_id=0
while :; do
    if [ -f "$_status" ] && [ ! -L "$_status" ]; then
        _age=$(_age_s) || _age=999
        if [ "$_age" -le "$_stale_s" ]; then
            _state=$(_field state)
            _gps=$(_field gps_fresh)
            _active=$(_field active)
            _code=$(_field code)
            _eid=$(_field event_id)
            case "$_eid" in
                ''|*[!0-9]*) _eid=0 ;;
            esac
            if [ "$_state" = ready ] && [ "$_gps" = 1 ] &&
               [ "$_active" = 1 ] && [ "$_eid" -gt 0 ]; then
                if [ "$_eid" != "$_last_id" ]; then
                    _wav=$(_event_wav "$_code") || _wav=
                    if [ -n "$_wav" ] && _play "$_wav"; then
                        _last_id=$_eid
                        _emit "event=$_eid code=$_code advisory=played"
                    else
                        _emit "event=$_eid code=$_code advisory=play-failed"
                    fi
                fi
            fi
        fi
    fi
    sleep "$_interval"
done
