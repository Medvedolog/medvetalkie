#!/usr/bin/env python3
"""Wire-level regression tests for MedveTalkie Core IPC Alpha (no devices needed)."""
import json
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time


def exact(sock, n):
    result = bytearray()
    while len(result) < n:
        part = sock.recv(n - len(result))
        if not part:
            raise EOFError("socket closed")
        result.extend(part)
    return bytes(result)


def exchange(path, payload):
    if isinstance(payload, str):
        data = payload.encode()
    else:
        data = json.dumps(payload, separators=(",", ":")).encode()
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(2)
        sock.connect(str(path))
        sock.sendall(struct.pack("!I", len(data)) + data)
        count = struct.unpack("!I", exact(sock, 4))[0]
        assert 0 < count <= 65536
        return json.loads(exact(sock, count))


def denied(path, data, declared_length=None):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(2)
        sock.connect(str(path))
        sock.sendall(struct.pack("!I", declared_length or len(data)) + data)
        try:
            assert sock.recv(1) == b"", "invalid frame must be dropped"
        except ConnectionResetError:
            # Linux may reset AF_UNIX when peer closes with unread rejected bytes.
            pass


def main(binary):
    with tempfile.TemporaryDirectory(prefix="mt-ipc-") as directory:
        path = Path(directory) / "core.sock"
        proc = subprocess.Popen([binary, "--ipc-socket", str(path)],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if path.exists():
                    break
                assert proc.poll() is None, "core terminated during startup"
                time.sleep(0.02)
            assert path.exists(), "core socket was not created"
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            health = exchange(path, {"v": 1, "type": "query", "action": "health"})
            assert health["type"] == "health"
            assert health["core"] == "reachable"
            assert health["audio"] == "not_implemented"

            # JSON key order, insignificant whitespace and aliases are accepted.
            assert exchange(path, ' { "action":"system.health", "type": "query", "v":1 } ')["type"] == "health"
            status = exchange(path, {"action": "system.status", "v": 1, "type": "query"})
            assert status["type"] == "snapshot"
            assert status["state"]["effective_mode"] == "UNKNOWN"
            assert status["state"]["bluetooth"] == "NOT_READY"
            caps = exchange(path, {"v": 1, "type": "query", "action": "system.capabilities"})
            assert caps["capabilities"]["core_ipc_v1"] is True
            assert caps["capabilities"]["hfp_audio"] is False
            rejected = exchange(path, {"v": 1, "type": "command",
                                       "id": "req_123", "action": "bt.pair", "args": {}})
            assert rejected["type"] == "rejected"
            assert rejected["id"] == "req_123"
            assert rejected["error"]["code"] == "NOT_READY"
            assert exchange(path, {"v": 2, "type": "query", "action": "health"})["error"]["code"] == "UNSUPPORTED_VERSION"
            assert exchange(path, {"v": 1, "type": "query", "action": "bt.scan"})["error"]["code"] == "NOT_SUPPORTED"
            assert exchange(path, {"v": 1, "type": "command",
                                   "id": "bad id", "action": "bt.scan"})["error"]["code"] == "BAD_REQUEST"
            assert exchange(path, "not a json object")["error"]["code"] == "BAD_REQUEST"
            assert exchange(path, '{"v":1,"type":"query","action":"health"} trailing')["error"]["code"] == "BAD_REQUEST"
            denied(path, b"x", 65537)
            denied(path, b'{"v":1}\x00{"v":1}')
            # An incomplete frame must time out; a slow client cannot block all others.
            slow = socket.socket(socket.AF_UNIX)
            slow.connect(str(path))
            slow.sendall(struct.pack("!I", 32) + b"{")
            start = time.monotonic()
            assert exchange(path, {"v": 1, "type": "query", "action": "health"})["type"] == "health"
            assert time.monotonic() - start < 1.0, "slow peer blocked independent requests"
            slow.close()
            assert proc.poll() is None, "core crashed on invalid input"
            print("PASS: framed JSON v1, read-only queries, unsupported mutations, limits, isolation")
        finally:
            proc.terminate()
            try:
                proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
        assert not path.exists(), "core failed to remove its own socket after shutdown"


if __name__ == "__main__":
    main(sys.argv[1])
