#!/usr/bin/env python3
"""Experimental bounded PCM relay, AIRIDE <-> UGREEN, without module-loopback.

Copies s16le/mono/16kHz PCM in 20ms frames. Tracks actual read/write bytes,
RMS, clipping and bounded audio queue overruns. Does not change BlueZ/PipeWire
profiles, pairings, gains, default routes, or long-lived system services.
"""
import argparse
import math
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
QUEUE_FRAMES = 15  # configurable 2..15 frames
MAX_SECONDS = 600

def frame_level_dbfs(frame):
    samples = array("h")
    samples.frombytes(frame)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return -180.0
    return 10*math.log10(max(sum(i*i for i in samples)/len(samples)/(32768.0**2), 1e-18))

class NoiseGate:
    """Optional speech-level expander, NOT acoustic echo cancellation."""
    def __init__(self, threshold, floor=0.15, hang_frames=15):
        if not math.isfinite(threshold) or not -70 <= threshold <= -20:
            raise ValueError("Gate threshold invalid")
        if not math.isfinite(floor) or not 0 <= floor <= 1:
            raise ValueError("Gate floor invalid")
        if not 0 <= hang_frames <= 100:
            raise ValueError("Gate hang invalid")
        self.threshold, self.floor, self.hang_frames = threshold, floor, hang_frames
        self.remaining = self.open_frames = self.closed_frames = 0
    def process(self, frame):
        if frame_level_dbfs(frame) >= self.threshold:
            self.remaining = self.hang_frames
            self.open_frames += 1
            return frame
        if self.remaining:
            self.remaining -= 1
            self.open_frames += 1
            return frame
        self.closed_frames += 1
        return scale_pcm(frame,self.floor) if self.floor else bytes(len(frame))



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



def scale_pcm(frame, gain):
    """Attenuate little-endian signed 16-bit PCM without modifying user audio settings."""
    if not math.isfinite(gain) or not 0 <= gain <= 1.0:
        raise ValueError("PCM gain must be 0..1.0")
    if gain == 1.0:
        return frame
    samples=array("h")
    samples.frombytes(frame)
    if sys.byteorder != "little":
        samples.byteswap()
    for i, sample in enumerate(samples):
        samples[i]=max(-32768,min(32767,round(sample*gain)))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()

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
        self.max_capture_gap_ms = 0.0
        self.last_capture_at = None
        self.queue_high_water = 0
        self.gate_open_frames = 0
        self.gate_closed_frames = 0

    def capture(self, data, now):
        if self.first_pcm is None:
            self.first_pcm = now
        if self.last_capture_at is not None:
            self.max_capture_gap_ms = max(self.max_capture_gap_ms, (now - self.last_capture_at)*1000)
        self.last_capture_at = now
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
            "max_capture_gap_ms": round(self.max_capture_gap_ms,1),
            "queue_high_water": self.queue_high_water,
            "gate_open_frames": self.gate_open_frames,
            "gate_closed_frames": self.gate_closed_frames,
            "errors": list(self.errors)
        }


