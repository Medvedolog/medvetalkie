#!/usr/bin/env python3
"""BlueZ controller-scoped CLI parser regression; also tests delayed response."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "platform/bluetooth/bluez_cli.py"
spec = importlib.util.spec_from_file_location("bluez_cli", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

C0 = "F4:4E:FC:57:69:64"
C1 = "F4:4E:FC:2D:FD:4B"
DEVICE = "41:42:63:27:E7:3A"


class BluezCliTests(unittest.TestCase):
    def test_only_readonly_queries_are_allowed(self):
        for query in ("devices", "devices Connected", "devices Paired",
                      "devices Bonded", "devices Trusted", "info "+DEVICE):
            mod.validate(C0, query)

    def test_no_injection_or_unsupported_cli_options(self):
        for query in ("remove "+DEVICE, "devices Connected; rm -rf /",
                      "scan bredr", "info ;", "devices Connected\nquit",
                      "devices  Connected", "devices NotPaired"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                mod.validate(C0, query)
        with self.assertRaises(ValueError):
            mod.validate("bad\npower off", "devices Connected")

    def test_wait_for_following_prompt_and_not_early_echo(self):
        self.assertFalse(mod.response_ready("[AIRIDE N1]> devices Connected\n",
                                           "devices Connected"))
        self.assertFalse(mod.response_ready("[AIRIDE N1]> devices Connected\n"
                                           "Device "+DEVICE+" AIRIDE N1\n",
                                           "devices Connected"))
        self.assertTrue(mod.response_ready("[AIRIDE N1]> devices Connected\n"
                                           "Device "+DEVICE+" AIRIDE N1\n"
                                           "[AIRIDE N1]> ", "devices Connected"))

    def test_empty_connected_list_is_valid_only_after_prompt(self):
        self.assertTrue(mod.response_ready("[bluetoothctl]> devices Connected\n"
                                           "[bluetoothctl]> ", "devices Connected"))

    def test_ansi_and_carriage_return(self):
        output = mod.clean(b"\x1b[0;94m[AIRIDE N1]>\x1b[0m devices Connected\r\n"
                           b"Device 41:42:63:27:E7:3A AIRIDE N1\r\n"
                           b"[AIRIDE N1]> ")
        self.assertTrue(mod.response_ready(output, "devices Connected"))

    def test_no_false_ready_from_unrelated_query(self):
        self.assertFalse(mod.response_ready("[AIRIDE N1]> info "+DEVICE+"\n"
                                            "[AIRIDE N1]> ", "devices Connected"))


if __name__ == "__main__":
    unittest.main()
