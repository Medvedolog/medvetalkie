#!/usr/bin/env python3
"""Read-only real headset/PipeWire telemetry to MTSTATUS1 for the ST7789 renderer.

Use INSTEAD of the legacy C status publisher, never concurrently writing the
same file. No Bluetooth pairing, profile changes, volumes or service actions.
Unknown observations must remain unknown, never become HFP_READY.
"""
import argparse
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile
import time

MAC_RE=re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
MAX_AGE=12

def execute(argv,timeout=5):
    result=subprocess.run(argv,capture_output=True,text=True,timeout=timeout,check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[:180])
    return result.stdout

def audio(user, *args):
    uid=pwd.getpwnam(user).pw_uid
    env=["XDG_RUNTIME_DIR=/run/user/%d"%uid,
         "PULSE_SERVER=unix:/run/user/%d/pulse/native"%uid]
    if os.geteuid()==0:
        return ["runuser","-u",user,"--","env",*env,*args]
    if os.geteuid()!=uid:
        raise PermissionError("Only root or audio account may query PipeWire")
    return ["env",*env,*args]

def bus_prop(path, interface, name, executor=execute):
    try:
        raw=executor(["busctl","--system","get-property","org.bluez",path,interface,name]).strip()
    except (OSError,RuntimeError,subprocess.TimeoutExpired):
        return None
    if raw.startswith('s "'):
        return raw[3:-1] if raw.endswith('"') else None
    if raw.startswith("b "):
        return raw[2:]=="true"
    if raw.startswith("y ") or raw.startswith("n ") or raw.startswith("q "):
        try:return int(raw[2:].strip())
        except ValueError:return None
    return None

def headset(mac, adapter, cards, sinks, sources, executor=execute):
    obj="/org/bluez/"+adapter+"/dev_"+mac.replace(":","_")
    bonded=bus_prop(obj,"org.bluez.Device1","Paired",executor)
    connected=bus_prop(obj,"org.bluez.Device1","Connected",executor)
    battery=bus_prop(obj,"org.bluez.Battery1","Percentage",executor)
    rssi=bus_prop(obj,"org.bluez.Device1","RSSI",executor)
    card="bluez_card."+mac.replace(":","_")
    profile=None
    for section in re.split(r"(?=^Card #\d+)",cards,flags=re.M):
        if re.search(r"^\s*Name:\s*"+re.escape(card)+r"\s*$",section,re.M):
            match=re.search(r"^\s*Active Profile:\s*(\S+)",section,re.M)
            profile=match.group(1) if match else None
            break
    source_present=any(("bluez_input."+mac).lower()==line.split()[1].lower()
                       for line in sources.splitlines() if len(line.split())>1)
    output_prefix="bluez_output."+mac.replace(":","_")+"."
    sink_present=any(line.split()[1].lower().startswith(output_prefix.lower())
                     for line in sinks.splitlines() if len(line.split())>1)
    volume=-1
    for line in sinks.splitlines():
        parts=line.split()
        if len(parts)>1 and parts[1].lower().startswith(output_prefix.lower()):
            try:
                vol=executor(audio("medvetalkie","pactl","get-sink-volume",parts[1]))
                match=re.search(r"/\s*(\d+)%",vol)
                if match:volume=min(150,int(match.group(1)))
            except (OSError,RuntimeError,subprocess.TimeoutExpired):pass
            break
    if connected is True and profile in ("headset-head-unit","headset-head-unit-cvsd") and source_present and sink_present:
        state="HFP_READY"
    elif connected is True and profile and profile.startswith("a2dp-") and sink_present:
        state="A2DP_READY"
    elif connected is True and profile and profile.startswith("a2dp-"):
        state="PROFILE_PENDING"
    elif connected is True and profile and profile.startswith("headset-head-unit"):
        state="PROFILE_PENDING"
    elif connected is True:
        state="CONNECTED_NO_AUDIO"
    elif connected is False and bonded is True:
        state="DISCONNECTED"
    elif bonded is True:
        state="DISCONNECTED"
    else:
        state="UNASSIGNED"
    return dict(state=state, battery=battery if isinstance(battery,int) and 0<=battery<=100 else -1,
                rssi=rssi if isinstance(rssi,int) and -127<=rssi<=20 else -128,
                volume=volume, profile="HFP" if state=="HFP_READY" else ("A2DP" if state=="A2DP_READY" else "UNKNOWN"),
                connected=connected is True)

