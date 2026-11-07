#!/usr/bin/env bash
# Stage a full Armbian image build for Orange Pi Zero 3 (H618).
# Default: prepare sources only. --build starts the resource-intensive image.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT=$(realpath "$HERE/../..")
DEST=$(realpath -m "${1:-$PWD/armbian-build-medvetalkie}")
WIFI_PROFILE=${WIFI_PROFILE:-apsta}
BT_PROFILE=${BT_PROFILE:-stock}
ARM_REF=664d5fdf0efa5284dd85daae15101c5423d6de73
UWE_REF=bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880
OPENWRT_REF=29b6faf6b08a2b62097e509eb0fa62720ab48996
BUILD_FLAG=${2:-}
case "$WIFI_PROFILE" in p0|apsta) ;; *) echo "WIFI_PROFILE must be p0 or apsta" >&2; exit 2 ;; esac
case "$BT_PROFILE" in stock|patched) ;; *) echo "BT_PROFILE must be stock or patched" >&2; exit 2 ;; esac
case "$BUILD_FLAG" in ""|--build) ;; *) echo "Optional second argument: --build" >&2; exit 2 ;; esac
for cmd in git tar bash patch realpath; do command -v "$cmd" >/dev/null || exit 1; done

if [[ ! -d "$DEST/.git" ]]; then
  [[ ! -e "$DEST" ]] || { echo "Destination exists but is not Armbian git checkout: $DEST" >&2; exit 1; }
  git clone --filter=blob:none --no-checkout https://github.com/armbian/build.git "$DEST"
fi
git -C "$DEST" checkout --detach "$ARM_REF"
[[ "$(git -C "$DEST" rev-parse HEAD)" == "$ARM_REF" ]] || exit 1
# Protect all pre-existing custom userpatches. Repeat preparation requires a
# fresh DEST, so no previous image tree can be silently mixed with this image.
for path in "$DEST/userpatches/medvetalkie-uwe5622-src" \
            "$DEST/userpatches/medvetalkie-uwe5622-scripts" \
            "$DEST/extensions/medvetalkie-uwe5622.sh"; do
  [[ ! -e "$path" ]] || { echo "Refusing to overwrite prepared file: $path" >&2; exit 1; }
done
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
git clone -q https://github.com/armbian/uwe5622.git "$WORK/uwe5622"
git -C "$WORK/uwe5622" checkout -q --detach "$UWE_REF"
git clone -q https://github.com/Medvedolog/opiz3-wlan-backport.git "$WORK/openwrt"
git -C "$WORK/openwrt" checkout -q --detach "$OPENWRT_REF"
if [[ "$BT_PROFILE" == patched ]]; then
  export MEDVETALKIE_BT_PATCHES=yes
else
  export MEDVETALKIE_BT_PATCHES=no
fi
bash "$HERE/apply-source-profile.sh" "$WORK/uwe5622" "$WORK/openwrt" "$WIFI_PROFILE"

STAGED="$DEST/userpatches/medvetalkie-uwe5622-src"
ASSETS="$DEST/userpatches/medvetalkie-uwe5622-scripts"
mkdir -p "$STAGED" "$ASSETS"
tar -C "$WORK/uwe5622" --exclude='./.git' -cf - . | tar -C "$STAGED" -xf -
cp "$HERE/install-image-modules.sh" "$STAGED/install-image-modules.sh"
cp "$PROJECT/platform/uwe5622/wifi/scripts/uwe5622-recover" "$ASSETS/"
cp "$PROJECT/platform/uwe5622/wifi/scripts/uwe5622-preflight" "$ASSETS/"
cp "$PROJECT/platform/uwe5622/wifi/scripts/uwe5622-abi-check" "$ASSETS/"
cp "$PROJECT/platform/uwe5622/wifi/scripts/medvetalkie-uwe5622-recover.service" "$ASSETS/"
cp "$HERE/medvetalkie-uwe5622.sh" "$DEST/extensions/medvetalkie-uwe5622.sh"
chmod +x "$STAGED/install-image-modules.sh"
{
  printf 'Armbian build: %s\nUWE5622 driver: %s\nOpenWrt patches: %s\n' "$ARM_REF" "$UWE_REF" "$OPENWRT_REF"
  printf 'Wi-Fi patch profile: %s\nBT transport patches: %s\n' "$WIFI_PROFILE" "$BT_PROFILE"
  printf 'USB Bluetooth: stock btusb / BlueZ; onboard attach service explicitly opt-in\n'
  printf 'Source: https://github.com/Medvedolog/medvetalkie\n'
} > "$STAGED/BUILD-PROVENANCE.txt"
echo "Prepared Armbian image build tree at $DEST"
echo "  BOARD=orangepizero3; BRANCH=current; RELEASE=trixie"
echo "  Wi-Fi profile=$WIFI_PROFILE; BT profile=$BT_PROFILE"
echo "  Full image NOT yet built; bootloader, DTB, kernel will be built from pinned Armbian source."
if [[ "$BUILD_FLAG" == --build ]]; then
  cd "$DEST"
  ./compile.sh BOARD=orangepizero3 BRANCH=current RELEASE=trixie \
    BUILD_DESKTOP=no BUILD_MINIMAL=yes KERNEL_CONFIGURE=no \
    INSTALL_HEADERS=yes EXPERT=yes ENABLE_EXTENSIONS=medvetalkie-uwe5622
  echo "Armbian output images: $DEST/output/images"
fi
