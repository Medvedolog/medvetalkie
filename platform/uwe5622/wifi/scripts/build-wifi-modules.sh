#!/usr/bin/env bash
# Build experimental WLAN+BSP modules only. No installation, DKMS or BT changes.
set -euo pipefail

if (( $# != 4 )); then
  echo "usage: $0 <uwe5622-git-tree> <opiz3-wlan-backport-git-tree> <kernel-build-tree> <output-dir>" >&2
  exit 2
fi

UWE=$(realpath "$1")
BACKPORT=$(realpath "$2")
KDIR=$(realpath "$3")
OUT=$4
PROFILE=${WIFI_PROFILE:-p0}
KVER=${EXPECTED_KERNEL_RELEASE:-6.18.60-current-sunxi64}
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PATCH_DIR="$BACKPORT/package/kernel/uwe5622/patches"
case "$PROFILE" in p0|apsta) ;; *) echo "Unknown WIFI_PROFILE: $PROFILE" >&2; exit 2 ;; esac
for path in "$UWE/.git" "$BACKPORT/.git" "$KDIR/Makefile" "$KDIR/Module.symvers" "$KDIR/include/generated/utsrelease.h"; do
  [[ -e "$path" ]] || { echo "Required source/kernel file missing: $path" >&2; exit 1; }
done
grep -Fx "#define UTS_RELEASE \"$KVER\"" "$KDIR/include/generated/utsrelease.h"
[[ $(git -C "$UWE" status --porcelain | wc -l) -eq 0 ]] || {
  echo "UWE5622 tree is not clean before patching" >&2; exit 1;
}
mkdir -p "$OUT"
OUT=$(realpath "$OUT")

apply_patch() {
  local num=$1 file
  if [[ "$num" == 030 || "$num" == 160 || "$num" == 190 || "$num" == 290 ]]; then
    case "$num" in
      030) file="$SCRIPT_DIR/../patches/030-cfg80211-netdev-locking-armbian.patch" ;;
      160) file="$SCRIPT_DIR/../patches/160-prepare-addba-armbian.patch" ;;
      190) file="$SCRIPT_DIR/../patches/190-addba-tid-array-armbian.patch" ;;
      290) file="$SCRIPT_DIR/../patches/290-per-interface-mac-armbian.patch" ;;
    esac
  else
    file=$(find "$PATCH_DIR" -maxdepth 1 -type f -name "$num-*.patch" -print -quit)
  fi
  [[ -n "$file" && -r "$file" ]] || { echo "Required patch $num missing" >&2; exit 1; }
  git -C "$UWE" apply --check --recount -- "$file"
  git -C "$UWE" apply --recount -- "$file"
  printf '%s %s\n' "$num" "$(basename "$file")" >> "$OUT/PATCHES.txt"
}
: > "$OUT/PATCHES.txt"

# Both profiles use only the verified upstream baseline, not the BT test patches.
# 070 is already matched by upstream; fail if this ceases to be true.
p070=$(find "$PATCH_DIR" -maxdepth 1 -type f -name '070-*.patch' -print -quit)
[[ -n "$p070" ]] || { echo "Cannot find patch 070" >&2; exit 1; }
git -C "$UWE" apply --reverse --check --recount -- "$p070" || {
  echo "Upstream no longer contains expected 070 fix; stop for review" >&2
  exit 1
}
echo "070 already present in pinned source" >> "$OUT/PATCHES.txt"
for number in 030 130 160 190 220 250 330; do
  apply_patch "$number"
done
if [[ "$PROFILE" == apsta ]]; then
  for number in 180 200 290 310; do apply_patch "$number"; done
fi

# Build dependent BSP first and then WLAN using its exact exported symbol CRCs.
JOBS=${BUILD_JOBS:-2}
make -C "$KDIR" -j"$JOBS" M="$UWE/unisocwcn" \
  CONFIG_AW_WIFI_DEVICE_UWE5622=y \
  UNISOC_FW_PATH_CONFIG=/lib/firmware/uwe5622/ modules
test -s "$UWE/unisocwcn/Module.symvers"
make -C "$KDIR" -j"$JOBS" M="$UWE/unisocwifi" \
  CONFIG_WLAN_UWE5622=m \
  UNISOC_BSP_INCLUDE="$UWE/unisocwcn/include" \
  UNISOC_WIFI_CUS_CONFIG=/lib/firmware/uwe5622 \
  KBUILD_EXTRA_SYMBOLS="$UWE/unisocwcn/Module.symvers" modules

for path in "$UWE/unisocwcn/uwe5622_bsp_sdio.ko" "$UWE/unisocwifi/sprdwl_ng.ko"; do
  [[ -s "$path" ]] || { echo "Module absent: $path" >&2; exit 1; }
  name=${path##*/}
  cp "$path" "$OUT/$name"
  vermagic=$(modinfo -F vermagic "$path")
  [[ "$vermagic" == "$KVER "* ]] || { echo "Unexpected vermagic: $name: $vermagic" >&2; exit 1; }
  readelf -h "$path" | grep -q 'Machine:.*AArch64' || {
    echo "Unexpected ELF architecture: $name" >&2; exit 1;
  }
  modinfo "$path" > "$OUT/$name.modinfo.txt"
done
cp "$UWE/unisocwcn/Module.symvers" "$OUT/BSP-Module.symvers"
sha256sum "$OUT"/*.ko > "$OUT/SHA256SUMS"
git -C "$UWE" rev-parse HEAD > "$OUT/UPSTREAM_COMMIT"
git -C "$BACKPORT" rev-parse HEAD > "$OUT/OPENWRT_COMMIT"
{
  echo "Profile: $PROFILE"
  echo "Header kernel release: $KVER"
  echo "UWE source: $(git -C "$UWE" rev-parse HEAD)"
  echo "OpenWrt patch source: $(git -C "$BACKPORT" rev-parse HEAD)"
  echo "Compiled kernel objects are experimental and NOT validated against the running board."
  echo "DO NOT INSTALL until actual module provenance, kernel symbol CRCs and recovery path are verified."
  echo "No BT module, BT firmware, kernel, or Device Tree was modified."
} > "$OUT/README-NOT-FOR-INSTALL.txt"
