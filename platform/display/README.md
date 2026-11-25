# MSP2008 / ST7789: Orange Pi Zero 3 bench test

This is a manual display bring-up tool, not the LVGL application. It uses Linux
GPIO character-device v2 and spidev directly; no Python packages or libgpiod are
needed. The target image includes GCC/libc development packages for its module
build. If `cc` is unavailable, the source still needs a C compiler before use.

## Wiring

Disconnect power before wiring. These are **physical positions on the 26-pin
header**, not Raspberry Pi BCM numbers. VCC and BLK use **3.3 V**.

| MSP2008 | Header pin | SoC / role |
| --- | --- | --- |
| GND | 6 | GND |
| VCC | 1 | 3.3 V |
| SCL | 23 | PH6 / SPI1 CLK |
| SDA | 19 | PH7 / SPI1 MOSI |
| RES | 11 | PC6 / GPIO output |
| DC | 13 | PC5 / GPIO output |
| CS | 24 | PH9 / GPIO chip select managed by SPI |
| BLK | 17 | 3.3 V, backlight always on |

No MISO connection is needed. GPIO chips are discovered by the actual line names
PC5/PC6, without assuming a `/dev/gpiochipN` index. Some Armbian device trees omit
line names. In that case the test requires the board's DT compatible string
`xunlong,orangepi-zero3` and a 288-line chip labelled `300b000.pinctrl`, then uses
the H616/H618 bank-C offsets PC5=69 and PC6=70. Both lines must be unnamed for this
fallback; unrelated/ambiguous chips are rejected. Busy GPIO requests fail instead
of overriding another consumer. The SPI driver owns CS; the application only
requests DC/RES.

## Enable the overlay once

```sh
cp -a /boot/armbianEnv.txt /boot/armbianEnv.txt.before-display
armbian-add-overlay platform/display/medvetalkie-spi1.dts
reboot
```

If this overlay has already been installed during the hardware session, skip
this step. The expected device is `/dev/spidev1.0`: logical CS0 is explicitly
mapped to physical PH9 using `cs-gpios`. No stock `spidev1_1` overlay is required.

## Compile and run manually as root

```sh
cc -std=c11 -Wall -Wextra -Werror -O2 \
  platform/display/st7789-test.c -o /root/st7789-test
/root/st7789-test
```

The test uses SPI mode 0, 8-bit MSB-first, 1 MHz and RGB565. It sends red, green,
blue, white and black screens, then landscape 320x240 RGB/white bars with a white
border, a black upper-left marker and a yellow lower-right marker. It waits for
Enter so that the GPIO request stays alive during inspection. Closing the program
releases GPIO ownership; retention of the image after that is not guaranteed.

If red and blue are swapped, rerun with `/root/st7789-test --bgr`. This is a
manual visual test: successful SPI writes do not prove an attached/working LCD.
The tool does not install services, enable autostart or change boot settings.


## Bjorni screensaver with live clock

Run the self-contained launcher on the wired, verified display:

```sh
bash platform/display/medvetalkie-screensaver.sh
```

It compiles the embedded C renderer with the installed compiler and decodes the
embedded 35-frame animation from the Bjorni GIF supplied by the project owner.
No Python, image libraries or asset downloads are needed on the SBC. The cropped
bear appears on a true black background, with a periodically tossed star or
mushroom, rotating rainbow pinwheel and moving white sweep for visual inspection
of trailing/jerky motion. The clock uses current system wall time, including
seconds, date and the system timezone; animation timing uses a monotonic clock.

The launcher checks HTTPS server time at startup and every 15 minutes, using
`http://192.168.11.100:10880` by default. A green `SYNC` indicator means the latest
check succeeded; amber `LOCAL` means it failed or was disabled. Failed HTTP
responses, stale cached headers and invalid dates never set the clock. This is
a seconds-resolution HTTPS time check, not a precision NTP measurement. Override
the proxy with `MEDVETALKIE_PROXY` and timezone with `MEDVETALKIE_TZ` (for example,
`Europe/Moscow`), or use `--no-sync` to leave the system clock alone.

