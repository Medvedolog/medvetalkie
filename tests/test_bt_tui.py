#!/usr/bin/env python3
"""Offline CI smoke checks for the SSH Bluetooth bench TUI."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "platform/bluetooth/medvetalkie-bt-tui.py"
spec = importlib.util.spec_from_file_location("medvetalkie_bt_tui", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TuiTests(unittest.TestCase):
    def test_controller_inventory(self):
        output = ("Controller F4:4E:FC:57:69:64 orangepizero3 #1 [default]\n"
                  "Controller F4:4E:FC:2D:FD:4B orangepizero3\n")
        with patch.object(mod, "run", return_value=(0, output)):
            result, error = mod.controllers()
        self.assertEqual(error, "")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["mac"], "F4:4E:FC:57:69:64")

    def test_known_airide_first(self):
        output = ("Device 00:9E:C8:92:D4:99 MIBOX3\n"
                  "Device 41:42:63:27:E7:3A AIRIDE N1\n")
        with patch.object(mod, "run", return_value=(0, output)) as call:
            result, error = mod.discovered("F4:4E:FC:57:69:64")
        self.assertFalse(error)
        self.assertEqual(result[0]["name"], "AIRIDE N1")
        self.assertEqual(call.call_args.args[0][:3],
                         ["bluetoothctl", "-i", "F4:4E:FC:57:69:64"])

    def test_no_scan_without_controller(self):
        bench = mod.Bench()
        bench.command("scan")
        self.assertIn("Контроллер", bench.notice)
        self.assertIsNone(bench._thread)

    def test_pair_requires_confirmation(self):
        bench = mod.Bench()
        bench.adapters = [{"mac": "F4:4E:FC:57:69:64", "name": "test"}]
        bench.devices = [{"mac": mod.HEADSET, "name": "AIRIDE N1"}]
        with patch.object(bench, "work") as worker:
            bench.command("pair")
        worker.assert_not_called()
        self.assertEqual(bench.pending_pair, mod.HEADSET)

    def test_audio_not_falsely_ready(self):
        self.assertTrue(mod.has_profile("UUID: Handsfree (0000111e-)"))
        self.assertFalse(mod.has_profile("Connected: yes\nUUID: Audio Sink"))


if __name__ == "__main__":
    unittest.main()
