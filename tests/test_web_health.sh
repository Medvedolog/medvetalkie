#!/bin/sh
set -eu
web=$1
core=$2
work=$(mktemp -d)
socket_path="$work/core.sock"
db_path="$work/settings.db"
mkdir -p "$work/sys/class/bluetooth"
core_pid=
web_pid=
cleanup() {
    [ -z "$web_pid" ] || { kill "$web_pid" 2>/dev/null || :; wait "$web_pid" 2>/dev/null || :; }
    [ -z "$core_pid" ] || { kill "$core_pid" 2>/dev/null || :; wait "$core_pid" 2>/dev/null || :; }
    rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM
"$web" --version | grep -q 'medvetalkie-web'
# Use a distinct local test port; live upgrades must not collide with
# an already running systemd Web Alpha on the production port 8765.
if "$web" --listen-port 80 >"$work/invalid-port.log" 2>&1; then
    echo "Privileged/invalid test listen port was accepted" >&2
    exit 1
fi
"$web" --ipc-socket "$socket_path" --listen-port 18765 >"$work/web.log" 2>&1 &
web_pid=$!
url=http://127.0.0.1:18765
i=0
while [ "$i" -lt 40 ]; do
    if curl --noproxy '*' --silent --max-time 1 "$url/" | grep -q 'Web Alpha'; then break; fi
    kill -0 "$web_pid" 2>/dev/null || { cat "$work/web.log" >&2; exit 1; }
    i=$((i + 1))
    sleep 0.1
done
[ "$i" -lt 40 ] || { echo 'web did not start' >&2; exit 1; }
code=$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' --max-time 2 "$url/api/v1/health")
[ "$code" = 503 ] || { echo "expected 503 without core; got $code" >&2; exit 1; }

# Force just this test Core onto a nonexistent D-Bus system socket.
# Live BlueZ may run on the operator's Orange Pi; its presence must not
# change the deterministic 503-offline expectation below.
DBUS_SYSTEM_BUS_ADDRESS="unix:path=$work/nonexistent-system-bus.sock" \
    "$core" --ipc-socket "$socket_path" --db-path "$db_path" \
    --bluetooth-sysfs-root "$work/sys" >"$work/core.log" 2>&1 &
core_pid=$!
i=0
while [ "$i" -lt 40 ]; do
    if curl --noproxy '*' --silent --max-time 1 "$url/api/v1/health" | grep -q '"core":"reachable"'; then break; fi
    kill -0 "$core_pid" 2>/dev/null || { cat "$work/core.log" >&2; exit 1; }
    i=$((i + 1))
    sleep 0.1
done
[ "$i" -lt 40 ] || { echo 'web -> core IPC failed' >&2; exit 1; }
curl --noproxy '*' --silent --fail --max-time 2 "$url/api/v1/status" | grep -q '"effective_mode":"UNKNOWN"'
curl --noproxy '*' --silent --fail --max-time 2 "$url/api/v1/capabilities" | grep -q '"hfp_audio":false'
curl --noproxy '*' --silent --fail --max-time 2 "$url/api/v1/settings" | grep -q '"device_name":"MedveTalkie"'
curl --noproxy '*' --silent --fail --max-time 2 "$url/api/v1/display" | grep -q '"hardware_applied":false'
curl --noproxy '*' --silent --fail --max-time 2 "$url/api/v1/bt/controllers" | grep -q '"controller_count":0'
curl --noproxy '*' --silent --fail --max-time 2 "$url/api/v1/bt/controllers" | grep -q '"bluez_state":"NOT_CHECKED"'
# On CI AND on a live Orange Pi with healthy BlueZ, only this test Core
# has no reachable D-Bus. Thus 503 is expected independently of the host.
code=$(curl --noproxy '*' --silent --output "$work/bluez.json" --write-out '%{http_code}' --max-time 2 "$url/api/v1/bt/bluez")
[ "$code" = 503 ] || { echo "BlueZ must report HTTP 503 offline: $code" >&2; exit 1; }
grep -q '"code":"NOT_READY"' "$work/bluez.json"
code=$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' --max-time 2 \
       -X POST "$url/api/v1/health")
[ "$code" = 405 ] || { echo "POST should be rejected: $code" >&2; exit 1; }
code=$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' --max-time 2 \
       -X PATCH -d '{"device_name":"evil"}' "$url/api/v1/settings")
[ "$code" = 405 ] || { echo "unauthenticated PATCH should be rejected: $code" >&2; exit 1; }

kill "$core_pid" 2>/dev/null || :
wait "$core_pid" 2>/dev/null || :
core_pid=
code=$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' --max-time 2 "$url/api/v1/status")
[ "$code" = 503 ] || { echo "core exit not surfaced: $code" >&2; exit 1; }
kill -0 "$web_pid" 2>/dev/null || { echo 'web crashed after core died' >&2; exit 1; }
echo "PASS: isolated localhost port; BlueZ outage 503 even with host bluetoothd; read-only API, Core failure"
