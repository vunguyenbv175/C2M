#!/bin/sh
# Candidate F boot voice + day/night transition advisory.  Detached, one-shot
# boot phase plus one detached transition monitor.  Fail-closed.
#
# Boot: plays the owner-requested Vietnamese greeting through cardv's own stock
# `audioplay 1 dev0 <absolute wav>` FIFO command, then exactly one light
# reminder:
#   dark   -> Light_Dark_TurnOn.wav   ("Bat den xe")
#   bright -> Light_Bright_TurnOff.wav ("Tat den khi troi sang")
#
# Monitor: after boot it checks the local clock every 30 s and plays the same
# reminder once whenever the day/night state changes, so a transition while
# driving is announced too.  The monitor uses the stock clock schedule only;
# it never opens a second ISP client.
#
# Default local time is UTC+7 (Vietnam), because this C2M unit runs its clock in
# UTC.  The stock C2M display schedule is 06:00:01..17:59:59 local.  An optional
# one-line file /customer/c2m/voice_tz_offset can override the offset, e.g. `0`
# when the camera clock has already been set to local time.  Valid range -12..14.
#
# The optional c2m-light AE helper remains manual-only.  It is called only at
# boot when /customer/c2m/AE_LIGHT_ENABLE exists.  The periodic monitor never
# calls it, because a second ISP client during driving is not proven safe.
#
# This script NEVER changes a car circuit.  The camera has no verified
# headlight output; the wavs are spoken reminders only.
#
# The C2M stock BusyBox v1.20.2 `timeout` takes `-t SECS` (not coreutils
# `timeout SECS`).  The old `timeout 5` form failed immediately with
# "can't execute '5'", which produced greeting=play-failed and no advisory.
# _timeout_init detects the local syntax and keeps a watchdog fallback.
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
_tz_file="$_dir/voice_tz_offset"
_tz_default=7
_threshold=500
_monitor_lock=/tmp/c2m-light-monitor.lock
_monitor_status=/tmp/c2m_light_monitor_status
_monitor_log=/tmp/c2m_light_monitor.log
_monitor_interval=30

_mode=boot
_no_monitor=0
_seed_state=
_seed_played=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --monitor-only)
            _mode=monitor
            shift
            _seed_state=${1:-}
            [ "$#" -gt 0 ] && shift
            _seed_played=${1:-0}
            [ "$#" -gt 0 ] && shift
            ;;
        --no-monitor)
            _no_monitor=1
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Bounded command runner.  BusyBox timeout: `timeout -t SECS PROG ...`
# coreutils timeout: `timeout SECS PROG ...`
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
# Time / day-night state.
# POSIX TZ reverses the sign: TZ=UTC-7 is UTC+7.
# ---------------------------------------------------------------------------
_tz_get() {
    _tzv=$_tz_default
    if [ -f "$_tz_file" ] && [ ! -L "$_tz_file" ]; then
        _tzraw=
        read -r _tzraw < "$_tz_file" 2>/dev/null
        _tzraw=$(printf '%s' "$_tzraw" | tr -d '\r' 2>/dev/null)
        case "$_tzraw" in
            ''|*[!0-9+-]*)
                ;;
            *)
                _tznum=${_tzraw#+}
                case "$_tznum" in
                    -[0-9]|-[1-9][0-9]|[0-9]|[1-9][0-9])
                        if [ "$_tznum" -ge -12 ] && [ "$_tznum" -le 14 ]; then
                            _tzv=$_tznum
                        fi
                        ;;
                esac
                ;;
        esac
    fi
    printf '%s\n' "$_tzv"
}

_tz_string() {
    _tzoff=$(_tz_get)
    if [ "$_tzoff" -eq 0 ]; then
        printf 'UTC0\n'
    elif [ "$_tzoff" -gt 0 ]; then
        printf 'UTC-%s\n' "$_tzoff"
    else
        printf 'UTC+%s\n' "$((0 - _tzoff))"
    fi
}

_local_stamp() {
    _tzs=$(_tz_string)
    TZ="$_tzs" date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null
}

