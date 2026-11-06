# Roadmap (priority, not dates)

## P0 — Hardware feasibility
1. Stock headless Armbian on Orange Pi Zero 3 (1 GB); identify AW859A and driver.
2. Verify one genuine HFP/SCO two-way audio session.
3. Verify two independent simultaneous HFP/SCO sessions, ideally with two controllers.
4. Measure stability, dropouts, body shielding, USB identity and power.

**No-Go:** If two simultaneous bidirectional HFP audio sessions cannot be made reliable on tested hardware, do not market a working full-duplex intercom.

## P1 — Control foundation and web UI
1. Versioned Unix IPC, command IDs, state snapshot/event subscription, reconnection and timeouts.
2. SQLite config with migrations; host BlueZ/Wi-Fi secrets remain in respective system stores.
3. BlueZ adapter/headset manager with stable identity and bounded backoff.
4. PipeWire route reconciliation and session state.
5. CivetWeb static responsive mobile web UI, separate login; AP on-demand.
6. Wi-Fi STA 5 GHz and scan/save network; audit UWE5622 patch compatibility.

## P2 — Local controls
1. HDMI LVGL simulator 320×240, physical keypad mappings.
2. ST7789 SPI driver and 5-way joystick + four buttons.
3. AP password+QR, status telemetry, headsets, basic radio control.

## P3 — Additional audio and accessories
1. SOLO_STEREO A2DP, FM ATS Mini V4 via stereo USB ADC, internet-radio.
2. Android A2DP source -> Linux sink -> headset forwarding.
3. Experimental phone HFP bridge; validate phone compatibility.
4. Offline voice commands, notifications, RetroArch on HDMI, power optimization.

Update milestones from actual hardware evidence, not a speculative feature checklist.
