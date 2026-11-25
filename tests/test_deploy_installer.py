#!/usr/bin/env python3
"""Deployment regression: mixed proxy handling + staged filesystem + rollback.

Runs unprivileged, never calls apt/systemctl or touches the real Orange Pi.
The simulator compiles the actual code and runs the complete Core/ST7789 suite.
"""
from pathlib import Path
import os
import stat
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


def check_release_access(staging):
    # The real ARM64 deployment previously passed CTest but failed to start:
    # root-owned mktemp 0700 release dirs were inaccessible to User=medvetalkie.
    prefix = staging / "opt" / "medvetalkie"
    release = (prefix / "current").resolve(strict=True)
    for directory in (prefix, prefix / "releases", release, release / "bin"):
        mode = stat.S_IMODE(directory.stat().st_mode)
        assert mode & 0o005 == 0o005, (
            f"{directory} not traversable by a non-root systemd service: {mode:04o}"
        )
        assert not (mode & 0o022), f"release directory writable by others: {directory}"
    for binary in ("medvetalkied", "medvetalkie-web", "medvetalkie-display-status"):
        target = release / "bin" / binary
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode & 0o005 == 0o005, f"{target} not executable by service user"
    assert stat.S_IMODE((release / "MANIFEST").stat().st_mode) & 0o004
    assert stat.S_IMODE((release / "medvetalkie-screensaver.sh").stat().st_mode) & 0o004


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

    # Real Armbian logs showed apt-get update exit 0 despite rejected
    # signatures and cached indexes. Fail closed without disabling sqv.
    validator = REPO / "platform" / "deploy" / "verify-apt-log.sh"
    with tempfile.TemporaryDirectory(prefix="mt-apt-log-") as temp:
        logfile = Path(temp) / "apt-update.log"
        clean = "Hit:1 http://deb.debian.org/debian trixie InRelease\nReading package lists... Done\n"
        logfile.write_text(clean)
        result = subprocess.run(["sh", str(validator), str(logfile)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        cases = (
            "W: OpenPGP signature verification failed: Not live until 2026-11-25T07:42:54Z",
            "W: OpenPGP signature verification failed: Missing key DF00FAF1C577104B50BF1D0093D6889F9F0E78D5",
            "W: Some index files failed to download. They have been ignored, or old ones used instead.",
            "W: Failed to fetch http://security.debian.org trixie-security InRelease",
            "E: The repository is not signed",
        )
        for warning in cases:
            logfile.write_text(clean + warning + "\n")
            result = subprocess.run(["sh", str(validator), str(logfile)],
                                    capture_output=True, text=True)
            assert result.returncode != 0, (warning, result.stdout, result.stderr)

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
        check_release_access(staging)
        assert not (prefix / "previous").exists()

        second = call("--simulate", staging, "--enable-display", "--no-proxy")
        assert "SIMULATION completed" in second.stdout
        updated = current.resolve(strict=True)
        assert updated != original
        previous = prefix / "previous"
        assert previous.is_symlink() and previous.resolve(strict=True) == original
        check_services(staging)
        check_release_access(staging)

        restored = call("--rollback", "--simulate", staging)
        assert "Rolled back to" in restored.stdout
        assert current.resolve(strict=True) == original
        assert previous.resolve(strict=True) == updated
        check_release_access(staging)

        # Do not overwrite an administrator-owned unit, even in simulator.
        unmanaged = staging / "etc" / "systemd" / "system" / "medvetalkie-web.service"
        unmanaged.write_text("[Unit]\nDescription=unrelated service\n")
        call("--simulate", staging, succeed=False)
        assert unmanaged.read_text().startswith("[Unit]")

    print("PASS deploy: mixed HTTP proxy, dry-run, invalid input, executable "
          "non-root release permissions, systemd, second install, rollback, "
          "unmanaged-unit protection")


if __name__ == "__main__":
    main()
