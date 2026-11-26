#!/usr/bin/env python3
"""Offline ST7789 v2 status preview and fail-closed invalid telemetry tests."""
import base64
import gzip
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SAVER=ROOT/"platform/display/screensaver"
builder=SAVER/"build-status-v2.py"

with tempfile.TemporaryDirectory(prefix="mt-status-v2-") as temp:
    folder=Path(temp)
    generated=folder/"screensaver-v2.c"
    subprocess.run(["python3",str(builder),"--output",str(generated)],check=True)
    binary=folder/"display-v2"
    result=subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-O2",
                           str(generated),"-lm","-o",str(binary)],
                          capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    asset=folder/"sprite.dat"
    asset.write_bytes(gzip.decompress(base64.b64decode(
        (SAVER/"bjorni-sprite.gz.b64").read_bytes())))
    env=dict(os.environ,MEDVETALKIE_SPRITE=str(asset))

    def preview(text,name):
        status=folder/"display.status"
        status.write_text(text)
        output=folder/name
        done=subprocess.run([str(binary),"--preview",str(output),
                             "--status-file",str(status)],env=env,
                            capture_output=True,text=True)
        assert done.returncode==0,done.stderr
        data=output.read_bytes()
        assert data.startswith(b"P6\n320 240\n255\n")
        assert len(data)>320*240*3
        return data

    base=("MTSTATUS1\nmode=UNKNOWN\nheadset1=PROFILE_PENDING\n"
          "headset2=PROFILE_PENDING\nvoice=NOT_VERIFIED\nnetwork=LAN\n"
          "radio=NOT_AVAILABLE\nbattery=UNKNOWN\nfault=NONE\n"
          "bt_usb=2\nbt_connected=2\n")
    known=(base+"h1_profile=HFP\nh2_profile=HFP\nh1_battery=70\n"
           "h2_battery=80\nh1_rssi=-58\nh2_rssi=-73\n"
           "h1_volume=90\nh2_volume=87\n")
    default=preview(base,"default.ppm")
    detailed=preview(known,"detailed.ppm")
    assert default!=detailed,"headset levels must visibly affect image"
    missing=preview(base+"h1_battery=-1\nh2_rssi=-128\n","missing.ppm")
    assert missing==default,"unknown sentinel must display same unknown state"
    invalid=preview(base+"h1_battery=200\n","invalid.ppm")
    assert invalid!=detailed
    malformed=preview(base+"h1_profile=HFP;bad\n","malformed.ppm")
    assert malformed!=detailed
    fault=preview(known.replace("fault=NONE","fault=BT_FAILED"),"fault.ppm")
    assert fault!=detailed,"fault banner must be visibly distinct"
    radio=preview(known.replace("mode=UNKNOWN","mode=RADIO"),"radio.ppm")
    game=preview(known.replace("mode=UNKNOWN","mode=GAME"),"game.ppm")
    intercom=preview(known.replace("mode=UNKNOWN","mode=INTERCOM"),"intercom.ppm")
    system=preview(known.replace("bt_connected=2","bt_connected=0"),"system.ppm")
    assert len({radio,game,intercom,system,fault})==5, "each approved screen must differ"
    assert detailed!=system, "connected headsets must show card dashboard, not system view"
    source=(SAVER/"build-status-v2.py").read_text()
    assert "happy_bear" in source and "full_bear" in source
    assert "render_game_v2" in source
    assert "full_bear(25,43,94,142)" in source
    assert "full_bear(220,43,89,142)" in source
    assert "happy_bear(x+74,105,2" in source
    assert "full_bear_idx[7776]" in generated.read_text()
    assert (SAVER/"medvetalkie-full-bear.palette16.z.b64").is_file()
    print("PASS ST7789 v2: full-body paws/keyboard in radio/game/system, headphone head in intercom")
