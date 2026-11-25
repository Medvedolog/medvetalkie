# MedveTalkie — development handoff

**As of:** 2026-11-24  
**Canonical handoff:** `docs/HANDOFF.md` on `work/uwe5622-wifi-armbian`.  
**Status:** Core/Web/UI and ST7789 code integrated into the Armbian work branch (2026-11-24); **joint CI passed 10/10 tests and the separate ST7789 rendering suite**. **Actual image deployment and full-duplex HFP are NOT proven**.

## 1. Working agreement — do not create branches for each iteration

- **Primary hardware/image/display integration:** `work/uwe5622-wifi-armbian` ([Draft PR #1](https://github.com/Medvedolog/medvetalkie/pull/1)).
- **Core API / Web Alpha / SQLite / BlueZ / display status producer:** ported and reconciled into `work/uwe5622-wifi-armbian` with the ST7789 renderer. The historical `feature/web-alpha-usb-diagnostics` ([PR #2](https://github.com/Medvedolog/medvetalkie/pull/2)) is superseded and must not receive further commits.
- `main` stays untouched until integrated tests and agreed release gates pass. `experimental/armbian-wifi-backport` is retained historical experimentation, **not** a branch for new display/API work.
- **Do not spawn a branch per iteration, test or subsystem.** All new MedveTalkie work goes into `work/uwe5622-wifi-armbian` until the release gate. PR #2 was not automatically mergeable; all required files were deliberately ported while preserving Armbian image and SPI code. PR #2 is closed/superseded following the passing combined CI; **do not auto-merge its duplicate history**.
- **Update this handoff with every substantive change**, including commit SHA, affected components, CI run, regression evidence, remaining risks and exact next action. PR descriptions/README are supporting material, not substitutes.

## 2. Hardware actually observed on the physical board

- Orange Pi Zero 3 / Allwinner H618, Armbian Debian 13, kernel `6.18.64-current-sunxi64` has booted in previous bench sessions; Ethernet `end0` working.
- MSP2008 ST7789 320×240 SPI display on `/dev/spidev1.0`, PC5/DC, PC6/RESET. The **original Bjorni** animation/clock has been physically observed with SPI 4 MHz and approximately 24–25 FPS.
- Two UGREEN CM390 / Actions ATS2851 USB BT controllers, VID:PID `10d7:b012`, enumerated through a USB hub/BlueZ. **Actual dual HFP/SCO/eSCO full duplex was not verified.**
- Built-in AW859A/UWE5622 modules were disabled in the operator's test boot using `module_blacklist=sprdwl_ng,sprdbt_tty,uwe5622_bsp_sdio`; reported freezes stopped/reduced, but long-duration proof is pending. Main stability profile: **wired Ethernet + USB Bluetooth**, no assumption that onboard WLAN AP is available.
- Do **not** claim the newly coded status-screen transition or Core API ran on the physical ST7789/board. Only earlier standalone Bjorni is hardware-verified.

## 3. Current implementation and separate CI proof

| Layer | Branch | Implemented now | Test/proof | Limits |
| --- | --- | --- | --- | --- |
| Core API | `feature/web-alpha-usb-diagnostics` | C11, versioned JSON/AF_UNIX with length framing, 64-KiB bound, same-UID `SO_PEERCRED` | `core_ipc_protocol` | No production access-policy model, subscriptions or hardware commands |
| Settings | feature branch | SQLite v1, `settings.get`, local gated `settings.patch` with CAS revision | `settings_sqlite` | Saves **desired** settings only; does not apply them |
| USB/HCI | feature branch | `bt.controllers` from kernel sysfs, USB physical port/VID/PID | `bt_inventory_sysfs`: two identical UGREEN fixtures, hot-unplug | Does not prove actual HFP or stable role assignment |
| BlueZ | feature branch | Read-only `bt.bluez`, `GetManagedObjects`, `Adapter1` / `Device1` | `bluez_dbus_parser` synthetic D-Bus message | `Paired`/`Connected` are not usable SCO/HFP audio |
| WebUI | feature branch | Separate loopback-only CivetWeb, read-only status/configuration/Bluetooth | `web_health`, real local HTTP->IPC, error responses | Not authenticated for LAN; never expose to untrusted network |
| Display runner | feature branch | Reads desired SPI/FPS settings and starts trusted Bjorni script when explicitly enabled | `display_runner_bridge`: fake-script/process test | Not auto-start or hot reload; not an integrated display service |
| Display status producer | feature branch | `medvetalkie-display-status` reads Core + passive BT state, writes atomic `MTSTATUS1` snapshot | `display_status_agent`: mocked IPC, offline/error/BT states, file permissions | No headset role binding, audio readiness, or display ownership |
| ST7789 status + Bjorni | `work/uwe5622-wifi-armbian` | **One SPI/GPIO owning renderer**; Russian dashboard, startup/state/error screens, return to Bjorni after 8 s in idle | `platform/display/screensaver/test-screensaver.py`: PPM previews, SPI `write/ioctl` wrappers, mock supervisor, launcher rebuild | New integrated status switching **not physically validated** |
| Image / WLAN backport | work branch | Armbian image scripting, selected UWE5622 patches, optional disabled onboard modules | CI build/module/patch checks from previous milestones | No claim new UI/API has been shipped in that image |

**Confirmed separate CI evidence, 2026-11-24:**
- [ST7789 renderer + status screen, GitHub Actions run 45483412806](https://github.com/Medvedolog/medvetalkie/actions/runs/45483412806): build and `test-screensaver.py` passed. Tests include status preview (Russian labels, faults, invalid/stale feed), SPI fake-write behavior, deterministic launcher generation and Bjorni render.
- [Core + IPC/SQLite/BlueZ + display status agent, run 45483547876](https://github.com/Medvedolog/medvetalkie/actions/runs/45483547876): **9/9 CTest suites passed**.
- **Unified CI:** [GitHub Actions 45484817825](https://github.com/Medvedolog/medvetalkie/actions/runs/45484817825) passed the combined checkout: **10/10 CTest** (including `core_display_ppm_e2e`) and **ST7789/Bjorni test-screensaver.py** (Russian status screen, invalid/stale feed, mock SPI, GIF rendering, launcher determinism, supervisor cleanup). This confirms the complete **software-simulated** pipeline, not physical SPI, hardware HFP or integration into a flashed Armbian image.

## 4. Status screen contract and transition policy

The technical-spec baseline is [MedveTalkie TZ v1.4](MedveTalkie_TZ_v1.4.md), especially section 9 and the API/isolated processes sections. Because the **full** runtime state machine isn't implemented, the initial dashboard uses a conservative subset:
- Mode, headset 1 and 2 placeholders, voice/HFP state, network, USB-BT and connected-ACL counts, radio availability, battery placeholder and fault banner.
- **Never equate** kernel-HCI presence, BlueZ `Connected=true`, or saved SQLite desired state with `HFP_READY`. Actual bidirectional SCO audio and PipeWire source/sink must be verified.
- Status transport: producer writes a private, atomically replaced, version-tagged `MTSTATUS1` text snapshot; renderer reads a strict enum-only format. Reject malformed or older-than-12-s data as Core unavailable, not a stale green status.
- When `mode=STANDBY`, `fault=NONE`, display the dashboard for **8 seconds** after start/change and then return to Bjorni; active modes, faults and stale data keep status visible. Dashboard ≈2 FPS; animated Bjorni retains the configured frame cap. Only one owner of `/dev/spidev1.0`/GPIO.
- **Important limitation:** the prototype producer maps `effective_mode=UNKNOWN, desired_mode=UNSET` to a **UI-only idle label** `STANDBY`. This is not authoritative proof of a real core standby state; replace it with a real `mode` event before product release.
- Physical buttons, RSSI, actual battery %, route/profile indicators and observed SCO/PipeWire graph are still missing. Avoid fabricated values.

## 5. Testing policy: each code layer has a fail-closed CI gate

1. **Unit and protocol:** malformed versions/frames, limits, concurrent IPC, schema migration, CAS conflicts, signed/unsigned bounds.
2. **Fixtures:** mock two identical ATS2851 adapters at distinct USB paths, simulate detach; fake BlueZ ObjectManager with `Paired/Connected` but **not** HFP-ready.
3. **HTTP integration:** run real core/web processes and verify actual responses, including 503 with missing core or BlueZ; no unauthenticated writes.
4. **Display simulation:** render to 320×240 PPM without GPIO/root; test explicit screen states, idle transition policies, pixel changes and deterministic self-contained launcher; mock SPI operations and process cleanup. Do not call this a full emulation of ST7789 electrical timing, Orange Pi H618 or a Bluetooth RF/audio link.
5. **Crash/recovery:** inject missing core, malformed/stale status, BlueZ outage, interrupted process and restart; verify fail-closed behavior and absence of orphan children or lingering false success.
6. **Hardware gate:** on Orange Pi verify screen transitions, one SPI/GPIO owner, 4-MHz/25-FPS behavior, USB-BT identity across reboot, actual BlueZ observed snapshots and HFP/SCO mic+speaker. Measure audio underruns, display CPU/RSS, run-time stability, error recovery.
7. **No green CI => no merge/release; no hardware confirmation => label NOT_VERIFIED**, even when all fixtures pass. Add a test for every regression before fixing it.

## 6. Next tasks (priority order)

1. **COMPLETED (software):** consolidated Core/Web/SQLite/BlueZ/Display into `work/uwe5622-wifi-armbian`, reconciled CMake/CI/docs, and closed the superseded PR #2 without touching `main`. The onboard module blacklist and existing Bjorni animation remain preserved.
2. **COMPLETED (CI):** both `ctest` and `platform/display/screensaver/test-screensaver.py` ran in one checkout. `core_display_ppm_e2e` covers `Core API -> display-status producer -> MTSTATUS1 -> ST7789 PPM preview` and fault after Core termination. [Run 45484817825](https://github.com/Medvedolog/medvetalkie/actions/runs/45484817825) passed 10/10 CTest and display regressions.
3. Provide a **single systemd-controlled display pipeline** with Core IPC and one SPI/GPIO owner; no untested boot autorun. Use `RuntimeDirectory`, `StateDirectory` and bounded restart policy. Verify ownership when producer and SPI renderer run as different users.
4. Test the complete status UI on the physical Orange Pi with UGREEN installed and builtin WLAN/BT blacklisted; verify fault/standby transitions and no interference with the existing Bjorni animation.
5. Upgrade the state model: explicit STANDBY, assigned headset roles, real HFP/SCO/PipeWire feedback, battery when available, controls, authorized LAN WebUI. Never expose loopback-only alpha to Ethernet before authentication.
6. Only after physical validation: integrate into an image build, verify launch/reboot/rollback, then consider promotion toward `main`.

## 7. Operational precautions

- Keep the live Orange Pi SD card unchanged until unified CI and a recoverable image are ready; maintain serial/Ethernet rollback. `main` remains unchanged.
- `medvetalkie-web` still binds `127.0.0.1:8765`; never open it to `0.0.0.0` before authentication, session/CSRF controls and privilege separation.
- `medvetalkie-display-status` writes file `0600`: ensure the display renderer has read access via an explicitly validated service identity or appropriate mode/ACL; do not blindly loosen permission.
- Separate physical **observed** state from SQLite **desired** state. The GUI may show a saved SPI value even if ST7789 did not apply it.
- Status indicator `BT_FAILED` currently denotes an unavailable BT observation or missing USB controller, not proof of an HFP session failure. This must be refined once role-aware BT/audio observation is implemented.

## 8. Integration implementation log — 2026-11-24

- Continued in the **existing** `work/uwe5622-wifi-armbian`, not a new branch.
- Ported IPC transport, SQLite, BlueZ D-Bus/system inventory, read-only Web Alpha, display settings runner, display-status producer and tests from the feature branch. Deliberately updated the core main entry point and CMake. Preserved native Armbian image scripts and Bjorni ST7789 renderer.
- Combined `.github/workflows/build.yml`: install CivetWeb, json-c, sqlite3 and libdbus; C11 CMake build, all Core CTest cases, ST7789/Bjorni/status screen regression in the **same checkout**.
- Added `tests/test_display_e2e.py` as a **no-GPIO/no-radio integration test**. It invokes the real Core, the real status-publisher IPC binary, and the actual self-contained Bjorni renderer with `--preview`; asserts fail-closed `CORE_OFFLINE` after killing Core. It does not prove SPI electrical timing or HFP audio.
- Reconciled `docs/IPC.md`, architecture description, TZ v1.4 appendices, and README. Independent source branch/PR retained only temporarily until green CI confirms integration.
- **Combined CI gate PASSED:** [run 45484817825](https://github.com/Medvedolog/medvetalkie/actions/runs/45484817825) — 10/10 CTest and separate Bjorni renderer regressions. **Next gate: physical Orange Pi** with a single SPI owner, UGREEN/BlueZ, Bjorni/status transitions. Live Orange Pi and `main` were not modified.


## 9. In-place Armbian deployment through mixed proxy — 2026-11-24

- Added one installer in the existing branch:
  [platform/deploy/install-opiz3.sh](../platform/deploy/install-opiz3.sh).
  Canonical operator instructions:
  [platform/deploy/README.md](../platform/deploy/README.md).
- A Clash/mihomo **mixed listener** is used through its **HTTP** proxy endpoint.
  Default borrowed from the existing Bjorni configuration:
  http://192.168.11.100:10880. Override with --proxy. No global proxy,
  permanent APT configuration or local API proxying. For git clone/pull,
  explicitly use git -c http.proxy=URL outside the installer.
- Installer supports default **read-only --dry-run**, real --apply, and
  **--simulate ABS_PATH** to build/test and stage an installation into
  a temporary filesystem with no root, APT or live systemd changes.
  Versioned releases are stored under /opt/medvetalkie/releases with
  current/previous pointers; systemd units are backed up before activation
  and failed activation attempts restore the managed definitions/pointer.
  Explicit --rollback selects the previous managed release.
- Service split: medvetalkie-core, medvetalkie-status and medvetalkie-web
  run as a dedicated non-login medvetalkie user. Core owns the private
  RuntimeDirectory/StateDirectory, status has only the explicit runtime
  snapshot WritePath. The renderer runs as root solely because the
  standalone ST7789 script requires SPI/GPIO and is **opt-in**
  (--enable-display). It does not replace or kill unmanaged SPI processes.
  Read-only Web Alpha remains 127.0.0.1:8765 only.
- The new unit files do not change kernel modules, built-in radio blacklist,
  Ethernet configuration, BlueZ pairings or /boot. The renderer is
  explicitly started with --no-sync and fixed previously tested 4 MHz/25 FPS.
  The desired SQLite settings do **not** yet apply live to the display.
- **CI validated:** [combined Actions run 45485960174](https://github.com/Medvedolog/medvetalkie/actions/runs/45485960174)
  passed CMake build, all **10/10 CTest** suites, standalone
  Bjorni/ST7789 regressions, and the new
  tests/test_deploy_installer.py: proxy argument validation, dry-run,
  staged installation of actual binaries + systemd files, second release,
  rollback, and refusal to overwrite unmanaged units.
- **NOT physically validated:** no installer execution yet on the
  operator's actual Orange Pi Zero 3. Before enabling renderer, stop the
  old manually launched Bjorni and verify /dev/spidev1.0 ownership.
  Verify systemctl status, health endpoint, status file, 8-second idle
  transition, real two UGREEN controller inventory, no repeated
  Bluetooth disconnects, and stable wired LAN. HFP/SCO still unverified.
  Do not claim physical readiness or merge to main on CI alone.
- Continue with **one** active branch work/uwe5622-wifi-armbian; no new
  integration branches. Update this handoff after first physical trial
  with actual command output, observed failures, and rollback decision.


## 10. First real Orange Pi Zero 3 deployment attempt — 2026-11-25

Operator provided a complete shell log from the physical test board
(`root@orangepizero3`) after the initial one-shot install. This is the
first direct hardware execution evidence for the in-place installer.

**Observed:**

- `git clone` through mixed HTTP proxy `192.168.11.100:10880` worked;
  branch `work/uwe5622-wifi-armbian` was up to date; `--dry-run` passed.
- The real `--apply` downloaded and installed 21 development packages
  (17 MB archive total) and compiled **all** C11 binaries on ARM64,
  using GCC 14.2, SQLite 3.46.1, D-Bus 1.16.2 and Python 3.13.5.
- Real board CTest passed **9/10** suites; `web_health` failed because it
  expected HTTP 503 from an unavailable BlueZ, while the **real board
  has responding BlueZ** and returned HTTP 200. This is a test-isolation
  bug, not evidence that the USB adapters or HFP/SCO are working.
- Because CTest failed, the installer did **not** deploy binaries or
  activate systemd services. There is no verified display transition yet.
- APT `sqv` also reported several Debian `InRelease` records as
  **Not live until 2026-11-25 07:xx UTC** (system wall clock was too
  early for their validity interval) and a missing Armbian signing key
  `DF00FAF1C577104B50BF1D0093D6889F9F0E78D5`. Despite this,
  `apt-get update` continued with cached indexes and package install
  succeeded. This is an **independent trust/clock fault**; never
  disable signing checks or automatically import an unverified key.

**Corrections committed in the existing work branch:**

- `medvetalkie-web --listen-port` selects another **loopback-only**
  HTTP port for tests; deployed systemd service continues at 8765.
  The test uses 18765 to avoid colliding with a previously installed
  service on repeat deployments.
- Web regression test starts its test-only Core with an intentionally
  inaccessible `DBUS_SYSTEM_BUS_ADDRESS`. It must observe HTTP 503
  independently of the physical board's functioning `bluetoothd`.
  The synthetic D-Bus parser test covers observed/successful objects.
- Installer now fails closed on APT partial signature failures, missing
  signing keys, stale-cache warnings and future-dated metadata, even
  when `apt-get update` returns exit 0.
  `platform/deploy/verify-apt-log.sh` is independently exercised against
  warning fixtures in `tests/test_deploy_installer.py`.
- All source changes remain in `work/uwe5622-wifi-armbian`; no new
  branches, no changes to /boot, Ethernet or module blacklist.

**Next physical procedure (only after combined CI is green):**

1. Check `date -u`, `timedatectl status` and reliable time sync.
   Verify the missing Armbian key through official signed vendor docs
   rather than disabling APT authentication.
2. Since the development dependencies were installed successfully on
   this particular board, reuse them and re-run the updated installer
   with `--apply --skip-packages` to avoid relying on currently
   untrusted APT indexes. This does **not** fix APT itself.
3. First run without `--enable-display`, verify Core/status/web
   services, `/run/medvetalkie/display.status`, BlueZ snapshots and
   actual USB adapter inventory. On successful validation, verify
   `/dev/spidev1.0` is free before explicitly enabling ST7789.
4. Record actual service status, active unit logs, two UGREEN identities,
   screen switching, crashes and rollback in this handoff.

**CI validation of fixes:** [GitHub Actions 45599477992](https://github.com/Medvedolog/medvetalkie/actions/runs/45599477992) passed **10/10 CTest**, Bjorni/ST7789 status-screen regression suite, and staged deployment/rollback simulator with new APT-signature-warning fixtures. The `web_health` fix passes in the GitHub runner; the **second physical-board run has not yet been performed**. Do not claim successful second physical installation until user logs confirm it.

## 11. Second physical OPiZ3 deployment attempt — 2026-11-25

**Observed from operator's SSH log:**

- `git pull --ff-only` advanced to `38a5894`.
- `date -u` remained at **2026-11-24 18:02:23 UTC**; `timedatectl`
  reported `System clock synchronized: no`, active NTP service, and
  an RTC reading in **1970**. The APT clock/key issue is still unresolved.
- Installer `--apply --skip-packages` ran fully on the physical
  ARM64 board: **10/10 CTest passed**, Bjorni/ST7789 render, pixel/SPI,
  time-sync mocks, supervisor and launcher regressions all passed.
- After staging, the three systemd services were enabled/started but the
  `http://127.0.0.1:8765/api/v1/health` endpoint failed to report
  `core=reachable`; installer invoked the rollback handler.
  **No systemd journal, HTTP response or exit statuses were included.**
  Actual cause must still be verified from service logs. The new display
  was not enabled.

**Concrete code defect found by postmortem review:** The installer
ran with `umask 077`, used `mkdir -p /opt/medvetalkie/releases` and
`mktemp -d` for releases, and then moved the **0700 root-owned**
directory into the active release path. The `medvetalkie-core`,
`medvetalkie-status` and `medvetalkie-web` units run as
`User=medvetalkie`, so they could not traverse the `/opt/medvetalkie`
releases or execute the installed binaries. This is a sufficient
explanation for the failed health check, although journal confirmation
remains outstanding.

**Fixes in the existing work branch:**

- Only the **public program** directories (`/opt/medvetalkie`,
  `releases`, the versioned release, `bin`) are mode `0755`;
  executable binaries are `0755`, manifest and self-contained Bjorni
  script are `0644`. No change to `/var/lib/medvetalkie`,
  `/run/medvetalkie`, service credentials, or backup privacy.
- Installer runs `runuser -u medvetalkie -- test -x` against each
  installed Core/Web/status executable before switching the current
  symlink to that version. Fail-closed if the service identity cannot
  traverse the release.
- Activation-failure diagnostics now print `systemctl status`,
  `journalctl` and release-path permissions **before** reverting units,
  so a future failure is actionable instead of merely saying that
  health-check failed.
- `tests/test_deploy_installer.py` asserts that the staged release,
  all ancestor directories and binaries are world-searchable/executable
  but not group/world-writable. This catches the precise bug even when
  the simulator is invoked without root.

**Corrected release-permission CI:** [GitHub Actions run 45600391479](https://github.com/Medvedolog/medvetalkie/actions/runs/45600391479) passed **10/10 CTest**, ST7789/Bjorni regressions and the complete staged installer simulation. The simulator explicitly checks permissions on the public /opt release path, binaries and manifest after two updates and rollback.

**Next physical gate:** pull the updated existing work branch through the
same mixed proxy and rerun `--apply --skip-packages` without display,
then collect `systemctl status`, health/BlueZ/USB responses and
`/run/medvetalkie/display.status`. If activation fails, the installer
will print service journal data **before automatic rollback**; collect
those errors. Do not enable the SPI renderer before Core/Web/status are
healthy. Correct the wall clock and Armbian signing key separately;
never bypass APT signature validation.


## 12. Third physical OPiZ3 deployment — first successful Core/Web/BT observation (2026-11-25)

**Hardware evidence:** operator pasted a complete command log from the actual
`root@orangepizero3`. After `git pull --ff-only` to `5e735b7`,
`sudo bash platform/deploy/install-opiz3.sh --apply --skip-packages
--proxy http://192.168.11.100:10880` **completed**:

- ARM64 GCC build passed, **10/10 CTest** passed, and the standalone
  Bjorni/ST7789 status-renderer/SPI-mock suite passed.
- The installer printed `INSTALLED:
  /opt/medvetalkie/releases/20261125T110330Z-5e735b7-8087`.
  `medvetalkie-core`, `medvetalkie-status`, and `medvetalkie-web`
  were all **enabled and active (running)**, with PIDs 9080, 9123, 9168.
  The operator confirmed the **actual** HTTP `/api/v1/health` response
  `{"v":1,"type":"health","service":"medvetalkied",
  "status":"ready","core":"reachable","bluetooth":"not_implemented",
  "audio":"not_implemented"}`. The loopback Web Alpha remains read-only.
- Real sysfs inventory: two independent USB HCI controllers
  `hci0` on physical port `1-1.3` and `hci1` on `1-1.4`, both
  VID:PID `10d7:b012` (UGREEN / Actions ATS2851). This is
  enumeration, **not** proof of audio route or independently assigned
  roles; sysfs inventory still says `identity_verified:false` and
  `hfp_ready:false`.
- Real BlueZ D-Bus observation: two powered adapters;
  `/org/bluez/hci0` at `F4:4E:FC:57:69:64`,
  `/org/bluez/hci1` at `F4:4E:FC:2D:FD:4B`, both
  `powered:true`, `discovering:false`. One known headset
  `AIRIDE N1` (`41:42:63:27:E7:3A`) appears under `hci0`,
  `paired:true` but `connected:false`; HFP audio and SCO transport
  remain `NOT_VERIFIED` / `NOT_CHECKED`.
- Real `/run/medvetalkie/display.status`:
  `MTSTATUS1`, `mode=STANDBY`, both headsets `UNASSIGNED`,
  `voice=NOT_VERIFIED`, `network=LAN`, `radio=NOT_AVAILABLE`,
  `battery=UNKNOWN`, `fault=NONE`, `bt_usb=2`,
  `bt_connected=0`. Note: this prototype `STANDBY` is
  inferred UI idle for `effective_mode=UNKNOWN/desired_mode=UNSET`;
  it is **not** authoritative voice/radio readiness.
- The display unit was deliberately **not enabled**
  (`display=0`), so the integrated status screen to Bjorni
  transition is still unverified on physical ST7789.

**Hardware milestone achieved:** one-stage local service deployment,
three real systemd units, Core/Web Unix IPC, live dual UGREEN inventory,
live BlueZ D-Bus and the status snapshot all work on OPiZ3. The
earlier `0700` release-directory bug is resolved in this physical run.
Do not confuse this milestone with HFP/SCO/full-duplex audio, role
assignment, pairing/connect commands, or Android/WebUI control.

**Next physical gate:** inspect `sudo fuser -v /dev/spidev1.0`,
stop the old unmanaged Bjorni renderer **by its original method** if
needed (do not kill arbitrary processes), then invoke the **existing
installer** with `--apply --skip-packages --enable-display`. Confirm
the status screen on ST7789 at startup, idle transition to Bjorni
after eight seconds, and behavior after Core/BlueZ failure. Check
`systemctl status medvetalkie-display` and journal; avoid changing
Wi-Fi modules or the Armbian image. Next, test headset roles and actual
HFP/SCO/record/playback using controlled hardware sessions.

**Independent maintenance debt:** previous `timedatectl` showed an
unsynchronized clock and an RTC in 1970, and APT reported a missing
Armbian signing key. The successful installation did not run APT because
`--skip-packages` was supplied. The new dated service log is not proof
of stable NTP synchronization or repaired repository trust. Investigate
separately without disabling APT signature verification.

**Branch policy:** continue solely in `work/uwe5622-wifi-armbian`
(PR #1 Draft); no additional branches and no change to `main`.


## 13. Physical ST7789 ownership blocker identified — 2026-11-25

Operator's `sudo fuser -v /dev/spidev1.0` showed root
`screensaver` PID 1026 holding SPI. Subsequent
`systemctl status 1026 --no-pager` identified the owner as
**cron.service**, not the new `medvetalkie-display.service`.
The old manually installed Bjorni start path is:

`root cron -> /usr/bin/flock -n -E 0 /run/medvetalkie-screensaver.lock ->
while :; do /bin/bash /root/medvetalkie-screensaver.sh;
sleep 5; done -> temporary embedded C screensaver`.

Observed process identifiers during this inspection (may have changed):
`cron 509`, launcher chain `667,674,690,694,1025`, renderer
`1026`. Repeated minute-by-minute cron attempts are logged,
although `flock` prevents duplicate active instances.

**Migration procedure for the physical board:**
back up root's current `crontab` first; comment only the exact job
containing `/run/medvetalkie-screensaver.lock`. Keep the global
`cron.service` running. Verify current PIDs/commands (do not rely
on captured stale PIDs), then terminate the specific older
supervisor/launcher via SIGTERM and confirm
`fuser -v /dev/spidev1.0` reports no owner. Preserve the original
`/root/medvetalkie-screensaver.sh` as a fallback.

Once SPI is free, update `work/uwe5622-wifi-armbian` through the
existing mixed proxy and run the tested opt-in installer
`--apply --skip-packages --proxy http://192.168.11.100:10880
--enable-display` with existing Core/status/web services preserved.
Check actual Russian status screen, idle 8-second Bjorni transition,
`systemctl status medvetalkie-display`, and display journal; do
not claim physical ST7789 status switching until observed.

The pasted terminal command prefixed by bracketed-paste bytes
`^[[200~` failed to run `ps`, and `cat /proc/1026/cgroup~`
had a stray tilde. These are terminal input artifacts, not device
or process faults.


## 14. First successful opt-in display-service activation on physical OPiZ3 — 2026-11-25

**User-provided physical SSH log:**

- Operator backed up root crontab as
  `/root/medvetalkie-crontab.backup`, applied a filter that comments
  any active job containing `/run/medvetalkie-screensaver.lock`,
  and checked with `sudo crontab -l | grep`; that last command printed
  **no matching line**, so the log alone does not prove an actual
  crontab entry was modified. The previously observed legacy PIDs
  `690,694,1026` were absent from `ps` at this check. There was
  no remaining process shown from that specific old chain.
- `git -c http.proxy=http://192.168.11.100:10880 pull --ff-only`
  reported **Already up to date**.
- On real Orange Pi Zero 3, operator executed
  `sudo bash platform/deploy/install-opiz3.sh --apply
  --skip-packages --proxy http://192.168.11.100:10880
  --enable-display`.
- Native GCC/ARM64 build, **10/10 CTest**, and the independent
  Bjorni/ST7789 render, display-status, SPI-mock, clock, launcher
  and supervisor regression suite all passed.
- Installer printed `INSTALLED:
  /opt/medvetalkie/releases/20261125T112540Z-daf4364-20155`,
  `Units: medvetalkie-core/status/web; display=1`; previous release
  `/opt/medvetalkie/releases/20261125T110937Z-daf4364-11380`;
  services were restarted, `--enable-display` enabled and started
  its unit, and installer completed its Core/Web and status-file
  health gates. Kernel, blacklist, boot and Ethernet remain unchanged.
- This is an installation/activation **success**, not physical
  confirmation of the observed LCD image. No
  `systemctl status medvetalkie-display` / journal or on-screen
  observation was supplied yet. Before claiming 8-second transition
  verification, collect `systemctl status medvetalkie-display`,
  `journalctl -u medvetalkie-display -n 60 --no-pager`,
  `sudo fuser -v /dev/spidev1.0` and a direct observation/photo:
  Russian status dashboard on startup, then animated Bjorni after
  roughly 8 seconds in STANDBY. If renderer uses the only SPA/GPIO
  pins, avoid running a second owner concurrently.
- Live two-controller USB/BlueZ inventory and Core/status/Web were
  validated in the prior hardware session; the second activation did
  not include a new Bluetooth diagnostic dump. HFP/SCO full-duplex
  audio and headset roles remain unverified.
- The unsynchronized system clock and the Armbian missing signing key
  remain independent outstanding maintenance faults; `--skip-packages`
  avoids APT in this run and does not repair them.

**Next gate:** verify physical ST7789 status/idle transition and exclusive
SPI ownership; only then test real headset connection/HFP/SCO.
Maintain a single active work branch and Draft PR #1, no main merge
until hardware acceptance criteria are met.


## 15. Physical UI expectation corrected — 2026-11-25

After successful `display=1` installation, the operator reports:
**"я не увидел новое меню"** (did not see the new menu).

Source inspection establishes that **no interactive SPI menu has been
implemented or installed yet**. `src/medvetalkie-ui/main.c` is still
the one-function `mt_scaffold_main` placeholder; no joystick/GPIO
navigation, settings controls, pairing commands or interactive
LVGL renderer are registered as a systemd UI service. The installed
`medvetalkie-display.service` runs the combined self-contained C11
ST7789 screensaver with an **informational dashboard**, not a menu.

In `platform/display/screensaver/screensaver.c`, after reading fresh
`MTSTATUS1`, the status dashboard is visible only for **8 seconds**
following service start or a state change while `mode=STANDBY` and
`fault=NONE`. Then Bjorni takes over. With the observed persistent
STANDBY (unassigned headsets, `voice=NOT_VERIFIED`), the dashboard
can easily be missed. Restart `medvetalkie-display.service` without
reinstalling to observe the initial 8-second status screen; if absent,
collect `systemctl status` and `journalctl`, actual SPI ownership,
and direct physical panel observation. This test has not yet been
reported by the operator.

**Implementation debt:** real navigable on-device menu and digital
5-way joystick + four context button input abstraction as specified
in `docs/MedveTalkie_TZ_v1.4.md` are a *future development stage*.
Do not claim this functionality, LVGL readiness, writable settings,
HFP pairing actions, or audio routing based on the current
display-only screen. Keep a single SPI renderer owner and shared Core
IPC before building this stage.


## 16. Live ST7789 hardware regression — repeated GPIO contention, 2026-11-25

**User's physical on-board observations:**
- Physical ST7789 continued showing the *old* jumping Bjorni, **no new
  dashboard for even one second**. The clock banner still displayed
  4 MHz but the observed FPS fell to about **8–9** from previously
  measured 24.3–25 with the old uninterrupted renderer.
- Journal of `medvetalkie-display.service` repeatedly reported:
  `Request PC5/DC and PC6/RESET (busy lines are not overridden):
  Device or resource busy`. systemd was continuously restarting the
  failed service; at one point restart counter reached **106**.
- Snapshot at 14:27 showed `medvetalkie-display.service`
  `Active: active (running)` during its C compilation stage
  (`cc` and `cc1` under the unit), **not an initialized renderer**.
  At the same time `fuser -v /dev/spidev1.0` reported
  `root screensaver` PID **11516**, **outside** the new
  service's displayed cgroup. This is a definite conflicting SPI
  owner and strongly suggests an old cron/manual Bjorni survived
  after disabling an assumed root crontab entry. Its actual parent
  and autostart source remain unconfirmed (PID is historical).
- `MTSTATUS1` snapshot was present and parseable with
  `mode=STANDBY`, 2 USB BT controllers, 0 connections and
  `fault=NONE`. Thus not seeing the dashboard is explained by the
  GPIO startup failure, not proof of a UI formatting problem.
- Restarts repeatedly compiled the 180KB embedded standalone C
  screensaver and competed for CPU resources. This is a plausible
  contributor to degraded FPS, but the precise throughput root
  cause must be measured again with exclusive SPI/GPIO ownership.

**Operator containment (not yet verified as executed):**
`sudo systemctl stop medvetalkie-display` followed by
`sudo systemctl disable medvetalkie-display`. These commands
leave Core, Web, status producer and both USB BT controllers alone.
Investigate `fuser`, `ps`, `pstree`, `systemctl status PID`
and the crontab sources, including `/etc/crontab` and
`/etc/cron.d`. Do not automatically kill a PID or stop
`cron.service`; remove/disable only the confirmed old Bjorni
supervisor, preserving backup and rollback.

**Source fixes staged to the same work branch:**
- New `platform/deploy/check-display-owner.sh` checks each SPI
  owner via `fuser` **and** `/proc/PID/cgroup`, distinguishing
  the authorized display unit from an external cron/manual process.
  Three modes: `--allow-managed` (installer before build),
  `--require-free` (after managed stop and systemd ExecCondition),
  and `--require-managed` (post-start renderer readiness gate).
  This does not evict any process and conservatively fails on
  unreadable/uncertain owner information.
- Installer refuses a competing external owner even when
  `medvetalkie-display.service` reports `active` during
  compilation; second SPI check runs after stopping the managed
  unit. Both guards run without APT, without disturbing kernel
  module or network settings. The helper is shipped inside each
  release, and installed display service invokes it as
  `ExecCondition`.
- systemd has `StartLimitIntervalSec=180`,
  `StartLimitBurst=2` and `RestartSec=15` to prevent sustained
  compiler/restart storms. An external SPI owner causes a skipped
  start, not repeated failed GPIO initialization.
- Installer no longer counts `systemctl is-active` during C
  compilation as display success: after Core/Web/MTSTATUS1 health,
  it waits for `fuser` to identify an **actual managed renderer**
  holding SPI. The failure rollback logs now include the display
  unit. This gate confirms exclusive *SPI process ownership* but
  does not yet prove pixels were rendered or validate two-way
  audio.
- `tests/test_deploy_installer.py` mocks a legacy `fuser`
  owner and checks the helper rejects it; also verifies the
  service's ExecCondition/start limits and the staged helper
  bytes. **CI confirmed:** [combined GitHub Actions 45605325119](https://github.com/Medvedolog/medvetalkie/actions/runs/45605325119) PASSED 10/10 CTest, standalone ST7789/Bjorni suite, mocked external owner checks, and the complete installer stage/rollback simulation. This is host simulation only; the live GPIO conflict and actual panel switch still require operator-side verification.

**Next physical gate:** first stop/disable the new display unit to
restore old Bjorni speed; locate the still-running legacy process
`11516` through the actual process tree and cron source; stop its
supervisor **only after confirming it**, and verify
`fuser -v /dev/spidev1.0` is empty. Only after CI green, upgrade
the same work branch with the fixed installer and
`--apply --skip-packages --enable-display`. Capture actual LCD
status-then-Bjorni transition and FPS, and verify no restart storm.
No unrelated Wi-Fi, kernel, boot or `main` changes.


## 17. Root cause of persistent legacy ST7789 owner: /etc/cron.d — 2026-11-25

Operator provided definitive `systemctl status 11516`, `pstree -aps`,
`fuser` and cron source search from the physical OPiZ3:

- `sudo systemctl stop medvetalkie-display` and `sudo systemctl
  disable medvetalkie-display` completed, leaving the new display
  unit disabled and preventing its compiler/restart storm.
- The legacy `/dev/spidev1.0` owner remained root
  `screensaver` PID **11516** (historical, may change), with
  parent `11345`, process group **11342**, owner systemd cgroup
  `/system.slice/cron.service`.
- Exact chain: `cron 509 -> CRON 11340 -> bash 11342 ->
  flock 11343 -> bash 11344 -> /root/medvetalkie-screensaver.sh
  11345 -> screensaver 11516`.
- **True autostart location conclusively found:**
  `/etc/cron.d/medvetalkie-screensaver`, **not** root's personal
  crontab. It contains TWO entries:
  `@reboot root /usr/bin/flock -n -E 0
  /run/medvetalkie-screensaver.lock ...` and a
  `* * * * * root /usr/bin/flock -n -E 0 ...` watchdog,
  both launching a `while :; do /bin/bash
  /root/medvetalkie-screensaver.sh; sleep 5; done` loop.
  Hence the previous `sudo crontab -l` filter had no effect.
  Further, removing a cron entry does **not** terminate the
  already running watchdog loop. Do not use stale PIDs blindly.
- The old renderer and the new service were contending for
  SPI1 plus DC=PC5 and RESET=PC6. This prevented display
  dashboard appearance and drove repeated compiler restarts;
  the observed 8–9 FPS should be remeasured after ownership
  is exclusive.

**Safe operator migration proposed (not yet verified performed):**
move `/etc/cron.d/medvetalkie-screensaver` to an archived
file outside `/etc/cron.d`, preserving the original script
and global cron service; verify the current group leader
`11342` via `ps`, then send TERM to **only that process group**
(`kill -TERM -- -11342`) if still matching the old cron/flock
supervisor. Verify `fuser -v /dev/spidev1.0` is empty.
Avoid arbitrary PID kills and stopping the global cron daemon.

**After SPI is free:** pull the latest existing
`work/uwe5622-wifi-armbian` branch via the mixed proxy,
verify the new SPI-owner preflight guard in source, and run
`--apply --skip-packages --enable-display`. The installer
must now fail closed if any legacy process owns SPI and only
report success if its own renderer opens SPI. Inspect physical
Russian status screen for the first ~8 s and Bjorni thereafter,
measure FPS without conflicting compiler load, and capture
`medvetalkie-display.service` logs. No result of this retry
has been supplied yet. HFP/SCO remains unverified.


## 18. Second guarded display installation blocked by cron respawn — 2026-11-25

**Actual physical SSH log from operator:**

- Legacy cron watchdog group was confirmed immediately before termination:
  `PGID=11342`, `flock 11343`, shell 11344, script
  `/root/medvetalkie-screensaver.sh` 11345, ST7789
  renderer 11516. Operator ran
  `sudo kill -TERM -- -11342` and `sleep 3`.
  Immediately afterward `sudo fuser -v /dev/spidev1.0`
  printed **nothing**, confirming successful *temporary* SPI release.
- In the pasted sequence, operator **did not run the suggested**
  `sudo mv /etc/cron.d/medvetalkie-screensaver
  /root/medvetalkie-screensaver.cron.backup` before redeployment.
  Therefore the discovered `@reboot` and **every-minute** cron.d
  entries remained the likely re-launch source.
- Operator pulled branch `daf4364..a266dc7`; native ARM64 GCC
  build, **10/10 CTest**, Bjorni/ST7789 render and SPI host mocks
  all passed.
- During subsequent deployment, an **entirely new** legacy
  `root screensaver` PID **26329** reappeared and took
  `/dev/spidev1.0`. The new installer's post-stop ownership
  guard correctly rejected it:
  `SPI /dev/spidev1.0 is held by PID 26329`;
  `SPI not released after stopping managed display; rolling back`.
- This occurred **after** the installer had already stopped
  Core/status/Web (their systemd records show clean exits at
  14:39:17 MSK). Installer invoked rollback and restored service
  definitions. The provided log **does not show** subsequent
  `systemctl is-active` or HTTP health checks, so explicitly verify
  they recovered. `medvetalkie-display` remained disabled.
  A check after the failure still found PID 26329 holding SPI.
- The archived `journalctl` displayed 42+ old restart-storm events
  from the *previous* renderer attempts, not new errors caused by
  the current guarded retry. Do not interpret retained historical
  journal lines as evidence the updated unit is restarting.

**Follow-up code correction in the same branch:**

- Added `platform/deploy/check-legacy-display-cron.sh`:
  fail-closed when `/etc/cron.d/medvetalkie-screensaver`
  contains an active noncommented entry launching
  `/root/medvetalkie-screensaver.sh`. Does **not** disable cron
  or kill a process. This prevents a known minute-watchdog
  from respawning during a long CMake/CTest step.
- Installer now checks both legacy cron.d and SPI ownership
  **before the build** and repeats both checks **before stopping
  any live systemd service**. Its existing post-stop guard remains
  for last-moment races, with rollback. This avoids needless
  Core/status/Web downtime for known external interference.
- New simulated fixture tests `@reboot`, minute watchdog,
  commented/disabled cron entries and absent cron file.
- The fix is **not yet physically installed or verified**;
  green CI and board retry status must be recorded separately.

**CI confirmation:** [GitHub Actions 45606655980](https://github.com/Medvedolog/medvetalkie/actions/runs/45606655980) passed all **10/10 CTest**, Bjorni/ST7789 renderer suite, and staged installer simulation including newly added cron.d watchdog fixture tests. Wi-Fi safety and upstream UWE5622 patch audits also passed on the related commit. The real board has **not** yet received this follow-up cron.d preflight fix; physical success remains pending.

**Next physical steps:** archive the actual file from
`/etc/cron.d` to `/root`, stop only the confirmed
currently-running legacy process group, verify
`fuser -v /dev/spidev1.0` remains empty **after a full
minute** and `systemctl is-active medvetalkie-core
medvetalkie-status medvetalkie-web` reports active. Then
pull the new branch and use `--apply --skip-packages
--enable-display`, inspect a real dashboard within
the first ~8 seconds, Bjorni thereafter, and FPS.
Do not merge `main` or claim HFP/SCO working.


## 19. First physical Russian status dashboard seen on ST7789 — 2026-11-25

Following removal of the competing legacy cron/SPI process and guarded
deployment, operator reports: **"показал при запуске таблицу состояний
не успел посмотреть"** (a state table appeared at startup but was gone
before the operator could inspect it).

This is the **first user-reported direct physical visual confirmation**
of the new Russian status dashboard on the real MSP2008/ST7789
(Orange Pi Zero 3). Unlike the earlier `display=1` installer-only
log, the operator explicitly observed the screen contents appearing.
It does **not** independently verify all text is legible, correct
status freshness, clock, measured FPS, or the precise 8-second
transition, and no updated systemd journal/photograph was provided.

The renderer's current policy is hard-coded in
`platform/display/screensaver/screensaver.c`:
`mode=STANDBY` and `fault=NONE` show the dashboard for ~8 s
after renderer initialization/state change, then switch to Bjorni.
The operator may restart only `medvetalkie-display` to repeat that
brief physical inspection, or inspect the full current
`/run/medvetalkie/display.status` text from the console.

**Usability follow-up:** A configurable on-boot status visibility
interval (e.g. 30 seconds for bench testing, then shorter for vehicle
use) would make hardware inspection practical. It has **not** yet
been implemented or validated. Do not confuse the status dashboard
with the planned interactive GPIO/LVGL settings menu.
The legacy cron removal, reboot persistence, SPI ownership, FPS
recovery and HFP/SCO hardware proof should be confirmed separately
before claiming the complete display/audio system is finished.
