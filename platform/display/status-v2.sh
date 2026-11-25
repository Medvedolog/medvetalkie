#!/usr/bin/env bash
# Optional ST7789 v2 status renderer. Does not replace Bjorni service.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
status=''
preview=0
args=()
while (( $# )); do
  case "$1" in
    --status-file)
      [[ $# -ge 2 && "$2" == /* ]] || { echo "Absolute --status-file required" >&2; exit 2; }
      status="$2"; shift 2 ;;
    --preview)
      [[ $# -ge 2 && "$2" == /* ]] || { echo "Absolute --preview required" >&2; exit 2; }
      args+=("$1" "$2"); preview=1; shift 2 ;;
    --spi-mhz|--fps|--status-seconds)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; exit 2; }
      args+=("$1" "$2"); shift 2 ;;
    *) echo "Unsupported option: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$status" ]] || { echo "--status-file required" >&2; exit 2; }
[[ "$status" != /dev/* ]] || { echo "Device status file disallowed" >&2; exit 2; }
if (( ! preview )); then
  (( EUID == 0 )) || { echo "Root required for SPI/GPIO" >&2; exit 1; }
  command -v fuser >/dev/null || { echo "fuser required for SPI ownership check" >&2; exit 1; }
  if fuser /dev/spidev1.0 >/dev/null 2>&1; then
    echo "SPI busy: stop existing display owner manually before using v2" >&2
    exit 1
  fi
fi
temp="$(mktemp -d /tmp/medvetalkie-display-v2.XXXXXXXX)"
cleanup() { rm -rf -- "$temp"; }
trap cleanup EXIT
python3 "$here/screensaver/build-status-v2.py" --output "$temp/renderer.c"
cc -std=c11 -O2 -Wall -Wextra "$temp/renderer.c" -lm -o "$temp/renderer"
python3 - "$here/screensaver/bjorni-sprite.gz.b64" "$temp/sprite.dat" <<'PY'
import base64,gzip,sys
from pathlib import Path
Path(sys.argv[2]).write_bytes(gzip.decompress(base64.b64decode(Path(sys.argv[1]).read_bytes())))
PY
export MEDVETALKIE_SPRITE="$temp/sprite.dat"
"$temp/renderer" --status-file "$status" --spi-mhz 4 --fps 25 --no-sync "${args[@]}"
