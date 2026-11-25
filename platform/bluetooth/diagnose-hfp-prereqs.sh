#!/bin/sh
# MedveTalkie HFP prerequisites: read-only, does not pair, connect, or route audio.
set -u

case "${1:-}" in
    --help|-h)
        echo "Usage: MT_AUDIO_USER=medvetalkie sh platform/bluetooth/diagnose-hfp-prereqs.sh"
        echo "Read-only BlueZ, USB-controller and PipeWire HFP prerequisite snapshot."
        exit 0 ;;
    "") ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac

section() { printf '\n=== %s ===\n' "$1"; }
check_binary() {
    if command -v "$1" >/dev/null 2>&1; then
        printf '%s: available (%s)\n' "$1" "$(command -v "$1")"
    else
        printf '%s: MISSING\n' "$1"
    fi
}
service_state() {
    if command -v systemctl >/dev/null 2>&1; then
        printf '%s: ' "$1"
        systemctl is-active "$1" 2>/dev/null || :
    else
        printf '%s: systemctl unavailable\n' "$1"
    fi
}

echo 'MedveTalkie HFP prerequisite diagnostic (PASSIVE; NOT an audio test)'
date -u '+UTC %Y-%m-%dT%H:%M:%SZ'
printf 'kernel=%s\n' "$(uname -r)"
section 'TOOLS'
for tool in bluetoothctl btmgmt btmon lsusb pactl wpctl pw-cli runuser; do
    check_binary "$tool"
done
section 'BLUEZ'
service_state bluetooth.service
if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl list 2>&1 || :
    echo '-- Devices connected via ACL (not proof of HFP) --'
    bluetoothctl devices Connected 2>&1 || :
fi
section 'USB BLUETOOTH IDENTITIES'
usb_count=0
for node in /sys/class/bluetooth/hci*; do
    [ -e "$node" ] || continue
    hci=${node##*/}
    parent=$(readlink -f "$node/device" 2>/dev/null || :)
    while [ -n "$parent" ] && [ "$parent" != / ]; do
        if [ -r "$parent/idVendor" ] && [ -r "$parent/idProduct" ]; then
            vid=$(cat "$parent/idVendor" 2>/dev/null || :)
            pid=$(cat "$parent/idProduct" 2>/dev/null || :)
            addr=$(cat "$node/address" 2>/dev/null || :)
            # BlueZ may expose an address via Adapter1 when kernel sysfs does not.
            if [ -z "$addr" ] && command -v bluetoothctl >/dev/null 2>&1; then
                addr=$(bluetoothctl show "$hci" 2>/dev/null | sed -n 's/^[[:space:]]*Controller \([[:xdigit:]:]*\).*/\1/p' | head -n 1)
            fi
            [ -n "$addr" ] || addr=unavailable
            printf '%s address=%s vid:pid=%s:%s usb_path=%s\n' "$hci" "$addr" "$vid" "$pid" "${parent##*/}"
            usb_count=$((usb_count + 1))
            break
        fi
        parent=$(dirname "$parent")
    done
    [ "$parent" != / ] && [ -n "$parent" ] || printf '%s non-USB or no USB mapping\n' "$hci"
done
printf 'usb_hci_count=%s (expect 2 external UGREEN 10d7:b012)\n' "$usb_count"
section 'AUDIO SERVICE / SESSION'
audio_user=${MT_AUDIO_USER:-medvetalkie}
if ! id "$audio_user" >/dev/null 2>&1; then
    printf 'audio_user=%s MISSING\n' "$audio_user"
else
    uid=$(id -u "$audio_user")
    runtime="/run/user/$uid"
    printf 'audio_user=%s uid=%s runtime=%s\n' "$audio_user" "$uid" "$runtime"
    for sock in "$runtime/pipewire-0" "$runtime/pulse/native"; do
        if [ -S "$sock" ]; then printf '%s: socket present\n' "$sock"; else printf '%s: missing\n' "$sock"; fi
    done
    if command -v runuser >/dev/null 2>&1 && [ "$(id -u)" -eq 0 ]; then
        if command -v pactl >/dev/null 2>&1; then
            echo '-- Pulse server --'
            runuser -u "$audio_user" -- env XDG_RUNTIME_DIR="$runtime" pactl info 2>&1 || :
            echo '-- Bluetooth cards / active profiles --'
            runuser -u "$audio_user" -- env XDG_RUNTIME_DIR="$runtime" pactl list cards 2>&1 |
                grep -E '^[[:space:]]*(Name: bluez_card\.|Active Profile:|api.bluez5.address =|api.bluez5.path =|headset-head-unit[^:]*:|handsfree_head_unit[^:]*:)' || :
            echo '-- Audio endpoints --'
            runuser -u "$audio_user" -- env XDG_RUNTIME_DIR="$runtime" pactl list short sinks 2>&1 || :
            runuser -u "$audio_user" -- env XDG_RUNTIME_DIR="$runtime" pactl list short sources 2>&1 || :
        fi
        if command -v wpctl >/dev/null 2>&1; then
            echo '-- WirePlumber status --'
            runuser -u "$audio_user" -- env XDG_RUNTIME_DIR="$runtime" wpctl status 2>&1 || :
        fi
    else
        echo 'Run as root to query the selected audio user; no permissions changed.'
    fi
fi
section 'INSTALLED AUDIO BACKENDS'
if command -v dpkg-query >/dev/null 2>&1; then
    for package in pipewire pipewire-pulse wireplumber libspa-0.2-bluetooth bluez; do
        dpkg-query -W -f='${db:Status-Abbrev} ${Package} ${Version}\n' "$package" 2>/dev/null || printf '%s: not installed\n' "$package"
    done
fi
section 'RESULT'
echo 'This is an inventory ONLY. USB HCI + BlueZ Connected + HFP profile do not establish SCO/eSCO audio.'
echo 'No SCO transport, PCM activity, microphone, speaker, or simultaneous full duplex was tested.'
