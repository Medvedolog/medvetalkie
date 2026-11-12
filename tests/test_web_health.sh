#!/bin/sh
set -eu
bin=$1
"$bin" --version | grep -q 'medvetalkie-web'
"$bin" >/dev/null 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || :; wait "$pid" 2>/dev/null || :' EXIT HUP INT TERM
ok=0
i=0
while [ "$i" -lt 40 ]; do
  if curl --noproxy '*' --silent --fail --max-time 1 http://127.0.0.1:8765/api/v1/health | grep -q '"core":"not_connected"'; then
    ok=1
    break
  fi
  kill -0 "$pid" 2>/dev/null || break
  i=$((i + 1))
  sleep 0.1
done
[ "$ok" -eq 1 ] || { echo 'web health failed' >&2; exit 1; }
code=$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' --max-time 2 -X POST http://127.0.0.1:8765/api/v1/health)
[ "$code" = 405 ] || { echo "unexpected POST response: $code" >&2; exit 1; }
