#!/usr/bin/env python3
"""Offline safety tests of operator-invoked PipeWire native loopback."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "platform/bluetooth/medvetalkie-native-loopback.py"
spec = importlib.util.spec_from_file_location("mt_native_loopback",path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PLAN={"A":{"source":"bluez_input.41:42:63:27:E7:3A","sink":"bluez_output.41_42_63_27_E7_3A.1"},
      "B":{"source":"bluez_input.B0:F0:0C:63:83:F5","sink":"bluez_output.B0_F0_0C_63_83_F5.1"}}


class NativeTests(unittest.TestCase):
    def test_routes_exactly_cross_wired(self):
        a=module.routes(PLAN,"a-to-b")
        b=module.routes(PLAN,"b-to-a")
        self.assertEqual(a,[("a-to-b",PLAN["A"]["source"],PLAN["B"]["sink"])])
        self.assertEqual(b,[("b-to-a",PLAN["B"]["source"],PLAN["A"]["sink"])])
        self.assertEqual(len(module.routes(PLAN,"both")),2)
        with self.assertRaises(ValueError):
            module.routes(PLAN,"wrong")

    def test_command_scopes_pipewire_client(self):
        with patch.object(module.os,"geteuid",return_value=0):
            with patch.object(module.pwd,"getpwnam") as account:
                account.return_value.pw_uid=1000
                cmd=module.native_command("medvetalkie",PLAN["A"]["source"],
                                          PLAN["B"]["sink"],40,"a-to-b")
        self.assertEqual(cmd[:5],["runuser","-u","medvetalkie","--","env"])
        self.assertIn("PIPEWIRE_RUNTIME_DIR=/run/user/1000",cmd)
        self.assertIn("--channels=1",cmd)
        self.assertIn("--channel-map=MONO",cmd)
        self.assertIn("--latency=40",cmd)
        self.assertIn("--capture="+PLAN["A"]["source"],cmd)
        self.assertIn("--playback="+PLAN["B"]["sink"],cmd)
        cap=next(x for x in cmd if x.startswith("--capture-props="))
        out=next(x for x in cmd if x.startswith("--playback-props="))
        self.assertEqual(json.loads(cap.split("=",1)[1])["target.object"],PLAN["A"]["source"])
        self.assertEqual(json.loads(out.split("=",1)[1])["target.object"],PLAN["B"]["sink"])
        self.assertNotIn("pactl",cmd)
        self.assertNotIn("bluetoothctl",cmd)

    def test_inspect_native_graph_detects_pulse_alias_mismatch(self):
        snapshot=[
            {"id":10,"type":"PipeWire:Interface:Node",
             "info":{"props":{"node.name":"bluez_input.native_A","media.class":"Audio/Source"},"state":"running"}},
            {"id":11,"type":"PipeWire:Interface:Node",
             "info":{"props":{"node.name":"bluez_output.native_B","media.class":"Audio/Sink"},"state":"running"}}
        ]
        def runner(argv):
            self.assertIn("pw-dump",argv)
            return json.dumps(snapshot)
        with patch.object(module.INTERCOM,"audio_cli",return_value=["pw-dump"]):
            text, failures=module.inspect_live_graph(
                "medvetalkie",[("a-to-b",PLAN["A"]["source"],PLAN["B"]["sink"])],runner)
        self.assertEqual(failures,1)
        self.assertIn("MISMATCH",text)

    def test_inspect_native_graph_shows_real_links(self):
        src=PLAN["A"]["source"]
        sink=PLAN["B"]["sink"]
        snapshot=[
            {"id":10,"type":"PipeWire:Interface:Node",
             "info":{"props":{"node.name":src},"state":"running"}},
            {"id":11,"type":"PipeWire:Interface:Node",
             "info":{"props":{"node.name":sink},"state":"running"}},
            {"id":12,"type":"PipeWire:Interface:Link",
             "info":{"output-node-id":10,"input-node-id":11,"state":"active"}}
        ]
        with patch.object(module.INTERCOM,"audio_cli",return_value=["pw-dump"]):
            text,failures=module.inspect_live_graph(
                "medvetalkie",[("a-to-b",src,sink)],lambda argv: json.dumps(snapshot))
        self.assertEqual(failures,0)
        self.assertIn("Graph links",text)

    def test_reject_bad_latency_and_unscoped_endpoints(self):
        with self.assertRaises(ValueError):
            module.native_command("medvetalkie","bluez_input.A","bluez_output.B",4,"a")
        with self.assertRaises(ValueError):
            module.native_command("medvetalkie","alsa_input.any","bluez_output.B",40,"a")
        with self.assertRaises(ValueError):
            module.native_command("medvetalkie","bluez_input.A","alsa_output.any",40,"a")


if __name__=="__main__":
    unittest.main()
