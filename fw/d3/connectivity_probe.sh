#!/bin/sh
# D3 boot-time passive Bluetooth inventory. The caller saves stdout after SD mount.
# No radio activation, pairing, module loading, network commands or UART access.
# Run once; do not infer hardware absence from missing kernel exposure.
# POSIX / BusyBox. Only bounded reads of known procfs/sysfs files are performed.
# V2 adds allowlisted Wi-Fi/SDIO/BT-transport context for RTL8821CS triage;
# still presence-only, no device nodes, no UART, no link resolution, no tool execution.

LC_ALL=C
export LC_ALL
fixture_mode=0
probe_root=
hci_seen=0
module_count=0

# Fixtures must not escape to live sysfs through symlinks (real sysfs uses links).
path_without_links() {
    checked_rest=${1#/}
    checked_walk=
    while [ -n "$checked_rest" ]; do
        checked_part=${checked_rest%%/*}
        case "$checked_rest" in
            */*) checked_rest=${checked_rest#*/} ;;
            *) checked_rest= ;;
        esac
        case "$checked_part" in ''|.|..) return 1 ;; esac
        checked_walk="$checked_walk/$checked_part"
        [ ! -L "$checked_walk" ] || return 1
    done
    return 0
}

safe_dir() {
    if [ "$fixture_mode" = 1 ]; then
        path_without_links "$1" || return 1
    fi
    [ -d "$1" ]
}

safe_file() {
    if [ "$fixture_mode" = 1 ]; then
        path_without_links "$1" || return 1
    fi
    # Reject devices and FIFOs, including in synthetic test roots.
    [ -f "$1" ] && [ -r "$1" ]
}

flag_value() {
    if safe_file "$1"; then
        flag_result=$(head -c 8 "$1" 2>/dev/null) || flag_result=
        case "$flag_result" in 0|1) printf '%s' "$flag_result"; return ;; esac
    fi
    printf 'unknown'
}

# Bounded numeric SDIO vendor/device sanitizer. Linux sysfs exposes these as
# small public numeric chip identities (for example 0x024c), not credentials.
# Accept only exact 0x/0X plus 4 hexadecimal digits; anything else becomes
# not_reported. Never used for modalias or uevent content.
sdio_hex4() {
    if safe_file "$1"; then
        sdio_result=$(head -c 16 "$1" 2>/dev/null) || sdio_result=
        case "$sdio_result" in
            0[xX]????)
                sdio_suffix=${sdio_result#0?}
                case "$sdio_suffix" in
                    ????)
                        case "$sdio_suffix" in
                            *[!0-9a-fA-F]*) ;;
                            *) printf '%s' "$sdio_result"; return ;;
                        esac
                        ;;
                esac
                ;;
        esac
    fi
    printf 'not_reported'
}

printf 'probe=C2M_D3_PASSIVE_BLUETOOTH_V2\n'
printf 'radio_test=NOT_PERFORMED\nstate_changes=NONE\n'
printf 'scope=kernel_exposure_only_not_physical_or_RF_verification\n'

# Unset means production /. An explicit override must be a non-root absolute
# directory without dot components, repeated separators, controls or symlinks.
if [ "${C2M_PROBE_ROOT+x}" = x ]; then
    fixture_mode=1
    probe_root=${C2M_PROBE_ROOT%/}
    root_ok=1
    case "$C2M_PROBE_ROOT" in *//*) root_ok=0 ;; esac
    case "$probe_root" in /*) ;; *) root_ok=0 ;; esac
    case "$probe_root" in
        ''|/|*//*|*/./*|*/../*|*/.|*/..|*[!a-zA-Z0-9_./\ -]*) root_ok=0 ;;
    esac
    if [ "$root_ok" != 1 ] || ! path_without_links "$probe_root" || [ ! -d "$probe_root" ]; then
        printf 'status=SKIPPED_UNSAFE_OR_MISSING_ROOT\n'
        printf 'verdict=NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE\n'
        printf 'meaning=probe_skipped_no_hardware_conclusion\n'
        exit 0
    fi
    printf 'source=isolated_fixture\n'
else
    printf 'source=live_read_only_filesystem\n'
fi

