# Orange Pi Zero 3: experimental HFP kernel module trial

**Kernel:** `6.18.60-current-sunxi64`, **hardware:** AW859A / UWE5622.
**Status:** GitHub Actions build **passed**, physical HFP trial **pending**.

## CI result

Workflow: https://github.com/Medvedolog/medvetalkie/actions/runs/42223637527

Artifact: `sprdbt-tty-arm64-6.18.60-experimental` (ZIP).
Its contents include `sprdbt_tty.ko`, `SHA256SUMS`, `modinfo.txt`,
and `UWE5622_SOURCE_COMMIT`.

Build used native ARM64 Debian trixie / GCC 14, archived Armbian kernel
headers `26.11.0-trunk.120`, and source commit
`bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880`.
Both patches applied and the workflow passed modpost and vermagic checks.
**This does not establish device-level compatibility, HFP functionality, or
exact equivalence with the Armbian driver source that built the stock module.**

## Transfer from PC

1. Open the successful workflow in GitHub while signed in.
2. Download the ZIP from the Artifacts section. Inspect/extract locally.
3. Send the ZIP to the board using ordinary LAN SSH/SCP. For example, from
   a PC with OpenSSH, substitute the real local file path:

   ```sh
   scp sprdbt-tty-arm64-6.18.60-experimental.zip root@192.168.1.200:/root/medvetalkie-build/
   ```

   This is the **test bench's recorded LAN IP**, not a general default.

## Read-only preflight on the board

```sh
cd /root/medvetalkie-build
mkdir -p artifact
unzip -o sprdbt-tty-arm64-6.18.60-experimental.zip -d artifact
(cd artifact && sha256sum -c SHA256SUMS)
uname -r
modinfo -n sprdbt_tty
modinfo -F vermagic "$(modinfo -n sprdbt_tty)"
modinfo -F vermagic artifact/sprdbt_tty.ko
modinfo -F depends artifact/sprdbt_tty.ko
```

Download the version-controlled helper via the known SOCKS5h proxy:

```sh
curl -fLsS --proxy socks5h://192.168.1.112:10880 \
  -o /root/medvetalkie-build/deploy-sprdbt-tty.sh \
  https://raw.githubusercontent.com/Medvedolog/medvetalkie/main/platform/uwe5622/tests/deploy-sprdbt-tty.sh

sh /root/medvetalkie-build/deploy-sprdbt-tty.sh \
  preflight /root/medvetalkie-build/artifact/sprdbt_tty.ko
```

**Stop here and inspect output**. A `preflight PASS` means only that
module name/full `vermagic` matches. Source-specific symbol versions and
behaviour still need testing. Confirm an independent SSH/Ethernet access path
before continuing.

## Explicit opt-in install

Only during a maintenance window, and only after reviewing preflight output:

```sh
sh /root/medvetalkie-build/deploy-sprdbt-tty.sh \
  install /root/medvetalkie-build/artifact/sprdbt_tty.ko
sh /root/medvetalkie-build/deploy-sprdbt-tty.sh status
```

This installs a separate override
`/lib/modules/6.18.60-current-sunxi64/updates/medvetalkie/sprdbt_tty.ko`,
runs `depmod`, and verifies `modinfo -n sprdbt_tty` points to the override.
It does **not** overwrite the stock module, call `rmmod`, restart the active
Bluetooth service, or reboot. **A separate manual reboot is required.**

## Tests after manual reboot

1. Confirm SSH over Ethernet still works and that
   `modinfo -n sprdbt_tty` points into `updates/medvetalkie/`.
2. Confirm `hci0`, normal pairing/connection and previously audible A2DP.
   No usable `hci0` means **stop and roll back**.
3. Find counter file:

   ```sh
   find /sys/devices -name hci_rx_stats -print
   hciconfig -a hci0
   ```

4. Read the discovered `hci_rx_stats` before HFP activation, keep the test
   running for five seconds, then read again. Use both mSBC and CVSD when
   switching profiles. Inspect `first_h4_sco`, `tty_partial`, `queued`,
   and `queue_alloc_fail`. Collect `btmon` SCO TX/RX independently.

Counter caveat: these are counts of the *first* H4 packet type per SDIO block,
not a full HCI parser. Zero `first_h4_sco` **does not prove** absence of any
SCO data embedded beyond the first H4 frame. It also does not establish
whether outbound audio physically reaches the helmet headset.

## Rollback (available without an Internet connection)

```sh
sh /root/medvetalkie-build/deploy-sprdbt-tty.sh rollback
# After verifying modinfo -n sprdbt_tty points to the original:
reboot
```

Rollback removes only the dedicated override and regenerates module indexes;
it checks the untouched stock module against the saved original hash.
If SSH becomes unavailable, local serial/UART or filesystem recovery may
be needed. **Do not assume rollback is automatic.**

## Report back

Provide `preflight` output first. After activation report
`modinfo -n sprdbt_tty`, `hciconfig -a hci0`, both readings of
`hci_rx_stats`, plus whether A2DP and HFP audio are audible.
Do not post raw btsnoop files publicly without sanitizing device identifiers.
