#!/usr/bin/env python3
"""Import the owner's 35-frame Bjorni GIF (Pillow needed only on the build host)."""
from collections import deque
from pathlib import Path
import base64
import gzip
import struct
import sys
from PIL import Image

if len(sys.argv) != 2:
    raise SystemExit('Usage: import-bjorni.py /path/to/Bjorni-v-dvizhenii.gif')
image = Image.open(sys.argv[1])
if image.size != (320, 310) or image.n_frames != 35:
    raise SystemExit('Expected the original 320x310, 35-frame Bjorni GIF')
w, h = 80, 112
frames = []
for index in range(image.n_frames):
    image.seek(index)
    crop = image.convert('RGB').crop((84, 32, 236, 245))
    pixels = crop.load()
    cw, ch = crop.size
    seen, queue = set(), deque()
    for x in range(cw): queue.extend(((x, 0), (x, ch-1)))
    for y in range(ch): queue.extend(((0, y), (cw-1, y)))
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen or x < 0 or y < 0 or x >= cw or y >= ch: continue
        r, g, b = pixels[x, y]
        if (r-55)**2 + (g-46)**2 + (b-61)**2 > 1800: continue
        seen.add((x, y))
        queue.extend(((x-1,y), (x+1,y), (x,y-1), (x,y+1)))
    for x, y in seen: pixels[x, y] = (0, 0, 0)
    frames.append(crop.resize((w, h), Image.Resampling.NEAREST))
sheet = Image.new('RGB', (w, h*len(frames)))
for i, frame in enumerate(frames): sheet.paste(frame, (0, i*h))
quantized = sheet.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
palette = quantized.getpalette()
black = min(range(64), key=lambda i: sum(palette[3*i:3*i+3]))
order = [black] + [i for i in range(64) if i != black]
remap = {old: new for new, old in enumerate(order)}
colours = []
for i in order:
    r, g, b = palette[3*i:3*i+3]
    colours.append(((r>>3)<<11) | ((g>>2)<<5) | (b>>3))
colours[0] = 0
raw = list(quantized.getdata())
runs, offsets = [], [0]
for frame in range(35):
    data = [remap[i] for i in raw[frame*w*h:(frame+1)*w*h]]
    pos = 0
    while pos < len(data):
        end = pos+1
        while end < len(data) and data[end] == data[pos] and end-pos < 1023: end += 1
        runs.append(((end-pos)<<6) | data[pos])
        pos = end
    offsets.append(len(runs))
blob = b'BJORN01\0' + struct.pack('<4I', w, h, 35, 280)
blob += struct.pack('<64H', *colours) + struct.pack('<36I', *offsets)
blob += struct.pack('<%dH' % len(runs), *runs)
path = Path(__file__).resolve().parent / 'bjorni-sprite.gz.b64'
path.write_bytes(base64.encodebytes(gzip.compress(blob, mtime=0)))
print(f'{path.name}: {path.stat().st_size} bytes')
