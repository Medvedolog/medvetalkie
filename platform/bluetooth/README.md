# MedveTalkie Bluetooth SSH bench

Run from a real SSH terminal (at least 64 columns × 18 rows):

```sh
cd ~/medvetalkie
git -c http.proxy=http://192.168.11.100:10880 pull --ff-only
sudo python3 platform/bluetooth/medvetalkie-bt-tui.py
```

Uses Python 3 standard library `curses`, BlueZ `bluetoothctl` and optional `pactl`. No additional Python packages. ANSI terminal colors and a live spinner/activity indicator. The animated bar is **not** a percentage complete indicator. Works over SSH without LVGL or ST7789 ownership.

Keyboard: `1`/`2` choose controller; `S` BR/EDR scan (~12 seconds); `R` refresh BlueZ cache; Up/Down select device; `I` details; `C` connect; `P` request pairing with additional `Y` confirmation; `H` read-only user PipeWire card/profile diagnostic; `L` toggle logs; `Q` quit. AIRIDE N1 `41:42:63:27:E7:3A` is highlighted when present, but other headsets are supported. The current pairing action uses a noninteractive `bluetoothctl` invocation; PIN/confirmation-based pairing may require interactive `bluetoothctl` outside this tool. The TUI will report errors instead of deleting bonds.

Caveats: current BlueZ cached-device enumeration may contain devices discovered earlier; it is not a continuously streaming RF scan. Controller selection is by BlueZ MAC (not an assumed HCI index). HFP profile registration failures (e.g. `br-connection-profile-unavailable`) require WirePlumber/session diagnostics. `Connected`, an HFP UUID, or a Bluetooth card do not prove SCO/eSCO or microphone/speaker PCM. No auto profile switches, bond deletion, forced trust, audio graph rewiring, or systemd/kernel changes are performed. 

Offline regression: `python3 -m py_compile platform/bluetooth/medvetalkie-bt-tui.py && python3 tests/test_bt_tui.py`. CI runs these checks; success on actual Orange Pi must be recorded separately.

## 10-second HFP full-duplex bench (new)

The `D` key starts a **confirmation-required** timed test on the selected Bluetooth headset. The `T` key starts the same test while also collecting a `btmon` HCI trace (requires root and `btmon` from BlueZ). Both run asynchronously with the TUI's spinner and indeterminate activity bar. The test does not change audio profiles, current volumes or default audio routing. It selects the exact `bluez_output.*` and `bluez_input.*` nodes for the currently selected headset, requiring an already active HFP card profile. Speak into the mic while brief low-level 440 Hz pips play over the headset; the tool records microphone audio in parallel, computes peak/RMS dBFS, 500 ms RMS windows and counts clipped samples. The WAV and optional raw `hci.btsnoop` trace are stored in a unique `/tmp/medvetalkie-bt-*/` directory. Read the TUI's **L** log to find the path. No recordings are uploaded. A successful subprocess completion proves that the parallel playback and recording clients ran, not that SCO stayed continuous: inspect the file and trace.

Run the same test without curses:

```sh
sudo python3 platform/bluetooth/bt_audio_bench.py --mac 41:42:63:27:E7:3A --seconds 10 --btmon
```

If `btmon` is unavailable, omit `--btmon` for the PCM test and install the required BlueZ tools before HCI tracing. Start with conservative headset output volume; the generated tone is intentionally low-amplitude. To test mSBC/CVSD, first choose an available HFP profile via the already verified PipeWire service account, then run the bench. The tool refuses non-HFP profiles. This is **not** a second-headset intercom or a live microphone VU meter yet. Recording analysis uses captured WAV data after the test, not a live mic stream. The headset mic gain at 120% is an experiment; check noise and clipping before making a permanent default.

## Second controller/headset

