#!/bin/sh
# MedveTalkie SPI ownership guard for Orange Pi Zero 3.
# fuser identifies /dev/spidev1.0 consumers; /proc/PID/cgroup distinguishes
# the managed renderer from a legacy cron/manual renderer. Never kills either.
set -eu
mode="${1:---allow-managed}"
device="${2:-/dev/spidev1.0}"
case "$mode" in
    --allow-managed|--require-free|--require-managed) ;;
    *) echo "Usage: check-display-owner.sh [--allow-managed|--require-free|--require-managed] [SPI_DEVICE]" >&2; exit 64 ;;
esac
if [ ! -c "$device" ] && [ ! -f "$device" ]; then
    echo "SPI device unavailable: $device" >&2
    exit 1
fi
if ! command -v fuser >/dev/null 2>&1; then
    echo "Cannot check display ownership: fuser missing" >&2
    exit 1
fi
pids="$(fuser "$device" 2>/dev/null || : )"
managed=0
for pid in $pids; do
    case "$pid" in
        *[!0-9]*|'') echo "Unexpected SPI owner PID: $pid" >&2; exit 1 ;;
    esac
    if [ "$mode" = "--require-free" ]; then
        echo "SPI $device is held by PID $pid; stop the previous renderer before activation" >&2
        exit 1
    fi
    if [ ! -r "/proc/$pid/cgroup" ]; then
        echo "Cannot verify SPI owner PID $pid" >&2
        exit 1
    fi
    if grep -Eq '(^|/)medvetalkie-display[.]service(/|$)' "/proc/$pid/cgroup"; then
        managed=$((managed+1))
    else
        echo "External SPI owner PID $pid (not in medvetalkie-display.service):" >&2
        ps -o pid,ppid,args -p "$pid" >&2 || :
        echo "Stop its legacy cron/manual supervisor; will not kill it automatically" >&2
        exit 1
    fi
done
if [ "$mode" = "--require-managed" ] && [ "$managed" -eq 0 ]; then
    echo "No MedveTalkie-managed renderer owns SPI yet: $device" >&2
    exit 1
fi
exit 0
