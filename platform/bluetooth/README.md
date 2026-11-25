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
