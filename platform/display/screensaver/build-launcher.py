#!/usr/bin/env python3
"""Regenerate the single-file launcher using only the Python standard library."""
from pathlib import Path
import hashlib

root = Path(__file__).resolve().parent
bench = (root.parent / 'st7789-test.c').read_text()
source = (root / 'screensaver.c').read_text()
source = source.replace('#include "../st7789-test.c"', bench)
asset = (root / 'bjorni-sprite.gz.b64').read_text()
template = (root / 'launcher.sh.in').read_text()
assert template.count('@SOURCE@') == template.count('@ASSET@') == 1
result = template.replace('@SOURCE@', source).replace('@ASSET@', asset)
result = result.replace('@SOURCE_SHA256@', hashlib.sha256(source.encode()).hexdigest())
path = root.parent / 'medvetalkie-screensaver.sh'
path.write_text(result)
path.chmod(0o755)
print(f'{path.name}: {path.stat().st_size} bytes')
