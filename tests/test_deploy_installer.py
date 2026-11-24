#!/usr/bin/env python3
"""Deployment regression: mixed proxy handling + staged filesystem + rollback.

Runs unprivileged, never calls apt/systemctl or touches the real Orange Pi.
The simulator compiles the actual code and runs the complete Core/ST7789 suite.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "platform" / "deploy" / "install-opiz3.sh"
UNITS = ("core", "status", "web", "display")


def call(*args, succeed=True):
    result = subprocess.run(["bash", str(SCRIPT), *map(str, args)],
                            cwd=REPO, text=True, capture_output=True, timeout=150)
    if succeed:
        assert result.returncode == 0, (args, result.stdout[-3000:], result.stderr[-3000:])
    else:
        assert result.returncode != 0, (args, result.stdout[-1000:])
    return result


def check_services(staging):
    units = staging / "etc" / "systemd" / "system"
    core = (units / "medvetalkie-core.service").read_text()
    status = (units / "medvetalkie-status.service").read_text()
    web = (units / "medvetalkie-web.service").read_text()
    display = (units / "medvetalkie-display.service").read_text()
    for unit in UNITS:
        source = REPO / "platform" / "deploy" / "systemd" / f"medvetalkie-{unit}.service"
        installed = units / source.name
        assert installed.read_bytes() == source.read_bytes()
        assert installed.read_text().startswith("# Managed by MedveTalkie installer")
    assert "User=medvetalkie" in core
    assert "RuntimeDirectory=medvetalkie" in core
    assert "StateDirectory=medvetalkie" in core
    assert "--allow-local-settings" not in core  # Remote writes remain unavailable.
    assert "User=medvetalkie" in status
    assert "ReadWritePaths=/run/medvetalkie" in status
    assert "User=medvetalkie" in web
    assert "0.0.0.0" not in web
    assert "User=root" in display
    assert "--no-sync" in display and "--status-file" in display
    assert "sprdwl_ng" not in "\n".join((core, status, web, display))
    assert "ExecStart=" in core and "ExecStart=" in status


def main():
    syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr

    dry = call("--dry-run", "--proxy", "http://192.168.11.100:10880")
    assert "mixed HTTP proxy=http://192.168.11.100:10880" in dry.stdout
    assert "DRY RUN" in dry.stdout
    assert "no network" in dry.stdout.lower()
    assert "WLAN" not in dry.stderr
    assert "systemctl" not in dry.stderr
    assert "installing" not in dry.stdout.lower()

    call("--dry-run", "--proxy", "socks5://192.168.11.100:10880", succeed=False)
    call("--dry-run", "--proxy", "http://192.168.11.100:99999", succeed=False)
    call("--dry-run", "--proxy", "http://user:pass@192.168.11.100:10880", succeed=False)
    call("--dry-run", "--proxy", "http://192.168.11.100:10880;touch /tmp/unwanted", succeed=False)

    with tempfile.TemporaryDirectory(prefix="medvetalkie-deploy-sim-") as tmp:
        staging = Path(tmp)
        prefix = staging / "opt" / "medvetalkie"
        first = call("--simulate", staging, "--proxy", "http://192.168.11.100:10880")
        assert "SIMULATION completed" in first.stdout
        current = prefix / "current"
        assert current.is_symlink()
        original = current.resolve(strict=True)
        assert original.parent == prefix / "releases"
        for binary in ("medvetalkied", "medvetalkie-display-status",
                       "medvetalkie-web", "medvetalkie-display-runner",
                       "medvetalkie-usb-inventory"):
            compiled = original / "bin" / binary
            assert compiled.is_file() and os.access(compiled, os.X_OK)
        assert (original / "medvetalkie-screensaver.sh").read_bytes() == (
            REPO / "platform" / "display" / "medvetalkie-screensaver.sh").read_bytes()
        check_services(staging)
        assert not (prefix / "previous").exists()

        second = call("--simulate", staging, "--enable-display", "--no-proxy")
        assert "SIMULATION completed" in second.stdout
        updated = current.resolve(strict=True)
        assert updated != original
        previous = prefix / "previous"
        assert previous.is_symlink() and previous.resolve(strict=True) == original
        check_services(staging)

        restored = call("--rollback", "--simulate", staging)
        assert "Rolled back to" in restored.stdout
        assert current.resolve(strict=True) == original
        assert previous.resolve(strict=True) == updated

        # Do not overwrite an administrator-owned unit, even in simulator.
        unmanaged = staging / "etc" / "systemd" / "system" / "medvetalkie-web.service"
        unmanaged.write_text("[Unit]\nDescription=unrelated service\n")
        call("--simulate", staging, succeed=False)
        assert unmanaged.read_text().startswith("[Unit]")

    print("PASS deploy: mixed HTTP proxy, dry-run, invalid input, staged binaries, "
          "systemd permissions, second install, rollback, unmanaged-unit protection")


if __name__ == "__main__":
    main()
