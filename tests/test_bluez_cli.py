#!/usr/bin/env python3
"""BlueZ 5.82 controller selection tests (no bluetoothctl -i)."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "platform/bluetooth/bluez_cli.py"
spec = importlib.util.spec_from_file_location("bluez_cli", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

C0 = "F4:4E:FC:57:69:64"
C1 = "F4:4E:FC:2D:FD:4B"
DEVICE = "41:42:63:27:E7:3A"


class SelectedTests(unittest.TestCase):
    def test_selected_controller_and_filter_share_session(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv,kwargs))
            return subprocess.CompletedProcess(argv, 0,
                "Controller "+C0+" orangepizero3 [default]\nDevice "+DEVICE+" AIRIDE N1", "")
        result = mod.selected(C0, "devices Connected", runner=runner)
        self.assertIn("AIRIDE N1", result)
        self.assertEqual(calls[0][0], ["bluetoothctl"])
        self.assertEqual(calls[0][1]["input"],
                         "select "+C0+"\ndevices Connected\nquit\n")
        self.assertFalse(any("-i" in part for part in calls[0][0]))

    def test_wrong_adapter_is_error_not_false_empty(self):
        def runner(argv, **kw):
            return subprocess.CompletedProcess(argv,0,
                 "Controller "+C1+" [default]\n", "")
        with self.assertRaises(mod.BluezCommandError):
            mod.selected(C0, "devices Connected", runner=runner)

    def test_no_mutating_command_or_shell_injection(self):
        for query in ("remove "+DEVICE, "devices Connected; rm -rf /",
                      "scan bredr", "info ;", "devices Connected\nquit"):
            with self.assertRaises(ValueError):
                mod.selected(C0, query)
        with self.assertRaises(ValueError):
            mod.selected("bad\npower off", "devices Connected")

    def test_bluez_error_detected(self):
        def runner(argv, **kw):
            return subprocess.CompletedProcess(argv,0,
                  "Controller "+C0+" [default]\nFailed to select controller", "")
        with self.assertRaises(mod.BluezCommandError):
            mod.selected(C0,"devices Connected",runner=runner)


if __name__=="__main__":
    unittest.main()