Use **2** to select the second UGREEN controller and **S** to scan, then use the arrow keys to select a distinct headset. **C** connects only the selected device; **P** requires another confirmation and might need an interactive PIN agent. Do not move the existing AIRIDE bond or change default BlueZ adapter globally. Cross-headset audio routing and two-device full-duplex stability are not implemented or verified yet; first establish both independent HFP inputs and outputs.


## Menu-based manager (replacement for old shortcut TUI)

The existing launcher `sudo python3 platform/bluetooth/medvetalkie-bt-tui.py` now starts `medvetalkie-bt-menu.py`. Requires SSH with `TERM=xterm-256color` (or another functioning ncurses `TERM`), terminal ≥ 84×21. No third-party Python dependencies. **Up/Down** moves the highlighted selection, **Tab** or **Left/Right** switches between device and action panels, **Enter** selects an action, **PgUp/PgDn** changes BlueZ controller, **Esc** goes back/cancels, **Q** quits. The right-side menu contains scanning, connect/disconnect, pairing with passkey/PIN prompts, mark trusted, A2DP / HFP mSBC / HFP CVSD profile selection, 6-second microphone capture, playback of latest recording, 10-second duplex and optional btmon, per-device playback volume ±10% and microphone gain ±10%, device info and logs. Confirmation prompts precede pairing, connecting, trusting or starting duplex tests.

**Device inventory:** BlueZ's discovered-cache list is merged with `bluetoothctl devices Paired` and `bluetoothctl devices Connected` on the chosen controller. Sorted into active connections first (green ●), remembered paired/bonded devices next (◇), and remaining discovered nearby devices (·). The selected device line reports MAC, connection, pairing, trust and battery. RSSI is shown in dBm only when `bluetoothctl info` provides it, possibly from its cache; **RSSI is not guaranteed to be live**, and absent data is shown as `RSSI —`. While idle, the inventory polls around every 15 seconds. Pairing may request agent PIN, passkey or confirmation and remains subject to BlueZ/remote device support; these flows are not yet hardware-tested with a fresh unpaired headset.

The menu does not automatically delete bonds, restart Bluetooth services, interfere with ST7789, change the network, or perform automatic cross-headset routing. The prior shortcut-oriented `Bench` remains in the launcher file solely for compatibility tests, but the launcher now hands control to the new menu. Verify arrow keys and pairing under the operator's actual SSH client; CI mocks cannot validate the terminal's escape sequences or Bluetooth agent prompts.


## Headless two-headset intercom bridge (experimental, no TUI)

The curses-based UI is not hardware-accepted (operator reports a blank screen); **do not depend on TUI for the next physical milestones**. The independent headless `medvetalkie-intercom-test.py` uses `bluetoothctl`, `pactl`, and the already running PipeWire headless session. It creates temporary cross-routing between the **two distinct currently connected HFP headsets on two different Bluetooth controllers**: A mic → B speaker; B mic → A speaker. It does not pair, scan, disconnect, change profiles or gains, or alter Core/network/display. The PipeWire Pulse-compatible `module-loopback` is loaded twice and both module IDs are unloaded on exit, interruption or partial failure. Default duration: 30 seconds; bound 5..300 seconds. Requires active HFP profiles for both headsets and user `medvetalkie`'s PipeWire pulse socket.

To discover paired/connected devices per controller (no TUI):

```sh
bluetoothctl list
bluetoothctl
# Inside bluetoothctl:
# select F4:4E:FC:57:69:64
# devices Connected
# devices Paired
# select F4:4E:FC:2D:FD:4B
# devices Connected
# devices Paired
# quit
```

First verify using your actual second headset MAC:

```sh
sudo python3 platform/bluetooth/medvetalkie-intercom-test.py \
  --a 41:42:63:27:E7:3A --b AA:BB:CC:DD:EE:FF --dry-run
```

Replace `AA:BB:CC:DD:EE:FF` with the **actual** MAC; it is deliberately a placeholder, not a claimed known headset. Once the dry-run proves both controller associations and active HFP PipeWire endpoints, run a bounded test:

