#!/usr/bin/env python3
"""Offline CI smoke checks for the SSH Bluetooth bench TUI."""
import importlib.util
import tempfile
import wave
import os
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
        with patch.object(mod, "selected_bluez", return_value=output) as call:
            result, error = mod.discovered("F4:4E:FC:57:69:64")
        self.assertFalse(error)
        self.assertEqual(result[0]["name"], "AIRIDE N1")
        self.assertEqual(call.call_args.args[:2],
                         ("F4:4E:FC:57:69:64", "devices"))

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



bench_path = Path(__file__).resolve().parents[1] / "platform/bluetooth/bt_audio_bench.py"
bench_spec = importlib.util.spec_from_file_location("mt_bt_audio_bench", bench_path)
audio = importlib.util.module_from_spec(bench_spec)
bench_spec.loader.exec_module(audio)


class AudioBenchTests(unittest.TestCase):
    def test_headset_filter_and_hfp_requirement(self):
        cards = ("Card #97\nName: bluez_card.41_42_63_27_E7_3A\n"
                 "Active Profile: headset-head-unit\n")
        def fake(argv):
            kind = argv[-1]
            if kind == "sinks":
                return ("112 bluez_output.41_42_63_27_E7_3A.1 PipeWire\n"
                        "86 alsa_output.mock PipeWire\n")
            if kind == "sources":
                return ("99 bluez_input.41:42:63:27:E7:3A PipeWire\n"
                        "112 bluez_output.41_42_63_27_E7_3A.1.monitor PipeWire\n")
            return cards
        with patch.object(audio, "audio_command", side_effect=lambda u,p,*a: [p,*a]):
            sink, source, profile = audio.find_audio_devices(audio_mac, "test", runner=fake)
        self.assertEqual(profile, "headset-head-unit")
        self.assertEqual(sink, "bluez_output.41_42_63_27_E7_3A.1")
        self.assertEqual(source, "bluez_input.41:42:63:27:E7:3A")

    def test_invalid_mac_never_runs_commands(self):
        with self.assertRaises(ValueError):
            audio.find_audio_devices("not-a-mac", "medvetalkie")

    def test_pcm_metrics_and_tone(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signal.wav"
            audio.tone(path, 3)
            metrics = audio.measure(path)
            self.assertEqual(metrics["rate"], 16000)
            self.assertEqual(metrics["seconds"], 3)
            self.assertEqual(metrics["clipped"], 0)
            self.assertLess(metrics["peak_dbfs"], -15)
            self.assertEqual(len(metrics["windows_dbfs"]), 6)

    def test_test_requires_confirmation(self):
        bench = mod.Bench()
        bench.adapters = [{"mac":"F4:4E:FC:57:69:64", "name":"UGREEN"}]
        bench.devices = [{"mac":audio_mac, "name":"AIRIDE N1"}]
        with patch.object(bench, "work") as worker:
            bench.command("duplex")
        worker.assert_not_called()
        self.assertEqual(bench.pending_duplex, (audio_mac, False))


audio_mac = "41:42:63:27:E7:3A"


if __name__ == "__main__":
    unittest.main()
