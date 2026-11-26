#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest

src=Path(__file__).resolve().parents[1]/"platform/display/live-status.py"
spec=importlib.util.spec_from_file_location("mt_live_status",src)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
A="41:42:63:27:E7:3A"
B="B0:F0:0C:63:83:F5"

class LiveStatusTests(unittest.TestCase):
    def test_private_atomic_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/"display.status")
            mod.publish(path,{"mode":"UNKNOWN","h1_rssi":-128})
            self.assertEqual(Path(path).read_text(),"MTSTATUS1\nmode=UNKNOWN\nh1_rssi=-128\n")
            self.assertEqual(Path(path).stat().st_mode&0o777,0o600)

    def test_known_headsets_profiles_battery_rssi_but_no_false_voice(self):
        from unittest.mock import patch
        def fake(argv,timeout=5):
            if argv[:3]==["busctl","--system","tree"]:
                return ("/org/bluez/hci0\n/org/bluez/hci1\n"+
                        "/org/bluez/hci0/dev_"+A.replace(":","_")+"\n"+
                        "/org/bluez/hci1/dev_"+B.replace(":","_")+"\n")
            if argv[:3]==["busctl","--system","get-property"]:
                prop=argv[-1]
                if prop in ("Paired","Connected"):return "b true"
                if prop=="Percentage":return "y "+("70" if A.replace(":","_") in argv[4] else "80")
                if prop=="RSSI":return "n -56"
                raise RuntimeError("unavailable")
            if "pactl" in argv:
                cmd=argv[argv.index("pactl")+1:]
                if cmd==["list","cards"]:
                    return ("Card #11\nName: bluez_card."+A.replace(":","_")+
                            "\nActive Profile: headset-head-unit\n"+
                            "Card #12\nName: bluez_card."+B.replace(":","_")+
                            "\nActive Profile: headset-head-unit\n")
                if cmd==["list","short","sinks"]:
                    return ("11 bluez_output."+A.replace(":","_")+".1 PipeWire\n"+
                            "12 bluez_output."+B.replace(":","_")+".1 PipeWire\n")
                if cmd==["list","short","sources"]:
                    return ("22 bluez_input."+A+" PipeWire\n"+
                            "23 bluez_input."+B+" PipeWire\n")
                if cmd[0]=="get-sink-volume":return "Volume: mono: 65536 / 100% / 0.00 dB"
            if argv[:3]==["ip","-br","-4"]:return "end0 UP 192.168.11.1/24"
            raise AssertionError("Unexpected request: "+repr(argv))
        with patch.object(mod.os,"geteuid",return_value=0):
            with patch.object(mod.pwd,"getpwnam") as account:
                account.return_value.pw_uid=1000
                state=mod.snapshot(A,B,executor=fake)
        self.assertEqual(state["headset1"],"PROFILE_PENDING")
        self.assertEqual(state["headset2"],"PROFILE_PENDING")
        self.assertEqual(state["h1_profile"],"HFP")
        self.assertEqual(state["h1_battery"],70)
        self.assertEqual(state["h2_battery"],80)
        self.assertEqual(state["h1_rssi"],-56)
        self.assertEqual(state["h2_volume"],100)
        self.assertEqual(state["voice"],"NOT_VERIFIED")

    def test_missing_bluez_is_not_hfp_ready(self):
        def query(argv,timeout=5):
            if argv[:3]==["busctl","--system","tree"]:raise RuntimeError("offline")
            if argv[:3]==["ip","-br","-4"]:return ""
            raise RuntimeError("unavailable")
        state=mod.snapshot(A,B,executor=query)
        self.assertEqual(state["headset1"],"UNASSIGNED")
        self.assertEqual(state["headset2"],"UNASSIGNED")
        self.assertEqual(state["voice"],"NOT_VERIFIED")
        self.assertEqual(state["fault"],"BT_FAILED")
        self.assertEqual(state["h1_battery"],-1)

    def test_core_mode_and_fault_use_fresh_separate_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            name=Path(tmp)/"core.status"
            name.write_text("MTSTATUS1\nmode=INTERCOM\nfault=NONE\nnetwork=LAN\nradio=NOT_AVAILABLE\n")
            value=mod.base_status(str(name))
            self.assertEqual(value["mode"],"INTERCOM")
            self.assertEqual(value["fault"],"NONE")
            name.write_text("MTSTATUS1\nmode=NOT_A_REAL_MODE\nfault=NONE\n")
            self.assertIsNone(mod.base_status(str(name)))

    def test_stale_core_rejected(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            name=Path(tmp)/"core.status"
            name.write_text("MTSTATUS1\nmode=INTERCOM\nfault=NONE\n")
            os.utime(name,(1,1))
            self.assertIsNone(mod.base_status(str(name)))

    def test_injection_rejected(self):
        with self.assertRaises(ValueError):mod.encode({"state":"READY\nfoo=BAD"})
        with self.assertRaises(ValueError):mod.encode({"foo\nbar":"READY"})

if __name__=="__main__":unittest.main()
