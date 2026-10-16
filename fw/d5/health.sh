#!/bin/sh
# D5 on-demand, read-only snapshot. No boot loop, file writes, GPS payload,
# socket/USB/UART access, configuration or process control. Output has no route,
# key, license, calibration, media filename or raw vendor/config contents.
case "${1-}" in
  --help) printf '%s\n' 'D5 health --snapshot: read-only existing status/process/link snapshot; not continuity or hardware acceptance.'; exit 0 ;;
  --snapshot) [ "$#" -eq 1 ] || exit 2 ;;
  *) exit 2 ;;
esac
PATH=/bin:/sbin:/usr/bin:/usr/sbin
export PATH
printf '%s\n' 'schema=c2m_d5_health_v1' 'read_only=1' 'snapshot_not_continuity=1'
if [ -r /proc/uptime ]; then
  awk '{split($1,a,"."); if(a[1] ~ /^[0-9]+$/) print "uptime_seconds=" a[1]}' /proc/uptime
fi
# Fixed small regular status sources only; never print unvalidated contents.
if [ -f /tmp/rec_status ] && [ ! -L /tmp/rec_status ] && [ "$(wc -c < /tmp/rec_status)" -le 16 ]; then
  if tr -d '\000\r\n' < /tmp/rec_status | grep -qx '1'; then
    printf '%s\n' 'recording_flag=1'
  else
    printf '%s\n' 'recording_flag=0'
  fi
else
  printf '%s\n' 'recording_flag=unknown'
fi
# /proc comm exposes only exact executable names, not commands/credentials.
_cardv=0; _adas=0; _signs=0; _web=0; _debug=0
for _comm in /proc/[0-9]*/comm; do
  [ -r "$_comm" ] || continue
  IFS= read -r _name < "$_comm" || continue
  case "$_name" in
    cardv) _cardv=$((_cardv + 1)) ;;
    adas) _adas=$((_adas + 1)) ;;
    c2m-signs) _signs=$((_signs + 1)) ;;
    c2m-web) _web=$((_web + 1)) ;;
    c2m-debug) _debug=$((_debug + 1)) ;;
  esac
done
printf 'cardv_count=%s\nadas_count=%s\nsigns_count=%s\nweb_count=%s\ndebug_count=%s\n' "$_cardv" "$_adas" "$_signs" "$_web" "$_debug"
# Passive kernel table only. Never connect to stock cardv's single WS slot.
if [ -f /proc/net/tcp ] && [ -r /proc/net/tcp ]; then
  awk 'BEGIN {a=0;b=0;c=0}
    $4=="01" && $3 ~ /^8120A8C0:/ {
      if($2=="7B20A8C0:1F90") a++;
      if($2=="7B20A8C0:5DCC") b++;
      if($2=="7B20A8C0:659C") c++;
    }
    END {print "m4_8080_established=" a; print "m4_24012_established=" b; print "m4_26012_established=" c}' /proc/net/tcp
else
  printf '%s\n' 'm4_connections=unknown'
fi
if [ -f /tmp/c2m_d4_status ] && [ ! -L /tmp/c2m_d4_status ] && [ "$(wc -c < /tmp/c2m_d4_status)" -le 4096 ]; then
  awk -F= '$1=="state" && $2 ~ /^(waiting_gps|warming_up|ready|stale|no_database|disabled|error)$/ {print "advisory_state=" $2}
    $1=="gps_fresh" && $2 ~ /^[01]$/ {print "advisory_gps_fresh=" $2}' /tmp/c2m_d4_status
else
  printf '%s\n' 'advisory_state=unavailable'
fi
if [ -f /tmp/c2m_debug_status ] && [ ! -L /tmp/c2m_debug_status ] && [ "$(wc -c < /tmp/c2m_debug_status)" -le 8192 ]; then
  awk -F= '$1=="state" && $2 ~ /^(starting|active|expired|failed|inactive|disabled)$/ {print "ssh_state=" $2}
    $1=="window_sec" && $2 ~ /^[0-9]+$/ {print "ssh_window_seconds=" $2}' /tmp/c2m_debug_status
else
  printf '%s\n' 'ssh_state=unavailable'
fi
printf '%s\n' 'recording_growth_and_gps_fix=not_tested' 'ap_radio_and_adas_quality=not_tested'
exit 0
