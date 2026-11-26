#!/bin/sh
# Reject an ACTIVE legacy Bjorni cron job before trying to claim ST7789.
# The physical board used /etc/cron.d/medvetalkie-screensaver with both
# @reboot and * * * * * watchdog entries; killing the renderer alone is not
# enough, because cron recreates it during the build. No files are modified.
set -eu
cronfile="${1:-/etc/cron.d/medvetalkie-screensaver}"
if [ ! -e "$cronfile" ]; then
    exit 0
fi
if [ ! -f "$cronfile" ]; then
    echo "Cannot inspect legacy cron source: $cronfile" >&2
    exit 1
fi
if awk '
    /^[[:space:]]*#/ { next }
    /\/root\/medvetalkie-screensaver[.]sh/ { active = 1 }
    END { exit !active }
' "$cronfile"; then
    echo "Legacy Bjorni cron watchdog remains enabled: $cronfile" >&2
    echo "Archive it outside /etc/cron.d and stop its already-running process group; no processes will be killed automatically" >&2
    exit 1
fi
exit 0
