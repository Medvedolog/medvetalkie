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
    if argv == ["busctl", "--system", "tree", "org.bluez"]:
        return ("/org/bluez/hci0\n/org/bluez/hci1\n"
                "/org/bluez/hci0/dev_"+A.replace(":","_")+"\n"
                "/org/bluez/hci1/dev_"+B.replace(":","_")+"\n")
    if argv[:4] == ["busctl", "--system", "get-property", "org.bluez"]:
        path, interface, prop = argv[4:]
        if interface == "org.bluez.Adapter1" and prop == "Address":
            return 's "' + (C0 if path.endswith("hci0") else C1) + '"'
        if interface == "org.bluez.Device1" and prop == "Connected":
            return "b true"
        raise AssertionError("unexpected D-Bus property " + repr(argv))
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

    def test_validate_two_controllers_and_hfp(self):
        plan=mt.validate(A,B,"test",executor=fake_executor)
        self.assertEqual(plan["A"]["adapter"],C0)
        self.assertEqual(plan["B"]["adapter"],C1)
        self.assertEqual(plan["A"]["source"],"bluez_input."+A)
        self.assertEqual(plan["B"]["profile"],"headset-head-unit-cvsd")

    def test_dbus_inventory_rejects_disconnected_headset(self):
        def disconnected(argv, timeout=12):
            if argv[-2:] == ["org.bluez.Device1", "Connected"] and (
                "dev_"+B.replace(":","_") in argv[4]):
                return "b false"
            return fake_executor(argv, timeout)
        with self.assertRaisesRegex(mt.BridgeError, "exactly one"):
            mt.validate(A, B, "test", executor=disconnected)

    def test_dbus_inventory_rejects_missing_controller(self):
        def only_one(argv, timeout=12):
            if argv[-1] == "org.bluez":
                return "/org/bluez/hci0\n/org/bluez/hci0/dev_"+A.replace(":","_")
            return fake_executor(argv, timeout)
        with self.assertRaisesRegex(mt.BridgeError, "two BlueZ"):
            mt.validate(A, B, "test", executor=only_one)

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

    def test_route_selection(self):
        plan=mt.validate(A,B,"test",executor=fake_executor)
        self.assertEqual(len(mt.route_pairs(plan, "both")), 2)
        self.assertEqual(mt.route_pairs(plan, "a-to-b"),
                         [(plan["A"]["source"], plan["B"]["sink"])])
        self.assertEqual(mt.route_pairs(plan, "b-to-a"),
                         [(plan["B"]["source"], plan["A"]["sink"])])
        with self.assertRaises(mt.BridgeError):
            mt.route_pairs(plan,"invalid")

    def test_endpoint_levels_are_read_only(self):
        plan=mt.validate(A,B,"test",executor=fake_executor)
        seen=[]
        def executor(argv):
            seen.append(argv)
            return "Volume: 100% / Mute: no"
        result=mt.endpoint_levels(plan,"test",executor)
        self.assertIn("A source volume",result)
        self.assertIn("B sink mute",result)
        self.assertEqual(len(seen),8)
        self.assertTrue(all("get-" in argv[-2] for argv in seen))

    def test_read_only_live_diagnostics(self):
        seen=[]
        def reader(argv):
            seen.append(argv)
            if argv[-1] == "modules":
                return "51 module-loopback a\n52 other-module b"
            if argv[-1] == "sinks":
                return "100 alsa_output.fake\n101 bluez_output.headset"
            if argv[-1] == "sources":
                return "100 alsa_input.fake\n101 bluez_input.headset"
            return "11 active_stream"
        result=mt.audio_snapshot("test", reader)
        self.assertIn("51 module-loopback", result)
        self.assertNotIn("52 other-module", result)
        self.assertIn("bluez_input.headset", result)
        self.assertTrue(all("pactl" in argv for argv in seen))
        self.assertFalse(any("load-module" in argv or "unload-module" in argv for argv in seen))

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
