#!/usr/bin/env python3
"""SQLite desired-settings contract: validation, CAS, persistence, migration gate."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

from test_core_ipc import exchange


def boot(binary, socket_path, db_path, writes=False):
    cmd = [binary, "--ipc-socket", str(socket_path), "--db-path", str(db_path)]
    if writes:
        cmd.append("--allow-local-settings")
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(100):
        if socket_path.exists():
            return process
        if process.poll() is not None:
            raise AssertionError("Core startup failed: " + process.stderr.read().decode())
        time.sleep(0.02)
    process.terminate()
    process.communicate(timeout=3)
    raise AssertionError("IPC socket never appeared")


def halt(process):
    process.terminate()
    _, stderr = process.communicate(timeout=3)
    assert process.returncode == 0, stderr.decode()


def query(path, action):
    return exchange(path, {"v": 1, "type": "query", "action": action})


def patch(path, request_id, revision, display=None, **fields):
    args = dict(fields, expected_revision=revision)
    if display is not None:
        args["display"] = display
    return exchange(path, {"v": 1, "type": "command",
                           "id": request_id, "action": "settings.patch", "args": args})


def main(binary):
    with tempfile.TemporaryDirectory(prefix="mt-settings-") as tmp:
        root = Path(tmp)
        path = root / "control.sock"
        db = root / "settings.db"
        process = boot(binary, path, db, False)
        try:
            initial = query(path, "settings.get")
            assert initial["type"] == "settings"
            assert initial["revision"] == 0
            assert initial["settings"]["device_name"] == "MedveTalkie"
            assert initial["settings"]["display"] == {
                "spi_mhz": 1, "fps": 25, "screensaver_enabled": False}
            assert stat.S_IMODE(db.stat().st_mode) == 0o600
            no_permission = patch(path, "p0", 0, display={"spi_mhz": 4})
            assert no_permission["error"]["code"] == "PERMISSION_DENIED"
            assert query(path, "system.capabilities")["capabilities"]["settings_write"] is False
        finally:
            halt(process)

        process = boot(binary, path, db, True)
        try:
            assert query(path, "system.capabilities")["capabilities"]["settings_write"] is True
            # Every malformed/unsupported field must fail before touching SQLite.
            invalid = [
                {"display": {"spi_mhz": 0}},
                {"display": {"spi_mhz": 17}},
                {"display": {"fps": 61}},
                {"display": {"fps": 2.5}},
                {"display": {"screensaver_enabled": "true"}},
                {"display": {"unknown_key": 3}},
                {"display": {}},
                {"device_name": ""},
                {"device_name": "X" * 65},
                {"device_name": "a\nb"},
                {"device_name": 19},
                {"secret_wifi_password": "test"},
            ]
            for index, field in enumerate(invalid):
                result = patch(path, "bad" + str(index), 0, **field)
                assert result["type"] == "rejected", result
                assert result["error"]["code"] == "BAD_REQUEST", result
            assert query(path, "settings.get")["revision"] == 0

            first = patch(path, "cfg1", 0, display={
                "spi_mhz": 4, "fps": 25, "screensaver_enabled": True},
                device_name="Бйорни")
            assert first["type"] == "result" and first["ok"]
            assert first["revision"] == 1
            assert first["applied"] == "saved_only"
            assert first["hardware_applied"] is False
            assert first["operation"] == "settings-1"
            assert query(path, "settings.get")["settings"]["device_name"] == "Бйорни"
            status = query(path, "system.status")
            assert status["revision"] == 1
            assert status["state"]["desired_display"]["spi_mhz"] == 4
            assert status["state"]["display"] == "NOT_READY"
            display = query(path, "display.status")
            assert display["desired"]["screensaver_enabled"] is True
            assert display["observed"] == "UNKNOWN"
            assert display["hardware_applied"] is False

            same = patch(path, "cfg1", 0, display={"spi_mhz": 4})
            assert same["error"]["code"] == "REVISION_CONFLICT"
            # Two independent clients cannot overwrite the same revision.
            with ThreadPoolExecutor(max_workers=2) as executor:
                one = executor.submit(patch, path, "cfg2", 1, display={"fps": 30})
                two = executor.submit(patch, path, "cfg3", 1, display={"fps": 40})
                outcomes = [one.result(), two.result()]
            assert sum(r.get("ok") is True for r in outcomes) == 1, outcomes
            assert sum(r.get("error", {}).get("code") == "REVISION_CONFLICT"
                       for r in outcomes) == 1, outcomes
            final = query(path, "settings.get")
            assert final["revision"] == 2
            assert final["settings"]["display"]["fps"] in (30, 40)
            assert final["settings"]["display"]["spi_mhz"] == 4
        finally:
            halt(process)

        process = boot(binary, path, db, False)
        try:
            restored = query(path, "settings.get")
            assert restored["revision"] == 2
            assert restored["settings"] == final["settings"]
            assert patch(path, "blocked", 2, device_name="Changed")["error"]["code"] == "PERMISSION_DENIED"
        finally:
            halt(process)

        with sqlite3.connect(db) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1
            conn.execute("PRAGMA user_version=999")
        rejected = subprocess.run(
            [binary, "--ipc-socket", str(path), "--db-path", str(db)],
            capture_output=True, timeout=4)
        assert rejected.returncode != 0
        assert not path.exists()
        with sqlite3.connect(db) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 999

        # Database paths that are world-readable or symlinks must fail closed.
        with sqlite3.connect(root / "other.db") as conn:
            conn.execute("PRAGMA user_version=1")
        other = root / "other.db"
        other.chmod(0o644)
        denied = subprocess.run(
            [binary, "--ipc-socket", str(path), "--db-path", str(other)],
            capture_output=True, timeout=4)
        assert denied.returncode != 0
        print("PASS: SQLite v1 schema, owner-private DB, whitelist, CAS, persistence, future-schema gate")


if __name__ == "__main__":
    main(sys.argv[1])
