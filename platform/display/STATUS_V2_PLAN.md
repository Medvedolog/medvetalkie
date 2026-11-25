# MedveTalkie ST7789 status screen v2 (no buttons)

This is an **opt-in software implementation** of section 9 of [MedveTalkie TZ v1.4](../../docs/MedveTalkie_TZ_v1.4.md). The existing Bjorni script and the systemd display owner remain untouched.

## Implemented in the optional v2 build

- 320x240 landscape screen, Russian labels, clock, explicit operating mode and voice readiness indicator.
- Two coloured Bluetooth headset cards: profile (HFP/A2DP/unknown), device link status, battery percent and bar, output volume percent and bar, BT RSSI in dBm when exposed by BlueZ.
- Network type, USB adapter/connected headset counts, radio placeholder and red faults.
- Unknown battery/RSSI/volume shows **--**, never fabricated zero or connected status. Battery1 and RSSI on BlueZ are optional; RSSI may be unavailable outside discovery. Profile availability does not equal active HFP SCO PCM.
- Original Bjorni animation remains in the generated renderer; one SPI/GPIO owner. The status feed is strictly validated, rejects unknown keys/values, and turns into Core-offline state on malformed/stale (>12s) data.
- No GPIO buttons, joystick, Bluetooth connection changes, default audio routing changes, network changes, or service replacement.

Files:
- `platform/display/live-status.py`: read-only BlueZ Device1/Battery1 and PipeWire/pactl inventory; atomically writes private MTSTATUS1 snapshots. Does not infer usable full-duplex audio merely from paired/connected/HFP endpoints.
- `platform/display/screensaver/build-status-v2.py`: generates a new C source from the existing tested Bjorni renderer plus v2 status cards; does not modify the original.
- `platform/display/status-v2.sh`: optional compilation and run wrapper. Refuses a live launch when another process already owns `/dev/spidev1.0`. No systemd or boot modification.
- `tests/test_display_status_v2.py` and `tests/test_display_live_status.py`: offline validation and PPM preview. The existing Bjorni regression suite continues to test the unchanged original.

## Offline preview (no SPI, no root)

```sh
cd ~/medvetalkie
python3 platform/display/live-status.py --once --output /tmp/medvetalkie-status-v2
bash platform/display/status-v2.sh --status-file /tmp/medvetalkie-status-v2 --preview /tmp/medvetalkie-v2.ppm
```

If no user-level PipeWire session or BlueZ is available, the snapshot conservatively shows unavailable statuses. Use an image viewer capable of PPM. Run the test suite without board hardware with:

```sh
python3 tests/test_display_status_v2.py
python3 tests/test_display_live_status.py
```

## Combining with authoritative Core state (optional)

When the existing C publisher is running, keep its file distinct and have the
v2 reader inherit validated `mode`, `network`, `radio` and `fault` from its
fresh `MTSTATUS1` snapshot:

```sh
sudo python3 platform/display/live-status.py \
  --base-status-file /run/medvetalkie/display.status \
  --output /tmp/medvetalkie-status-v2 --interval 2
```

The example base path must be checked against the installed systemd unit. A
missing, stale, malformed or inaccessible base is explicitly marked
`CORE_OFFLINE`, rather than fabricating an active operating mode. Even a Core
fault value `NONE` cannot mask a missing observed USB Bluetooth controller.
The `voice` status remains `NOT_VERIFIED` unless a future audio engine publishes
validated active duplex routing.

## Later on-board supervised verification (do not run concurrently with Bjorni)

Keep the existing display service untouched until physically present. After inspecting `sudo fuser -v /dev/spidev1.0`, stop the **known owner** using its corresponding service or process. Start the v2 publisher in a different shell with an independent status path; do not run legacy `medvetalkie-display-status` against that path:

```sh
sudo python3 platform/display/live-status.py --output /tmp/medvetalkie-status-v2 --interval 2
```

In a second shell, only when SPI is free:

```sh
sudo bash platform/display/status-v2.sh --status-file /tmp/medvetalkie-status-v2
```

Ctrl+C stops the explicitly started processes and leaves the normal display service untouched, so the original display can be restored using its existing service arrangement.

## Outstanding before section 9 is complete

The reader of actual authoritative modes still needs connection to Core (this standalone observer shows UNKNOWN rather than inventing active INTERCOM). Audio status remains NOT_VERIFIED until active PCM transport is observed. Internet connectivity (rather than IP-link), radio frequency/RDS, active ROM/game metadata, power-bank/supply battery, low-power alerts and per-headset addressable gain require suitable **real** producer APIs; these fields currently show UNKNOWN/NOT_AVAILABLE. The operator must validate glyph legibility, colours, refresh rate and service ownership on physical ST7789 before enabling v2 at boot. Do not claim production-ready status UI yet.
