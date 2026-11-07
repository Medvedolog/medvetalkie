# Experimental WLAN+BSP ARM64 builds — not installable without board validation

The GitHub Actions workflow
[`uwe5622-wifi-modules.yml`](../../../.github/workflows/uwe5622-wifi-modules.yml)
builds **only** `uwe5622_bsp_sdio.ko` and `sprdwl_ng.ko` on a native
ARM64 runner with the official Armbian 26.11.0-trunk.120 header package
for `6.18.60-current-sunxi64`. The current headers package hash observed
during CI and now enforced before package installation is
`ff5247313924b0851af4983466483050b25a2434aa65f9acae99631c1c999cc6`.

## Immutable source selection

| Input | Pinned revision |
|---|---|
| `armbian/uwe5622` | `bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880` |
| `Medvedolog/opiz3-wlan-backport` | `29b6faf6b08a2b62097e509eb0fa62720ab48996` |
| Armbian headers | `linux-headers-current-sunxi64` 26.11.0-trunk.120, 6.18.60-current-sunxi64 |

These revisions describe the **build experiment**, not proof that the
installed Orange Pi Zero 3 kernel modules come from the same commit.

## Build profiles

| Profile | Patches | Intended use |
|---|---|---|
| `p0` | 030, 130, 160, 190, 220, 250, 330; 070 already in upstream | Kernel safety and recovery prerequisites, without diagnostics-only patch 150 |
| `apsta` | `p0` plus 180, 200, 290, 310 | 5 GHz AP, channel limits, per-interface MAC and AP+STA teardown |

Armbian-specific rebases are stored in
[`patches/`](patches/). These remove incidental dependencies on
OpenWrt-only or diagnostics-only changes rather than silently importing
all 30 patches.

## Controlled build process

1. Check out two Git repositories at pinned commits and require the
   original source tree to be clean.
2. Verify kernel headers, release string and `Module.symvers`.
3. Check and apply selected patches with `git apply --recount`, aborting
   on the first conflict.
4. Compile BSP first; compile WLAN second, pointing
   `KBUILD_EXTRA_SYMBOLS` to BSP's matching `Module.symvers`.
5. Validate ELF AArch64 architecture and first `vermagic` token.
6. Upload both `.ko` files with source commit IDs, patch manifest,
   SHA256 hashes and conspicuous experimental warning.

No `dkms install`, `depmod`, `modprobe`, SDIO reset, firmware replacement
or file writes to the running board occur in GitHub Actions.

## Validation still needed on the actual board

Run these from the matching MedveTalkie checkout:

```bash
sh platform/uwe5622/wifi/scripts/uwe5622-preflight status
sh platform/uwe5622/wifi/scripts/uwe5622-abi-check strict
```

Capture the output without altering the installed modules. Match
`uname -r`, build-tree configuration, `Module.symvers`, loaded module
`modinfo`, toolchain, dependencies, and firmware path. Compare hashes of
original modules and retain a physical/serial recovery route before any
test installation.

**A green CI build does not demonstrate that an ARM64 module is safe for
a specific board.** The full-duplex BT subsystem remains out of scope.

## Confirmed GitHub Actions result

Native ARM64 compilation of both profiles succeeded in [SHA256-pinned run 42297748346](https://github.com/Medvedolog/medvetalkie/actions/runs/42297748346). The workflow produced `uwe5622_bsp_sdio.ko` and `sprdwl_ng.ko`, checked the first `vermagic` token and AArch64 ELF header, and uploaded quarantined artifacts. This is **build validation only**, not hardware validation or proof that the board uses the same kernel configuration and driver provenance.