printf '\n[hci]\n'
hci_count=0
if safe_dir "$probe_root/sys/class/bluetooth"; then
    printf 'bluetooth_class=present\n'
    for entry in "$probe_root"/sys/class/bluetooth/hci[0-9]*; do
        name=${entry##*/}
        index=${name#hci}
        case "$index" in ''|*[!0-9]*) continue ;; esac
        safe_dir "$entry" || continue
        hci_seen=1
        hci_count=$((hci_count + 1))
        if [ "$hci_count" -gt 16 ]; then
            printf 'hci_inventory=truncated_at_16\n'
            break
        fi
        # Never dump addresses, device names, uevents or raw capability blobs.
        if [ "${#name}" -gt 24 ]; then name=hci_index_redacted; fi
        state=not_reported
        if safe_file "$entry/operstate"; then
            candidate=$(head -c 32 "$entry/operstate" 2>/dev/null) || candidate=
            case "$candidate" in
                up|down|unknown|dormant|notpresent|lowerlayerdown|testing) state=$candidate ;;
            esac
        fi
        printf 'hci=%s sysfs_operstate=%s\n' "$name" "$state"
    done
else
    printf 'bluetooth_class=not_observed\n'
fi
[ "$hci_seen" = 1 ] || printf 'hci=none_observed\n'

printf '\n[kernel_support_context_only]\n'
if [ "$fixture_mode" = 0 ]; then
    kernel_family=$(uname -s 2>/dev/null) || kernel_family=
    case "$kernel_family" in Linux) printf 'kernel_family=Linux\n' ;; *) printf 'kernel_family=unknown\n' ;; esac
else
    printf 'kernel_family=fixture_not_queried\n'
fi
for module in bluetooth btusb hci_uart hci_vhci btrtl btbcm btintel btmtk btsdio rtk_bt rtk_btusb 8821cs cfg80211 mac80211; do
    if safe_dir "$probe_root/sys/module/$module"; then
        printf 'sysfs_module=%s\n' "$module"
    fi
done
if safe_file "$probe_root/proc/modules"; then
    printf 'loaded_module_scan=first_32768_bytes_max_32_matches\n'
    head -c 32768 "$probe_root/proc/modules" 2>/dev/null |
    while read -r module remainder; do
        case "$module" in
            bluetooth|btusb|hci_uart|hci_vhci|btrtl|btbcm|btintel|btmtk|btsdio|rtk_bt|rtk_btusb|8821cs|cfg80211|mac80211)
                module_count=$((${module_count:-0} + 1))
                [ "$module_count" -le 32 ] || break
                printf 'loaded_module=%s\n' "$module"
                ;;
        esac
    done
else
    printf 'loaded_modules=unavailable\n'
fi
if safe_file "$probe_root/proc/config.gz"; then
    printf 'kernel_config_gz=present_not_decoded\n'
else
    printf 'kernel_config_gz=not_observed\n'
fi

printf '\n[rfkill_context_only]\n'
rfkill_count=0
rfkill_scanned=0
if safe_dir "$probe_root/sys/class/rfkill"; then
    for entry in "$probe_root"/sys/class/rfkill/rfkill[0-9]*; do
        name=${entry##*/}
        index=${name#rfkill}
        case "$index" in ''|*[!0-9]*) continue ;; esac
        safe_dir "$entry" || continue
        rfkill_scanned=$((rfkill_scanned + 1))
        if [ "$rfkill_scanned" -gt 64 ]; then
            printf 'rfkill_scan=truncated_at_64_entries\n'
            break
        fi
        safe_file "$entry/type" || continue
        kind=$(head -c 32 "$entry/type" 2>/dev/null) || kind=
        [ "$kind" = bluetooth ] || continue
        rfkill_count=$((rfkill_count + 1))
        if [ "$rfkill_count" -gt 16 ]; then
            printf 'rfkill_inventory=truncated_at_16\n'
            break
        fi
        if [ "${#name}" -gt 24 ]; then name=rfkill_index_redacted; fi
        soft=$(flag_value "$entry/soft")
        hard=$(flag_value "$entry/hard")
        printf 'rfkill=%s type=bluetooth soft=%s hard=%s\n' "$name" "$soft" "$hard"
    done
fi
[ "$rfkill_count" -gt 0 ] || printf 'bluetooth_rfkill=none_observed\n'

printf '\n[device_tree_context_only]\n'
dt_base=
if safe_dir "$probe_root/sys/firmware/devicetree/base"; then
    dt_base="$probe_root/sys/firmware/devicetree/base"
elif safe_dir "$probe_root/proc/device-tree"; then
    dt_base="$probe_root/proc/device-tree"
fi
dt_seen=0
if [ -n "$dt_base" ]; then
    # Deliberately shallow, non-recursive and names-only; never read serial,
    # MAC, compatible or other binary properties containing private values.
    for entry in "$dt_base"/bluetooth* "$dt_base"/*/bluetooth* \
                 "$dt_base"/*/*/bluetooth* "$dt_base"/*/*/*/bluetooth*; do
        if safe_dir "$entry"; then dt_seen=1; break; fi
    done
    if [ "$dt_seen" = 1 ]; then
        printf 'bluetooth_named_node=observed_context_only\n'
    else
        printf 'bluetooth_named_node=none_observed_within_depth_4\n'
    fi
else
    printf 'device_tree=unavailable\n'
fi

printf '\n[wifi_interface_context_only]\n'
wifi_seen=0
for wname in wlan0 c2msta0; do
    wentry="$probe_root/sys/class/net/$wname"
    if safe_dir "$wentry"; then
        wifi_seen=1
        wstate=not_reported
        if safe_file "$wentry/operstate"; then
            wcandidate=$(head -c 32 "$wentry/operstate" 2>/dev/null) || wcandidate=
            case "$wcandidate" in
                up|down|unknown|dormant|notpresent|lowerlayerdown|testing) wstate=$wcandidate ;;
            esac
        fi
        printf 'wifi_interface=%s sysfs_operstate=%s\n' "$wname" "$wstate"
    fi
