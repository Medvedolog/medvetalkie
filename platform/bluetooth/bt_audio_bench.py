#!/usr/bin/env python3
"""Bounded HFP voice bench: simultaneous PipeWire input/output plus optional btmon.

Explicit operator invocation only. No bond removal, profile switching, or
routing changes. Stdlib + parecord, paplay, pactl, optional btmon.
"""
import argparse
import math
import os
import pwd
import shutil
import signal
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path


def audio_command(user, program, *args):
    uid = pwd.getpwnam(user).pw_uid
    runtime = "/run/user/%d" % uid
    if os.geteuid() == 0:
        return ["runuser", "-u", user, "--", "env",
                "XDG_RUNTIME_DIR=" + runtime,
                "PULSE_SERVER=unix:" + runtime + "/pulse/native",
                program, *args]
    if os.geteuid() != uid:
        raise RuntimeError("Запустите через sudo либо от пользователя %s" % user)
    return [program, *args]


def capture_output(argv, timeout=8):
    p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout,
                       errors="replace", check=False)
    if p.returncode:
        raise RuntimeError("%s (exit %s): %s" % (
            argv[-1], p.returncode, (p.stderr or p.stdout).strip()[:400]))
    return p.stdout


def find_audio_devices(mac, user, runner=capture_output):
    if not isinstance(mac, str) or len(mac.split(":")) != 6 or any(
            len(x) != 2 or any(ch not in "0123456789abcdefABCDEF" for ch in x)
            for x in mac.split(":")):
        raise ValueError("Invalid Bluetooth MAC")
    outputs = runner(audio_command(user, "pactl", "list", "short", "sinks"))
    inputs = runner(audio_command(user, "pactl", "list", "short", "sources"))
    slug = mac.upper().replace(":", "_")
    sinks = [line.split()[1] for line in outputs.splitlines()
             if len(line.split()) >= 2 and line.split()[1].startswith("bluez_output."+slug+".")]
    sources = [line.split()[1] for line in inputs.splitlines()
               if len(line.split()) >= 2 and line.split()[1].lower().startswith(
                   "bluez_input."+mac.lower())]
    if len(sinks) != 1 or len(sources) != 1:
        raise RuntimeError("Expected one HFP sink+source for %s, found sinks=%s sources=%s. "
                           "Connect headset and select an HFP card profile first." %
                           (mac, sinks, sources))
    cards = runner(audio_command(user, "pactl", "list", "cards"))
    name = "bluez_card." + slug
    section = next((x for x in cards.split("Card #") if "Name: "+name in x), "")
    active = next((x.strip().split("Active Profile:", 1)[1].strip()
                   for x in section.splitlines() if "Active Profile:" in x), "")
    if not active.startswith("headset-head-unit"):
        raise RuntimeError("Active profile is '%s' (HFP required)." % active)
    return sinks[0], sources[0], active


