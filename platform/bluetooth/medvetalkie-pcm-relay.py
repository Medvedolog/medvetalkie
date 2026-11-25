#!/usr/bin/env python3
"""Experimental bounded PCM relay, AIRIDE <-> UGREEN, without module-loopback.

Copies s16le/mono/16kHz PCM in 20ms frames. Tracks actual read/write bytes,
RMS, clipping and bounded audio queue overruns. Does not change BlueZ/PipeWire
profiles, pairings, gains, default routes, or long-lived system services.
"""
import argparse
from array import array
import importlib.util
import os
from pathlib import Path
import pwd
import queue
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("mt_intercom", ROOT / "medvetalkie-intercom-test.py")
MT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MT)

RATE = 16000
CHANNELS = 1
SAMPLE_BYTES = 2
FRAME_MS = 20
FRAME_BYTES = RATE * CHANNELS * SAMPLE_BYTES * FRAME_MS // 1000  # 640 bytes
QUEUE_FRAMES = 15  # 300ms upper bound, drop oldest instead of growing indefinitely


def pulse_args(user, program, endpoint, latency_ms=80):
    if not 40 <= latency_ms <= 500:
        raise ValueError("Latency must be 40..500 ms")
    kind = "source" if program == "parecord" else "sink"
    if program not in ("parecord", "paplay"):
        raise ValueError("Unexpected PCM program")
    return MT.audio_cli(
        user, program, "--raw", "--rate=%d" % RATE,
        "--channels=1", "--format=s16le", "--device="+endpoint,
        "--latency-msec=%d" % latency_ms,
        "--process-time-msec=%d" % FRAME_MS)


class Stats:
    def __init__(self):
        self.received = 0
        self.forwarded = 0
        self.dropped = 0
        self.peak = 0
        self.squares = 0
        self.samples = 0
        self.clipped = 0
        self.first_pcm = None
        self.first_playback = None
        self.pending_frames = 0
        self.errors = []

    def capture(self, data, now):
        if self.first_pcm is None:
            self.first_pcm = now
        self.received += len(data)
        even = data[:len(data) & ~1]
        vals = array("h")
        vals.frombytes(even)
        if sys.byteorder != "little":
            vals.byteswap()
        for value in vals:
            level = abs(value)
            self.peak = max(self.peak, level)
            self.squares += value * value
            self.clipped += int(level >= 32760)
        self.samples += len(vals)

    def write(self, size, now):
        if size and self.first_playback is None:
            self.first_playback = now
        self.forwarded += size

    def report(self, seconds):
        import math
        rms = math.sqrt(self.squares/self.samples) if self.samples else 0
        db = lambda v: round(20*math.log10(max(v/32768,1e-9)), 1)
        return {
            "received_bytes": self.received,
            "forwarded_bytes": self.forwarded,
            "dropped_bytes": self.dropped,
            "rms_dbfs": db(rms),
            "peak_dbfs": db(self.peak),
            "clipped_samples": self.clipped,
            "capture_kib_s": round(self.received/max(.001,seconds)/1024,1),
            "playback_kib_s": round(self.forwarded/max(.001,seconds)/1024,1),
            "startup_ms": (round((self.first_playback-self.first_pcm)*1000)
                           if self.first_playback is not None and self.first_pcm is not None else None),
            "errors": list(self.errors)
        }


