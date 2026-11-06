#!/bin/sh
# Check sequential application without changing the source checkout.
set -eu
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/armbian-uwe5622-source" >&2
  exit 2
fi
src=$1
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$script_dir/.." && pwd)
[ -f "$src/tty-sdio/tty.c" ] || { echo "Missing $src/tty-sdio/tty.c" >&2; exit 2; }
command -v patch >/dev/null || { echo "Install patch utility" >&2; exit 2; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir -p "$tmp/tty-sdio"
cp "$src/tty-sdio/tty.c" "$tmp/tty-sdio/tty.c"
for name in \
  0001-sprdbt-tty-add-hci-rx-sdio-counters.patch \
  0002-sprdbt-tty-fix-rx-queue-ownership.patch
do
  echo "Checking $name"
  (cd "$tmp" && patch --batch --forward -p1 < "$root/patches/$name")
done
grep -q 'hci_rx_stats_show' "$tmp/tty-sdio/tty.c"
grep -q 'rx->data = kmalloc' "$tmp/tty-sdio/tty.c"
echo "PASS: both patches apply sequentially and expected symbols are present"
