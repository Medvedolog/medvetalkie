#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
eth="$root/network/10-medvetalkie-ethernet.nmconnection"
wifi="$root/network/20-medvetalkie-wifi-ap.nmconnection"
ext="$root/medvetalkie-uwe5622.sh"
prep="$root/prepare-full-image.sh"
[ -s "$eth" ] && [ -s "$wifi" ]
grep -Fx 'type=ethernet' "$eth"
grep -Fx 'interface-name=end0' "$eth"
grep -Fx 'method=shared' "$eth"
grep -Fx 'address1=192.168.11.1/24' "$eth"
grep -Fx 'type=wifi' "$wifi"
grep -Fx 'interface-name=wlan0' "$wifi"
grep -Fx 'mode=ap' "$wifi"
grep -Fx 'ssid=MedveTalkie' "$wifi"
grep -Fx 'band=a' "$wifi"
grep -Fx 'channel=36' "$wifi"
grep -Fx 'method=shared' "$wifi"
grep -Fx 'address1=192.168.12.1/24' "$wifi"
grep -Fx 'psk=Medve12345!' "$wifi"
grep -F 'dnsmasq-base' "$ext"
grep -F 'btusb' "$ext"
grep -F 'NETWORKING_STACK=network-manager' "$prep"
grep -F '0001 0002' "$root/apply-source-profile.sh" >/dev/null
echo 'PASS: separate Ethernet/Wi-Fi shared subnets, AP profile, USB BT and pinned patch pipeline'
