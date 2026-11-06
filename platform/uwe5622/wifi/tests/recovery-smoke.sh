#!/bin/sh
set -eu
SCRIPT=${1:-platform/uwe5622/wifi/scripts/uwe5622-recover}
sh -n "$SCRIPT"
out=$(sh "$SCRIPT" dry-run)
printf '%s\n' "$out" | grep -q 'No changes: dry-run only'
set +e
sh "$SCRIPT" unknown >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ]
echo 'recovery static/dry-run tests passed'
