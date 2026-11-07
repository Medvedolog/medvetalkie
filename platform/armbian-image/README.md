# MedveTalkie: complete Armbian image for Orange Pi Zero 3

**Status: source integration under test; a bootable full image has NOT yet
been compiled or tested on the physical board.** The native ARM64 module
builds and static patch checks are distinct from a full Armbian image build.

## Why not simply copy the 6.18.60 .ko files into a new image?

Armbian may build a different patchlevel, kernel configuration or symbol CRC.
The image profile builds its own kernel, DTBs, bootloader and Debian 13
rootfs through the standard Armbian framework, then **recompiles**
the BSP/Wi-Fi/BT modules against that image's installed exact kernel headers
and Module.symvers. The build fails if headers, modules or module lookup fail.

## Base and hardware

- Device: Orange Pi Zero 3, Allwinner H618, AW859A/UWE5622.
- Armbian builder: `armbian/build` commit
  `664d5fdf0efa5284dd85daae15101c5423d6de73`.
- Armbian settings: `BOARD=orangepizero3 BRANCH=current RELEASE=trixie
  BUILD_DESKTOP=no BUILD_MINIMAL=yes KERNEL_CONFIGURE=no`.
- Existing Armbian `uwe5622-allwinner` extension is preserved; it includes
  the AW859A Wi-Fi/BT services, rfkill, BlueZ, SDIO BT module inclusion
  and the `hciattach_opi` helper.
- The Armbian sunxi64-current kernel config includes `CONFIG_BT_HCIBTUSB=m`,
  `CONFIG_BT_HCIUART=m` and `CONFIG_SND_USB_AUDIO=y`. Both USB
  UGREEN CM390 adapters therefore use **stock USB Bluetooth**, independent
  of the optional onboard `sprdbt_tty` transport.
- The Armbian build framework itself is pinned. Its separate fetched
  kernel/bootloader dependencies must also be captured in the final build
  manifest before describing an image as bit-for-bit reproducible.

## Profiles

| `WIFI_PROFILE` | Wi-Fi patches | Purpose |
| --- | --- | --- |
| `p0` | 030,130,160,190,220,250,330 | Stability and recovery prerequisites |
| `apsta` | P0 + 180,200,290,310 | 5 GHz access point, AP+STA MAC and teardown |

`070` must already match the pinned upstream tree.

| `BT_PROFILE` | SDIO BT transport |
| --- | --- |
| `stock` | Compile unmodified upstream `sprdbt_tty` with same image kernel ABI |
| `patched` | Also apply `0001` RX/HCI counters and `0002` RX queue ownership fixes |

The patched Bluetooth transport is still experimental; it **has not
proven two-way HFP voice** on physical hardware. In particular, the absence
of SCO RX in prior observations may originate below the TTY layer.

## Prepare build workspace (no image build)

On a Linux host with Git and Bash, from a MedveTalkie checkout:

```bash
WIFI_PROFILE=apsta BT_PROFILE=stock \
  bash platform/armbian-image/prepare-full-image.sh "$HOME/armbian-build-medvetalkie"
```

The script fetches pinned Armbian and UWE5622 source and applies the reviewed
Wi-Fi patches; it places an Armbian extension under `extensions/` and
stage sources under `userpatches/`. It rejects pre-existing MedveTalkie
stage files rather than silently overwriting them.

## Build complete SD-card image

Armbian's documented image builds require approximately **50 GiB free disk**
and 8 GiB RAM; use a Debian 13/Armbian or properly configured Docker-capable
host. Check the host's kernel/chroot/container prerequisites.

```bash
WIFI_PROFILE=apsta BT_PROFILE=stock \
  bash platform/armbian-image/prepare-full-image.sh "$HOME/armbian-build-medvetalkie" --build
```

Output: `$HOME/armbian-build-medvetalkie/output/images/` on a successful
full image compile. `BT_PROFILE=patched` produces the experimental
Bluetooth variant. To switch profiles, use a **new empty build directory**.

GitHub Actions also has a **manual** build workflow at
[`.github/workflows/armbian-full-image.yml`](../../.github/workflows/armbian-full-image.yml).
The image job refuses to run with less than 50 GiB free. A self-hosted ARM64
runner may be required; the default hosted runner may not have the needed
storage. Automatic push events validate the patch combinations but **do not
build a bootable image**. GitHub only exposes manual `workflow_dispatch`
from the UI once the workflow exists on the default branch; while this PR
is draft, the supported full-image path is the local `--build` command.


## Boot and safety

- **First boot the image on a separate microSD card.** Retain the
  original working Armbian card untouched; a full-image flash cannot be
  rolled back by the .deb's watchdog.
- Wired Ethernet/serial console are required for initial diagnosis.
- The stock Armbian Wi-Fi service remains enabled; the patched driver
  is installed as an `updates/medvetalkie` module override with
  `depmod` and an explicit module lookup check.
- USB Bluetooth and BlueZ remain available.
- The built-in AW859A Bluetooth **attach service** requires an explicit
  `/etc/medvetalkie/enable-onboard-bluetooth` marker. This does not
  blacklist or unload the `sprdbt_tty` kernel module.
- The `uwe5622-recover` script and systemd service are included, but
  neither the dangerous SDIO reset opt-in marker nor an automatic udev
  CP-assert trigger is installed by default.
- No credentials or Wi-Fi AP passwords are embedded in the image.

### Enabling onboard Bluetooth attach for controlled testing

Only after collecting a known-good baseline and ensuring USB BT is not
selected for the same audio path:

```bash
sudo install -d /etc/medvetalkie
sudo touch /etc/medvetalkie/enable-onboard-bluetooth
sudo systemctl restart aw859a-bluetooth.service
```

Undo with `sudo rm /etc/medvetalkie/enable-onboard-bluetooth` and
`sudo systemctl stop aw859a-bluetooth.service`.

### Read-only diagnosis on a booted image

```bash
sudo /usr/local/sbin/uwe5622-preflight status
sudo /usr/local/sbin/uwe5622-abi-check strict
modinfo -n sprdwl_ng
modinfo -n sprdbt_tty
```

**Do not deploy or write a full image to the active storage device without
a separate, bootable fallback and UART access.**

## Verified three-module CI (not a bootable image)

[Combined ARM64 kernel module run 42370939364](https://github.com/Medvedolog/medvetalkie/actions/runs/42370939364)
completed successfully for all four Wi-Fi × Bluetooth source combinations.
Each compiled all three modules (`uwe5622_bsp_sdio`, `sprdwl_ng`,
`sprdbt_tty`) against one pinned Armbian 6.18.60 kernel ABI and verified
AArch64 ELF and matching `vermagic`. Actual full-image kernel compilation,
bootloader and DTB integration, first boot, Bluetooth SCO audio and SDIO
recovery remain untested.
