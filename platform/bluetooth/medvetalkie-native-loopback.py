#!/usr/bin/env python3
"""Operator-launched native PipeWire loopback A/B experiment.

Does not replace the proven Python PCM relay. Does not change Bluetooth,
system audio profiles, device volumes, display, network or systemd units.
No noise gate or per-route attenuation: test one direction first.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "medvetalkie_intercom", HERE / "medvetalkie-intercom-test.py")
INTERCOM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INTERCOM)


def native_command(user, source, sink, latency_ms, label):
    if not 10 <= latency_ms <= 200:
        raise ValueError("Native latency must be 10..200 ms")
    if not source.startswith("bluez_input.") or not sink.startswith("bluez_output."):
        raise ValueError("Require explicit physical Bluetooth input/output nodes")
    capture = {"target.object": source, "node.dont-reconnect": True}
    playback = {"target.object": sink, "node.dont-reconnect": True}
    uid = pwd.getpwnam(user).pw_uid
    env = ["XDG_RUNTIME_DIR=/run/user/%d" % uid,
           "PIPEWIRE_RUNTIME_DIR=/run/user/%d" % uid]
    program = ["pw-loopback", "--name=medvetalkie-native-"+label,
               "--channels=1", "--channel-map=MONO",
               "--latency=%d" % latency_ms,
               "--capture="+source, "--playback="+sink,
               "--capture-props="+json.dumps(capture,separators=(",",":")),
               "--playback-props="+json.dumps(playback,separators=(",",":"))]
    if os.geteuid() == 0:
        return ["runuser", "-u", user, "--", "env", *env, *program]
    if os.geteuid() != uid:
        raise INTERCOM.BridgeError("Run as root or "+user)
    return ["env", *env, *program]


def routes(plan, direction):
    if direction not in ("a-to-b", "b-to-a", "both"):
        raise ValueError("Invalid direction")
    results = []
    if direction in ("a-to-b","both"):
        results.append(("a-to-b",plan["A"]["source"],plan["B"]["sink"]))
    if direction in ("b-to-a","both"):
        results.append(("b-to-a",plan["B"]["source"],plan["A"]["sink"]))
    return results



def pipewire_snapshot(user, runner=INTERCOM.run):
    """Read actual native PipeWire node names/links, not Pulse-compatible aliases."""
    raw=runner(INTERCOM.audio_cli(user,"pw-dump"))
    objects=json.loads(raw)
    nodes={}
    links=[]
    for obj in objects:
        props=obj.get("info",{}).get("props") or {}
        if obj.get("type")=="PipeWire:Interface:Node":
            nodes[obj["id"]]={
                "name":str(props.get("node.name","")),
                "description":str(props.get("node.description","")),
                "state":str(obj.get("info",{}).get("state","")),
                "media":str(props.get("media.class",""))
            }
        elif obj.get("type")=="PipeWire:Interface:Link":
            info=obj.get("info",{})
            links.append((info.get("output-node-id"),info.get("input-node-id"),
                          str(info.get("state",""))))
    return nodes,links


def inspect_live_graph(user, targets, runner=INTERCOM.run):
    nodes,links=pipewire_snapshot(user,runner)
    names={node["name"]:ident for ident,node in nodes.items()}
    report=[]
    failures=0
    for label,source,sink in targets:
        source_id=names.get(source)
        sink_id=names.get(sink)
        related=[(ident,data) for ident,data in nodes.items()
                 if "medvetalkie-native" in data["name"] or
                    "loopback" in data["name"].lower() or
                    "bluez_" in data["name"]]
        report.append("%s: PipeWire source=%s sink=%s" % (label,source_id,sink_id))
        if source_id is None or sink_id is None:
            report.append("  MISMATCH: Pulse device names are not actual PipeWire node.name entries.")
            failures+=1
        for ident,data in related:
            report.append("  Node %s: %s state=%s class=%s" %
                          (ident,data["name"],data["state"],data["media"]))
        match_links=[(out,inp,state) for out,inp,state in links
                     if out==source_id or inp==sink_id or
                     (out in dict(related) and inp in dict(related))]
        report.append("  Graph links: "+repr(match_links[:24]))
        if source_id is not None and not any(out==source_id for out,_,_ in links):
            report.append("  WARNING: source node has no outgoing PipeWire links")
            failures+=1
        if sink_id is not None and not any(inp==sink_id for _,inp,_ in links):
            report.append("  WARNING: sink node has no incoming PipeWire links")
            failures+=1
    return "\n".join(report),failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a",default="41:42:63:27:E7:3A")
    parser.add_argument("--b",default="B0:F0:0C:63:83:F5")
    parser.add_argument("--user",default="medvetalkie")
    parser.add_argument("--direction",choices=("a-to-b","b-to-a","both"),
                        default="a-to-b")
    parser.add_argument("--seconds",type=int,default=15)
    parser.add_argument("--latency-ms",type=int,default=40)
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--diagnose",action="store_true", help="inspect actual native PipeWire node and link graph during playback")
    args = parser.parse_args()
    if not 5 <= args.seconds <= 60:
        parser.error("seconds must be 5..60")
    if not 10 <= args.latency_ms <= 200:
        parser.error("latency-ms must be 10..200")
    owned = []
    try:
        plan = INTERCOM.validate(args.a,args.b,args.user)
        targets = routes(plan,args.direction)
        for label,source,sink in targets:
            print(label+": "+source+" -> "+sink,flush=True)
        print("Native PipeWire: mono, %d ms target; no gate or attenuation" %
              args.latency_ms,flush=True)
        commands=[native_command(args.user,source,sink,args.latency_ms,label)
                  for label,source,sink in targets]
        if args.dry_run:
            for command in commands:
                print("DRY RUN:", " ".join(command),flush=True)
            print("DRY RUN: no PipeWire stream started",flush=True)
            return 0
        if shutil.which("pw-loopback") is None:
            raise RuntimeError("pw-loopback missing; verify pipewire-bin installed")
        for label,command in zip((item[0] for item in targets),commands):
            proc = subprocess.Popen(command,stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE,start_new_session=True)
            owned.append((label,proc))
            time.sleep(.5)
            if proc.poll() is not None:
                err=proc.stderr.read().decode(errors="replace")[:700]
                raise RuntimeError(label+" pw-loopback exited: "+err)
            print(label+" native stream process active (not proof of audio)",flush=True)
        if args.diagnose:
            time.sleep(1)
            print("=== Native PipeWire node/link diagnosis ===",flush=True)
            diagnostic,missing=inspect_live_graph(args.user,targets)
            print(diagnostic,flush=True)
            print("=== End graph diagnosis (%d issue(s)) ===" % missing,flush=True)
        print("Listen for live speech; Ctrl+C to stop. No AEC/gate in this experiment.",
              flush=True)
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            time.sleep(min(.5,max(.01,deadline-time.monotonic())))
            for label,proc in owned:
                if proc.poll() is not None:
                    err=proc.stderr.read().decode(errors="replace")[:700]
                    raise RuntimeError(label+" unexpectedly exited: "+err)
        print("Native trial completed; compare audibility/delay with Python relay.",flush=True)
        return 0
    except KeyboardInterrupt:
        print("Interrupted by operator.",file=sys.stderr)
        return 130
    except (OSError,ValueError,RuntimeError,INTERCOM.BridgeError,KeyError) as exc:
        print("NOT READY: "+str(exc),file=sys.stderr)
        return 2
    finally:
        for label,proc in reversed(owned):
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL)
                proc.wait(timeout=3)
            print("Stopped owned native stream "+label,flush=True)


if __name__=="__main__":
    sys.exit(main())
