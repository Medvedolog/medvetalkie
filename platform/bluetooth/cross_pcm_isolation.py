#!/usr/bin/env python3
"""Isolate HFP source PCM and remote sink during simultaneous activity.

Records A microphone while playing a quiet test tone to B headphones.
Read-only device discovery, no profile/volume changes. Output WAV and metrics.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bt_audio_bench", HERE / "bt_audio_bench.py")
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)

A = "41:42:63:27:E7:3A"
B = "B0:F0:0C:63:83:F5"


def one_device(mac, user):
    sink, source, profile = audio.find_audio_devices(mac, user)
    return sink, source, profile


def test(user="medvetalkie", seconds=8, monitor=False):
    if seconds < 4 or seconds > 20:
        raise ValueError("seconds must be 4..20")
    _, source_a, profile_a = one_device(A, user)
    sink_b, _, profile_b = one_device(B, user)
    if monitor and os.geteuid() != 0:
        raise RuntimeError("btmon needs root")
    folder = Path(tempfile.mkdtemp(prefix="medvetalkie-cross-pcm-"))
    account = __import__("pwd").getpwnam(user)
    if os.geteuid() == 0:
        os.chown(folder, account.pw_uid, account.pw_gid)
        os.chmod(folder, 0o700)
    wav = folder / "airide-during-ugreen-playback.wav"
    reference = folder / "quiet-reference.wav"
    audio.tone(reference, seconds - 1)
    os.chmod(reference, 0o644)
    trace = folder / "bluetooth.btsnoop"
    recorder = player = btmon = None
    playback_ok = False
    try:
        if monitor:
            btmon = subprocess.Popen(["btmon", "-w", str(trace)], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
            time.sleep(.3)
            if btmon.poll() is not None:
                raise RuntimeError("btmon failed to start")
        recorder = subprocess.Popen(audio.audio_command(user, "parecord",
            "--device="+source_a, "--file-format=wav", "--channels=1",
            "--rate=16000", "--format=s16le", str(wav)),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(.5)
        if recorder.poll() is not None:
            raise RuntimeError("parecord failed: "+recorder.stderr.read().decode(errors="replace")[:500])
        player = subprocess.Popen(audio.audio_command(user,"paplay",
            "--device="+sink_b, str(reference)), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print("SAY WORDS INTO AIRIDE NOW: UGREEN should hear quiet short pips.",flush=True)
        try:
            _, error = player.communicate(timeout=seconds+5)
        except subprocess.TimeoutExpired:
            raise RuntimeError("UGREEN playback timed out")
        if player.returncode:
            raise RuntimeError("UGREEN paplay exit %s: %s" %
                               (player.returncode,error.decode(errors="replace")[:400]))
        playback_ok = True
    finally:
        for process in (player, recorder, btmon):
            audio.terminate(process)
    metrics = audio.measure(wav)
    print("AIRIDE profile:",profile_a)
    print("UGREEN profile:",profile_b)
    print("PCM capture:",wav)
    print("Test tone played to UGREEN:",playback_ok)
    print("Capture duration: %.2f s, peak %.1f dBFS, RMS %.1f dBFS, clipped %d" % (
        metrics["seconds"],metrics["peak_dbfs"],metrics["rms_dbfs"],metrics["clipped"]))
    print("Half-second RMS:",metrics["windows_dbfs"])
    if monitor:
        print("Raw btmon:",trace)
    print("Note: nonzero PCM does not prove real-time cross-headset routing.")
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds",type=int,default=8)
    parser.add_argument("--user",default="medvetalkie")
    parser.add_argument("--btmon",action="store_true")
    args = parser.parse_args()
    try:
        test(args.user,args.seconds,args.btmon)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1,"FAILED: "+str(error)+"\n")


if __name__ == "__main__":
    main()
