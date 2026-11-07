#!/usr/bin/env bash
# Runs INSIDE the target Armbian image chroot, after kernel + matching headers.
# Rebuilds all three UWE5622 modules against exactly the image kernel ABI.
set -euo pipefail
if (( $# != 1 )); then echo "Usage: $0 <target-kernel-release>" >&2; exit 2; fi
KVER=$1
ROOT=/usr/src/medvetalkie-uwe5622-1.0
KDIR="/lib/modules/$KVER/build"
DEST="/lib/modules/$KVER/updates/medvetalkie"
[[ -f "$KDIR/Makefile" && -s "$KDIR/Module.symvers" ]] || {
  echo "No matching kernel headers or Module.symvers for $KVER" >&2; exit 1;
}
grep -Fx "#define UTS_RELEASE \"$KVER\"" "$KDIR/include/generated/utsrelease.h"
for tool in make gcc modinfo readelf depmod sha256sum; do
  command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done
make -C "$KDIR" -j2 M="$ROOT/unisocwcn" CONFIG_AW_WIFI_DEVICE_UWE5622=y \
  UNISOC_FW_PATH_CONFIG=/lib/firmware/uwe5622/ modules
[[ -s "$ROOT/unisocwcn/Module.symvers" ]] || exit 1
make -C "$KDIR" -j2 M="$ROOT/unisocwifi" CONFIG_WLAN_UWE5622=m \
  UNISOC_BSP_INCLUDE="$ROOT/unisocwcn/include" \
  UNISOC_WIFI_CUS_CONFIG=/lib/firmware/uwe5622 \
  KBUILD_EXTRA_SYMBOLS="$ROOT/unisocwcn/Module.symvers" modules
make -C "$KDIR" -j2 M="$ROOT/tty-sdio" CONFIG_TTY_OVERY_SDIO=m \
  UNISOC_BSP_INCLUDE="$ROOT/unisocwcn/include" \
  KBUILD_EXTRA_SYMBOLS="$ROOT/unisocwcn/Module.symvers" modules
mods=( "$ROOT/unisocwcn/uwe5622_bsp_sdio.ko" "$ROOT/unisocwifi/sprdwl_ng.ko" "$ROOT/tty-sdio/sprdbt_tty.ko" )
for f in "${mods[@]}"; do
  [[ -s "$f" ]] || { echo "Missing built module: $f" >&2; exit 1; }
  [[ "$(modinfo -F vermagic "$f")" == "$KVER "* ]] || {
    echo "ABI release mismatch in $f" >&2; exit 1;
  }
  readelf -h "$f" | grep -q 'Machine:.*AArch64' || {
    echo "Architecture mismatch in $f" >&2; exit 1;
  }
done
install -d -m 755 "$DEST" /usr/share/medvetalkie/uwe5622
for f in "${mods[@]}"; do
  install -m 644 "$f" "$DEST/"
done
cp "$ROOT/unisocwcn/Module.symvers" /usr/share/medvetalkie/uwe5622/BSP-Module.symvers
cp "$ROOT/BUILD-PROVENANCE.txt" /usr/share/medvetalkie/uwe5622/BUILD-PROVENANCE.txt
(
  cd "$DEST"
  sha256sum ./*.ko > /usr/share/medvetalkie/uwe5622/SHA256SUMS
)
depmod -a "$KVER"
for m in uwe5622_bsp_sdio sprdwl_ng sprdbt_tty; do
  resolved=$(modinfo -k "$KVER" -n "$m" 2>/dev/null || :)
  case "$resolved" in
    "$DEST/"*) echo "Resolved patched $m: $resolved" ;;
    *) echo "Module lookup did not prioritize patched $m: $resolved" >&2; exit 1 ;;
  esac
done
printf 'All 3 UWE5622 modules built and installed for %s; no hardware validation.\n' "$KVER"
