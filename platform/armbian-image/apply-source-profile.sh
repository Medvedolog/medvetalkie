#!/usr/bin/env bash
# Prepare one auditable UWE5622 source tree for an Armbian full-image build.
# Never touches the running board. Inputs must be clean pinned Git worktrees.
set -euo pipefail
if (( $# != 3 )); then
  echo "Usage: $0 <uwe5622-source> <opiz3-wlan-backport-source> <p0|apsta>" >&2
  exit 2
fi
UWE=$(realpath "$1")
BACKPORT=$(realpath "$2")
PROFILE=$3
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
OPENWRT_PATCHES="$BACKPORT/package/kernel/uwe5622/patches"
for path in "$UWE/.git" "$BACKPORT/.git" "$OPENWRT_PATCHES"; do
  [[ -e "$path" ]] || { echo "Missing checkout/patch directory: $path" >&2; exit 1; }
done
case "$PROFILE" in p0|apsta) ;; *) echo "Invalid Wi-Fi profile: $PROFILE" >&2; exit 2 ;; esac
[[ -z $(git -C "$UWE" status --porcelain) ]] || { echo "Driver tree must be clean" >&2; exit 1; }
ref=$(git -C "$UWE" rev-parse HEAD)
[[ "$ref" == "bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880" ]] || {
  echo "Unreviewed UWE5622 revision $ref" >&2; exit 1;
}
ref=$(git -C "$BACKPORT" rev-parse HEAD)
[[ "$ref" == "29b6faf6b08a2b62097e509eb0fa62720ab48996" ]] || {
  echo "Unreviewed OpenWrt patch revision $ref" >&2; exit 1;
}
already=$(find "$OPENWRT_PATCHES" -maxdepth 1 -type f -name '070-*.patch' -print -quit)
[[ -n "$already" ]] && git -C "$UWE" apply --reverse --check --recount "$already" || {
  echo "Expected upstream 070 fix absent" >&2; exit 1;
}
echo '070 present in base source'
apply_one() {
  local id=$1 file
  case "$id" in
    030) file="$HERE/../wifi/patches/030-cfg80211-netdev-locking-armbian.patch" ;;
    160) file="$HERE/../wifi/patches/160-prepare-addba-armbian.patch" ;;
    190) file="$HERE/../wifi/patches/190-addba-tid-array-armbian.patch" ;;
    290) file="$HERE/../wifi/patches/290-per-interface-mac-armbian.patch" ;;
    *) file=$(find "$OPENWRT_PATCHES" -maxdepth 1 -type f -name "$id-*.patch" -print -quit) ;;
  esac
  [[ -n "$file" && -f "$file" ]] || { echo "Missing patch: $id" >&2; exit 1; }
  git -C "$UWE" apply --check --recount -- "$file"
  git -C "$UWE" apply --recount -- "$file"
  echo "Applied $id $(basename "$file")"
}
for id in 030 130 160 190 220 250 330; do apply_one "$id"; done
if [[ "$PROFILE" == apsta ]]; then
  for id in 180 200 290 310; do apply_one "$id"; done
fi
# Bluetooth transport activation remains opt-in even when its source is patched.
if [[ "${MEDVETALKIE_BT_PATCHES:-no}" == yes ]]; then
  for id in 0001 0002; do
    file=$(find "$HERE/../patches" -maxdepth 1 -type f -name "$id-sprdbt-tty-*.patch" -print -quit)
    [[ -n "$file" ]] || { echo "Missing optional BT patch $id" >&2; exit 1; }
    patch -d "$UWE" --forward --batch -p1 < "$file"
    echo "Applied optional BT $id $(basename "$file")"
  done
fi
echo "Prepared patched UWE5622 source: Wi-Fi=$PROFILE, BT patches=${MEDVETALKIE_BT_PATCHES:-no}"
