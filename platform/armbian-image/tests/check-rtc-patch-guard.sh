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
PATCH_NAME="drv-rtc-pcf8563-pass-driver-data-to-irq-handler.patch"
mkdir -p "$PATCH_DIR" "$SOURCE_DIR"

# Case 1: base kernel already has the exact fix. Only this duplicate patch is removed.
printf '\tpcf8563_driver.driver.name, pcf8563);\n' > "$SOURCE_DIR/rtc-pcf8563.c"
printf '%s\n' \
  '+\tpcf8563_driver.driver.name, pcf8563);' \
  '-\tpcf8563_driver.driver.name, client);' > "$PATCH_DIR/$PATCH_NAME"
kernel_extra_create_patches__medvetalkie_rtc_patch_guard
test ! -e "$PATCH_DIR/$PATCH_NAME"

# Case 2: base kernel still needs the fix. The original patch must remain.
printf '\tpcf8563_driver.driver.name, client);\n' > "$SOURCE_DIR/rtc-pcf8563.c"
printf '%s\n' \
  '+\tpcf8563_driver.driver.name, pcf8563);' \
  '-\tpcf8563_driver.driver.name, client);' > "$PATCH_DIR/$PATCH_NAME"
kernel_extra_create_patches__medvetalkie_rtc_patch_guard
test -s "$PATCH_DIR/$PATCH_NAME"

echo "PASS: RTC duplicate patch is skipped only when the source already contains the exact fix"