def tone(path, duration, rate=16000):
    """Conservative short pips for output reference; never generate loud audio."""
    n = int(duration * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        data = bytearray()
        for i in range(n):
            t = i / rate
            pos = t % 1
            # 120 ms sine pip per second with 10 ms fade at both edges.
            envelope = (min(1, pos / .01, (.12-pos) / .01) if pos < .12 else 0)
            sample = int(2600 * max(0, envelope) * math.sin(2*math.pi*440*t))
            data.extend(struct.pack("<h", sample))
        w.writeframes(data)


def measure(path, window=.5):
    with wave.open(str(path), "rb") as w:
        nch, sw, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if nch != 1 or sw != 2:
            raise RuntimeError("Expected mono 16-bit PCM capture; got %sch/%sB" % (nch,sw))
        data = w.readframes(frames)
    samples = struct.unpack("<%dh" % (len(data)//2), data) if data else ()
    if not samples:
        raise RuntimeError("No PCM captured")
    peak = max(abs(i) for i in samples)
    rms = math.sqrt(sum(x*x for x in samples)/len(samples))
    # Relative peak/RMS are measurement observations, not a speech/duplex proof.
    db = lambda value: 20*math.log10(max(1e-9, value/32768))
    clipping = sum(abs(x) >= 32760 for x in samples)
    size = max(1, int(rate*window))
    windows = []
    for start in range(0, len(samples), size):
        part = samples[start:start+size]
        if not part:
            continue
        wrms = math.sqrt(sum(x*x for x in part)/len(part))
        windows.append(round(db(wrms), 1))
    return {"seconds": round(len(samples)/rate, 2), "rate": rate,
            "peak_dbfs": round(db(peak), 1), "rms_dbfs": round(db(rms), 1),
            "clipped": clipping, "windows_dbfs": windows}


def terminate(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def execute(mac, user="medvetalkie", seconds=10, monitor=False, outdir=None):
    if not (3 <= seconds <= 30):
        raise ValueError("Duration must be 3..30 seconds")
    sink, source, profile = find_audio_devices(mac, user)
    if not shutil.which("parecord") or not shutil.which("paplay"):
        raise RuntimeError("Install pulseaudio-utils (parecord and paplay)")
    if monitor and (os.geteuid() != 0 or not shutil.which("btmon")):
        raise RuntimeError("btmon requires root and installed bluez tools")
    directory = Path(outdir or tempfile.mkdtemp(prefix="medvetalkie-bt-"))
    directory.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        uid = pwd.getpwnam(user).pw_uid
        gid = pwd.getpwnam(user).pw_gid
        if not outdir:
            os.chown(directory, uid, gid)
            os.chmod(directory, 0o700)
        elif directory.stat().st_uid != uid:
            raise RuntimeError("For root execution, --outdir must be owned by audio user")
    # Avoid overwriting an earlier test on purpose.
    capture = directory / "headset-capture.wav"
    playback = directory / "test-pips.wav"
    if capture.exists() or playback.exists():
        raise FileExistsError("Existing bench files in %s" % directory)
    tone(playback, seconds)
    os.chmod(playback, 0o644)
    monitor_file = directory / "hci.btsnoop"
    mon = rec = play = None
    started = time.monotonic()
    playback_ok = False
    try:
        if monitor:
            # Runs only for this explicit test, with an isolated output file.
            mon = subprocess.Popen(["btmon", "-w", str(monitor_file)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(.3)
            if mon.poll() is not None:
                raise RuntimeError("btmon exited before audio capture")
        rec = subprocess.Popen(audio_command(user, "parecord",
            "--device="+source, "--file-format=wav", "--rate=16000",
            "--channels=1", "--format=s16le", str(capture)),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(.4)
        if rec.poll() is not None:
            raise RuntimeError("parecord failed: %s" % rec.stderr.read().decode(errors="replace")[:350])
        play = subprocess.Popen(audio_command(user, "paplay", "--device="+sink,
                                  str(playback)),
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            _, stderr = play.communicate(timeout=seconds+5)
        except subprocess.TimeoutExpired:
            raise RuntimeError("paplay timeout")
        if play.returncode:
            raise RuntimeError("paplay exit %d: %s" % (play.returncode,
                                stderr.decode(errors="replace")[:350]))
        playback_ok = True
    finally:
        terminate(rec)
        terminate(play)
        terminate(mon)
    # Recording is stopped after playback ends; inspect captured speech with headphones.
    metrics = measure(capture)
    result = {"profile": profile, "sink": sink, "source": source,
              "recording": str(capture), "tone_file": str(playback),
              "playback_ok": playback_ok, "metrics": metrics,
              "elapsed": round(time.monotonic()-started, 2)}
    if monitor:
        result["btmon"] = str(monitor_file)
        # This counts evidence in a text decode; no claim if unavailable.
        try:
            decoded = capture_output(["btmon", "-r", str(monitor_file)], timeout=10)
            result["hci_synchronous_mentions"] = len([
                line for line in decoded.splitlines()
                if "Synchronous Connection" in line or "SCO Data" in line or "ISO Data" in line
            ])
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            result["btmon_decode_error"] = str(exc)
    return result


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mac", required=True, help="paired, connected headset Bluetooth address")
    p.add_argument("--user", default="medvetalkie")
    p.add_argument("--seconds", type=int, default=10)
    p.add_argument("--btmon", action="store_true", help="capture HCI trace (root)")
    p.add_argument("--outdir", help="new output folder; default unique /tmp folder")
    args = p.parse_args()
    try:
        result = execute(args.mac, args.user, args.seconds, args.btmon, args.outdir)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        p.exit(1, "Ошибка: %s\n" % exc)
    print("Profile:", result["profile"])
    print("Playback:", "completed" if result["playback_ok"] else "not verified")
    print("Microphone:", result["recording"])
    print("SCO monitor:", result.get("btmon", "not requested"))
    print("Peak/RMS dBFS:", result["metrics"]["peak_dbfs"],
          result["metrics"]["rms_dbfs"])
    print("Clipped PCM samples:", result["metrics"]["clipped"])
    print("500ms RMS dBFS:", result["metrics"]["windows_dbfs"])
    print("Note: inspect recording and synchronized HCI trace for actual duplex;" 
          " parallel audio clients alone do not prove continuous SCO.")


if __name__ == "__main__":
    cli()
