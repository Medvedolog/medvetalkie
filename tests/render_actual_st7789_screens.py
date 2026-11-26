#!/usr/bin/env python3
"""Render exact ST7789 C-generated framebuffer previews; no artistic redrawing."""
import base64
import gzip
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

ROOT=Path(__file__).resolve().parents[1]
SAVER=ROOT/"platform/display/screensaver"
FRAMES=("intercom","radio","game","system")

def png(rgb,width,height):
    stride=width*3
    scan=b"".join(b"\x00"+rgb[row*stride:(row+1)*stride] for row in range(height))
    def chunk(tag,data):
        return struct.pack(">I",len(data))+tag+data+struct.pack(">I",zlib.crc32(tag+data)&0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"+
            chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(scan,9))+chunk(b"IEND",b""))

def build(out):
    with tempfile.TemporaryDirectory() as d:
        temp=Path(d)
        c=temp/"renderer.c"
        subprocess.run(["python3",str(SAVER/"build-status-v2.py"),"--output",str(c)],check=True)
        binary=temp/"renderer"
        subprocess.run(["cc","-std=c11","-O2",str(c),"-lm","-o",str(binary)],check=True)
        sprite=temp/"sprite.dat"
        sprite.write_bytes(gzip.decompress(base64.b64decode((SAVER/"bjorni-sprite.gz.b64").read_bytes())))
        env=dict(os.environ,MEDVETALKIE_SPRITE=str(sprite))
        framebuf={}
        header=b"P6\n320 240\n255\n"
        for mode in FRAMES:
            status=temp/"snapshot.status"
            state="INTERCOM" if mode=="intercom" else mode.upper()
            connected=2 if mode=="intercom" else 0
            status.write_text(
                "MTSTATUS1\nmode="+state+"\nheadset1=PROFILE_PENDING\nheadset2=PROFILE_PENDING\n"
                "voice=NOT_VERIFIED\nnetwork=LAN\nradio=NOT_AVAILABLE\nbattery=UNKNOWN\n"
                "fault=NONE\nbt_usb=2\nbt_connected="+str(connected)+"\n"
                "h1_profile=HFP\nh2_profile=HFP\nh1_battery=70\nh2_battery=80\n"
                "h1_rssi=-58\nh2_rssi=-73\nh1_volume=90\nh2_volume=87\n")
            ppm=temp/(mode+".ppm")
            subprocess.run([str(binary),"--preview",str(ppm),"--status-file",str(status)],
                           check=True,env=env)
            raw=ppm.read_bytes()
            assert raw.startswith(header),(mode,raw[:35])
            rgb=raw[len(header):]
            assert len(rgb)==320*240*3,(mode,len(rgb))
            framebuf[mode]=rgb
            (out/(mode+".png")).write_bytes(png(rgb,320,240))
        width,height=640,480
        mosaic=bytearray(width*height*3)
        for n,mode in enumerate(FRAMES):
            x0=(n%2)*320
            y0=(n//2)*240
            img=framebuf[mode]
            for y in range(240):
                offset=((y0+y)*width+x0)*3
                mosaic[offset:offset+320*3]=img[y*320*3:(y+1)*320*3]
        result=png(mosaic,width,height)
        (out/"original-st7789-montage.png").write_bytes(result)
        print("ST7789_ORIGINAL_PNG_BASE64_BEGIN")
        print(base64.b64encode(result).decode())
        print("ST7789_ORIGINAL_PNG_BASE64_END")
        print("Original 2x2 native C framebuffers: intercom, radio, game, system")

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    a=p.parse_args()
    dest=Path(a.output)
    dest.mkdir(parents=True,exist_ok=True)
    build(dest)

if __name__=="__main__":
    main()
