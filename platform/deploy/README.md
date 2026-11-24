# In-place deployment of MedveTalkie on Orange Pi Zero 3

This is an opt-in userspace update on an already booted Armbian/Debian 13
Orange Pi Zero 3. No SD-card image is flashed. The installer never alters
/boot, onboard UWE5622 Wi-Fi/Bluetooth module blacklists, Ethernet IP,
access point settings, or Bluetooth pairings.

## 1. Download using Clash/mihomo mixed proxy

Use the HTTP endpoint of your mixed-port listener, not a socks5:// URL.
The example is inherited from the existing Bjorni time-sync configuration.
Allow LAN access to the mixed listener and HTTPS CONNECT on the proxy host.

    PROXY=http://192.168.11.100:10880
    git -c http.proxy="$PROXY" clone --depth 1 \
      --branch work/uwe5622-wifi-armbian \
      https://github.com/Medvedolog/medvetalkie.git
    cd medvetalkie
    bash platform/deploy/install-opiz3.sh --dry-run --proxy "$PROXY"

If you already have a checkout on the Orange Pi, work in that same checkout
and use a fast-forward git pull with the same per-command HTTP proxy;
do not clone or reset a modified directory without checking changes.

## 2. Install Core, Web Alpha, status producer

    sudo bash platform/deploy/install-opiz3.sh --apply --proxy "$PROXY"

This builds the real C11 programs and runs CTest and the standalone Bjorni
render/SPi-simulation regressions BEFORE changing systemd services. It stages
a versioned release under /opt/medvetalkie/releases/ and activates three units:
medvetalkie-core, medvetalkie-status and medvetalkie-web.

The integrated status/Bjorni renderer is installed but NOT automatically
started. To activate it, first stop any older manually launched Bjorni process:

    sudo fuser -v /dev/spidev1.0
    # If a process owns this SPI device, stop it by its original launch method.
    sudo bash platform/deploy/install-opiz3.sh \
      --apply --proxy "$PROXY" --enable-display

With --enable-display, the new single SPI owner displays Russian status
screens and Bjorni in standby. The renderer uses the previously verified
4 MHz SPI and 25 FPS. It runs with --no-sync, so it neither sets system
time nor needs an Internet proxy during operation.

## 3. Verify after installation

    systemctl --no-pager --full status \
      medvetalkie-core medvetalkie-status medvetalkie-web medvetalkie-display

    curl --noproxy '*' -fsS http://127.0.0.1:8765/api/v1/health
    sudo cat /run/medvetalkie/display.status
    journalctl -u medvetalkie-core -u medvetalkie-status \
      -u medvetalkie-display -n 80 --no-pager

Core and status producer run as a dedicated medvetalkie service user. SQLite
is under /var/lib/medvetalkie and the private Unix socket/status snapshot
under /run/medvetalkie. The display renderer runs as root only to access
SPI/GPIO. The Web Alpha process is still read-only and binds exclusively
to 127.0.0.1:8765, NEVER to LAN. To inspect remotely from a trusted desktop:

    ssh -L 8765:127.0.0.1:8765 root@192.168.11.1

Then open http://127.0.0.1:8765/ on that desktop. The Ethernet address
shown is the test bench convention, not installed or changed by the script.

## 4. Simulate installation and roll back

The no-root simulator stages the release, unit files and binaries in a
temporary filesystem and exercises real CMake, CTest, Core-to-PPM and
Bjorni/ST7789 regression tests, without reaching any actual SPI, BlueZ
or systemd service:

    mkdir -p /tmp/medvetalkie-deploy-sim
    bash platform/deploy/install-opiz3.sh \
      --simulate /tmp/medvetalkie-deploy-sim --proxy "$PROXY"

Repeated real deployments retain the prior managed release and backup
existing managed systemd units in /var/backups/medvetalkie/. A failed
service activation triggers an attempt to restore the prior release and
unit files. After a second deployment, the previous version can also be
selected explicitly:

    sudo bash platform/deploy/install-opiz3.sh --rollback

Rollback is not an OS restore; it cannot reverse independently installed
software, changes to an SD image, or unrelated system services. The
installer deliberately does not make those modifications.

## 5. Current technical limitations

- The installed WebUI is read-only, loopback-only and unauthenticated;
  it is NOT a finished configuration web app available at 192.168.11.1.
- Two USB UGREEN Bluetooth controllers can be inventoried through
  sysfs/BlueZ. Actual two-way HFP/SCO/eSCO, audio signal paths and
  headset roles remain UNVERIFIED.
- SQLite stores desired display settings but does not dynamically
  apply them to ST7789; the display unit currently uses fixed 4 MHz/25 FPS.
- Source download via git and package installation via APT use the
  mixed proxy only for the corresponding commands. No persistent
  global APT, system-wide proxy or network settings are changed.
- CI simulation and PPM pixel checks do NOT replace the physical
  Orange Pi Zero 3 deployment gate and on-screen inspection.
