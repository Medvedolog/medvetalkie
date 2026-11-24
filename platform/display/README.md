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

## Hardware observations, 2026-11-24

- Operator confirmed boot of the stock USB-BT image; `uname -r` reports
  `6.18.64-current-sunxi64`.
- After installing this overlay, `/dev/spidev1.0` appeared and the kernel logged
  successful SPI1 host/child registration. Earlier pinctrl messages remain
  recorded; complete pin-level/visual verification is still pending.
- On the operator's image, `gpiodetect` reports `gpiochip0 [7022000.pinctrl]`
  with 32 lines and `gpiochip1 [300b000.pinctrl]` with 288 lines. Lines 69/70
  are unnamed inputs. The original name-only test stopped before display
  initialization; the fallback above addresses that software discovery failure.
- Two USB Bluetooth adapters enumerate behind a Realtek RTS5411 hub, both with
  VID:PID `10d7:b012`. Linux v6.18 `btusb.c` identifies this as Actions ATS2851
  and applies `BTUSB_ACTIONS_SEMI` quirks. This is USB enumeration evidence,
  not proof of two BlueZ controllers or working HFP audio.
- Display pixels, pairing, independent controller addresses, one-headset HFP
  speaker/microphone and two simultaneous HFP sessions remain unverified.

References: [Linux GPIO v2](https://docs.kernel.org/userspace-api/gpio/gpio-v2-get-line-ioctl.html),
[spidev](https://docs.kernel.org/spi/spidev.html),
[MSP2008 documentation](https://www.lcdwiki.com/2.0inch_IPS_Module),
[Linux v6.18 btusb](https://github.com/torvalds/linux/blob/v6.18/drivers/bluetooth/btusb.c).
