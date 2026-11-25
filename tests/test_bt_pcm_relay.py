#!/usr/bin/env python3
"""Offline regression tests for bounded cross-HFP PCM relay."""
import importlib.util
import math
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

path=Path(__file__).resolve().parents[1]/"platform/bluetooth/medvetalkie-pcm-relay.py"
spec=importlib.util.spec_from_file_location("mt_pcm_relay",path)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PCMRelayTests(unittest.TestCase):
    def test_20ms_frame_size_and_bounded_queue(self):
        self.assertEqual(mod.FRAME_BYTES,640)
        route=mod.Route("test","medvetalkie","input","output",80)
        self.assertEqual(route.queue.maxsize,15)
        self.assertEqual(route.queue.maxsize*mod.FRAME_MS,300)

    def test_pcm_peak_rms_and_clipping(self):
        stat=mod.Stats()
        data=struct.pack("<hhhh",0,32767,-32768,16384)
        stat.capture(data,1.0)
        stat.write(4,1.04)
        result=stat.report(1)
        self.assertEqual(result["received_bytes"],8)
        self.assertEqual(result["forwarded_bytes"],4)
        self.assertEqual(result["clipped_samples"],2)
        self.assertEqual(result["peak_dbfs"],0.0)
        self.assertEqual(result["startup_ms"],40)
        self.assertGreater(result["rms_dbfs"],-5)

    def test_zero_pcm_is_reported(self):
        stat=mod.Stats()
        stat.capture(bytes(640),1)
        result=stat.report(1)
        self.assertLess(result["rms_dbfs"],-100)
        self.assertEqual(result["clipped_samples"],0)

    def test_args_have_mono_low_latency_and_exact_target(self):
        with patch.object(mod.MT,"audio_cli",side_effect=lambda user,*parts:list(parts)):
            recv=mod.pulse_args("medvetalkie","parecord","bluez_input.A",80)
            send=mod.pulse_args("medvetalkie","paplay","bluez_output.B",80)
        for args in (recv,send):
            self.assertIn("--raw",args)
            self.assertIn("--rate=16000",args)
            self.assertIn("--channels=1",args)
            self.assertIn("--format=s16le",args)
            self.assertIn("--latency-msec=80",args)
            self.assertIn("--process-time-msec=20",args)
        self.assertIn("--device=bluez_input.A",recv)
        self.assertIn("--device=bluez_output.B",send)

    def test_rejects_unsafe_latency(self):
        for value in (-1,0,20,1000):
            with self.assertRaises(ValueError):
                mod.pulse_args("medvetalkie","paplay","sink",value)

    def test_route_isolation(self):
        plan={"A":{"source":"a-mic","sink":"a-speaker"},
              "B":{"source":"b-mic","sink":"b-speaker"}}
        self.assertEqual(mod.choose_routes(plan,"a-to-b"),
                         [("AIRIDE->UGREEN","a-mic","b-speaker")])
        self.assertEqual(mod.choose_routes(plan,"b-to-a"),
                         [("UGREEN->AIRIDE","b-mic","a-speaker")])
        self.assertEqual(len(mod.choose_routes(plan,"both")),2)

    def test_duration_rejected_before_creating_streams(self):
        with patch.object(mod.Route,"begin") as begin:
            with self.assertRaises(ValueError):
                mod.execute({"A":{},"B":{}},"a-to-b","medvetalkie",120,80)
        begin.assert_not_called()


if __name__=="__main__":
    unittest.main()
