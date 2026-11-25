#!/usr/bin/env python3
"""Offline safety and routing tests for MedveTalkie headless bridge."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "platform/bluetooth/medvetalkie-intercom-test.py"
spec = importlib.util.spec_from_file_location("medvetalkie_intercom", PATH)
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

A = "41:42:63:27:E7:3A"
B = "22:33:44:55:66:77"
C0 = "F4:4E:FC:57:69:64"
C1 = "F4:4E:FC:2D:FD:4B"

def fake_executor(argv, timeout=12):
    tail = argv[-1]
    if argv == ["bluetoothctl", "list"]:
        return "Controller "+C0+" First\nController "+C1+" Second"
    if tail == "cards":
        return (
            "Card #1\n Name: alsa_card.mock\n Active Profile: output:stereo-fallback\n"
            "Card #97\n Name: bluez_card."+A.replace(":","_")+
            "\n Active Profile: headset-head-unit\n"
            "Card #98\n Name: bluez_card."+B.replace(":","_")+
            "\n Active Profile: headset-head-unit-cvsd\n")
    if tail == "sinks":
        return ("12 bluez_output."+A.replace(":","_")+".1 PipeWire\n"
                "13 bluez_output."+B.replace(":","_")+".1 PipeWire\n")
    if tail == "sources":
        return ("18 bluez_input."+A+" PipeWire\n"
                "19 bluez_input."+B+" PipeWire\n"
                "20 bluez_output."+A.replace(":","_")+".1.monitor PipeWire\n")
    raise AssertionError("unexpected command "+repr(argv))


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.audio = patch.object(mt, "audio_cli", side_effect=lambda user, *a: list(a))
        self.audio.start()
        self.addCleanup(self.audio.stop)
        self.selected = patch.object(mt, "selected_bluez", side_effect=lambda controller, query: (
            "Controller "+controller+" [default]\nDevice "+(A if controller == C0 else B)+" headset"))
        self.selected.start()
        self.addCleanup(self.selected.stop)

    def test_validate_two_controllers_and_hfp(self):
        plan=mt.validate(A,B,"test",executor=fake_executor)
        self.assertEqual(plan["A"]["adapter"],C0)
        self.assertEqual(plan["B"]["adapter"],C1)
        self.assertEqual(plan["A"]["source"],"bluez_input."+A)
        self.assertEqual(plan["B"]["profile"],"headset-head-unit-cvsd")

    def test_same_device_rejected(self):
        with self.assertRaisesRegex(mt.BridgeError,"distinct"):
            mt.validate(A,A,"test",executor=fake_executor)

    def test_same_adapter_rejected(self):
        with self.assertRaisesRegex(mt.BridgeError,"same controller|share one controller"):
            mt.assign_controllers(A,B,{A:{C0},B:{C0}})

    def test_unknown_adapters_rejected(self):
        with self.assertRaisesRegex(mt.BridgeError,"exactly one"):
            mt.assign_controllers(A,B,{A:set(),B:{C1}})

    def test_profile_failure_prevents_routes(self):
        def fake(argv):
            out=fake_executor(argv)
            if argv[-1]=="cards":
                return out.replace("Active Profile: headset-head-unit-cvsd",
                                   "Active Profile: a2dp-sink")
            return out
        with self.assertRaisesRegex(mt.BridgeError,"not an HFP"):
            mt.validate(A,B,"test",executor=fake)

    def test_loopback_uses_crossed_routes(self):
        plan=mt.validate(A,B,"test",executor=fake_executor)
        actions=[]
        ids=iter(("201","202"))
        def fake(argv):
            actions.append(argv)
            if "load-module" in argv: return next(ids)
            if "unload-module" in argv:return ""
            raise AssertionError(argv)
        with patch.object(mt.time, "monotonic", side_effect=[0.0, 5.1]):
            mt.bridge(plan,"test",5,80,executor=fake,sleep=lambda _:None)
        modules=[i for i in actions if "load-module" in i]
        self.assertEqual(len(modules),2)
        self.assertIn("source=bluez_input."+A, modules[0])
        self.assertIn("sink=bluez_output."+B.replace(":","_")+".1",modules[0])
        self.assertIn("source=bluez_input."+B,modules[1])
        unload=[i[-1] for i in actions if "unload-module" in i]
        self.assertEqual(unload,["202","201"])

    def test_partial_failure_unloads_first(self):
        plan=mt.validate(A,B,"test",executor=fake_executor)
        unloaded=[]
        def fake(argv):
            if "load-module" in argv and not unloaded:
                if not hasattr(fake, "loaded"):
                    fake.loaded=True
                    return "42"
                raise mt.BridgeError("second module refused")
            if "unload-module" in argv:
                unloaded.append(argv[-1])
                return ""
            raise AssertionError(argv)
        with self.assertRaisesRegex(mt.BridgeError,"second module"):
            mt.bridge(plan,"test",5,80,executor=fake,sleep=lambda _:None)
        self.assertEqual(unloaded,["42"])

    def test_module_id_rejects_unexpected_output(self):
        for value in ("", "module 3", "3\n4", "-1"):
            with self.assertRaises(mt.BridgeError):
                mt.parse_module_id(value)

    def test_delay_limits(self):
        with self.assertRaises(mt.BridgeError):
            mt.loopback_args("source","sink",5)
        self.assertEqual(mt.loopback_args("one","two",80)[-1],
                         "sink_dont_move=true")


if __name__=="__main__":
    unittest.main()
