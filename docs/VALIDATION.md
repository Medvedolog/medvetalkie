# Hardware validation checklist

**Current evidence (2026-11-06):** one headset paired and connected on the built-in AW859A; **A2DP SBC playback passed with an audible 440 Hz tone**. HFP mSBC and CVSD both failed the actual two-way audio test. An HCI eSCO session established successfully, but its test trace recorded **595 SCO TX / 0 SCO RX**, and the captured microphone WAV contained only zeros. **The full-duplex feasibility gate remains blocked.**

Detailed reproducible report: [Orange Pi Zero 3 bench — 2026-11-06](HARDWARE-BENCH-2026-11-06.md). UWE5622 kernel transport investigation is isolated in [platform/uwe5622](../platform/uwe5622/README.md). These observations apply to the tested Armbian 6.18.60 / AIRIDE N1 combination; they are not proof of a universal controller limitation.

## 0. Record test environment

Capture exact Armbian image, kernel `uname -a`, device tree, AW859A firmware, BlueZ/PipeWire versions, Bluetooth controller addresses, actual USB IDs and physical port topology, firmware revisions of the two test headsets. Retain sanitized `btmon` traces, kernel logs and PipeWire node snapshots.

## 1. Baseline Orange Pi

- Boot an unmodified Armbian CLI build over Ethernet; no X11/Wayland.
- Verify AW859A controller exists and survives cold boot and reboot.
- Pair one headset; confirm HFP microphone and playback audio, not merely Bluetooth ACL.
- Repeat with all radios off then with Wi-Fi STA 5 GHz hotspot.
- If AW859A is absent, investigate DT / firmware / services before declaring a failed chip.

## 2. Two headsets

- Prefer one HFP/SCO connection per independent controller; test one-controller dual HFP as optional research.
- Capture synchronous link establishment via `btmon` for **both** active sessions.
- Cross-route mic1→speaker2, mic2→speaker1, no self-monitoring; measure dropouts, delays, audio quality and recovery.
- Reboot 10 times, vary USB probe order, remove/reinsert a dongle, and verify no hard-coded HCI index / transient PipeWire IDs.
- Test body shielding (rider between SBC and passenger), head movement and 20–30 m line-of-sight rider separation as an *aspirational* field target, not a claimed spec.

## 3. Networking and modes

- Verify Wi-Fi STA 5 GHz under Armbian (reported working on OpenWrt is not transferable proof).
- Measure HFP stability with idle and streaming Wi-Fi, with AP and after Wi-Fi recovery.
- AP is user-enabled from local screen: randomly generated PSK, scannable standard Wi-Fi QR, separate web login, idle timeout.
- SOLO_STEREO: verify audio A2DP output and microphone unavailability; restoring HFP must not leave stuck links.
- Android media and call bridging are separate tests; Android assistant and call control are **not assumed**.

## 4. UI / FM / power

- HDMI UI before SPI arrival; 320×240 layout and physical button mapping.
- ST7789 SPI later: measure sustained update throughput, CPU and UI reaction.
- ATS Mini V4 stereo line-in sound and USB-noise impact; do not assume USB Audio available.
- Power USB 5 V inline tester: idle, 1/2 HFP, 5 GHz STA streaming, AP, A2DP, CPU governor/cap sweeps; measure `MemAvailable` and CPU frequency too.

## Exit gate

Mark full-duplex intercom as supported only after both HFP microphones and two outputs work simultaneously on documented hardware for a sustained test with recovery and field checks. Report failed combinations explicitly.
