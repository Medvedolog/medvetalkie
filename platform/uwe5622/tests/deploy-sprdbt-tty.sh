#!/bin/sh
# Experimental UWE5622 Bluetooth module installer.
# Never overwrites distro driver. Activation requires manual reboot.
set -eu
KVER=6.18.60-current-sunxi64
STATE=/root/medvetalkie-build/uwe5622-deploy
TARGET=/lib/modules/$KVER/updates/medvetalkie/sprdbt_tty.ko
die() { echo "ERROR: $*" >&2; exit 1; }
need_root() { [ "$(id -u)" = 0 ] || die "Run as root"; [ "$(uname -r)" = "$KVER" ] || die "Kernel mismatch"; }
selected() { modinfo -n sprdbt_tty; }
baseline() {
    mkdir -p "$STATE"
    chmod 700 "$STATE"
    if [ -f "$STATE/original-path" ]; then
        [ -s "$STATE/original.ko" ] || die "Original backup missing"
        return
    fi
    orig=$(selected)
    [ "$orig" != "$TARGET" ] || die "Override already selected without backup"
    [ -f "$orig" ] || die "Original module not found"
    case "$orig" in *.ko) ;; *) die "Compressed module: manual review needed" ;; esac
    cp -p "$orig" "$STATE/original.ko"
    printf '%s\n' "$orig" > "$STATE/original-path"
    modinfo -F vermagic "$orig" > "$STATE/original-vermagic"
    sha256sum "$STATE/original.ko" > "$STATE/original.sha256"
}
check_candidate() {
    [ -f "$1" ] || die "Candidate module not found: $1"
    [ "$(modinfo -F name "$1")" = sprdbt_tty ] || die "Module name mismatch"
    candidate=$(modinfo -F vermagic "$1")
    original=$(cat "$STATE/original-vermagic")
    [ "$candidate" = "$original" ] || die "Full vermagic mismatch. Candidate: $candidate; Original: $original"
    [ "$(printf '%s\n' "$candidate" | cut -d ' ' -f1)" = "$KVER" ] || die "Kernel version mismatch"
}
need_root
case "$1" in
  preflight)
    [ "$#" -eq 2 ] || die "Usage: $0 preflight /path/to/sprdbt_tty.ko"
    baseline
    check_candidate "$2"
    echo "PASS: matching full vermagic and module name"
    echo "Original: $(cat "$STATE/original-path")"
    echo "Candidate SHA256:"
    sha256sum "$2"
    echo "Candidate dependencies:"
    modinfo -F depends "$2"
    echo "NO FILES under /lib/modules were modified"
    ;;
  install)
    [ "$#" -eq 2 ] || die "Usage: $0 install /path/to/sprdbt_tty.ko"
    [ -s "$STATE/original.ko" ] || die "Run preflight first"
    check_candidate "$2"
    [ ! -e "$TARGET" ] || die "Override already installed; rollback first"
    mkdir -p "$(dirname "$TARGET")"
    tmp="$TARGET.tmp.$$"
    trap 'rm -f "$tmp"' EXIT HUP INT TERM
    install -m 0644 "$2" "$tmp"
    mv "$tmp" "$TARGET"
    trap - EXIT HUP INT TERM
    depmod -a "$KVER"
    chosen=$(selected)
    if [ "$chosen" != "$TARGET" ]; then
        rm -f "$TARGET"
        depmod -a "$KVER"
        die "Unexpected modprobe choice: $chosen; override removed"
    fi
    echo "Experimental module staged as override, stock driver intact."
    echo "No running module was unloaded. Manual reboot required to activate."
    ;;
  rollback)
    [ -s "$STATE/original.ko" ] || die "No original backup"
    orig=$(cat "$STATE/original-path")
    [ -f "$orig" ] || die "Stock module missing"
    a=$(sha256sum "$STATE/original.ko" | awk '{print $1}')
    b=$(sha256sum "$orig" | awk '{print $1}')
    [ "$a" = "$b" ] || die "Stock module differs from backup; stop"
    rm -f "$TARGET"
    depmod -a "$KVER"
    [ "$(selected)" = "$orig" ] || die "Stock module not selected after rollback"
    echo "Original module selected; reboot to apply if experimental version is loaded."
    ;;
  status)
    echo "Kernel: $(uname -r)"
    echo "Selected: $(selected)"
    [ ! -e "$TARGET" ] || echo "Override installed: $TARGET"
    [ ! -e "$STATE/original-path" ] || { echo "Original: $(cat "$STATE/original-path")"; }
    grep '^sprdbt_tty ' /proc/modules || :
    find /sys/devices -name hci_rx_stats -type f -print 2>/dev/null || :
    ;;
  *) die "Usage: $0 {preflight /path/to/module.ko|install /path/to/module.ko|rollback|status}" ;;
esac