```sh
sudo python3 platform/bluetooth/medvetalkie-intercom-test.py \
  --a 41:42:63:27:E7:3A --b AA:BB:CC:DD:EE:FF \
  --seconds 30 --latency-ms 80
```

Wear both headsets and test speech both ways, including overlapping speech. `--latency-ms` is a target and **not** a measured one-way or round-trip delay. Check subjective echo/volume/interruptions; neither low-latency performance nor sustained duplex on two ATS2851 adapters is validated yet.

**Safety:** The bridge must refuse one headset on both sides, disconnected devices, devices on the same controller, unavailable HFP profile, or multiple competing sources/sinks. It creates *only* two loopback modules and unloads **only its own** allocated module IDs. If a process is killed uncleanly (e.g. SIGKILL/power loss) or cleanup fails, run `pactl list short modules` in the `medvetalkie` audio session and manually remove only the orphaned module-loopback IDs after confirming ownership; do not blindly unload all audio modules. Use `Ctrl+C` to request clean shutdown. This is a controlled hardware validation harness, not a production background intercom daemon.


## BlueZ 5.82 CLI compatibility (important)

The Orange Pi has BlueZ 5.82. **There is no `bluetoothctl -i` option.** Controller selection is performed **inside the same `bluetoothctl` session** using `select <controller MAC>`, followed by `devices Connected`, `devices Paired`, `info <device MAC>` or other commands. The headless bridge and menu's inventory use `platform/bluetooth/bluez_cli.py` to run scoped, read-only commands and verify controller selection, avoiding accidental queries on the default adapter. Regression: `python3 tests/test_bluez_cli.py`. Operator-confirmed inventory output is still required for hardware acceptance.


## Live PCM relay experiment (after silent Pulse module-loopback)

`platform/bluetooth/medvetalkie-pcm-relay.py` is a **bounded, operator-launched** real-time PCM relay designed to diagnose the failure of cross-headset live voice despite successful simultaneous AIRIDE capture and UGREEN playback of short diagnostic pips, and successful delayed WAV replay. It does **not** modify the existing `medvetalkie-intercom-test.py`, BlueZ controller pairing/profiles, volumes, services or display. It validates both controller associations and HFP sources/sinks with the proven BlueZ D-Bus + PipeWire dry-run, then starts `parecord --raw` and `paplay --raw` against exact PipeWire device names with 16 kHz mono signed 16-bit audio, 20 ms block size, explicit 80 ms latency target and max 15 queued frames (300 ms). An overfull queue drops the oldest frame instead of accumulating infinite delay.

Run first in **A→B only** mode (wear both headsets, speak continuously into AIRIDE):
```sh
cd ~/medvetalkie
sudo python3 platform/bluetooth/medvetalkie-pcm-relay.py --dry-run
sudo python3 platform/bluetooth/medvetalkie-pcm-relay.py --direction a-to-b --seconds 12 --latency-ms 80
```

The output reports read KiB/s, written KiB/s, queue depth, dropped bytes, input RMS/peak dBFS, clipping count and time to first attempted playback write. At 16 kHz × mono × 16-bit the theoretical PCM data rate is **31.25 KiB/s** in steady state. If input has sensible RMS and output is being written near that speed but UGREEN is still silent, investigate whether `paplay`/PipeWire actually renders live stream rather than assuming headset microphone failure. If input falls to approximately 0 KiB/s or -180 dBFS, investigate source transport. This test does not prove audio rendering or end-to-end delay from OS pipe metrics alone. No WAV is stored by this relay.

After the one-direction test, `--direction b-to-a` and `--direction both` are available, but avoid the full-duplex mode until A→B is audible and stable. Only owned `parecord`/`paplay` processes are terminated on exit. CI regression: `python3 tests/test_bt_pcm_relay.py`. No production daemon or auto-start should be enabled before physical acceptance.
