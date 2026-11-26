#!/usr/bin/env bash
# In-place MedveTalkie install for existing Orange Pi Zero 3 Armbian.
# Never reflashes, changes Wi-Fi modules, network settings, or boot files.
set -Eeuo pipefail
umask 077

SOURCE_DIR="$(cd "$(dirname "$0")/../.." && pwd -P)"
MODE=dry-run
SIMROOT=""
ROLLBACK=0
DISPLAY=0
SKIP_APT=0
USE_PROXY=1
PROXY="http://192.168.11.100:10880"
if [[ -v MEDVETALKIE_PROXY ]]; then PROXY="$MEDVETALKIE_PROXY"; fi
PREFIX=/opt/medvetalkie
UNIT_DIR=/etc/systemd/system
BACKUP_DIR=/var/backups/medvetalkie
BUILD=""
STAGE=""
OLD_RELEASE=""
CHANGED=0

log() { printf '[MedveTalkie] %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
units() {
 printf '%s\n' medvetalkie-core.service medvetalkie-status.service medvetalkie-web.service medvetalkie-display.service
}
help_text() {
cat <<'HELP'
MedveTalkie: install on an already booted Orange Pi Zero 3 / Armbian.
  bash platform/deploy/install-opiz3.sh --dry-run [--proxy http://HOST:PORT]
  sudo bash platform/deploy/install-opiz3.sh --apply [--proxy http://HOST:PORT] [--enable-display]
  sudo bash platform/deploy/install-opiz3.sh --rollback
  bash platform/deploy/install-opiz3.sh --simulate /absolute/staging/root
Flags:
  --proxy http://HOST:PORT  HTTP frontend of a Clash/mihomo mixed proxy.
  --no-proxy               Direct APT connectivity.
  --enable-display         Opt in to owning ST7789 SPI; first stop old renderer.
  --skip-packages          Only when build/runtime dependencies are installed.
  --dry-run                Default: no modifications and no network calls.
  --simulate ABS_PATH      Build, test and install to fake root. No APT/systemd.
  --apply                  Real deploy and systemd activation.
  --rollback               Restore the previous release symlink.
All network package operations use the selected HTTP proxy; local API and
WebUI do not. WebUI is read-only on 127.0.0.1:8765, NOT exposed to LAN.
Does not touch /boot, onboard UWE5622 blacklist, Wi-Fi, LAN or SD image.
HELP
}
while (($#)); do
 case "$1" in
 --help|-h) help_text; exit 0;;
 --dry-run) MODE=dry-run;;
 --apply) MODE=apply;;
 --simulate) (($# >= 2)) || die "Missing --simulate path"; MODE=simulate; SIMROOT="$2"; shift;;
 --rollback) ROLLBACK=1; if [[ "$MODE" == dry-run ]]; then MODE=apply; fi;;
 --proxy) (($# >= 2)) || die "Missing --proxy URL"; PROXY="$2"; USE_PROXY=1; shift;;
 --no-proxy) USE_PROXY=0;;
 --enable-display) DISPLAY=1;;
 --skip-packages) SKIP_APT=1;;
 *) die "Unknown option $1";;
 esac
 shift
