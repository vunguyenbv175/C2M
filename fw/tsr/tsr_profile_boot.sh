#!/bin/sh
# D-TSR experiment. Invoked before stock adas_service.sh.
# Only adas.flag (authoritative encoded source) is atomically replaced.
# Stock run.sh reconciles adas_de.flag itself; no two-file transaction.
# Private backup is pre-D/post-C, not factory/pre-C. No calib/license writes.
# All failures leave stock boot unblocked; status contains no config payload.
_cfg=/customer/minieye/config
_status=/tmp/c2m_tsr_status.txt
_work=/tmp/c2m_tsr_work
_backup=$_cfg/.c2m-tsr-pre-d

status() {
    printf 'TSR_PROFILE v=D2 status=%s\n' "$1" > "$_status"
}
fail() {
    status "$1"
    rm -rf "$_work"
    exit 0
}

status START
for _tool in awk base64 cat cmp cp grep md5sum mkdir mv rm sync wc; do
    command -v "$_tool" >/dev/null 2>&1 || { status MISSING_STOCK_TOOL; exit 0; }
done
[ -f "$_cfg/.c2m-tsr-disabled" ] && { status DISABLED_BY_OWNER_MARKER; exit 0; }
[ -d "$_cfg" ] && [ ! -L "$_cfg" ] || { status NO_CONFIG; exit 0; }
[ -f "$_cfg/adas.flag" ] && [ ! -L "$_cfg/adas.flag" ] || { status NO_ENCODED_FLAG; exit 0; }
# Never reuse arbitrary existing /tmp objects or follow links.
[ ! -e "$_work" ] && [ ! -L "$_work" ] || { status WORK_PATH_EXISTS; exit 0; }
umask 077
mkdir "$_work" || { status NO_WORK_DIR; exit 0; }
_bytes=$(wc -c < "$_cfg/adas.flag") || fail SIZE_READ_FAILED
[ "$_bytes" -gt 0 ] && [ "$_bytes" -le 98304 ] || fail INPUT_SIZE_BLOCK
cp -p "$_cfg/adas.flag" "$_work/source.flag" || fail SOURCE_COPY_FAILED
base64 -d "$_work/source.flag" > "$_work/decoded" || fail DECODE_FAILED
# wc -l counts LF bytes while awk NR also counts an unterminated final record.
# Reject that input BEFORE awk/grep can normalize a byte outside TSR keys.
_lines=$(wc -l < "$_work/decoded") || fail LF_CHECK_FAILED
_records=$(awk 'END { print NR+0 }' "$_work/decoded") || fail LF_CHECK_FAILED
[ "$_lines" -eq "$_records" ] || fail MISSING_FINAL_LF
# awk implementations differ in whether `\r` is represented portably.
# Reject CRLF before parsing so line-ending drift cannot pass the shape gate.
if grep -q "$(printf '\r')" "$_work/decoded"; then fail CONFIG_SHAPE_BLOCK; fi
# Require LF input, finite canonical values and one unambiguous active key.
# Existing unrelated bytes are copied in order; only this five-key allowlist
# may change/add. Missing keys are explicit known gflags, not guessed flags.
awk '
BEGIN {
    key[1]="enable_tsr"; val[1]="true"
    key[2]="tsrw_interval"; val[2]="5"
    key[3]="tsrw_sli_over_min_ratio"; val[3]="10"
    key[4]="tsrw_sli_over_min_thresh"; val[4]="5"
    key[5]="tsrw_sli_host_speed_min_thresh"; val[5]="20"
}
{
    if (index($0, "\r") || length($0)>4096) bad=1
    text=$0; sub(/^[ \t]+/, "", text)
    if (text ~ /^#/ || text ~ /^[ \t]*$/) { print $0; next }
    matched=0
    for (i=1; i<=5; i++) {
        prefix="--" key[i]
        if (index(text,prefix)==1 && substr(text,length(prefix)+1,1) ~ /[= \t]/) {
            matched=1
            if (++seen[i]>1 || text !~ /^--[a-z_]+=[^ \t#]+[ \t]*$/) bad=1
            old=text; sub(/^[^=]*=/,"",old); sub(/[ \t]+$/,"",old)
            if (i==1) { if (old!="true" && old!="false") bad=1 }
            else if (old !~ /^[0-9]+([.][0-9]+)?$/ || old+0>3600) bad=1
            print "--" key[i] "=" val[i]
            break
        }
    }
    if (!matched) print $0
}
END {
    if (NR==0 || bad) exit 2
    for (i=1; i<=5; i++) if (!seen[i]) print "--" key[i] "=" val[i]
}' "$_work/decoded" > "$_work/profile" || fail CONFIG_SHAPE_BLOCK
# Verify unrelated lines byte-for-byte using a filter on exact active keys.
_filter='^[ \t]*--(enable_tsr|tsrw_interval|tsrw_sli_over_min_ratio|tsrw_sli_over_min_thresh|tsrw_sli_host_speed_min_thresh)='
grep -v -E "$_filter" "$_work/decoded" > "$_work/outside_before"
_g=$?; [ "$_g" -le 1 ] || fail FILTER_FAILED
grep -v -E "$_filter" "$_work/profile" > "$_work/outside_after"
_g=$?; [ "$_g" -le 1 ] || fail FILTER_FAILED
cmp -s "$_work/outside_before" "$_work/outside_after" || fail OUTSIDE_BYTES_CHANGED
base64 "$_work/profile" > "$_work/encoded" || fail ENCODE_FAILED
base64 -d "$_work/encoded" > "$_work/roundtrip" || fail ROUNDTRIP_FAILED
cmp -s "$_work/profile" "$_work/roundtrip" || fail ROUNDTRIP_MISMATCH
if cmp -s "$_work/decoded" "$_work/profile"; then
    status ALREADY_APPLIED
    rm -rf "$_work"
    exit 0
fi
# No live write without a complete first-install backup. Existing backup
# must validate against its own checksum; never replace it on later boots.
if [ -e "$_backup" ] || [ -L "$_backup" ]; then
    [ -d "$_backup" ] && [ ! -L "$_backup" ] || fail BACKUP_PATH_BLOCK
    [ -f "$_backup/complete" ] && [ ! -L "$_backup/adas.flag" ] || fail BACKUP_INCOMPLETE
    (cd "$_backup" && md5sum -c SHA_MD5SUMS.txt >/dev/null 2>&1) || fail BACKUP_HASH_BLOCK
else
    mkdir "$_backup" || fail BACKUP_CREATE_FAILED
    cp -p "$_cfg/adas.flag" "$_backup/adas.flag" || fail BACKUP_COPY_FAILED
    if [ -f "$_cfg/adas_de.flag" ]; then
        [ ! -L "$_cfg/adas_de.flag" ] || fail DECODED_LINK_BLOCK
        cp -p "$_cfg/adas_de.flag" "$_backup/adas_de.flag" || fail BACKUP_COPY_FAILED
    fi
    (cd "$_backup" && md5sum adas.flag > SHA_MD5SUMS.txt &&
        { [ ! -f adas_de.flag ] || md5sum adas_de.flag >> SHA_MD5SUMS.txt; }) || fail BACKUP_CHECKSUM_FAILED
    (cd "$_backup" && md5sum -c SHA_MD5SUMS.txt >/dev/null 2>&1) || fail BACKUP_HASH_BLOCK
    printf 'pre-D/post-C config backup, NOT factory state\n' > "$_backup/complete" || fail BACKUP_MARK_FAILED
    sync
fi
# Stage in the SAME filesystem preserving stock encoded-file metadata. Only
# rename after complete write, roundtrip and unchanged-source checks.
_stage=$_cfg/.c2m-tsr-adas.flag.new
[ ! -e "$_stage" ] && [ ! -L "$_stage" ] || fail STAGE_PATH_EXISTS
cmp -s "$_cfg/adas.flag" "$_work/source.flag" || fail SOURCE_CHANGED
cp -p "$_cfg/adas.flag" "$_stage" || fail STAGE_CREATE_FAILED
if ! cat "$_work/encoded" > "$_stage"; then rm -f "$_stage"; fail STAGE_WRITE_FAILED; fi
base64 -d "$_stage" > "$_work/staged_decoded" || { rm -f "$_stage"; fail STAGE_DECODE_FAILED; }
cmp -s "$_work/staged_decoded" "$_work/profile" || { rm -f "$_stage"; fail STAGE_MISMATCH; }
cmp -s "$_cfg/adas.flag" "$_work/source.flag" || { rm -f "$_stage"; fail SOURCE_CHANGED; }
sync
mv -f "$_stage" "$_cfg/adas.flag" || { rm -f "$_stage"; fail COMMIT_FAILED; }
sync
status APPLIED_WAIT_STOCK_REDECODE
rm -rf "$_work"
exit 0
