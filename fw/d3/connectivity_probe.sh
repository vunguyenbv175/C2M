#!/bin/sh
# D3 boot-time passive Bluetooth inventory. The caller saves stdout after SD mount.
# No radio activation, pairing, module loading, network commands or UART access.
# Run once; do not infer hardware absence from missing kernel exposure.
# POSIX / BusyBox. Only bounded reads of known procfs/sysfs files are performed.

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

printf 'probe=C2M_D3_PASSIVE_BLUETOOTH_V1\n'
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
for module in bluetooth btusb hci_uart hci_vhci btrtl btbcm btintel btmtk btsdio rtk_bt rtk_btusb; do
    if safe_dir "$probe_root/sys/module/$module"; then
        printf 'sysfs_module=%s\n' "$module"
    fi
done
if safe_file "$probe_root/proc/modules"; then
    printf 'loaded_module_scan=first_32768_bytes_max_32_matches\n'
    head -c 32768 "$probe_root/proc/modules" 2>/dev/null |
    while read -r module remainder; do
        case "$module" in
            bluetooth|btusb|hci_uart|hci_vhci|btrtl|btbcm|btintel|btmtk|btsdio|rtk_bt|rtk_btusb)
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