def current_network(executor=execute):
    try:
        raw=executor(["ip","-br","-4","addr","show"])
        for line in raw.splitlines():
            parts=line.split()
            if len(parts)<3 or parts[1]!="UP" or not any("/" in x for x in parts[2:]):continue
            if parts[0].startswith(("end","eth","en")):return "LAN"
            if parts[0].startswith(("wlan","wl")):return "WIFI"
    except (OSError,RuntimeError,subprocess.TimeoutExpired):pass
    return "NO_LINK"

def snapshot(mac_a,mac_b,user="medvetalkie",executor=execute):
    try:tree=executor(["busctl","--system","tree","org.bluez"])
    except (OSError,RuntimeError,subprocess.TimeoutExpired):tree=""
    adapters=sorted(set(re.findall(r"/org/bluez/(hci\d+)(?:\b|/)",tree)))
    mac_to_adapter={}
    for adapter in adapters:
        address=bus_prop("/org/bluez/"+adapter,"org.bluez.Adapter1","Address",executor)
        if isinstance(address,str):mac_to_adapter[address.upper()]=adapter
    # Only known bonded device object paths count. No false mapping by adapter order.
    device_adapters={}
    for mac in (mac_a,mac_b):
        for adapter in adapters:
            if "/org/bluez/"+adapter+"/dev_"+mac.replace(":","_") in tree:
                device_adapters[mac]=adapter
                break
    try:
        cards=executor(audio(user,"pactl","list","cards"))
        sinks=executor(audio(user,"pactl","list","short","sinks"))
        sources=executor(audio(user,"pactl","list","short","sources"))
    except (OSError,RuntimeError,PermissionError,subprocess.TimeoutExpired):
        cards=sinks=sources=""
    result=[]
    for mac in (mac_a,mac_b):
        adapter=device_adapters.get(mac)
        if adapter:
            result.append(headset(mac,adapter,cards,sinks,sources,executor))
        else:
            result.append(dict(state="UNASSIGNED",battery=-1,rssi=-128,volume=-1,profile="UNKNOWN",connected=False))
    a,b=result
    voice="READY" if a["state"]=="HFP_READY" and b["state"]=="HFP_READY" else "NOT_VERIFIED"
    # Even with two HFP profiles, this is not proof an active two-way PCM
    # bridge has been established. Do not expose READY from this inventory alone.
    voice="NOT_VERIFIED"
    net=current_network(executor)
    count=sum(int(s["connected"]) for s in result)
    return dict(mode="STANDBY",headset1=a["state"],headset2=b["state"],voice=voice,
                network=net,radio="NOT_AVAILABLE",battery="UNKNOWN",
                fault="NONE" if adapters else "BT_FAILED",
                bt_usb=min(32,len(adapters)),bt_connected=count,
                h1_battery=a["battery"],h2_battery=b["battery"],
                h1_rssi=a["rssi"],h2_rssi=b["rssi"],
                h1_volume=a["volume"],h2_volume=b["volume"],
                h1_profile=a["profile"],h2_profile=b["profile"])

def encode(data):
    rows=["MTSTATUS1"]
    for k,v in data.items():
        if not re.fullmatch(r"[a-z0-9_]+",k):raise ValueError("Unsafe key")
        if isinstance(v,str) and not re.fullmatch(r"[A-Z0-9_]+",v):raise ValueError("Unsafe value")
        rows.append("%s=%s"%(k,v))
    return ("\n".join(rows)+"\n").encode()

def publish(path,data):
    dest=Path(path)
    if not dest.is_absolute():raise ValueError("Absolute output required")
    payload=encode(data)
    if len(payload)>1024:raise ValueError("Snapshot too large")
    fd,name=tempfile.mkstemp(prefix=".mtstatus-",dir=str(dest.parent))
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"wb") as target:
            fd=-1
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(name,path)
    finally:
        if fd>=0:os.close(fd)
        if os.path.exists(name):os.unlink(name)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a",default="41:42:63:27:E7:3A")
    p.add_argument("--b",default="B0:F0:0C:63:83:F5")
    p.add_argument("--user",default="medvetalkie")
    p.add_argument("--output",required=True)
    p.add_argument("--interval",type=int,default=2)
    p.add_argument("--once",action="store_true")
    args=p.parse_args()
    if not MAC_RE.fullmatch(args.a) or not MAC_RE.fullmatch(args.b) or args.a==args.b:
        p.error("Two distinct valid headset MACs required")
    if not 1<=args.interval<=9:p.error("interval must be 1..9")
    while True:
        publish(args.output,snapshot(args.a.upper(),args.b.upper(),args.user))
        if args.once:break
        time.sleep(args.interval)

if __name__=="__main__":
    main()