The default remains the verified **1 MHz** SPI speed. The operator confirmed
that the first screensaver version ran on the panel at about **3 FPS**. The
optimized renderer trims unchanged edges from changed tile runs and packs pixels
across rows into writes up to the driver's reported buffer size (maximum 4096
bytes). In a 30-frame host protocol test, pixel payload fell from 914944 to
526440 bytes (42%); this is a software sample, not a hardware FPS measurement.
The displayed FPS and average SPI transfer milliseconds describe the actual
software/transfer cadence; they do not measure panel response time or actual
input-to-photon latency. The animation now targets up to 25 FPS, subject to SPI
throughput. Initial display setup still runs at 1 MHz before selecting the
requested animation speed.

The operator subsequently confirmed **24.3–25 FPS without visible artifacts**
with the optimized screensaver at the requested **4 MHz** on the current panel
and wiring (2026-11-24). This reaches the configured 25 FPS ceiling; keep 4 MHz
for this bench. This observation does not establish long-duration stability or
measure panel latency. 8 MHz and higher have not been tested on this bench.

Use `bash platform/display/medvetalkie-screensaver.sh --spi-mhz 4` for the
confirmed fast mode. `--fps N` selects a
1–60 FPS ceiling. `MEDVETALKIE_SPI_MHZ=4` and `MEDVETALKIE_FPS=25` provide the
same settings through cron's environment, without changing its command lines.
CLI options override environment settings. SPI accepts integer MHz values 1–16;
4 MHz is visually confirmed on the current bench; higher settings remain
experimental. Return to 1 MHz if output is corrupted. Changing speed is per process; no overlay or boot
configuration change is required. The displayed MHz is the requested setting,
not a measurement of the physical clock. The original GIF itself has 280 ms
frames; the spinner, throws, sweep and clock update independently.

Press **Ctrl+C** to stop, turn the display off and release GPIO. The time-check
worker is also stopped. No services or autostart entries are installed. Use
`--bgr` only if red/blue are swapped. Exit the bench colour-bar test before
starting the screensaver; both programs use the same GPIO lines.

Host preview, regeneration and checks:

```sh
bash platform/display/medvetalkie-screensaver.sh --preview /tmp/bjorni.ppm --frame 8.9
python3 platform/display/screensaver/build-launcher.py
python3 platform/display/screensaver/test-screensaver.py
```

Preview mode does not open GPIO/SPI, use the network or set the clock. Renderer,
launcher template and packed sprites are in `platform/display/screensaver/`.
`import-bjorni.py` reproduces the packed asset from the owner's original GIF
using Pillow on the build host; rerun `build-launcher.py` after source/asset changes.

## Unified ST7789 status screen and Bjorni standby

The **same** C11 renderer holds SPI/GPIO while displaying either the
dashboard or Bjorni animation. Never start two independent SPI display
processes. The display remains independent of the audio process.

The optional `--status-file` argument (or `MEDVETALKIE_STATUS_FILE`)
enables a small 320x240 Russian-labelled dashboard. It shows:
mode; headset 1/2 role state; voice link; network; USB-BT/ACL counts;
radio availability; battery or a critical fault. **Headset battery, RSSI,
volume and actual audio profile are not yet published by Core Alpha**;
their absence must not be presented as good reception or charged batteries.
On the current API, headset roles are UNASSIGNED and voice is
NOT_VERIFIED; HFP_READY is forbidden until microphone, playback and SCO
are verified on the real board.

When an atomically refreshed status feed reports `mode=STANDBY` and
`fault=NONE`, display the dashboard for 8 seconds after startup or a
state change, then return to the animated Bjorni clock. The standalone CLI
supports `--status-seconds N` (1-120, default 8) or environment variable
`MEDVETALKIE_STATUS_SECONDS`, with CLI taking precedence. The managed
`medvetalkie-display.service` explicitly selects **30 seconds** for easier
physical bench inspection; it still uses the same single renderer and
4 MHz/25 FPS animation settings. Any active
mode, pairing, fault, absent or stale feed pins the status screen. The
status screen refreshes at approximately 2 FPS to reduce SPI overhead;
standby animation retains its configured 25 FPS ceiling. No other process
takes SPI ownership during transitions.