done
if [ "$wifi_seen" = 1 ]; then
    printf 'wifi_interface_context=allowlisted_interface_observed\n'
else
    printf 'wifi_interface=none_observed_allowlisted_only\n'
    printf 'wifi_interface_context=none_observed_allowlisted_only\n'
fi

printf '\n[rtl8821cs_bundled_module_context_only]\n'
rtl_seen=0
for modpath in /customer/wifi/lib/8821cs.ko /wifi/lib/8821cs.ko /lib/modules/8821cs.ko; do
    if safe_file "$probe_root$modpath"; then
        printf 'bundled_module_present=%s\n' "$modpath"
        rtl_seen=1
    else
        printf 'bundled_module_not_observed=%s\n' "$modpath"
    fi
done
if [ "$rtl_seen" = 1 ]; then
    printf 'rtl8821cs_module=bundled_present\n'
else
    printf 'rtl8821cs_module=not_observed\n'
fi

printf '\n[sdio_context_only]\n'
if safe_dir "$probe_root/sys/bus/sdio"; then
    printf 'sdio_bus=present\n'
else
    printf 'sdio_bus=not_observed\n'
fi
sdio_count=0
sdio_scanned=0
sdio_known_seen=0
if safe_dir "$probe_root/sys/bus/sdio/devices"; then
    printf 'sdio_devices_dir=present\n'
    for sentry in "$probe_root"/sys/bus/sdio/devices/*; do
        sname=${sentry##*/}
        case "$sname" in '*'|.*) continue ;; esac
        safe_dir "$sentry" || continue
        # Production shape is strict numeric mmc bus/address/function with
        # colons (for example mmc1:0001:1). The dash form exists ONLY so
        # Windows-forbidden colons can be fixture-tested; live production
        # never accepts dashes.
        case "$sname" in
            mmc*:*:*) ;;
            mmc*-*-*)
                if [ "$fixture_mode" != 1 ]; then continue; fi
                ;;
            *) continue ;;
        esac
        # Reject any overlong or lettered private-looking name beyond hex.
        # The fixed "mmc" prefix needs m/M besides hex digits.
        case "$sname" in *[!0-9a-fA-FmM:._-]*) continue ;; esac
        if [ "${#sname}" -gt 24 ]; then continue; fi
        case "$sname" in
            *:*:*:*|*-*-*-*) continue ;;
        esac
        # Numeric bus/address/function validation. Address is 4 hex digits;
        # bus and function are decimal digits. No free-string names survive.
        sbody=${sname#mmc}
        case "$sname" in *:*:*) ssep=: ;; *-*-*) ssep=- ;; *) continue ;; esac
        case "$ssep" in
            :)
                case "$sbody" in *:*|*) ;; *) continue ;; esac
                sbus=${sbody%%:*}
                srest=${sbody#*:}
                case "$srest" in *:*|*) ;; *) continue ;; esac
                saddr=${srest%%:*}
                sfunc=${srest#*:}
                ;;
            *)
                case "$sbody" in *-*|*) ;; *) continue ;; esac
                sbus=${sbody%%-*}
                srest=${sbody#*-}
                case "$srest" in *-*|*) ;; *) continue ;; esac
                saddr=${srest%%-*}
                sfunc=${srest#*-}
                ;;
        esac
        case "$sbus" in ''|*[!0-9]*) continue ;; esac
        case "$saddr" in ????) ;; *) continue ;; esac
        case "$saddr" in *[!0-9a-fA-F]*) continue ;; esac
        case "$sfunc" in ''|*[!0-9]*) continue ;; esac
        case "$sbus$saddr$sfunc" in *:*|*-*|*.*|*_* ) continue ;; esac
        sdio_scanned=$((sdio_scanned + 1))
        if [ "$sdio_scanned" -gt 64 ]; then
            printf 'sdio_scan=truncated_at_64_entries\n'
            break
        fi
        sdio_count=$((sdio_count + 1))
        if [ "$sdio_count" -gt 16 ]; then
            printf 'sdio_inventory=truncated_at_16\n'
            break
        fi
        # Never read modalias or uevent. Vendor/device are bounded numeric
        # chip identities only, sanitized to exact 0x plus 4 hex digits.
        sdiv_vendor=$(sdio_hex4 "$sentry/vendor")
        sdiv_device=$(sdio_hex4 "$sentry/device")
        printf 'sdio_device=%s vendor=%s device=%s present_context_only\n' \
            "$sname" "$sdiv_vendor" "$sdiv_device"
        case "$sdiv_vendor" in
            0[xX]024[cC])
                case "$sdiv_device" in
                    0[xX][cC]821|0[xX][bB]821|0[xX][cC]80[cC]|0[xX]8733)
                        sdio_known_seen=1
                        ;;
                esac
                ;;
        esac
    done
