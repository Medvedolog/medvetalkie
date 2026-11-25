#!/usr/bin/env python3
"""MedveTalkie: explicitly initiated, bounded two-headset HFP bridge.

Dry-run and status never mutate Bluetooth or PipeWire. The live bridge only
loads two PipeWire Pulse module-loopback instances and unloads those exact IDs
on exit, even on SIGINT/SIGTERM. No BlueZ pairing/profile changes.
"""
import argparse
import os
import pwd
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
CONTROLLER_RE = re.compile(r"^Controller\s+((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})", re.M)
DEVICE_RE = re.compile(r"^Device\s+((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\b", re.M)
ID_RE = re.compile(r"^\s*(\d+)\s*$")


class BridgeError(RuntimeError):
    pass


def normalize_mac(value):
    if not MAC_RE.fullmatch(value):
        raise BridgeError("Invalid Bluetooth MAC address: %r" % value)
    return value.upper()


def run(argv, timeout=12):
    try:
        process = subprocess.run(argv, capture_output=True, text=True,
                                 errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BridgeError("Command error: %s: %s" % (argv[0], exc)) from exc
    if process.returncode:
        raise BridgeError("%s: %s" % (argv[0],
                (process.stderr or process.stdout).strip()[:500]))
    return process.stdout.strip()


def audio_cli(user, *args):
    account = pwd.getpwnam(user)
    runtime = "/run/user/%d" % account.pw_uid
    env = ["XDG_RUNTIME_DIR="+runtime,
           "PULSE_SERVER=unix:"+runtime+"/pulse/native"]
    if os.geteuid() == 0:
        return ["runuser", "-u", user, "--", "env", *env, *args]
    if os.geteuid() != account.pw_uid:
        raise BridgeError("Run as root or the configured audio user %s" % user)
    return ["env", *env, *args]


def controller_inventory(mac_a, mac_b, executor=run):
    """Read BlueZ system D-Bus state; never scrape asynchronous bluetoothctl prompts.

    The BlueZ object tree is a snapshot. Device1.Connected and Adapter1.Address
    identify the active BR/EDR link and its actual controller. No state changes.
    """
    tree = executor(["busctl", "--system", "tree", "org.bluez"])
    adapter_paths = sorted(set(re.findall(r"/org/bluez/(hci[0-9]+)(?:/|\\b)", tree)))
    device_paths = set(re.findall(
        r"/org/bluez/hci[0-9]+/dev_(?:[0-9A-Fa-f]{2}_){5}[0-9A-Fa-f]{2}", tree))
    if len(adapter_paths) < 2:
        raise BridgeError("Need two BlueZ controllers; D-Bus tree has %d" % len(adapter_paths))
    memberships = {}
    for adapter in adapter_paths:
        adapter_path = "/org/bluez/" + adapter
        address = executor(["busctl", "--system", "get-property", "org.bluez",
                            adapter_path, "org.bluez.Adapter1", "Address"])
        match = re.fullmatch(r's\\s+"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})"', address.strip())
        if not match:
            raise BridgeError("Unexpected adapter address property for %s: %s" %
                              (adapter, address[:120]))
        controller_mac = match.group(1).upper()
        for device_mac in (mac_a, mac_b):
            object_path = adapter_path + "/dev_" + device_mac.replace(":", "_")
            if object_path not in device_paths:
                continue
            connected = executor(["busctl", "--system", "get-property", "org.bluez",
                                  object_path, "org.bluez.Device1", "Connected"]).strip()
            if connected not in ("b true", "b false"):
                raise BridgeError("Invalid Connected property for %s: %s" %
                                  (device_mac, connected[:120]))
            if connected == "b true":
                memberships.setdefault(device_mac, set()).add(controller_mac)
    return memberships


def assign_controllers(mac_a, mac_b, memberships):
    a = memberships.get(mac_a, set())
    b = memberships.get(mac_b, set())
    if len(a) != 1 or len(b) != 1:
        raise BridgeError("Both devices must be connected to exactly one known controller "
                          "(A=%s, B=%s)" % (sorted(a), sorted(b)))
    ca, cb = next(iter(a)), next(iter(b))
    if ca == cb:
        raise BridgeError("Both headsets share one controller %s; use separate adapters" % ca)
    return ca, cb


def card_profile(cards, mac):
    name = "bluez_card."+mac.replace(":", "_")
    for section in re.split(r"(?=^Card #\d+)", cards, flags=re.M):
        if re.search(r"^\s*Name:\s*"+re.escape(name)+r"\s*$", section, re.M):
            match = re.search(r"^\s*Active Profile:\s*(\S+)", section, re.M)
            return match.group(1) if match else None
    return None


def device_names(table, prefix, mac):
    stem = prefix + "." + mac.replace(":", "_") if prefix == "bluez_output" else prefix + "." + mac
    return [parts[1] for line in table.splitlines()
            if len(parts := line.split()) > 1 and parts[1].lower().startswith(stem.lower())
            and not parts[1].endswith(".monitor")]


def resolve_audio(mac_a, mac_b, user, executor=run):
    cards = executor(audio_cli(user, "pactl", "list", "cards"))
    sinks = executor(audio_cli(user, "pactl", "list", "short", "sinks"))
    sources = executor(audio_cli(user, "pactl", "list", "short", "sources"))
    paths = {}
    for mac in (mac_a, mac_b):
        profile = card_profile(cards, mac)
        if profile not in ("headset-head-unit", "headset-head-unit-cvsd"):
            raise BridgeError("%s active profile %s is not an HFP voice profile" % (mac, profile))
        sink_names = device_names(sinks, "bluez_output", mac)
        source_names = device_names(sources, "bluez_input", mac)
        if len(sink_names) != 1 or len(source_names) != 1:
            raise BridgeError("%s needs exactly one HFP output and input; got sinks=%s sources=%s"
                              % (mac, sink_names, source_names))
        paths[mac] = {"profile": profile, "sink": sink_names[0],
                      "source": source_names[0]}
    return paths


def validate(mac_a, mac_b, user, executor=run):
    mac_a, mac_b = normalize_mac(mac_a), normalize_mac(mac_b)
    if mac_a == mac_b:
        raise BridgeError("Specify two distinct headsets")
    locations = controller_inventory(mac_a, mac_b, executor)
    adapter_a, adapter_b = assign_controllers(mac_a, mac_b, locations)
    paths = resolve_audio(mac_a, mac_b, user, executor)
    return {"A": {**paths[mac_a], "mac": mac_a, "adapter": adapter_a},
            "B": {**paths[mac_b], "mac": mac_b, "adapter": adapter_b}}


def parse_module_id(text):
    match = ID_RE.fullmatch(text)
    if not match:
        raise BridgeError("Unexpected pactl load-module reply: %r" % text[:200])
    return int(match.group(1))


def loopback_args(source, sink, latency):
    if not (40 <= latency <= 500):
        raise BridgeError("Latency must be between 40 and 500 ms")
    return ["pactl", "load-module", "module-loopback",
            "source="+source, "sink="+sink, "latency_msec="+str(latency),
            "source_dont_move=true", "sink_dont_move=true"]


def print_plan(plan, latency):
    a, b = plan["A"], plan["B"]
    print("A %s [%s] %s" % (a["mac"], a["adapter"], a["profile"]))
    print("  input  %s" % a["source"])
    print("  output %s" % a["sink"])
    print("B %s [%s] %s" % (b["mac"], b["adapter"], b["profile"]))
    print("  input  %s" % b["source"])
    print("  output %s" % b["sink"])
    print("A microphone -> B speaker; B microphone -> A speaker")
    print("Target loopback latency: %d ms (not a measured RTT)" % latency)


def bridge(plan, user, seconds, latency, executor=run, sleep=time.sleep):
    if not (5 <= seconds <= 300):
        raise BridgeError("Duration must be 5..300 seconds")
    a, b = plan["A"], plan["B"]
    loaded = []
    try:
        for source, sink in ((a["source"], b["sink"]), (b["source"], a["sink"])):
            args = audio_cli(user, *loopback_args(source, sink, latency))
            module_id = parse_module_id(executor(args))
            # Register ownership immediately. Only these IDs are ever unloaded.
            loaded.append(module_id)
            print("Active loopback module %d: %s -> %s" % (module_id, source, sink),
                  flush=True)
        print("Two-way bridge active for %d seconds. Ctrl+C to stop." % seconds,
              flush=True)
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            sleep(min(.5, deadline-time.monotonic()))
    finally:
        cleanup_failures = []
        for module_id in reversed(loaded):
            try:
                executor(audio_cli(user, "pactl", "unload-module", str(module_id)))
                print("Unloaded module %d" % module_id, flush=True)
            except Exception as exc:
                cleanup_failures.append("%s: %s" % (module_id, exc))
        if cleanup_failures:
            print("CLEANUP WARNING (manual unload may be required): "+
                  "; ".join(cleanup_failures), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", required=True, help="first headset MAC")
    parser.add_argument("--b", required=True, help="second headset MAC")
    parser.add_argument("--user", default="medvetalkie")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--latency-ms", type=int, default=80)
    parser.add_argument("--dry-run", action="store_true",
                        help="validate both headsets and show routes without audio changes")
    args = parser.parse_args()
    try:
        if not (40 <= args.latency_ms <= 500):
            raise BridgeError("Latency must be between 40 and 500 ms")
        if not (5 <= args.seconds <= 300):
            raise BridgeError("Duration must be 5..300 seconds")
        plan = validate(args.a, args.b, args.user)
        print_plan(plan, args.latency_ms)
        if args.dry_run:
            print("DRY RUN: no PipeWire modules were changed.")
            return 0
        print("LIVE TEST: microphones are routed crosswise. Ensure both headsets are worn.")
        previous = signal.getsignal(signal.SIGTERM)
        def on_term(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, on_term)
        try:
            bridge(plan, args.user, args.seconds, args.latency_ms)
        finally:
            signal.signal(signal.SIGTERM, previous)
        print("Bridge stopped; test routes removed.")
        return 0
    except (BridgeError, KeyError) as exc:
        print("NOT READY: "+str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted; cleanup handled.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
