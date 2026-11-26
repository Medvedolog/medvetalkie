#!/usr/bin/env python3
"""Offline checks for cross PCM isolation."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
root = Path(__file__).resolve().parents[1] / "platform/bluetooth"
spec = importlib.util.spec_from_file_location("cross_pcm_isolation",root/"cross_pcm_isolation.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class IsolationTests(unittest.TestCase):
    def test_mac_assignment(self):
        self.assertEqual(mod.A,"41:42:63:27:E7:3A")
        self.assertEqual(mod.B,"B0:F0:0C:63:83:F5")
        self.assertNotEqual(mod.A,mod.B)

    def test_user_source_lookup(self):
        with patch.object(mod.audio,"find_audio_devices",return_value=("out","in","headset-head-unit")) as finder:
            self.assertEqual(mod.one_device(mod.A,"medvetalkie"),
                             ("out","in","headset-head-unit"))
        finder.assert_called_once_with(mod.A,"medvetalkie")

    def test_replay_option_is_explicit_opt_in(self):
        import inspect
        parameter = inspect.signature(mod.test).parameters["replay"]
        self.assertIs(parameter.default, False)

    def test_duration_rejected_before_audio_mutation(self):
        with patch.object(mod,"one_device") as probe:
            with self.assertRaises(ValueError):
                mod.test(seconds=2)
        probe.assert_not_called()

if __name__=="__main__":
    unittest.main()
