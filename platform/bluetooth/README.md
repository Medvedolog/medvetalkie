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
