#!/usr/bin/env python3
"""Real process integration: Core IPC -> status bridge -> Bjorni/ST7789 PPM.
No live SPI/GPIO, D-Bus, BT adapter or network access is needed.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time


def invoke(args, timeout=20):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    assert p.returncode == 0, (args, p.returncode, p.stdout[-1500:], p.stderr[-1500:])
    return p


def start_core(binary, path, db):
    p = subprocess.Popen([binary, "--ipc-socket", str(path),
                          "--db-path", str(db)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(100):
        if path.exists():
            return p
        assert p.poll() is None, "core died before accepting IPC requests"
        time.sleep(0.02)
    p.terminate()
    p.communicate(timeout=3)
    raise AssertionError("Core IPC socket did not appear")


def preview(script, status, output):
    invoke(["bash", str(script), "--no-sync", "--preview", str(output),
            "--status-file", str(status)], timeout=20)
    data = output.read_bytes()
    assert data.startswith(b"P6\n320 240\n255\n"), "expected 320x240 PPM"
    assert len(data) == len(b"P6\n320 240\n255\n") + 320 * 240 * 3
    return data


def main(core_binary, status_binary, bjorni_script):
    with tempfile.TemporaryDirectory(prefix="mt-display-e2e-") as temp:
        d = Path(temp)
        socket = d / "core.sock"
        db = d / "settings.db"
        output = d / "display.status"
        online_ppm = d / "online.ppm"
        offline_ppm = d / "offline.ppm"
        core = start_core(core_binary, socket, db)
        try:
            invoke([status_binary, "--ipc-socket", str(socket),
                    "--output", str(output), "--once"])
            text = output.read_text()
            assert text.startswith("MTSTATUS1\n")
            assert "mode=STANDBY\n" in text, text
            assert "headset1=UNASSIGNED\n" in text
            assert "headset2=UNASSIGNED\n" in text
            assert "voice=NOT_VERIFIED\n" in text
            assert "bt_connected=0\n" in text or "bt_connected=" in text
            assert "voice=READY" not in text
            assert "HFP_READY" not in text
            image_online = preview(bjorni_script, output, online_ppm)
            assert image_online.count(b"\0\0\0") > 1000
        finally:
            core.terminate()
            core.communicate(timeout=3)

        # Offline Core is a status change, not the last positive snapshot.
        invoke([status_binary, "--ipc-socket", str(socket),
                "--output", str(output), "--once"])
        text = output.read_text()
        assert "mode=CORE_OFFLINE\n" in text
        assert "fault=CORE_OFFLINE\n" in text
        assert "voice=NOT_VERIFIED\n" in text
        image_offline = preview(bjorni_script, output, offline_ppm)
        assert image_offline != image_online, "offline must change visible status"
        assert not socket.exists(), "Core did not clean up its socket"
        print("PASS: real Core -> IPC -> MTSTATUS1 -> Russian ST7789 preview -> offline fault")


if __name__ == "__main__":
    main(*sys.argv[1:])
