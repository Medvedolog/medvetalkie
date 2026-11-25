#!/usr/bin/env python3
"""Offline tests for MedveTalkie menu: discovery, status and control surface."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "platform/bluetooth/medvetalkie-bt-menu.py"
spec = importlib.util.spec_from_file_location("mt_bt_menu", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class MenuTests(unittest.TestCase):
    def test_menu_has_all_user_requested_operations(self):
        actions = {key for _, key in mod.ACTIONS}
        self.assertTrue({
            "scan", "connect", "pair", "trust", "disconnect",
            "a2dp-sink", "headset-head-unit", "headset-head-unit-cvsd",
            "record", "play", "sink+", "sink-", "source+", "source-",
            "duplex", "trace"
        }.issubset(actions))

    def test_device_parse(self):
        found = mod.parse_devices(
            "Device 41:42:63:27:E7:3A AIRIDE N1\n"
            "Device 00:9E:C8:92:D4:99 MIBOX3\njunk\n")
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0]["name"], "AIRIDE N1")

    def test_device_info(self):
        info = ("Name: AIRIDE N1\n Paired: yes\n Bonded: yes\n"
                " Trusted: yes\n Connected: yes\n RSSI: -54\n"
                " Battery Percentage: 0x46 (70)\n")
        flags = mod.parse_device_info(info)
        self.assertTrue(flags["connected"])
        self.assertTrue(flags["paired"])
        self.assertTrue(flags["trusted"])
        self.assertEqual(flags["rssi"], -54)
        self.assertEqual(flags["battery"], 70)

    def test_rssi_quality_indicator(self):
        self.assertEqual(mod.rssi_indicator(-49), "||||")
        self.assertEqual(mod.rssi_indicator(-65), "|||.")
        self.assertEqual(mod.rssi_indicator(-77), "||..")
        self.assertEqual(mod.rssi_indicator(-92), "|...")
        self.assertEqual(mod.rssi_indicator(None), "----")

    def test_no_rssi_not_fabricated(self):
        flags = mod.parse_device_info("Connected: yes\nPaired: yes")
        self.assertIsNone(flags["rssi"])
        self.assertEqual(mod.device_group(flags), 0)

    def test_merge_saved_and_connected(self):
        first = [{"mac":"00:9E:C8:92:D4:99","name":"MIBOX3"}]
        def fake(argv, timeout=20):
            if argv[-1] == "Paired":
                return 0, "Device 41:42:63:27:E7:3A AIRIDE N1"
            if argv[-1] == "Connected":
                return 0, "Device 41:42:63:27:E7:3A AIRIDE N1"
            if argv[-2:] == ["info", "41:42:63:27:E7:3A"]:
                return 0, "Connected: yes\nPaired: yes\nRSSI: -48\n"
            return 0, "Connected: no\nPaired: no\n"
        with patch.object(mod, "command", side_effect=fake):
            merged, warnings = mod.enrich_devices("F4:4E:FC:57:69:64", first)
        self.assertEqual(warnings, [])
        self.assertEqual(merged[0]["name"], "AIRIDE N1")
        self.assertEqual(merged[0]["rssi"], -48)
        self.assertEqual(mod.device_group(merged[1]), 2)

    def test_profile_scoped_to_card(self):
        txt = ("Card #3\n Name: alsa_card.h616\n Active Profile: output\n"
               "Card #97\n Name: bluez_card.41_42_63_27_E7_3A\n"
               " Active Profile: headset-head-unit\n")
        self.assertEqual(mod.parse_profile(txt, "41:42:63:27:E7:3A"),
                         "headset-head-unit")

    def test_gain_parser(self):
        self.assertEqual(mod.percent("Volume: front-left: 78643 / 120% / +4.5 dB"), 120)
        self.assertIsNone(mod.percent("No volume"))

    def test_audio_nodes_exclude_monitor(self):
        def fake(argv, timeout=20):
            if argv[-1] == "sinks":
                return 0, "112 bluez_output.41_42_63_27_E7_3A.1 PipeWire\n"
            return 0, ("99 bluez_input.41:42:63:27:E7:3A PipeWire\n"
                       "112 bluez_output.41_42_63_27_E7_3A.1.monitor PipeWire\n")
        with patch.object(mod, "invoke_user", side_effect=lambda *a: list(a)):
            with patch.object(mod, "command", side_effect=fake):
                sink, source = mod.audio_devices("41:42:63:27:E7:3A")
        self.assertEqual(sink, "bluez_output.41_42_63_27_E7_3A.1")
        self.assertEqual(source, "bluez_input.41:42:63:27:E7:3A")


if __name__ == "__main__":
    unittest.main()
