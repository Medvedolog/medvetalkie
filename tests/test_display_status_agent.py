#!/usr/bin/env python3
"""Core -> MTSTATUS1 bridge tests: no actual BlueZ, SPI or network required."""
from pathlib import Path
import json
import os
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading

from test_core_ipc import exact


def run_agent(binary, core_sock, out_path):
    return subprocess.run([binary, "--ipc-socket", str(core_sock),
                           "--output", str(out_path), "--once"],
                          text=True, capture_output=True, timeout=6)


def mocked_core(sock_path, mode="UNKNOWN", bluez_ok=True):
    ready = threading.Event()
    error = []
    def worker():
        try:
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(sock_path))
                server.listen(4)
                server.settimeout(5)
                ready.set()
                for _ in range(3):
                    conn, _ = server.accept()
                    with conn:
                        conn.settimeout(3)
                        length = struct.unpack("!I", exact(conn, 4))[0]
                        data = json.loads(exact(conn, length))
                        action = data["action"]
                        if action == "system.status":
                            message = {"v": 1, "type": "snapshot", "state": {
                                "desired_mode": "UNSET", "effective_mode": mode}}
                        elif action == "bt.controllers":
                            message = {"v": 1, "type": "controllers",
                                       "usb_controller_count": 2,
                                       "controllers": []}
                        elif action == "bt.bluez":
                            if not bluez_ok:
                                message = {"v": 1, "type": "error",
                                           "error": {"code": "NOT_READY"}}
                            else:
                                message = {"v": 1, "type": "bluez", "devices": [
                                    {"connected": True, "paired": True,
                                     "alias": "Untrusted\nmode=INTERCOM"},
                                    {"connected": False, "paired": True}]}
                        else:
                            raise AssertionError(f"unexpected action: {action}")
                        encoded = json.dumps(message).encode()
                        conn.sendall(struct.pack("!I", len(encoded)) + encoded)
        except Exception as exc:
            error.append(exc)
        finally:
            ready.set()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    assert ready.wait(2)
    return thread, error


def load(path):
    text = path.read_text()
    assert text.startswith("MTSTATUS1\n")
    assert all("=" in row for row in text.splitlines()[1:])
    return dict(line.split("=", 1) for line in text.splitlines()[1:])


def main(binary):
    with tempfile.TemporaryDirectory(prefix="mt-status-agent-") as tmp:
        root = Path(tmp)
        out = root / "display.status"
        sock = root / "core.sock"
        # Core unavailable: produce explicit fault; never retain stale success.
        result = run_agent(binary, sock, out)
        assert result.returncode == 0, result.stderr
        offline = load(out)
        assert offline["mode"] == "CORE_OFFLINE"
        assert offline["fault"] == "CORE_OFFLINE"
        assert offline["voice"] == "NOT_VERIFIED"
        assert stat.S_IMODE(out.stat().st_mode) == 0o600

        thread, errors = mocked_core(sock)
        result = run_agent(binary, sock, out)
        assert result.returncode == 0, result.stderr
        thread.join(2)
        assert not errors, errors
        snapshot = load(out)
        assert snapshot["mode"] == "STANDBY"  # UI idle != verified voice
        assert snapshot["fault"] == "NONE"
        assert snapshot["bt_usb"] == "2"
        assert snapshot["bt_connected"] == "1"
        assert snapshot["headset1"] == snapshot["headset2"] == "UNASSIGNED"
        assert snapshot["voice"] == "NOT_VERIFIED"
        assert "Untrusted" not in out.read_text()
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
        sock.unlink()

        thread, errors = mocked_core(sock, mode="INTERCOM", bluez_ok=False)
        result = run_agent(binary, sock, out)
        assert result.returncode == 0, result.stderr
        thread.join(2)
        assert not errors, errors
        failed = load(out)
        assert failed["mode"] == "INTERCOM"
        assert failed["fault"] == "BT_FAILED"
        assert failed["voice"] == "NOT_VERIFIED"
        sock.unlink()

        denied = subprocess.run(
            [binary, "--output", "relative.path", "--once"],
            text=True, capture_output=True, timeout=3)
        assert denied.returncode != 0
        print("PASS: offline recovery, UI standby, USB+ACL counts, no alias injection, BT failure, 0600 snapshots")


if __name__ == "__main__":
    main(sys.argv[1])