_clock_state() {
    _tzs=$(_tz_string)
    _h=$(TZ="$_tzs" date +%H 2>/dev/null) || return 1
    _m=$(TZ="$_tzs" date +%M 2>/dev/null) || return 1
    _s=$(TZ="$_tzs" date +%S 2>/dev/null) || return 1
    case "$_h$_m$_s" in
        ''|*[!0-9]*)
            return 1
            ;;
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

# ---------------------------------------------------------------------------
# Stock cardv FIFO playback.
# ---------------------------------------------------------------------------
_status_write() {
    printf '%s\n' "$1" > "$_status" 2>/dev/null
}

_fifo_write() {
    _wav=$1
    [ -p "$_fifo" ] || return 1
    _timeout_run 5 sh -c 'printf "audioplay 1 dev0 %s\n" "$1" > "$2"' \
        sh "$_wav" "$_fifo" 2>/dev/null
}

_play() {
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    _fifo_write "$1" || return 1
    return 0
}

_play_retry() {
    _pr_wav=$1
    _pr_tries=${2:-4}
    _pr_i=0
    while [ "$_pr_i" -lt "$_pr_tries" ]; do
        if _play "$_pr_wav"; then
            return 0
        fi
        _pr_i=$((_pr_i + 1))
        [ "$_pr_i" -lt "$_pr_tries" ] && sleep 2
    done
    return 1
}

_advisory_wav() {
    case "$1" in
        dark)
            printf '%s\n' "$_dark_wav"
            ;;
        bright)
            printf '%s\n' "$_bright_wav"
            ;;
        *)
            return 1
            ;;
    esac
}

_play_advisory() {
    _pa_wav=$(_advisory_wav "$1") || return 1
    _play "$_pa_wav"
}

# ---------------------------------------------------------------------------
# Monitor log / status.
# ---------------------------------------------------------------------------
_monitor_log() {
    _ml_msg=$1
    _ml_stamp=$(_local_stamp)
    [ -n "$_ml_stamp" ] || _ml_stamp=unknown
    printf '%s %s\n' "$_ml_stamp" "$_ml_msg" > "$_monitor_status" 2>/dev/null
    printf '%s %s\n' "$_ml_stamp" "$_ml_msg" >> "$_monitor_log" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Detached transition monitor.  It is started by the boot phase and also
# supports --monitor-only so it can be tested/restarted over SSH.
# ---------------------------------------------------------------------------
_monitor_main() {
    if ! mkdir "$_monitor_lock" 2>/dev/null; then
        _oldpid=$(cat "$_monitor_lock/pid" 2>/dev/null)
        if [ -n "$_oldpid" ] && kill -0 "$_oldpid" 2>/dev/null; then
            exit 0
        fi
        rm -rf "$_monitor_lock" 2>/dev/null
        mkdir "$_monitor_lock" 2>/dev/null || exit 0
    fi
    printf '%s\n' "$$" > "$_monitor_lock/pid" 2>/dev/null
    trap 'rm -rf "$_monitor_lock" 2>/dev/null' EXIT INT TERM

    _last=$_seed_state
    _retry=$_seed_played
    _monitor_log "monitor=start seed=${_last:-none} retry=${_retry:-0} tz=$(_tz_get) interval=${_monitor_interval}s"

    while :; do
        _now=$(_clock_state 2>/dev/null)
        case "$_now" in
            dark|bright)
                ;;
            *)
                sleep "$_monitor_interval"
                continue
                ;;
        esac

        if [ ! -p "$_fifo" ]; then
            _monitor_log "monitor=fifo-missing state=$_now"
            sleep "$_monitor_interval"
            continue
        fi

        if [ -z "$_last" ]; then
            if [ "$_retry" = 1 ]; then
                if _play_advisory "$_now"; then
                    _last=$_now
                    _retry=0
                    _monitor_log "monitor=init state=$_now advisory=played"
                else
                    _monitor_log "monitor=init state=$_now advisory=play-failed"
                fi
            else
                _last=$_now
                _monitor_log "monitor=init state=$_now advisory=skipped"
            fi
        elif [ "$_now" != "$_last" ]; then
            if _play_advisory "$_now"; then
                _last=$_now
                _monitor_log "monitor=transition state=$_now advisory=played"
            else
                _monitor_log "monitor=transition state=$_now advisory=play-failed"
            fi
        fi

        sleep "$_monitor_interval"
    done
}

