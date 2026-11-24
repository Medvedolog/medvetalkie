#!/usr/bin/env python3
"""Host checks: render without GPIO; simulate HTTPS/date without changing time."""
from pathlib import Path
import base64
import gzip
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
ENV = dict(os.environ, LC_ALL='C', MEDVETALKIE_TZ='Europe/Moscow')

def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, **kwargs)

with tempfile.TemporaryDirectory(prefix='medvetalkie-saver-check-') as temp:
    tmp = Path(temp)
    asset = tmp / 'sprite.dat'
    asset.write_bytes(gzip.decompress(base64.b64decode((ROOT/'bjorni-sprite.gz.b64').read_bytes())))
    env = dict(ENV, MEDVETALKIE_SPRITE=str(asset))
    binary = tmp / 'saver'
    result = run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                  str(ROOT/'screensaver.c'), '-lm', '-o', str(binary)])
    assert result.returncode == 0, result.stderr
    preview = tmp / 'preview.ppm'
    for second in [0, .28, .9, 1.8, 2.1, 4, 4.9, 8, 8.9, 9.8, 13.1, 59.9, 86400]:
        result = run([str(binary), '--preview', str(preview), '--frame', str(second)], env=env)
        assert result.returncode == 0, (second, result.stderr)
        header, dims, depth, pixels = preview.read_bytes().split(b'\n', 3)
        assert (header, dims, depth) == (b'P6', b'320 240', b'255')
        assert len(pixels) == 320*240*3 and pixels[:3] == b'\0\0\0'
        assert pixels.count(b'\xff\xff\xff') > 100, 'clock must be bright on black'
    for bad in ['nan', '-1', '86401', 'oops']:
        assert run([str(binary), '--preview', str(preview), '--frame', bad], env=env).returncode == 2
    broken = tmp/'broken.dat'
    broken.write_bytes(asset.read_bytes()[:-100])
    assert run([str(binary), '--preview', str(preview)],
               env=dict(env, MEDVETALKIE_SPRITE=str(broken))).returncode == 1
    print('PASS render: star/mushroom/animation frames, black background, bright clock, invalid input')

    # A failed HTTPS status must never set time even when it carries a Date.
    tools = tmp/'bin'
    tools.mkdir()
    fake_curl = tools/'curl'
    fake_curl.write_text('''#!/bin/bash
headers=''
while (( $# )); do
 if [[ "$1" == --dump-header ]]; then headers=$2; shift; fi
 shift
done
case "$CASE" in
 success|set-denied)
 printf 'HTTP/1.1 200 Connection established\\r\\n\\r\\nHTTP/2 204\\r\\nDate: Tue, 24 Nov 2026 15:37:00 GMT\\r\\n\\r\\n' > "$headers" ;;
 failure)
 printf 'HTTP/2 404\\r\\nDate: Tue, 24 Nov 2026 15:37:00 GMT\\r\\n\\r\\n' > "$headers"; exit 22 ;;
 stale)
 printf 'HTTP/2 200\\r\\nDate: Tue, 24 Nov 2026 15:37:00 GMT\\r\\nAge: 120\\r\\n\\r\\n' > "$headers" ;;
 malformed)
 printf 'HTTP/2 200\\r\\nDate: nonsense\\r\\n\\r\\n' > "$headers" ;;
 redirect)
 printf 'HTTP/2 302\\r\\nDate: Tue, 24 Nov 2037 15:37:00 GMT\\r\\n\\r\\nHTTP/2 204\\r\\nDate: Tue, 24 Nov 2026 15:37:00 GMT\\r\\n\\r\\n' > "$headers" ;;
 missing-final-date)
 printf 'HTTP/2 302\\r\\nDate: Tue, 24 Nov 2026 15:37:00 GMT\\r\\n\\r\\nHTTP/2 204\\r\\n\\r\\n' > "$headers" ;;
esac
''')
    fake_curl.chmod(0o755)
    fake_date = tools/'date'
    fake_date.write_text('''#!/bin/bash
for arg in "$@"; do
 if [[ "$arg" == --set=* ]]; then
  [[ "$CASE" == set-denied ]] && exit 1
  printf '%s\\n' "$arg" >> "$SET_LOG"
  exit 0
 fi
done
exec /usr/bin/date "$@"
''')
    fake_date.chmod(0o755)
    template = (ROOT/'launcher.sh.in').read_text()
    function = 'sync_clock() {' + template.split('sync_clock() {', 1)[1].split('\nif (( sync_enabled )); then', 1)[0]
    function_path = tmp/'sync-function.sh'
    function_path.write_text(function)
    for case in ['success', 'redirect', 'failure', 'stale', 'malformed', 'missing-final-date', 'set-denied']:
        log = tmp/'set.log'
        log.unlink(missing_ok=True)
        state = tmp/'time-status'
        state.write_text('0\n')
        shell = 'set -uo pipefail; wait_pid=""; proxy_url="http://192.168.11.100:10880"; source "$FUNCTION"; sync_clock'
        result = run(['bash', '-c', shell], env=dict(ENV, PATH=str(tools)+':'+os.environ['PATH'],
                     CASE=case, SET_LOG=str(log), FUNCTION=str(function_path),
                     work_dir=str(tmp), MEDVETALKIE_SYNC_STATUS=str(state)))
        good = case in ('success', 'redirect')
        assert (result.returncode == 0) == good, (case, result.stdout, result.stderr)
        assert state.read_text().strip() == ('1' if good else '0'), case
        assert log.exists() == good, case
        if good: assert log.read_text().strip() == '--set=@1795534620', log.read_text()
    print('PASS time: HTTPS success, redirects, 404, stale cache, missing/bad Date, permission failure')

    # The shipped single-file entry point must work without network/root in preview mode.
    launcher = ROOT.parent/'medvetalkie-screensaver.sh'
    before = launcher.read_bytes()
    result = run(['python3', str(ROOT/'build-launcher.py')])
    assert result.returncode == 0 and launcher.read_bytes() == before, 'regeneration must be deterministic'
    assert run(['bash', '-n', str(launcher)]).returncode == 0
    assert run(['bash', str(launcher), '--help']).returncode == 0
    result = run(['bash', str(launcher), '--preview', str(preview), '--frame', '8.9'], env=ENV)
    assert result.returncode == 0, result.stderr
    print('PASS launcher: deterministic build, syntax/help and self-contained preview')

    # Exercise the supervisor with a fake renderer. No device or system clock access.
    import signal
    import time
    fake_cc = tools/'cc'
    fake_cc.write_text('''#!/bin/bash
out=''
while (( $# )); do
 if [[ "$1" == -o ]]; then out=$2; shift; fi
 shift
done
cat > "$out" <<'RENDERER'
#!/bin/bash
printf '%s\\n' "$$" > "$CHILD_LOG"
exec /bin/sleep 600
RENDERER
chmod +x "$out"
''')
    fake_cc.chmod(0o755)
    supervisor = tmp/'supervisor-test.sh'
    supervisor.write_text(launcher.read_text().replace('if (( ! preview )) && (( EUID != 0 )); then', 'if false; then'))
    def descendants(pid):
        table = run(['ps', '-eo', 'pid=,ppid=']).stdout.splitlines()
        pairs = [(int(row.split()[0]), int(row.split()[1])) for row in table]
        def collect(parent):
            children = [p for p, pp in pairs if pp == parent]
            return children + [p for child in children for p in collect(child)]
        return collect(pid)
    for sig, expected in [(signal.SIGINT, 130), (signal.SIGTERM, 143)]:
        child_log = tmp/'child.log'
        child_log.unlink(missing_ok=True)
        process = subprocess.Popen(['bash', str(supervisor)], start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=dict(ENV, PATH=str(tools)+':'+os.environ['PATH'], CASE='success',
                     SET_LOG=str(tmp/'set.log'), CHILD_LOG=str(child_log)))
        try:
            deadline = time.monotonic()+5
            while not child_log.exists() and time.monotonic()<deadline: time.sleep(.02)
            assert child_log.exists(), 'fake renderer did not start'
            live = descendants(process.pid)
            assert len(live) >= 3, (process.pid, process.poll(), live, run(['ps','-eo','pid,ppid,args']).stdout)  # renderer, sync worker, sleeping interval
            process.send_signal(sig)
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == expected, (process.returncode, stdout, stderr)
            assert not any(Path(f'/proc/{pid}').exists() for pid in live), ('leftover children',live)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
    print('PASS supervisor: Ctrl+C/SIGTERM stop renderer and time worker without leftover children')