done
if ((USE_PROXY)); then
 [[ "$PROXY" =~ ^http://[A-Za-z0-9.-]+:[0-9]{1,5}/?$ ]] ||
   die "Mixed proxy must have format http://HOST:PORT (no credentials)"
 port="$(printf '%s' "$PROXY" | sed 's/.*://; s:/$::')"
 ((10#$port >= 1 && 10#$port <= 65535)) || die "Invalid proxy port"
 PROXY="$(printf '%s' "$PROXY" | sed 's:/$::')"
fi
if [[ -n "$SIMROOT" ]]; then
 [[ "$MODE" == simulate && "$SIMROOT" == /* && "$SIMROOT" != "/" &&
    "$SIMROOT" != "/opt" && "$SIMROOT" != "/etc" && "$SIMROOT" != "/tmp" && ! -L "$SIMROOT" ]] ||
    die "Simulation needs dedicated absolute non-symlink staging directory"
 PREFIX="$SIMROOT/opt/medvetalkie"
 UNIT_DIR="$SIMROOT/etc/systemd/system"
 BACKUP_DIR="$SIMROOT/var/backups/medvetalkie"
fi
[[ -f "$SOURCE_DIR/CMakeLists.txt" &&
   -f "$SOURCE_DIR/tests/test_display_e2e.py" &&
   -f "$SOURCE_DIR/platform/display/medvetalkie-screensaver.sh" ]] ||
   die "Incomplete integrated MedveTalkie checkout"
plan() {
 log "mode=$MODE; prefix=$PREFIX"
 if ((USE_PROXY)); then log "mixed HTTP proxy=$PROXY (APT/curl only)"; else log "direct package access"; fi
 log "Enable core/status/read-only WebUI; enable ST7789=$DISPLAY"
 log "Build and test all components before activation; preserve kernel and network config"
}
if [[ "$MODE" == dry-run ]]; then
 ((ROLLBACK == 0)) || die "--rollback requires --apply or --simulate"
 plan
 log "DRY RUN completed: no network or filesystem changes"
 exit 0
fi
if [[ "$MODE" == apply ]]; then
 ((EUID == 0)) || die "--apply must run under sudo"
 [[ "$(uname -m)" == aarch64 && -f /proc/device-tree/compatible ]] ||
   die "Only physical aarch64 Orange Pi Zero 3 is supported"
 tr '\0' '\n' </proc/device-tree/compatible | grep -Fxq xunlong,orangepi-zero3 ||
   die "Refusing to install on a different board"
 command -v apt-get >/dev/null || die "Armbian/Debian apt-get missing"
 command -v systemctl >/dev/null || die "systemd missing"
 if ((DISPLAY && !ROLLBACK)); then
   [[ -c /dev/spidev1.0 ]] || die "/dev/spidev1.0 not available"
 fi
fi
[[ ! -L "$PREFIX" && (! -e "$PREFIX/current" || -L "$PREFIX/current") ]] ||
  die "Refusing unmanaged/symlinked target"
for unit in $(units); do
 if [[ -f "$UNIT_DIR/$unit" ]]; then
   grep -Fqx '# Managed by MedveTalkie installer' "$UNIT_DIR/$unit" ||
     die "Refusing to overwrite unmanaged $unit"
 fi
done

if ((ROLLBACK)); then
 [[ -L "$PREFIX/previous" ]] || die "No previous managed release"
 previous="$(readlink "$PREFIX/previous")"
 [[ "$previous" == "$PREFIX/releases/"* && -d "$previous" ]] || die "Invalid previous release"
 current=""
 [[ ! -L "$PREFIX/current" ]] || current="$(readlink "$PREFIX/current")"
 if [[ "$MODE" == apply ]]; then
   for unit in $(units); do systemctl stop "$unit" || :; done
 fi
 ln -s "$previous" "$PREFIX/.next.$$"
 mv -Tf "$PREFIX/.next.$$" "$PREFIX/current"
 if [[ -n "$current" && -d "$current" ]]; then ln -sfn "$current" "$PREFIX/previous"; fi
 if [[ "$MODE" == apply ]]; then
   systemctl daemon-reload
   for unit in medvetalkie-core.service medvetalkie-status.service medvetalkie-web.service; do
     systemctl restart "$unit"
   done
   if systemctl is-enabled --quiet medvetalkie-display.service; then
     systemctl restart medvetalkie-display.service
   fi
 fi
 log "Rolled back to $previous"
 exit 0
fi

if [[ "$MODE" == apply && "$SKIP_APT" == 0 ]]; then
 if ((USE_PROXY)); then
   curl --proxy "$PROXY" --noproxy '' --head --fail --silent --show-error \
     --connect-timeout 3 --max-time 12 https://github.com/ >/dev/null ||
     die "Mixed proxy failed HTTPS tunneling: check its listener and firewall"
   apt_proxy() {
     apt-get -o "Acquire::http::Proxy=$PROXY/" \
             -o "Acquire::https::Proxy=$PROXY/" "$@"
   }
 else
   apt_proxy() { apt-get "$@"; }
 fi
 log "Installing dependencies via selected proxy, without changing global APT proxy settings"
 # apt-get update can return 0 even if some InRelease signatures fail and
 # old cached indexes are silently reused. Never proceed on those warnings.
 apt_update_log="$(mktemp /tmp/medvetalkie-apt-update.XXXXXXXX)"
 if ! apt_proxy update >"$apt_update_log" 2>&1; then
   cat "$apt_update_log" >&2
   rm -f "$apt_update_log"
   die "APT update failed; check clock sync, signed repository keys and mixed proxy"
 fi
 if ! sh "$SOURCE_DIR/platform/deploy/verify-apt-log.sh" "$apt_update_log"; then
   cat "$apt_update_log" >&2
   rm -f "$apt_update_log"
   die "APT index verification warnings: refusing cached indexes; fix clock/key or use --skip-packages after confirming dependencies"
 fi
 cat "$apt_update_log"
 rm -f "$apt_update_log"
 DEBIAN_FRONTEND=noninteractive apt_proxy install -y --no-install-recommends \
   build-essential cmake pkg-config libjson-c-dev libsqlite3-dev \
   libdbus-1-dev libcivetweb-dev python3 curl ca-certificates git psmisc
fi

if [[ "$MODE" == apply && "$DISPLAY" == 1 ]]; then
 # The hardware trial proved a cron.d watchdog can respawn a legacy
 # renderer between the first SPI check and service activation.
 sh "$SOURCE_DIR/platform/deploy/check-legacy-display-cron.sh" ||
   die "Legacy cron.d display autostart must be disabled before --enable-display"
 # Even if the systemd display unit appears active, its current process may
 # only be compiling/restarting while a legacy cron screensaver holds SPI.
 # Verify every owner PID belongs to OUR display cgroup, otherwise stop
 # before recompiling the entire project or replacing any running services.
 sh "$SOURCE_DIR/platform/deploy/check-display-owner.sh" --allow-managed ||
   die "Unmanaged SPI renderer detected: disable its cron/manual supervisor"
fi
command -v cmake >/dev/null || die "cmake missing"
command -v python3 >/dev/null || die "python3 missing"
command -v cc >/dev/null || die "C compiler missing"
BUILD="$(mktemp -d /tmp/medvetalkie-build.XXXXXXXX)"
cleanup() {
 [[ -z "$BUILD" || ! -d "$BUILD" ]] || rm -rf -- "$BUILD"
 [[ -z "$STAGE" || ! -d "$STAGE" ]] || rm -rf -- "$STAGE"
}
trap cleanup EXIT
log "Build and full regression tests run BEFORE service replacement"
cmake -S "$SOURCE_DIR" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build "$BUILD" --parallel 2
ctest --test-dir "$BUILD" --output-on-failure
python3 "$SOURCE_DIR/platform/display/screensaver/test-screensaver.py"

if [[ "$MODE" == apply ]] && ! id medvetalkie >/dev/null 2>&1; then
 useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin medvetalkie
fi
# Root stages releases, but the Core/Web/status systemd units run as a
# dedicated non-root user. Every parent directory and the final release
# must be searchable by that user. NEVER relax StateDirectory/RuntimeDirectory.
install -d -m 0755 "$PREFIX" "$PREFIX/releases" "$UNIT_DIR"
install -d -m 0700 "$BACKUP_DIR"
revision="$(git -C "$SOURCE_DIR" rev-parse --short HEAD 2>/dev/null || echo local)"
release="$PREFIX/releases/$(date -u +%Y%m%dT%H%M%SZ)-$revision-$$"
STAGE="$(mktemp -d "$PREFIX/releases/.stage.XXXXXXXX")"
mkdir -p "$STAGE/bin"
for binary in medvetalkied medvetalkie-web medvetalkie-display-status medvetalkie-display-runner medvetalkie-usb-inventory; do
 [[ -x "$BUILD/$binary" ]] || die "Missing compiled $binary"
 install -m 0755 "$BUILD/$binary" "$STAGE/bin/$binary"
done
install -m 0644 "$SOURCE_DIR/platform/display/medvetalkie-screensaver.sh" "$STAGE/medvetalkie-screensaver.sh"
install -m 0644 "$SOURCE_DIR/platform/deploy/check-display-owner.sh" "$STAGE/check-display-owner.sh"
install -m 0644 "$SOURCE_DIR/platform/deploy/check-legacy-display-cron.sh" "$STAGE/check-legacy-display-cron.sh"
printf 'source_revision=%s\n' "$revision" >"$STAGE/MANIFEST"
chmod 0644 "$STAGE/MANIFEST"
# mktemp -d uses 0700. Leaving that mode in a release breaks every
# systemd User=medvetalkie service with a 203/EXEC or access failure.
# Only executables and release directories are public; private settings,
# IPC, and rollbacks remain 0700 in their separate systemd directories.
chmod 0755 "$STAGE" "$STAGE/bin"
OLD_RELEASE=""
[[ ! -L "$PREFIX/current" ]] || OLD_RELEASE="$(readlink "$PREFIX/current")"

if [[ "$MODE" == simulate ]]; then
 mv "$STAGE" "$release"; STAGE=""
 ln -s "$release" "$PREFIX/.next.$$"
 mv -Tf "$PREFIX/.next.$$" "$PREFIX/current"
 for unit in $(units); do
   install -m 0644 "$SOURCE_DIR/platform/deploy/systemd/$unit" "$UNIT_DIR/$unit"
 done
 if [[ -n "$OLD_RELEASE" && -d "$OLD_RELEASE" ]]; then
   ln -sfn "$OLD_RELEASE" "$PREFIX/previous"
 fi
 plan
 log "SIMULATION completed: all files under $SIMROOT, no apt/systemd/hardware changes"
 exit 0
fi

backup="$BACKUP_DIR/$(basename "$release")"
mkdir -m 0700 "$backup"
printf '%s\n' "$OLD_RELEASE" > "$backup/previous-release"
for unit in $(units); do
 [[ ! -f "$UNIT_DIR/$unit" ]] || cp -a "$UNIT_DIR/$unit" "$backup/$unit"
 systemctl is-active --quiet "$unit" && : > "$backup/$unit.active" || :
 systemctl is-enabled --quiet "$unit" && : > "$backup/$unit.enabled" || :
done

restore_failure() {
 local code=$?
 trap - ERR INT TERM
 set +e
 if ((CHANGED)); then
   log "Activation failed ($code). Diagnostics BEFORE rollback:"
   # Record unit status and recent errors while the attempted release
   # and its service processes are still present. Diagnostic failures
   # must never block the rollback.
   systemctl --no-pager --full status medvetalkie-core.service medvetalkie-status.service medvetalkie-web.service medvetalkie-display.service || :
   journalctl --no-pager --output=short-iso -n 65 \
     -u medvetalkie-core.service -u medvetalkie-status.service \
     -u medvetalkie-web.service -u medvetalkie-display.service || :
   ls -ld "$PREFIX" "$PREFIX/releases" "$release" "$release/bin" || :
   log "Restoring the previous release and service definitions"
   for unit in $(units); do systemctl stop "$unit" >/dev/null 2>&1 || :; done
   if [[ -n "$OLD_RELEASE" && -d "$OLD_RELEASE" ]]; then
     ln -sfn "$OLD_RELEASE" "$PREFIX/current"
   else
     rm -f "$PREFIX/current"
   fi
   for unit in $(units); do
     if [[ -f "$backup/$unit" ]]; then cp -a "$backup/$unit" "$UNIT_DIR/$unit"
     else rm -f "$UNIT_DIR/$unit"; fi
   done
   systemctl daemon-reload
   for unit in $(units); do
     if [[ -f "$backup/$unit.enabled" ]]; then systemctl enable "$unit" >/dev/null 2>&1 || :
     else systemctl disable "$unit" >/dev/null 2>&1 || :; fi
     if [[ -f "$backup/$unit.active" ]]; then systemctl restart "$unit" || :; fi
   done
 fi
 exit "$code"
}
# Last preflight before stopping any existing healthy Core/Web service.
# A once-per-minute cron watchdog can have restarted while CTest ran.
if ((DISPLAY)); then
 sh "$SOURCE_DIR/platform/deploy/check-legacy-display-cron.sh" ||
   die "Legacy Bjorni cron watchdog became active during build; no services changed"
 sh "$SOURCE_DIR/platform/deploy/check-display-owner.sh" --allow-managed ||
   die "External display renderer appeared during build; no services changed"
fi
trap restore_failure ERR INT TERM
CHANGED=1
for unit in $(units); do systemctl stop "$unit" >/dev/null 2>&1 || :; done
# An externally supervised renderer can appear between preflight and
# activation. Never let two GPIO/SPI clients compete after stop.
if ((DISPLAY)); then
 if ! sh "$SOURCE_DIR/platform/deploy/check-display-owner.sh" --require-free; then
   echo "SPI not released after stopping managed display; rolling back" >&2
   false
 fi
fi
mv "$STAGE" "$release"; STAGE=""
# Verify the *actual service user* can traverse the entire installed
# /opt path before we replace services or modify the current symlink.
command -v runuser >/dev/null || die "runuser missing: cannot verify non-root release access"
for binary in medvetalkied medvetalkie-web medvetalkie-display-status; do
  runuser -u medvetalkie -- test -x "$release/bin/$binary" ||
    die "medvetalkie user cannot execute $release/bin/$binary"
done
for unit in $(units); do
 install -m 0644 "$SOURCE_DIR/platform/deploy/systemd/$unit" "$UNIT_DIR/$unit.next"
 mv -f "$UNIT_DIR/$unit.next" "$UNIT_DIR/$unit"
done
ln -s "$release" "$PREFIX/.next.$$"
mv -Tf "$PREFIX/.next.$$" "$PREFIX/current"
systemctl daemon-reload
for unit in medvetalkie-core.service medvetalkie-status.service medvetalkie-web.service; do
 systemctl enable "$unit"
 systemctl restart "$unit"
 systemctl is-active --quiet "$unit"
done
if ((DISPLAY)); then
 systemctl enable medvetalkie-display.service
 systemctl restart medvetalkie-display.service
 systemctl is-active --quiet medvetalkie-display.service
else
 systemctl disable --now medvetalkie-display.service >/dev/null 2>&1 || :
fi
health=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
 if curl --noproxy '*' --silent --fail --max-time 2 \
    http://127.0.0.1:8765/api/v1/health | grep -q '"core":"reachable"'; then
   health=1; break
 fi
 sleep 0.5
done
if ((health==0)); then echo "Core/Web health check failed" >&2; false; fi
if [[ ! -f /run/medvetalkie/display.status ]]; then echo "No status snapshot" >&2; false; fi
grep -q '^MTSTATUS1$' /run/medvetalkie/display.status
if ((DISPLAY)); then
 # systemctl is-active is insufficient: Type=simple reports active while
 # the launcher compiles its C source, and then may fail on busy GPIO.
 # Success requires the real renderer to own SPI within this unit cgroup.
 display_ready=0
 for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
   if systemctl is-active --quiet medvetalkie-display.service &&
      sh "$SOURCE_DIR/platform/deploy/check-display-owner.sh" --require-managed >/dev/null 2>&1; then
     display_ready=1
     break
   fi
   sleep 0.5
 done
 if ((display_ready==0)); then
   echo "Display is not rendering: no medvetalkie-display cgroup PID owns SPI; check GPIO PC5/PC6 and cron" >&2
   false
 fi
fi
if [[ -n "$OLD_RELEASE" && -d "$OLD_RELEASE" ]]; then
 ln -sfn "$OLD_RELEASE" "$PREFIX/previous"
fi
CHANGED=0
trap - ERR INT TERM
log "INSTALLED: $release"
log "Web Alpha: http://127.0.0.1:8765/ (local only)"
log "Units: medvetalkie-core/status/web; display=$DISPLAY"
log "Previous release: $OLD_RELEASE; backed-up units: $backup"
log "Existing boot/kernel/WLAN blacklist and network configuration are unchanged"
