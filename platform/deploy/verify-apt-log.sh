#!/bin/sh
# Inspect captured apt-get update output. apt may return 0 despite
# failed signatures, using stale indexes. Never bypass signature checks.
set -eu
[ "$#" -eq 1 ] && [ -r "$1" ] || {
    echo 'Usage: verify-apt-log.sh READABLE_APT_UPDATE_LOG' >&2
    exit 64
}
if grep -Eiq 'Not live until|Missing key|NO_PUBKEY|OpenPGP signature|signature verification|Failed to fetch|Some index files failed|Release file.*not valid|^W:.*(signature|repository|index files)|^E:' "$1"; then
    echo "APT update contained signature or repository errors; refusing stale package indexes" >&2
    exit 1
fi
exit 0
