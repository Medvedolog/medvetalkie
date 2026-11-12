#!/bin/sh
set -eu
binary=$1
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
mkdir -p "$work/1-1" "$work/1-2" "$work/usb1" "$work/1-1:1.0"
printf '%s\n' 0a12 > "$work/1-1/idVendor"
printf '%s\n' 0001 > "$work/1-1/idProduct"
printf '%s\n' DUPLICATE > "$work/1-1/serial"
printf '%s\n' 1 > "$work/1-1/busnum"
printf '%s\n' 7 > "$work/1-1/devnum"
printf '%s\n' 0a12 > "$work/1-2/idVendor"
printf '%s\n' 0001 > "$work/1-2/idProduct"
printf '%s\n' DUPLICATE > "$work/1-2/serial"
printf '%s\n' 1 > "$work/1-2/busnum"
printf '%s\n' 8 > "$work/1-2/devnum"
"$binary" --sysfs "$work" > "$work/out"
[ "$(wc -l < "$work/out")" -eq 3 ]
grep -q "$(printf '1-1\t0a12\t0001\tDUPLICATE')" "$work/out"
grep -q "$(printf '1-2\t0a12\t0001\tDUPLICATE')" "$work/out"
if "$binary" --sysfs "$work/missing" >/dev/null 2>&1; then
  echo 'expected non-zero exit on missing sysfs' >&2
  exit 1
fi
