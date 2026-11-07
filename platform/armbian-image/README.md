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

## GitHub Actions and home Windows / WSL2 runner

The user-managed home PC has an x86-64 Ryzen CPU. Do **not** request ARM64
labels for that computer: compile the ARM64 Armbian image through Armbian's
supported x86-64 build container. GitHub guarantees 14 GiB of storage for standard Ubuntu VMs, but an actual
GitHub-hosted `ubuntu-24.04` probe on 2026-11-07 found **86 GiB free**, 15 GiB
RAM and working Docker. The build pipeline therefore supports both hosted
and home Linux/X64 runners and refuses to build if the real disk check fails.

### Self-hosted runner installation / discovery

Runner registration is **scoped to a GitHub repository** for a personal
account. A runner registered to `Medvedolog/medvewrt` does **not**
automatically run jobs for `Medvedolog/medvetalkie`.

Open [MedveTalkie's runner settings](https://github.com/Medvedolog/medvetalkie/settings/actions/runners)
and check registered runners. The full image workflow needs this exact
set of labels:

```
self-hosted, Linux, X64, armbian-image
```

Use WSL2 (Debian 13 preferred), or native Linux, **not** a native Windows
runner. Create a *separate* GitHub runner installation for the MedveTalkie
repository if the home machine currently runs only `medvewrt` jobs.
GitHub's Settings > Actions > Runners > New self-hosted runner
page provides the current installer version and a short-lived local
registration token. **Do not post that token in chat or commit it.**
During registration add the custom `armbian-image` label.

Windows-side inventory script (read-only):

```powershell
powershell -ExecutionPolicy Bypass -File platform/armbian-image/inspect-runners-windows.ps1
```

Linux / WSL2 resources probe, run with a Linux `ext4` workspace:

```bash
bash platform/armbian-image/home-runner-preflight.sh "$HOME"
```

This checks 8 GiB assigned Linux RAM, 50 GiB free *inside the exact build
filesystem*, Docker, `sudo -n` and build prerequisites. WSL2 users must
also ensure sufficient free space on the physical Windows drive hosting its
VHDX. It does not modify runner services or the system.

### Launching from the draft PR branch

[Workflow](../../.github/workflows/armbian-full-image.yml) provides a
read-only *home-runner-probe* triggered by a trusted branch push whose
commit message contains `[armbian-home-probe]`. If its job remains queued,
the expected Linux/X64 runner with `armbian-image` is not presently
available to this repository. Being queued does not establish whether the
runner is offline, busy, mislabelled or registered elsewhere.

The two **full** images are requested only by a trusted branch push with
`[armbian-hosted-build]` (GitHub-hosted x64) or `[armbian-home-build]`
(home WSL2 runner) in the commit message, or manual `workflow_dispatch`
once the workflow exists on the default branch. The matrix uses
`max-parallel: 1`:

- AP+STA Wi-Fi + unmodified upstream SDIO Bluetooth transport
- AP+STA Wi-Fi + two experimental `sprdbt_tty` fixes

The original bootable Armbian microSD remains the safety fallback.
No full-image build is triggered by ordinary pushes. Never enable
untrusted pull requests to execute commands on a personal self-hosted
runner, particularly one with Docker/sudo access. For a public repository,
treat this builder as disposable and isolate it from personal files and
secrets. Self-hosted runners cannot be guaranteed to be as isolated as
GitHub-hosted VMs.


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

## Full build-workspace staging smoke test

[GitHub Actions run 42371121890](https://github.com/Medvedolog/medvetalkie/actions/runs/42371121890)
passed the four patch combinations and staged the **actual pinned Armbian
build tree**, prepared the combined patched UWE5622 source and copied the
extension, recovery scripts and build manifest. It **did not compile an
Armbian `.img`**, and this smoke test must not be described as a firmware
release.