else
    printf 'sdio_devices_dir=not_observed\n'
fi
if [ "$sdio_count" -gt 0 ]; then
    printf 'sdio_context=devices_observed_context_only\n'
else
    printf 'sdio_context=none_observed_context_only\n'
fi
if [ "$sdio_known_seen" = 1 ]; then
    printf 'rtl8821cs_sdio_hint=driver_supported_id_not_physical_bt_proof\n'
else
    printf 'rtl8821cs_sdio_hint=no_known_id_matched_context_only\n'
fi

printf '\n[bt_transport_context_only]\n'
bt_fw_seen=0
for fwpath in /lib/firmware/rtl_bt/rtl8821c_fw.bin /lib/firmware/rtl_bt/rtl8821c_config.bin /lib/firmware/rtl_bt/rtl8821cs_fw.bin /lib/firmware/rtl_bt/rtl8821cs_config.bin; do
    if safe_file "$probe_root$fwpath"; then
        printf 'bt_firmware_present=%s\n' "$fwpath"
        bt_fw_seen=1
    else
        printf 'bt_firmware_not_observed=%s\n' "$fwpath"
    fi
done
bt_helper_seen=0
for btool in hciattach rtk_hciattach btattach; do
    if command -v "$btool" >/dev/null 2>&1; then
        printf 'bt_helper=%s present_not_executed\n' "$btool"
        bt_helper_seen=1
    else
        printf 'bt_helper=%s not_found\n' "$btool"
    fi
done
if [ "$bt_fw_seen" = 1 ] || [ "$bt_helper_seen" = 1 ]; then
    printf 'bt_transport_context=firmware_or_helper_observed_context_only\n'
else
    printf 'bt_transport_context=none_observed_context_only\n'
fi

printf '\n[command_presence_context_only]\n'
# Presence checks only: never execute these tools, even when timeout exists.
for tool in hciconfig hcitool bluetoothctl btmgmt rfkill; do
    if command -v "$tool" >/dev/null 2>&1; then
        printf 'tool=%s present_not_executed\n' "$tool"
    else
        printf 'tool=%s not_found\n' "$tool"
    fi
done

printf '\n[result]\nstatus=COMPLETE\n'
if [ "$hci_seen" = 1 ]; then
    printf 'verdict=HCI_PRESENT_NOT_RADIO_TESTED\n'
    printf 'meaning=kernel_HCI_interface_observed_radio_and_physical_hardware_not_tested\n'
else
    printf 'verdict=NO_HCI_OBSERVED_NOT_HARDWARE_ABSENCE\n'
    printf 'meaning=no_kernel_HCI_observed_hardware_may_be_unexposed_or_unsupported\n'
fi
exit 0
