#!/usr/bin/env python3
"""Deterministic, read-only UGREEN/HCI topology tests; no Bluetooth required."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from test_core_ipc import exchange


def core_start(binary, socket, sysroot):
    process = subprocess.Popen(
        [binary, "--ipc-socket", str(socket),
         "--bluetooth-sysfs-root", str(sysroot)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(100):
        if socket.exists():
            return process
        assert process.poll() is None, process.stderr.read().decode()
        time.sleep(0.02)
    raise AssertionError("core IPC startup timeout")


def query(sock, action):
    return exchange(sock, {"v": 1, "type": "query", "action": action})


def usb_hci(root, name, port, address, serial=None):
    hci = root / "class" / "bluetooth" / name
    hci.mkdir(parents=True)
    (hci / "address").write_text(address + "\n")
    node = root / "devices" / "usb1" / port
    iface = node / (port + ":1.0")
    iface.mkdir(parents=True, exist_ok=True)
    (node / "idVendor").write_text("10d7\n")
    (node / "idProduct").write_text("b012\n")
    (node / "product").write_text("UGREEN CM390\n")
    if serial is not None:
        (node / "serial").write_text(serial + "\n")
    (hci / "device").symlink_to(iface, target_is_directory=True)


def main(binary):
    with tempfile.TemporaryDirectory(prefix="mt-bt-sysfs-") as tmp:
        base = Path(tmp)
        root = base / "sys"
        (root / "class" / "bluetooth").mkdir(parents=True)
        # hci indices are intentionally not in physical USB-port order.
        usb_hci(root, "hci8", "1-1.3", "F4:12:34:56:78:90")
        usb_hci(root, "hci1", "1-1.2", "F4:12:34:56:78:91")
        (root / "class" / "bluetooth" / "hcix").mkdir()
        unrelated = root / "class" / "bluetooth" / "hci4"
        unrelated.mkdir()
        (unrelated / "address").write_text("00:11:22:33:44:55\n")

        sock = base / "core.sock"
        process = core_start(binary, sock, root)
        try:
            r = query(sock, "bt.controllers")
            assert r["type"] == "controllers", r
            assert r["source"] == "kernel_sysfs"
            assert r["bluez_state"] == "NOT_CHECKED"
            assert r["controller_count"] == 3
            assert r["usb_controller_count"] == 2
            arr = r["controllers"]
            assert [c["hci"] for c in arr] == ["hci1", "hci8", "hci4"]
            assert [c["usb"]["port"] for c in arr[:2]] == ["1-1.2", "1-1.3"]
            assert all(c["usb"]["vid"] == "10d7" for c in arr[:2])
            assert all(c["usb"]["pid"] == "b012" for c in arr[:2])
            assert arr[0]["address"] == "F4:12:34:56:78:91"
            assert arr[2]["transport"] == "non_usb_or_unknown"
            assert all(c["identity_verified"] is False for c in arr)
            assert all(c["hfp_ready"] is False for c in arr)
            assert all(c["hfp_observed"] == "NOT_CHECKED" for c in arr)
            assert all("serial" not in c.get("usb", {}) for c in arr)
            caps = query(sock, "system.capabilities")["capabilities"]
            assert caps["bt_controller_inventory"] is True
            assert caps["bluetooth_management"] is False
            assert caps["hfp_audio"] is False

            # Unplugging one adapter must change only the inventory.
            (root / "class" / "bluetooth" / "hci8" / "device").unlink()
            (root / "class" / "bluetooth" / "hci8" / "address").unlink()
            (root / "class" / "bluetooth" / "hci8").rmdir()
            after = query(sock, "bt.controllers")
            assert after["controller_count"] == 2
            assert after["usb_controller_count"] == 1
            assert query(sock, "health")["core"] == "reachable"
            print("PASS BT inventory: two identical UGREEN, physical port mapping, "
                  "unverified HFP, hot-unplug, no serial leak")
        finally:
            process.terminate()
            _, err = process.communicate(timeout=3)
            assert process.returncode == 0, err.decode()

        unavailable = base / "missing_sys"
        process = core_start(binary, sock, unavailable)
        try:
            r = query(sock, "bt.controllers")
            assert r["type"] == "error"
            assert r["error"]["code"] == "NOT_READY"
            print("PASS BT inventory: missing sysfs reports NOT_READY, not zero devices")
        finally:
            process.terminate()
            process.communicate(timeout=3)


if __name__ == "__main__":
    main(sys.argv[1])
