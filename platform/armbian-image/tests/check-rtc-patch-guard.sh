#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
EXTENSION="$ROOT/medvetalkie-uwe5622.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

exit_with_error() {
  printf 'unexpected guard error: %s\n' "$*" >&2
  exit 1
}
display_alert() { :; }

source "$EXTENSION"

SRC="$TMP/armbian"
KERNELPATCHDIR="archive/sunxi-6.18"
kernel_work_dir="$TMP/kernel"
PATCH_DIR="$SRC/patch/kernel/$KERNELPATCHDIR/patches.armbian"
SOURCE_DIR="$kernel_work_dir/drivers/rtc"
SERIES_FILE="$SRC/patch/kernel/$KERNELPATCHDIR/series.conf"
PATCH_NAME="drv-rtc-pcf8563-pass-driver-data-to-irq-handler.patch"
SERIES_ENTRY="patches.armbian/$PATCH_NAME"
mkdir -p "$PATCH_DIR" "$SOURCE_DIR"

# Case 1: fixed base source: remove only its series entry and patch file.
printf '\tpcf8563_driver.driver.name, pcf8563);\n' > "$SOURCE_DIR/rtc-pcf8563.c"
printf '+\tpcf8563_driver.driver.name, pcf8563);\n-\tpcf8563_driver.driver.name, client);\n' > "$PATCH_DIR/$PATCH_NAME"
printf '\t%s\n' "$SERIES_ENTRY" 'patches.armbian/keep-this-unrelated.patch' > "$SERIES_FILE"
kernel_extra_create_patches__medvetalkie_rtc_patch_guard
test ! -e "$PATCH_DIR/$PATCH_NAME"
! awk -v target="$SERIES_ENTRY" '$1 == target { found=1 } END { exit !found }' "$SERIES_FILE"
grep -Fxq 'patches.armbian/keep-this-unrelated.patch' "$SERIES_FILE"

# Case 2: unfixed base source: keep both patch and series entry.
printf '\tpcf8563_driver.driver.name, client);\n' > "$SOURCE_DIR/rtc-pcf8563.c"
printf '+\tpcf8563_driver.driver.name, pcf8563);\n-\tpcf8563_driver.driver.name, client);\n' > "$PATCH_DIR/$PATCH_NAME"
printf '\t%s\n' "$SERIES_ENTRY" 'patches.armbian/keep-this-unrelated.patch' > "$SERIES_FILE"
kernel_extra_create_patches__medvetalkie_rtc_patch_guard
test -s "$PATCH_DIR/$PATCH_NAME"
awk -v target="$SERIES_ENTRY" '$1 == target { found=1 } END { exit !found }' "$SERIES_FILE"

echo "PASS: duplicate RTC patch and only its exact series entry are skipped when source already has the fix"