class Route:
    def __init__(self, label, user, source, sink, latency, queue_frames=QUEUE_FRAMES, gain=1.0,
                 gate_dbfs=None, gate_floor=0.15, gate_hang_ms=300):
        self.label=label
        self.user=user
        self.source=source
        self.sink=sink
        self.latency=latency
        if not 2 <= queue_frames <= 15:
            raise ValueError('Queue depth must be 2..15')
        if not math.isfinite(gain) or not 0.25 <= gain <= 1.0:
            raise ValueError('Gain must be 0.25..1.0')
        self.gain=gain
        if not 0 <= gate_hang_ms <= 2000 or gate_hang_ms % FRAME_MS:
            raise ValueError("Gate hang must be 20ms aligned and <=2000ms")
        self.gate=(NoiseGate(gate_dbfs,gate_floor,gate_hang_ms//FRAME_MS)
                   if gate_dbfs is not None else None)
        self.queue=queue.Queue(maxsize=queue_frames)
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
                    if not self.stop.is_set():
                        self.stats.errors.append("parecord EOF before shutdown")
                    break
                self.stats.capture(data,time.monotonic())
                pending.extend(data)
                while len(pending)>=FRAME_BYTES:
                    frame=bytes(pending[:FRAME_BYTES])
                    if self.gate is not None:
                        frame=self.gate.process(frame)
                        self.stats.gate_open_frames=self.gate.open_frames
                        self.stats.gate_closed_frames=self.gate.closed_frames
                    frame=scale_pcm(frame,self.gain)
                    del pending[:FRAME_BYTES]
                    try:
                        self.queue.put_nowait(frame)
                        self.stats.queue_high_water=max(self.stats.queue_high_water,self.queue.qsize())
                    except queue.Full:
                        try:
                            old=self.queue.get_nowait()
                            self.stats.dropped+=len(old)
                        except queue.Empty:
                            pass
                        try:
                            self.queue.put_nowait(frame)
                            self.stats.queue_high_water=max(self.stats.queue_high_water,self.queue.qsize())
                        except queue.Full:
                            self.stats.dropped+=len(frame)
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


def execute(plan, direction, user, seconds, latency, queue_frames=QUEUE_FRAMES,
            gain_a_to_b=1.0, gain_b_to_a=1.0, report_interval=1,
            gate_dbfs=None, gate_floor=0.15, gate_hang_ms=300):
    if direction not in ("a-to-b","b-to-a","both"):
        raise ValueError("Invalid direction")
    if not 5 <= seconds <= MAX_SECONDS:
        raise ValueError("Duration must be 5..600s")
    if not 1 <= report_interval <= 30:
        raise ValueError("Report interval must be 1..30")
    routes=[Route(name,user,source,sink,latency,queue_frames,
                  gain_a_to_b if name=='AIRIDE->UGREEN' else gain_b_to_a,
                  gate_dbfs,gate_floor,gate_hang_ms)
            for name,source,sink in choose_routes(plan,direction)]
    started=time.monotonic()
    try:
        for route in routes:
            print("%s: %s -> %s"%(route.label,route.source,route.sink),flush=True)
            route.begin()
        end=started+seconds
        while time.monotonic()<end:
            time.sleep(min(report_interval,max(.01,end-time.monotonic())))
            elapsed=time.monotonic()-started
            for route in routes:
                stats=route.stats.report(elapsed)
                print("%s %.1fs read=%.1f KiB/s write=%.1f KiB/s queue=%d/%d drop=%dB RMS=%s dBFS peak=%s dBFS max-gap=%.0fms gate=%d/%d"%
                    (route.label,elapsed,stats["capture_kib_s"],stats["playback_kib_s"],
                     route.queue.qsize(),route.queue.maxsize,stats["dropped_bytes"],
                     stats["rms_dbfs"],stats["peak_dbfs"],stats["max_capture_gap_ms"],
                     stats["gate_open_frames"],stats["gate_closed_frames"]),flush=True)
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
    parser.add_argument("--queue-frames",type=int,default=QUEUE_FRAMES)
    parser.add_argument("--gain-a-to-b",type=float,default=1.0)
    parser.add_argument("--gain-b-to-a",type=float,default=1.0)
    parser.add_argument("--report-interval",type=int,default=1,
                        help="progress report every 1..30 seconds")
    parser.add_argument("--gate-dbfs",type=float,
                        help="opt-in speech gate -70..-20dBFS, disabled by default")
    parser.add_argument("--gate-floor",type=float,default=0.15,
                        help="quiet-frame amplitude multiplier 0..1, not AEC")
    parser.add_argument("--gate-hang-ms",type=int,default=300,
                        help="keep gate open after speech in 20ms multiples, 0..2000")
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    try:
        if not 2 <= args.queue_frames <= 15:
            raise ValueError('Queue frames must be 2..15')
        if not all(math.isfinite(v) and 0.25 <= v <= 1.0 for v in (args.gain_a_to_b,args.gain_b_to_a)):
            raise ValueError('Gains must be finite 0.25..1.0')
        if not 40 <= args.latency_ms <= 500:
            raise ValueError('Latency must be 40..500ms')
        if not 5 <= args.seconds <= MAX_SECONDS:
            raise ValueError("Seconds must be 5..600")
        if not 1 <= args.report_interval <= 30:
            raise ValueError("report-interval must be 1..30")
        if args.gate_dbfs is not None and (not math.isfinite(args.gate_dbfs)
                or not -70 <= args.gate_dbfs <= -20):
            raise ValueError("gate-dbfs must be finite and -70..-20")
        if not math.isfinite(args.gate_floor) or not 0 <= args.gate_floor <= 1:
            raise ValueError("gate-floor must be 0..1")
        if not 0 <= args.gate_hang_ms <= 2000 or args.gate_hang_ms % FRAME_MS:
            raise ValueError("gate-hang-ms must be 0..2000 and divisible by 20")
        plan=MT.validate(args.a,args.b,args.user)
        routes=choose_routes(plan,args.direction)
        print("16 kHz s16le mono, 20ms frames, %dms bounded queue; latency target %dms"%(args.queue_frames*20,args.latency_ms))
        for name,source,sink in routes:print(name,source,"->",sink)
        if args.dry_run:
            print("DRY RUN: no audio streams started")
            return
        execute(plan,args.direction,args.user,args.seconds,args.latency_ms,
                args.queue_frames,args.gain_a_to_b,args.gain_b_to_a,args.report_interval,
                args.gate_dbfs,args.gate_floor,args.gate_hang_ms)
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        parser.exit(2,"FAILED: "+str(exc)+"\n")
    except KeyboardInterrupt:
        print("Interrupted; owned audio clients stopped.",file=sys.stderr)


if __name__=="__main__":
    main()