The transport is a local, versioned `MTSTATUS1` text snapshot written
atomically to an owner-private file. It is a **display-only adapter**,
not a second command API:

```text
MTSTATUS1
mode=STANDBY
headset1=UNASSIGNED
headset2=UNASSIGNED
voice=NOT_VERIFIED
network=LAN
radio=NOT_AVAILABLE
battery=UNKNOWN
fault=NONE
bt_usb=2
bt_connected=0
```

The format admits only whitelisted enum values and two bounded counts.
Malformed, missing or older-than-12-second data fails closed to
`CORE_OFFLINE`, not a retained READY state. It contains no Bluetooth
MAC addresses, passwords, paths, names or arbitrary user text. The
separate `medvetalkie-display-status` producer on
`feature/web-alpha-usb-diagnostics` queries the Core Unix IPC,
system status, passive USB count and BlueZ connected ACL count and
publishes this file. ACL connection is **not** HFP-ready voice.

For a local **preview** without GPIO, display or time synchronization:

```sh
printf 'MTSTATUS1\nmode=STANDBY\nheadset1=UNASSIGNED\nheadset2=UNASSIGNED\nvoice=NOT_VERIFIED\nnetwork=LAN\nradio=NOT_AVAILABLE\nbattery=UNKNOWN\nfault=NONE\nbt_usb=2\nbt_connected=0\n' > /tmp/medvetalkie-status-test
bash platform/display/medvetalkie-screensaver.sh --no-sync \
  --status-file /tmp/medvetalkie-status-test \
  --preview /tmp/medvetalkie-status.ppm
```

**Physical milestone (2026-11-25):** The operator has now observed the
informational dashboard during startup on the real ST7789 after removing
the legacy cron renderer; the screen was too brief to inspect at the
original eight-second setting. Physical FPS and reboot persistence are
not yet reconfirmed. This is **not** an interactive menu: GPIO input and
LVGL navigation remain separate unimplemented milestones. Do not
run the legacy cron screensaver alongside the systemd display service.
The standalone old no-status-file launch command remains supported.

## Hardware observations, 2026-11-24

- Operator confirmed boot of the stock USB-BT image; `uname -r` reports
  `6.18.64-current-sunxi64`.
- After installing this overlay, `/dev/spidev1.0` appeared and the kernel logged
  successful SPI1 host/child registration. Earlier pinctrl messages remain
  recorded; visual display output was subsequently confirmed below.
- On the operator's image, `gpiodetect` reports `gpiochip0 [7022000.pinctrl]`
  with 32 lines and `gpiochip1 [300b000.pinctrl]` with 288 lines. Lines 69/70
  are unnamed inputs. The original name-only test stopped before display
  initialization; the fallback above addresses that software discovery failure.
- After the GPIO discovery fix (`6ff101af3cdb21ab2b8cff837f0f982eee6a8acf`),
  the operator visually confirmed the colour fills and final colour bars on the
  connected MSP2008/ST7789. This validates basic display initialization and
  drawing with the wiring above at 1 MHz. Individual corner markers, sustained
  refresh, LVGL integration and automatic startup have not been verified.
- Two USB Bluetooth adapters enumerate behind a Realtek RTS5411 hub, both with
  VID:PID `10d7:b012`. Linux v6.18 `btusb.c` identifies this as Actions ATS2851
  and applies `BTUSB_ACTIONS_SEMI` quirks. The operator's `bluetoothctl list`
  subsequently showed two controllers with distinct addresses, and BlueZ 5.82
  was active. Pairing, one-headset HFP speaker/microphone and two simultaneous
  HFP sessions remain unverified.

References: [Linux GPIO v2](https://docs.kernel.org/userspace-api/gpio/gpio-v2-get-line-ioctl.html),
[spidev](https://docs.kernel.org/spi/spidev.html),
[MSP2008 documentation](https://www.lcdwiki.com/2.0inch_IPS_Module),
[Linux v6.18 btusb](https://github.com/torvalds/linux/blob/v6.18/drivers/bluetooth/btusb.c).
