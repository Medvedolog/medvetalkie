#!/usr/bin/env python3
"""Check that the local Bjorni runner obeys saved settings without SPI hardware."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

from test_settings_api import boot, halt, patch


def command(runner, sock, script, *opts):
    return subprocess.run([runner, "--ipc-socket", str(sock),
                           "--script", str(script), *opts],
                          capture_output=True, text=True, timeout=3)


def main(core, runner):
    with tempfile.TemporaryDirectory(prefix="mt-bjorni-bridge-") as tmp:
        base = Path(tmp)
        sock = base / "control.sock"
        db = base / "settings.db"
        script = base / "medvetalkie-screensaver.sh"
        script.write_text('#!/bin/bash\nprintf "ARGS:%s|%s|%s|%s\\n" "$1" "$2" "$3" "$4"\n')
        script.chmod(0o644)
        process = boot(core, sock, db, True)
        try:
            disabled = command(runner, sock, script, "--run")
            assert disabled.returncode == 0, disabled.stderr
            assert "disabled" in disabled.stdout.lower()
            assert "ARGS:" not in disabled.stdout

            change = patch(sock, "display1", 0, display={
                "spi_mhz": 4, "fps": 25, "screensaver_enabled": True
            })
            assert change["ok"] is True, change
            dry = command(runner, sock, script)
            assert dry.returncode == 0, dry.stderr
            assert "DRY_RUN" in dry.stdout
            assert "spi_mhz=4" in dry.stdout
            assert "fps=25" in dry.stdout
            assert "ARGS:" not in dry.stdout

            launched = command(runner, sock, script, "--run")
            assert launched.returncode == 0, launched.stderr
            assert "ARGS:--spi-mhz|4|--fps|25" in launched.stdout

            script.chmod(0o666)
            unsafe = command(runner, sock, script, "--run")
            assert unsafe.returncode != 0
            assert "trusted local script" in unsafe.stderr
            script.chmod(0o644)

            link = base / "untrusted-link.sh"
            link.symlink_to(script)
            assert command(runner, sock, link, "--run").returncode != 0

            # Configuration read is a single, bounded IPC query.
            offline = command(runner, base / "missing.sock", script, "--run")
            assert offline.returncode != 0
            print("PASS display bridge: disabled, dry-run, validated args, unsafe script and core outage")
        finally:
            halt(process)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
