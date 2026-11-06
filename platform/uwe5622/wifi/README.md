# AW859A / UWE5622 Wi-Fi integration for Armbian

Status: **experimental, opt-in manual CP-assert recovery staged**; no driver replacement, no installed udev trigger, no automatic recovery. See [RECOVERY.md](RECOVERY.md) for safety gates.

Target test hardware: Orange Pi Zero 3 / H618, Armbian 26.11.0-trunk.120,
Debian 13, `6.18.60-current-sunxi64`. This kernel identification comes from
the handover and **has not been independently checked on the live board**.

## OpenWrt-to-Armbian mapping

| OpenWrt component | Function | Armbian treatment |
| --- | --- | --- |
| `/lib/uwe5622.sh` | Locate platform phy, SDIO host, module control | Retain dynamic detection; replace UCI/netifd helpers |
| `sprdwl-delay` | Defer BSP and WLAN module loading to preserve Ethernet boot | Design systemd ordering after identifying active network stack and autoload behavior |
| `uwe5622-recover` | Limit CP-assert recovery, unload BSP/WLAN, reset SDIO, reload | Gate behind manual enablement and validated kernel/driver; use flock and persistent reason logs |
| `50-uwe5622-recover` | React to `unisoc_wifi` change event | Verify real uevent; udev must only request a systemd oneshot unit |
| `uwe5622-clamp-htmode` | Avoid unsupported configured channel width | Validate NetworkManager/hostapd capabilities without UCI and avoid restart loops |
| `uwe5622-default-ap` | OpenWrt first-boot AP with publicly known credentials | Do not copy password; generate strong unique credentials at UI request |
| `77-mm-uwe5622-ignore.rules` | Avoid ModemManager probing Wi-Fi | Review installed ModemManager rules before adding an override |

## Read-only inspection

```sh
sh platform/uwe5622/wifi/scripts/uwe5622-preflight status
sh platform/uwe5622/wifi/scripts/uwe5622-preflight dry-run
```

The inventory deliberately does not assume `phy0`, `wlan0`, `mmc1`
or that NetworkManager is installed.

## Safety gates before enabling recovery

1. Collect live `uname -a`, loaded module provenance and hashes,
   `modinfo` vermagic, device tree, exact network manager and systemd units.
2. Determine whether Armbian already contains CP-assert handling.
3. Confirm that the platform `change` uevent uniquely identifies a real
   CP assert; ordinary disconnect must not reset SDIO.
4. Establish a wired SSH recovery path and a rollback procedure.
5. Verify compatibility of the source patch 250 with the exact BSP source.
6. Prove both USB Bluetooth controllers remain unaffected.
7. Only then opt in to udev-initiated recovery; never enable by default.

The original OpenWrt package pins Armbian UWE5622 source commit
`cc2835a3f935d5297e03cdce464c1785381a7b4d`.
The handover also mentions `bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880`.
Neither is proof of the source currently installed on the device.

Reference: https://github.com/Medvedolog/opiz3-wlan-backport

## Kernel ABI inventory (read-only)

Before selecting module sources or staging any driver replacement, capture
the live `modinfo` vermagic, SHA256, `Module.symvers`, compiler and kernel
configuration without making any system changes:

```sh
sh platform/uwe5622/wifi/scripts/uwe5622-abi-check status
sh platform/uwe5622/wifi/scripts/uwe5622-abi-check strict
```

`strict` exits nonzero if the matching build tree or either driver module is
missing or a vermagic kernel-release mismatch is detected. Passing it is a
**necessary but not sufficient** ABI condition: compiler/toolchain differences,
symbol CRCs and installed module source provenance still require review.

See [PATCH-STATUS.md](PATCH-STATUS.md) for the 30-patch matrix and
reproducible GitHub Actions audit.

