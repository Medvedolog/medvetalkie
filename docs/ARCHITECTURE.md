# Architecture — proposed v1

## Design goals

- Maintain independent real-time Bluetooth audio paths; never couple audio samples to the web UI or SQLite.
- Fault-contain device lifecycle work and local display in separate processes.
- Avoid hard-coded HCI indices, transient PipeWire IDs or USB bus/device numbers.
- Keep control plane responsive under lost headsets, missing display, unplugged radio or AP toggles.
- Keep runtime dependencies measured on a 1 GB SBC.

## Processes

```text
 Android browser -- HTTP (future authenticated interface)
                      |
                 medvetalkie-web (C11, CivetWeb)
                 isolated process, loopback health only in Alpha 0
                      |
              versioned Unix IPC [planned]
                      |
                 medvetalkied (C11)
                 SQLite desired config
                 mode coordinator
                   |          |
              UNIX IPC     UNIX IPC
                   |          |
          medvetalkie-bt  medvetalkie-ui
          BlueZ D-Bus     LVGL SPI/HDMI
                   |          |
            BlueZ + PipeWire/WirePlumber
                   |
              headset 1 / headset 2
```

WebUI is now designed as a separate process to prevent a crash in HTTP code from terminating the core. The initial binary is deliberately limited to loopback `127.0.0.1:8765` and a GET-only `/api/v1/health` endpoint. It reports that core integration is absent. This is **not yet** a remotely accessible/authenticated management interface. Do not expose the loopback diagnostic service by a reverse proxy until authentication, authorization and CSRF protection are implemented. The full IPC connection and status model remain planned.

No audio sample traffic travels through the Unix IPC control protocol. PipeWire/WirePlumber remain independent system services. A separate PipeWire routing helper may be introduced only after hardware validation.

## Ownership

| Resource | Authoritative owner |
| --- | --- |
| User's desired operating mode and app settings | core + SQLite |
| Actual Bluetooth controllers, bonds, HFP profiles | BlueZ (queried by BT service) |
| Audio graph and audio device status | PipeWire/WirePlumber |
| Wi-Fi connections and credentials | NetworkManager **or** systemd-networkd (selected per image), not SQLite |
| Small-screen rendering and physical input | UI process |
| Process startup/restart | systemd |

Every restart runs reconciliation: discover current hardware state first, compare to desired configuration, then request a safe transition. No blindly replayed stale operations.

## Bluetooth

Roles `headset_1` and `headset_2` are logical, not brand-specific. One SCO/eSCO slot per adapter is a conservative default, **not a Bluetooth standard limit**. Two simultaneous active HFP links must be proven, not inferred from pairing or an HFP control connection.

HFP AG to a helmet headset and HFP HF to an Android phone are different roles. Phone bridge is an advanced integration milestone. A2DP playback to the same headset generally excludes its HFP microphone while active.

## UI and hardware

2.0-inch MSP2008/ST7789, 320×240 landscape. Digital five-way switch at the left; four face buttons at the right, plus any system controls needed after mechanical validation. GPIO input events are converted to core commands; LVGL does not own mode transitions. HDMI simulator mirrors local UI layout during pre-display development, without claiming that HDMI and SPI are the same hardware output backend.

FM is a removable ATS Mini V4 module. Initially accept stereo analog audio over a verified stereo USB line-in; USB serial remote control is optional, RDS remains viewable on the receiver itself. Digital USB audio conversion of ATS Mini is deferred.

## External references

- [Medvedolog/opiz3-wlan-backport](https://github.com/Medvedolog/opiz3-wlan-backport) — original owner's OpenWrt-specific AW859A/UWE5622 work. Compare individual patches to Armbian code; do not apply blindly.
- [phieri/bt-intercom](https://github.com/phieri/bt-intercom) — comparative research and field testing reference. The project's non-standard license restricts code reuse. **Do not copy/transpile its source.**