_start_monitor() {
    _sm_seed=$1
    _sm_played=$2
    [ "$_no_monitor" = 1 ] && return 0

    if command -v setsid >/dev/null 2>&1; then
        setsid /bin/sh "$0" --monitor-only "$_sm_seed" "$_sm_played" \
            >/dev/null 2>&1 &
    elif command -v nohup >/dev/null 2>&1; then
        nohup /bin/sh "$0" --monitor-only "$_sm_seed" "$_sm_played" \
            >/dev/null 2>&1 &
    else
        ( /bin/sh "$0" --monitor-only "$_sm_seed" "$_sm_played" \
            >/dev/null 2>&1 & )
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Boot phase.
# ---------------------------------------------------------------------------
_boot_main() {
    # One attempt per boot; /tmp is a tmpfs boot artifact.
    [ ! -e "$_once" ] && [ ! -L "$_once" ] || exit 0
    mkdir "$_once" 2>/dev/null || exit 0

    _tznow=$(_tz_get)
    _stamp=$(_local_stamp)

    if [ ! -f "$_greeting" ] || [ -L "$_greeting" ]; then
        _status_write "greeting=missing tz=${_tznow} local=${_stamp}"
        _start_monitor "" 1
        exit 0
    fi

    # Wait for the stock FIFO inode, then retry the write.  The inode can exist
    # before cardv's audio reader is ready; a bounded retry avoids the old
    # one-shot failure while keeping boot non-blocking (the hook is detached).
    _n=0
    while [ "$_n" -lt 30 ]; do
        if [ -p "$_fifo" ]; then
            break
        fi
        sleep 1
        _n=$((_n + 1))
    done
    if [ ! -p "$_fifo" ]; then
        _status_write "fifo=missing tz=${_tznow} local=${_stamp}"
        _start_monitor "" 1
        exit 0
    fi

    if ! _play_retry "$_greeting" 4; then
        _status_write "greeting=play-failed tz=${_tznow} local=${_stamp}"
        _start_monitor "" 1
        exit 0
    fi
    _status_write "greeting=played tz=${_tznow} local=${_stamp}"

    # The greeting is about 2.0 s at 24 kHz; give the decoder a clean gap.
    sleep 3

    _state=
    _source=
    _detail=
    if [ -f "$_ae_enable" ] && [ ! -L "$_ae_enable" ] &&
       [ -x "$_light_bin" ] && [ ! -L "$_light_bin" ]; then
        _reading=$(_timeout_run 10 "$_light_bin" --threshold "$_threshold" 2>/dev/null)
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
                _status_write "greeting=played light=unknown tz=${_tznow} local=${_stamp}"
                _start_monitor "" 1
                exit 0
                ;;
        esac
    fi

    _advisory=$(_advisory_wav "$_state")
    if [ -z "$_advisory" ]; then
        _status_write "greeting=played light=invalid tz=${_tznow} local=${_stamp}"
        _start_monitor "" 1
        exit 0
    fi

    if ! _play_retry "$_advisory" 3; then
        _status_write "greeting=played light=${_state} source=${_source} detail=${_detail} tz=${_tznow} local=${_stamp} advisory=play-failed"
        _start_monitor "" 1
        exit 0
    fi

    _status_write "greeting=played light=${_state} source=${_source} detail=${_detail} tz=${_tznow} local=${_stamp} advisory=played"

    # Seed the monitor with the clock state (the periodic monitor always uses
    # the clock).  If the boot advisory used AE and differs, do not replay it
    # immediately; wait for the next clock transition.
    _clock_now=$(_clock_state 2>/dev/null)
    case "$_clock_now" in
        dark|bright)
            _monitor_seed=$_clock_now
            ;;
        *)
            _monitor_seed=
            ;;
    esac
    _start_monitor "$_monitor_seed" 0
    exit 0
}

case "$_mode" in
    monitor)
        _monitor_main
        ;;
    *)
        _boot_main
        ;;
esac
