#!/bin/sh
set -eu
[ "$#" -eq 1 ] || { echo "Usage: $0 /path/to/armbian-uwe5622" >&2; exit 2; }
src=$1
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/.." && pwd)
command -v patch >/dev/null 2>&1 || { echo "patch utility required" >&2; exit 2; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
for f in unisocwcn/sdio/sdiohal_main.c unisocwcn/platform/loopcheck.c unisocwifi/cfg80211.c; do
  [ -f "$src/$f" ] || { echo "Missing $src/$f" >&2; exit 2; }
  mkdir -p "$tmp/$(dirname "$f")"
  cp "$src/$f" "$tmp/$f"
done
for p in 220-unisocwcn-sdiohal-unlock-on-dt-rw-fail.patch 330-unisocwcn-loopcheck-fail-no-self-cancel.patch 310-unisocwifi-wait-for-disconnect-event.patch; do
  echo "Applying $p to isolated source copy"
  (cd "$tmp" && patch --batch --fuzz=0 --forward -p1 < "$root/patches/$p")
done
grep -q 'clear_bit(WCN_LOOPCHECK_OPEN' "$tmp/unisocwcn/platform/loopcheck.c"
grep -q 'no disconnect event within 1 s' "$tmp/unisocwifi/cfg80211.c"
echo 'PASS: three source patches applied to pinned driver revision'
