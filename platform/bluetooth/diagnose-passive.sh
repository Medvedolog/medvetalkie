#!/bin/sh
# MedveTalkie passive Bluetooth/PipeWire inventory.
# Read-only by design: never pair, connect, switch profiles or create audio links.
set -u

echo '=== MEDVETALKIE PASSIVE BT INVENTORY ==='
date -u '+UTC %Y-%m-%dT%H:%M:%SZ'
echo "kernel=$(uname -r)"
echo

echo '=== BLUEZ CONTROLLERS ==='
if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl list 2>&1 || :
    echo
    echo '=== CONNECTED HEADSETS (NOT PROOF OF VOICE) ==='
    bluetoothctl devices Connected 2>&1 || :
else
    echo 'bluetoothctl unavailable'
fi
echo

echo '=== HCI CONTROLLERS ==='
if command -v hciconfig >/dev/null 2>&1; then
    hciconfig -a 2>&1 || :
else
    echo 'hciconfig unavailable; bluetoothctl list remains authoritative for enumeration'
fi
echo

echo '=== PIPEWIRE SESSION ==='
# This tool does not elevate privileges or guess a root audio session.
# Run as the PipeWire owning user, or set MT_AUDIO_USER explicitly.
MT_AUDIO_USER=${MT_AUDIO_USER:-medvetalkie}
if command -v id >/dev/null 2>&1 && id "$MT_AUDIO_USER" >/dev/null 2>&1; then
    MT_UID=$(id -u "$MT_AUDIO_USER")
    MT_RUNTIME="/run/user/$MT_UID"
    if [ -S "$MT_RUNTIME/pulse/native" ] && command -v runuser >/dev/null 2>&1; then
        echo "audio_user=$MT_AUDIO_USER audio_uid=$MT_UID"
        echo '-- cards --'
        runuser -u "$MT_AUDIO_USER" -- env XDG_RUNTIME_DIR="$MT_RUNTIME" pactl list cards short 2>&1 || :
        echo '-- profiles and controller properties (headsets only) --'
        runuser -u "$MT_AUDIO_USER" -- env XDG_RUNTIME_DIR="$MT_RUNTIME" pactl list cards 2>&1 |
            grep -E '^[[:space:]]*(Name: bluez_card\.|api.bluez5.address =|api.bluez5.path =|Active Profile:|headset-head-unit[^:]*:|a2dp-sink[^:]*:)' || :
        echo '-- sinks --'
        runuser -u "$MT_AUDIO_USER" -- env XDG_RUNTIME_DIR="$MT_RUNTIME" pactl list sinks short 2>&1 || :
        echo '-- sources --'
        runuser -u "$MT_AUDIO_USER" -- env XDG_RUNTIME_DIR="$MT_RUNTIME" pactl list sources short 2>&1 || :
    else
        echo "PipeWire/Pulse endpoint not reachable at $MT_RUNTIME/pulse/native"
    fi
else
    echo "Audio user '$MT_AUDIO_USER' unavailable"
fi
echo

echo '=== UWE5622 RX COUNTERS (WHEN AVAILABLE) ==='
if [ -r /sys/devices/platform/mtty/hci_rx_stats ]; then
    cat /sys/devices/platform/mtty/hci_rx_stats
else
    echo 'No experimental UWE5622 counters; this is normal with USB adapters.'
fi
echo
echo '=== INTERPRETATION ==='
echo 'Connected != paired voice session; HFP profile != active bidirectional audio.'
echo 'SCO budget is unverified until simultaneous HFP/eSCO links AND microphone audio are tested.'
echo 'Do not infer a controller budget from number of paired devices or A2DP sinks.'