class Route:
    def __init__(self, label, user, source, sink, latency):
        self.label=label
        self.user=user
        self.source=source
        self.sink=sink
        self.latency=latency
        self.queue=queue.Queue(maxsize=QUEUE_FRAMES)
        self.stats=Stats()
        self.stop=threading.Event()
        self.processes=[]
        self.threads=[]

    def begin(self):
        # Prohibit shell involvement; exact selected Pulse nodes only.
        source_cmd=pulse_args(self.user,"parecord",self.source,self.latency)
        sink_cmd=pulse_args(self.user,"paplay",self.sink,self.latency)
        try:
            capture=subprocess.Popen(source_cmd,stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,bufsize=0)
            self.processes.append(capture)
            playback=subprocess.Popen(sink_cmd,stdin=subprocess.PIPE,
                                      stderr=subprocess.PIPE,bufsize=0)
            self.processes.append(playback)
            for fn in (self.read_pcm, self.write_pcm):
                thread=threading.Thread(target=fn,daemon=True)
                self.threads.append(thread)
                thread.start()
        except Exception:
            self.close()
            raise

    def read_pcm(self):
        proc=self.processes[0]
        pending=bytearray()
        try:
            while not self.stop.is_set():
                data=os.read(proc.stdout.fileno(),FRAME_BYTES*2)
                if not data:
                    self.stats.errors.append("parecord EOF")
                    break
                self.stats.capture(data,time.monotonic())
                pending.extend(data)
                while len(pending)>=FRAME_BYTES:
                    frame=bytes(pending[:FRAME_BYTES])
                    del pending[:FRAME_BYTES]
                    try:
                        self.queue.put_nowait(frame)
                    except queue.Full:
                        try:
                            old=self.queue.get_nowait()
                            self.stats.dropped+=len(old)
                        except queue.Empty:
                            pass
                        try:self.queue.put_nowait(frame)
                        except queue.Full:self.stats.dropped+=len(frame)
        except OSError as exc:
            if not self.stop.is_set():self.stats.errors.append("read: "+str(exc))

    def write_pcm(self):
        proc=self.processes[1]
        try:
            while not self.stop.is_set():
                try: frame=self.queue.get(timeout=.2)
                except queue.Empty:continue
                view=memoryview(frame)
                while view and not self.stop.is_set():
                    n=os.write(proc.stdin.fileno(),view)
                    if n<=0:raise BrokenPipeError("paplay consumed zero bytes")
                    view=view[n:]
                    self.stats.write(n,time.monotonic())
        except OSError as exc:
            if not self.stop.is_set():self.stats.errors.append("write: "+str(exc))

    def close(self):
        self.stop.set()
        # Closing/terminating clients unblocks worker threads. Do not kill others.
        for p in self.processes:
            if p.poll() is None:p.terminate()
        for p in self.processes:
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=2)
        for thread in self.threads:thread.join(timeout=2)
        for p in self.processes:
            if p.returncode not in (None,0,-15,-9) and p.stderr:
                try:
                    msg=p.stderr.read(600).decode(errors="replace").strip()
                    if msg:self.stats.errors.append(msg)
                except OSError:pass


def choose_routes(plan, direction):
    return [
        ("AIRIDE->UGREEN",plan["A"]["source"],plan["B"]["sink"])
        for _ in [0] if direction in ("a-to-b","both")
    ]+[
        ("UGREEN->AIRIDE",plan["B"]["source"],plan["A"]["sink"])
        for _ in [0] if direction in ("b-to-a","both")
    ]


def execute(plan, direction, user, seconds, latency):
    if direction not in ("a-to-b","b-to-a","both"):
        raise ValueError("Invalid direction")
    if not 5 <= seconds <= 60:
        raise ValueError("Duration must be 5..60s")
    routes=[Route(name,user,source,sink,latency)
            for name,source,sink in choose_routes(plan,direction)]
    started=time.monotonic()
    try:
        for route in routes:
            print("%s: %s -> %s"%(route.label,route.source,route.sink),flush=True)
            route.begin()
        end=started+seconds
        while time.monotonic()<end:
            time.sleep(min(1.0,max(.01,end-time.monotonic())))
            elapsed=time.monotonic()-started
            for route in routes:
                stats=route.stats.report(elapsed)
                print("%s %.1fs read=%.1f KiB/s write=%.1f KiB/s queue=%d/15 drop=%dB RMS=%s dBFS peak=%s dBFS"%
                    (route.label,elapsed,stats["capture_kib_s"],stats["playback_kib_s"],
                     route.queue.qsize(),stats["dropped_bytes"],
                     stats["rms_dbfs"],stats["peak_dbfs"]),flush=True)
                if any(p.poll() is not None for p in route.processes):
                    raise RuntimeError("%s: an audio client exited early" % route.label)
    finally:
        for route in routes:route.close()
        elapsed=time.monotonic()-started
        for route in routes:
            print("FINAL %s: %s"%(route.label,route.stats.report(elapsed)),flush=True)
    return routes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a",default="41:42:63:27:E7:3A")
    parser.add_argument("--b",default="B0:F0:0C:63:83:F5")
    parser.add_argument("--user",default="medvetalkie")
    parser.add_argument("--direction",choices=("a-to-b","b-to-a","both"),default="a-to-b")
    parser.add_argument("--seconds",type=int,default=12)
    parser.add_argument("--latency-ms",type=int,default=80)
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    try:
        plan=MT.validate(args.a,args.b,args.user)
        routes=choose_routes(plan,args.direction)
        print("16 kHz s16le mono, 20ms frames, 300ms bounded queue; latency target %dms"%args.latency_ms)
        for name,source,sink in routes:print(name,source,"->",sink)
        if args.dry_run:
            print("DRY RUN: no audio streams started")
            return
        execute(plan,args.direction,args.user,args.seconds,args.latency_ms)
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        parser.exit(2,"FAILED: "+str(exc)+"\n")
    except KeyboardInterrupt:
        print("Interrupted; owned audio clients stopped.",file=sys.stderr)


if __name__=="__main__":
    main()
