# UWE5622 / AW859A Bluetooth transport workbench

This directory isolates experimental kernel/Bluetooth transport work from the MedveTalkie application. **Nothing here is built, installed or patched automatically.**

## Why it exists

On Orange Pi Zero 3, built-in AW859A / UWE5622 successfully pairs with AIRIDE N1 and plays A2DP audio, yet HFP CVSD/mSBC produces neither audible output nor nonzero microphone input. eSCO setup succeeds; a 2026-11-06 `btmon` trace contained 595 SCO TX and zero SCO RX.

Full reproduction and environment: [hardware bench report](../../docs/HARDWARE-BENCH-2026-11-06.md).

## Source references

- https://github.com/armbian/uwe5622/tree/master/tty-sdio — `sprdbt_tty` and HCI framing.
- https://github.com/Medvedolog/opiz3-wlan-backport — related WCN/SDIO and Wi-Fi reverse engineering; OpenWrt package does **not** include `sprdbt_tty.ko`.
- Armbian's actual installed module should be mapped to the **exact** build-source revision before preparing a patch; upstream master is only a reference.

## Work items

1. Obtain exact driver revision and source/binary build correspondence.
2. Instrument SDIO receive callback `mtty_rx_cb` with opt-in packet-type and TTY-drop counters, without noisy frame dumps.
3. Verify inbound HCI `0x03` (SCO) handling against HCI controller counters.
4. Fix existing RX overflow queue buffer-ownership issue, then bound worker retries.
5. Validate a reversible kernel-module patch against the exact kernel ABI; retain successful A2DP and Ethernet connectivity.
6. If no SCO is delivered at SDIO ingress, investigate WCN firmware and voice routing instead of blaming the TTY driver without proof.

Directory conventions (populate when real files exist): `patches/` for version-pinned changes; `tests/` for bounded checks; `logs/` for sanitized summaries. **Do not commit raw btsnoop traces or firmware images without reviewing identifiers and redistribution rights.**
