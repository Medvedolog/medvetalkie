# Staged UWE5622 CP-assert recovery — Armbian

**EXPERIMENTAL: do not deploy or enable on the hardware yet.**

This recovery is intentionally manual-only until a live Armbian capture proves
which `unisoc_wifi` events unequivocally indicate a firmware CP assert.
A disconnected hotspot, DNS failure or loss of Internet is **not** an assert.

## Read-only checks

```sh
sh platform/uwe5622/wifi/scripts/uwe5622-preflight status
sh platform/uwe5622/wifi/scripts/uwe5622-recover status
sh platform/uwe5622/wifi/scripts/uwe5622-recover dry-run
systemctl is-active NetworkManager systemd-networkd wpa_supplicant hostapd || :
journalctl -k -b --no-pager | grep -Ei 'uwe5622|unisoc|sprdwl|marlin|cp assert|sdio' | tail -100
udevadm info -a -p /sys/bus/platform/devices/unisoc_wifi 2>/dev/null || :
```

Capture the actual kernel release, `modinfo -F vermagic` for **both**
modules, loaded module paths, firmware version, device-tree path, and boot
network manager before ANY recovery trial.

## Explicit future test procedure (only with Ethernet/serial rescue)

1. Ensure a physical recovery route and copy existing .ko files and network configuration.
2. Verify patch 250's BSP SDIO unregister behavior applies to the installed module.
3. On the **test board only**, stage the script at
   `/usr/local/sbin/uwe5622-recover` and the service at
   `/etc/systemd/system/medvetalkie-uwe5622-recover.service`.
4. The service deliberately has no `[Install]` section. Do **not** call
   `systemctl enable`.
5. Only after verifying a **real CP assert** create
   `/etc/medvetalkie/allow-uwe5622-sdio-reset` and explicitly run
   `sudo systemctl start medvetalkie-uwe5622-recover.service`.
6. Inspect `journalctl -t uwe5622-recover -b` and
   `systemctl status medvetalkie-uwe5622-recover.service`.
7. Test failure injection in an isolated lab setup, never during a remote-only SSH session.

The script attempts no more than three recoveries within 1800 seconds,
stores the timestamps under `/var/lib/medvetalkie/uwe5622/`, and uses a
nonblocking flock lock. It will **not** reset an ambiguous SDIO host.
The service performs neither network-manager restarts nor BT operations.

### Rollback

```sh
sudo rm -f /etc/medvetalkie/allow-uwe5622-sdio-reset
sudo systemctl stop medvetalkie-uwe5622-recover.service || :
sudo rm -f /etc/systemd/system/medvetalkie-uwe5622-recover.service
sudo systemctl daemon-reload
```

If modules have already been unloaded and Wi-Fi did not recover, use the
established local rescue/physical reboot route. **Do not try repeated SDIO
resets.** No `udev` rule should be installed until validated.

## Important limits

- The service is deliberately not a boot/startup solution. A separately
  validated deferred-load service is needed if this Armbian installation
  actually autoloads BSP too early.
- The script assumes the installed BSP can unload cleanly; this is **unproven**.
- Android STA / AP may require network-manager reconfiguration after recovery;
  no automatic network-manager change is attempted.
- No claim of successful hardware recovery or ABI-safe kernel modules is made.
