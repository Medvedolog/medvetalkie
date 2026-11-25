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


## 20. Next iteration: configurable standby dashboard dwell — 2026-11-25

After first seeing the real Russian status table on ST7789, operator said
the original **8-second** display interval was too brief to inspect and
asked "Что дальше" ("what next?"). The highest-value immediate UI change
is to make the startup/dashboard dwell configurable rather than
requiring the operator to race an 8-second window.

**Implemented in existing branch, no new branches:**

- `platform/display/screensaver/screensaver.c`: new bounded
  `--status-seconds N` parameter (integer **1–120**), with matching
  `MEDVETALKIE_STATUS_SECONDS` environment override. CLI wins over
  environment when both are present, except invalid environment values
  still fail validation early. Standalone default remains **8 s** for
  backward compatibility; actual standby dashboard duration uses the
  validated value. Error, offline and active-mode status screens
  continue to persist rather than falling back to animation.
- `platform/deploy/systemd/medvetalkie-display.service`: explicitly
  requests **`--status-seconds 30`** at the previously observed
  4 MHz / 25 FPS settings. One renderer still exclusively owns SPI1,
  PC5/DC and PC6/RESET; no extra display process or library added.
- `platform/display/screensaver/launcher.sh.in` and generated
  self-contained `platform/display/medvetalkie-screensaver.sh` are
  regenerated together with the embedded C SHA-256, preserving the
  existing no-download installation flow.
- `platform/display/screensaver/test-screensaver.py`: tests the
  1/30/120-second valid boundaries and invalid 0/121/noninteger
  inputs, plus environment validation; existing PPM renderer, SPI
  frame integrity, supervisor, and deterministic launcher
  regeneration tests remain in place.
- `tests/test_deploy_installer.py`: asserts managed systemd
  unit sets 30-second dashboard visibility.
- `platform/display/README.md` updated to describe current physical
  observation and 30s managed / 8s standalone behavior, replacing
  outdated "not yet integrated / do not enable" instructions.

**Hardware acceptance gates before broader feature development:**
1. On the actual board confirm legacy `/etc/cron.d` Bjorni jobs
   are archived, and `fuser -v /dev/spidev1.0` lists only the
   authorized managed renderer, including after reboot.
2. Pull this branch and redeploy via `sudo bash
   platform/deploy/install-opiz3.sh --apply --skip-packages
   --proxy http://192.168.11.100:10880 --enable-display` only
   with the SPI checks satisfied. Observe **30 seconds**
   of dashboard, then Bjorni; confirm readability and current
   status, and measure live FPS, rather than treating a CTest pass
   as an on-device measurement.
3. Confirm Core/status/Web health, two UGREEN BlueZ controllers,
   no GPIO contention/restart storms and stable operation after
   a clean reboot.
4. Next engineering milestone is actual paired headset connection
   and HFP/SCO microphone+playback verification using the existing
   shared Core API and state machine. Interactive GPIO joystick,
   buttons, true LVGL menu and Android settings UI remain separate
   planned functionality, **not** claimed done.

**CI verification:** [GitHub Actions 45608285963](https://github.com/Medvedolog/medvetalkie/actions/runs/45608285963) completed **successfully** for the updated generated launcher and configurable status dwell: native C11 build, 10/10 CTest, Bjorni/ST7789 standalone rendering/SPI mock checks including deterministic SHA-256 launcher regeneration and CLI/environment bounds, and full installer stage/rollback simulation. This is host CI; physical 30-second dwell and full 25 FPS are not verified yet. Neither the new 30-second
physical behavior nor the restored 25 FPS has been observed yet.


## Bluetooth prerequisite diagnostics — 2026-11-25

- Commit `81b6b659fd1960bb99d1b80b85d3f6bc486b2b12` added `platform/bluetooth/diagnose-hfp-prereqs.sh` in the existing work branch. No changes to `main`, display/SPI, systemd units, pairing, radio configuration or audio routing.
- The read-only tool reports two USB HCI controller identities (including physical USB port), BlueZ and connected ACL devices, presence of PipeWire/Pulse/WirePlumber tools and session sockets, HFP-related cards/profiles, sinks/sources and installed Debian audio backend packages. It makes **no** audio-readiness claim.
- The `medvetalkie-bt` executable is still only a scaffold. No active HFP lifecycle, SCO transport or duplex routing code is present, and no Orange Pi measurement was made in this iteration.
- Next hardware action: `sudo sh platform/bluetooth/diagnose-hfp-prereqs.sh` after pulling the work branch; share its output. If the audio session belongs to a different user, set `MT_AUDIO_USER` explicitly. Inspect findings before designing the active, opt-in one-headset HFP/audio test.
- Verification: file creation confirmed by GitHub commit; CI and board execution of this new script are **not yet verified**.


## Bluetooth board preflight observed — 2026-11-25

Operator ran `diagnose-hfp-prereqs.sh` twice on Orange Pi Zero 3, kernel `6.18.64-current-sunxi64`:

- BlueZ 5.82 active; two USB adapters VID:PID `10d7:b012`, sysfs `hci0 -> 1-1.3` and `hci1 -> 1-1.4`. BlueZ lists controller addresses `F4:4E:FC:57:69:64` and `F4:4E:FC:2D:FD:4B`, but the sysfs `address` attributes are blank, so HCI-to-MAC pairing is **not verified** by this log. No connected ACL headset devices.
- `pactl`, `wpctl`, `pw-cli` missing; `pipewire`, `pipewire-pulse`, `wireplumber`, `libspa-0.2-bluetooth` not installed. Service user `medvetalkie` is UID 1000, no per-user PipeWire/Pulse socket.
- HFP/SCO/PCM and two-way voice are **NOT TESTED**. No need to change USB/BlueZ driver or touch the ST7789 on the evidence above.
- Follow-up commit `49c91f0`: diagnostic handles missing sysfs address without treating the MAC mapping as proof; BlueZ lookup is best-effort.
- Next action: resolve previous APT signature/time problems first, then install the four missing audio packages (plus CLI helpers as needed) from authenticated repositories; enable user-session PipeWire/WirePlumber for the dedicated medvetalkie account and re-run preflight before any active pairing. Audio stack setup and CI of the diagnostic script remain **unverified**.


## Next image build requirement accepted — 2026-11-25

User directed that the **next full Armbian image** contain the complete Bluetooth HFP audio prerequisite stack by default. TZ v1.4 §28 and `platform/armbian-image/README.md` now require PipeWire, pipewire-pulse, WirePlumber, Bluetooth SPA, diagnostic tools, an unprivileged persistent headless audio user session, reliable verified APT and separate build/boot/hardware audio gates. Both UGREEN remain USB-based; do not regress ST7789, Core, network, blacklist or rollback.

**Not implemented in the image build scripts yet.** A documentation requirement is not a working build. Next engineering task: integrate the package set + user-systemd provisioning in the image recipe, add rootfs/boot smoke checks, then confirm on the physical OPiZ3. Do not claim actual HFP/SCO/full-duplex until hardware proof.


## Physical OPiZ3 PipeWire/WirePlumber bring-up — 2026-11-25

Operator supplied actual post-install output from the physical Orange Pi Zero 3 (kernel `6.18.64-current-sunxi64`):

- User manager started for `medvetalkie` (on this board UID 1000), user `pipewire.socket`, `pipewire-pulse.socket` and `wireplumber.service` enabled. `pactl info` under `medvetalkie` reached local Pulse-compatible socket and identified `PulseAudio (on PipeWire 1.4.2)`; `wpctl status` showed running PipeWire and WirePlumber clients.
- `pipewire 1.4.2-1`, `pipewire-pulse 1.4.2-1`, `wireplumber 0.5.8-2`, `libspa-0.2-bluetooth 1.4.2-1`, `bluez 5.82-1.1+rpt2` installed. `pactl`, `wpctl` and `pw-cli` now available. Both user audio sockets present. ALSA sinks visible. No actual Bluetooth card, headset source or sink exists yet because no headset is connected.
- BlueZ remains active with two controllers; sysfs maps `hci0 -> 1-1.3` and `hci1 -> 1-1.4`, VID:PID `10d7:b012`. No connected ACL devices. Current diagnostic still reports `address=unavailable` for both sysfs-mapped HCI interfaces; do not assume the two BlueZ MAC addresses are mapped to particular USB ports until proven.
- `wpctl status` reports absent RTKit D-Bus service and fallback realtime priority; nonfatal for basic process startup, but latency/underrun behavior is untested. Consider `rtkit` with measured audio requirements.
- **Confirmed:** headless audio service is reachable on the live board at this moment. **Unverified:** persistence after reboot, WirePlumber Bluetooth headset profile, SCO/eSCO setup, microphone PCM, full duplex, and audio stream routing.
- **Next gate:** explicitly pair one AIRIDE N1 with one selected Bluetooth controller, inspect resulting BlueZ Device1 and PipeWire Bluetooth card/profile/source/sink; preserve bonds and avoid changing other controllers or existing display/network services. Then run an opt-in active audio test before claiming HFP readiness.


## SSH Bluetooth interactive bench TUI — 2026-11-25

- Added `platform/bluetooth/medvetalkie-bt-tui.py` (color curses TUI; only Python stdlib + BlueZ CLI) and `platform/bluetooth/README.md`. `sudo python3 platform/bluetooth/medvetalkie-bt-tui.py` from the work branch. Controller switch (1/2), asynchronous timed BR/EDR scan, BlueZ-cache refresh and selected device inspection, explicit connect, pairing with extra confirmation, PipeWire-card diagnostic, animated activity indicator and logs. The indicator is indeterminate activity, **not percentage progress**. No SPI/GPIO, BlueZ service restarts, automatic bond deletes, profile changes or core/network updates.
- Added `tests/test_bt_tui.py` offline mocks and a GitHub Actions job step (`python3 -m py_compile` + tests). This validates CLI parsing/safety at CI level; neither live RFCOMM/SCO nor the actual SSH-TUI execution is proved.
- **Observed failure motivating tool:** `AIRIDE N1` MAC `41:42:63:27:E7:3A` previously paired/trusted, advertised Handsfree UUID `0000111e`, but BlueZ connect failed `br-connection-profile-unavailable`. Investigate Audio Gateway profile registration in headless WirePlumber and BlueZ before further retries. Do not delete existing bonds.
- Next steps: confirm CI green; pull tool on physical OPiZ3, run TUI and validate terminal behavior, scan and log output. Then implement an explicitly opt-in active HFP/SCO/PCM test; current TUI only checks prerequisites and connection attempts.


## First real AIRIDE N1 USB-Bluetooth audio connection — 2026-11-25

Operator applied per-user WirePlumber configuration under `/home/medvetalkie/.config/wireplumber/wireplumber.conf.d/51-medvetalkie-bluetooth.conf` (previously proposed headless `monitor.bluez.seat-monitoring = disabled`, `bluez5.roles = [ a2dp_source hfp_ag ]`, `bluez5.hfphsp-backend = "native"`), restarted only the user's `wireplumber.service`, and connected an existing paired/trusted AIRIDE N1 without re-pairing.

**Physical evidence:** `bluetoothctl select F4:4E:FC:57:69:64`; `connect 41:42:63:27:E7:3A` returned `Connection successful`; kernel/BlueZ reported `hci0 ... type BR/EDR connected`, `Device1.Connected=yes`, `ServicesResolved=yes`, new A2DP SEPs and transport `/org/bluez/hci0/dev_41_42_63_27_E7_3A/sep1/fd0` (volume 127). BlueZ `Battery Percentage: 0x46 (70)`. The earlier `br-connection-profile-unavailable` failure was not reproduced after WirePlumber configuration; this temporal association does not independently prove the exact root cause.

**Still NOT verified:** HFP/HSP profile selection, SCO/eSCO connection, input microphone source, active sample transport or two-way voice. No second headset test performed. `journalctl _UID=1000 --user-unit=wireplumber.service` showed no entries (wrong/empty journal selector is not evidence of no warnings).

Next: inspect the actual `bluez_card.41_42_63_27_E7_3A` card profile list under the `medvetalkie` user's PipeWire Pulse socket. If HFP profile is available, use only that exact profile with `pactl set-card-profile` (explicit hardware test) and then inspect Bluetooth sink/source and SCO HCI events. Preserve existing bonding and display/network state.


## AIRIDE N1 HFP mSBC profile and dual PipeWire nodes observed — 2026-11-25

Physical operator log confirms `pactl set-card-profile bluez_card.41_42_63_27_E7_3A headset-head-unit` returned success, and `pactl list cards` showed `Active Profile: headset-head-unit`. A Bluetooth HFP sink `bluez_output.41_42_63_27_E7_3A.1` (`s16le`, 1 channel, 16000 Hz) and headset microphone source `bluez_input.41:42:63:27:E7:3A` (`float32le`, 1 channel, 48000 Hz) appeared. Both were `SUSPENDED` (idle, no live PCM stream), so **SCO audio is not proven**. Operator subsequently ran `pactl set-card-profile ... headset-head-unit-cvsd` without an error, but has not yet posted the active CVSD card or sink/source snapshots.

Next hardware test: confirm CVSD active profile, start a bounded mic recording plus playback to the headset (explicit operator action), capture HCI synchronous connection event with `btmon`; check actual audible signal and captured wave content before promoting any HFP readiness state. Then repeat in mSBC, then two separate controller/headset slots. Preserve existing bonds and ST7789/network.


## AIRIDE N1 HFP playback reported audible — 2026-11-25

- Operator reported **"есть воспроизведение"** after the CVSD/record-and-playback test instructions. This is evidence that sound was heard during playback through AIRIDE N1; it is **not yet an unambiguous confirmation that the WAV actually contained voice captured from the AIRIDE microphone**.
- Distinguish: audible playback verified by operator; recording capture and nonzero vocal PCM require explicit operator confirmation or waveform examination; simultaneous two-way audio, SCO/eSCO packet counters and long-term stability remain **NOT VERIFIED**.
- Next: ask whether the spoken recording was heard, then inspect `btmon` synchronously during streaming and test duplex with two real headsets/controllers. Preserve pairing, display, network and existing audio session.


## First real AIRIDE N1 HFP microphone-to-playback loop validated by operator — 2026-11-25

The operator explicitly clarified that, after the CVSD switch and guided `parecord`/`paplay` workflow, they heard **their own recorded voice** in the AIRIDE N1, describing the sound as **telephone quality**. This confirms functional *sequential* headset microphone capture and headset playback through the selected HFP path on the physical Orange Pi Zero 3 / first UGREEN ATS2851 controller. Previous operator output had shown `headset-head-unit` profile and both Bluetooth PipeWire source/sink nodes; `headset-head-unit-cvsd` was subsequently selected successfully before this test, but no independent post-switch profile snapshot was submitted. Attribute the successful voice check to the CVSD test sequence, without inventing HCI trace or asserting codec negotiation beyond the selected profile.

**Verified by human hearing:** microphone input and output both work in a sequential record-then-playback test. **Still unverified:** simultaneous full-duplex, HCI SCO/eSCO event/packet trace, measured latency/packet loss, confirmed mSBC voice quality and the second independent USB controller/headset. Avoid claiming a completed two-headset intercom.

Next hardware plan: repeat the microphone/playback test under `headset-head-unit` mSBC; collect `btmon` during a bounded active stream; run simultaneous playback/recording on one headset; then connect a distinct second headset on the other UGREEN and implement isolated cross-routing with failure recovery. Preserve display, existing bond and network.


## AIRIDE N1 mSBC subjective comparison — 2026-11-25

Operator repeated real headset microphone recording and playback after selecting `headset-head-unit` (mSBC) and reported **better voice quality than CVSD, but relatively low volume**. This is a human observation for the first UGREEN / AIRIDE N1 path, not calibrated codec/SCO/latency evidence. Next check playback sink gain and headset hardware volume first (90% target, no above-100% software boost); separately inspect microphone source gain and only raise it to 100% if lower, then re-evaluate recordings for distortion. No claim of simultaneous duplex or second headset readiness.


## AIRIDE N1 gain adjustment — 2026-11-25

Operator reports satisfactory playback volume after previous recommendation of a 90% Bluetooth sink level, and explicitly states they set the headset microphone source volume to **120%**. 90% is the suggested sink target, **not independently confirmed by a readback**; confirm via `pactl get-sink-volume` if used as a product default. The 120% microphone level is a user-applied experimental gain, not a calibrated safe default; test loud speech for clipping and noise before persisting. mSBC sequential microphone record/playback remains operator confirmed. Full duplex and second headset remain unverified.


## Uploaded real AIRIDE WAVs measured; duplex playback/record attempt — 2026-11-25

User supplied three real 16-bit 16-kHz mono PCM WAVs from the physical headset setup: `airide-mic.wav` (6.0 s, sample peak -14.3 dBFS, overall RMS -37.1 dBFS), `airide-msbc.wav` (6.0 s, peak -20.0 dBFS, RMS -41.4 dBFS), and `airide-duplex.wav` (10.0 s, peak -12.9 dBFS, RMS -37.1 dBFS). All three have non-silent audio, and none show digital full-scale clipping (no samples >= 0.999 absolute). Duplex track contains speech, consistent with recording being active during the combined test; exact real-time overlap with the output stream and SCO packet continuity remain UNPROVEN because a WAV alone is not a synchronized trace. Record-and-playback comparisons use PipeWire PCM WAV sample rate, which by itself cannot establish negotiated Bluetooth codec (CVSD may be resampled to 16 kHz). Gain differences could be due to speech effort, mic placement, gain settings and profiles; do not assert a calibrated codec-only effect. Need `btmon` and active-time metadata for a conclusive full-duplex verdict; later add repeatable TUI timed duplex + waveform/RMS/peak/clipping report.


## Automated HFP duplex bench integrated into color SSH TUI — 2026-11-25

- Added `platform/bluetooth/bt_audio_bench.py` (Python stdlib; requires `pactl`, `parecord`, `paplay`, optionally root `btmon`). Explicitly chooses one selected Bluetooth headset's already active HFP `bluez_input` and `bluez_output` from PipeWire, runs about 10 seconds of quiet diagnostic pips in parallel with microphone recording. Does **not** switch profiles, change volumes/default sinks, modify BlueZ trust/bonds, or touch ST7789/SPI/network. Saves WAV + per-500-ms RMS/peak/clipping measurements in a unique restricted temp directory, optional HCI btsnoop capture. HCI mention counts are provisional evidence, not a packet-level verdict.
- Integrated with `platform/bluetooth/medvetalkie-bt-tui.py`: `D` confirmation-required duplex test, `T` same with btmon, animated indeterminate progress, `L` for logs/report and file locations, `2` for second adapter scanning. Added offline mock unit tests to `tests/test_bt_tui.py` and compile checks for both Python scripts to `.github/workflows/build.yml`. Documented operator commands in `platform/bluetooth/README.md`.
- **Pending acceptance:** GitHub Actions pass on latest commit, then actual OPiZ3 test and review of WAV/btmon, true simultaneous SCO continuity, second headset+adapter connection and real cross-routing. No real-time input level meter or intercom audio engine is implemented by this milestone; WAV statistics are calculated after the test.


## Full keyboard-navigable Bluetooth menu, connected/paired inventory — 2026-11-25

User found first color TUI inadequate: arrow keys/navigation, actual menu, device addition, PIN/agent pairing, profile switches, record/play and gain control were missing. The follow-up requires clearly visible active connections (with reception RSSI where available) and remembered bonded/paired devices.

- Added `platform/bluetooth/medvetalkie-bt-menu.py`; original `medvetalkie-bt-tui.py` launch path now invokes menu. Arrow selection, Tab/Left/Right focus, Enter actions, PgUp/PgDn controller selection, Esc cancel, Q exit; right-side actions: scan, connect/disconnect, pairing via interactive `bluetoothctl` PTY agent (PIN/passkey/confirmation dialogs), trust, A2DP/HFP mSBC/HFP CVSD, short voice record/play, duplex, optional btmon, per-headset sink ±10% and source ±10%, device details and log.
- Inventory merges discovered BlueZ cache with `bluetoothctl devices Paired` and `bluetoothctl devices Connected`; per-device `info` parses Connected/Paired/Bonded/Trusted, battery percentage and RSSI (dBm or `RSSI —` when BlueZ has no value). Prioritizes connected devices, then paired/bonded devices, then other seen devices. Automatic refresh approximately every 15s while idle. RSSI may reflect cached inquiry, **not a guaranteed live per-link measurement**.
- Added offline `tests/test_bt_menu.py` for status parsing, merged paired/connected inventory, profile parsing, audio node lookup, gain parsing and menu action coverage; checks wired into existing build workflow. Docs: `platform/bluetooth/README.md`.
- **Still unverified on hardware:** new curses arrow-key experience under actual SSH client; interactive BlueZ PIN/passkey responses in a live fresh pairing; accurate live RSSI for active classic link, profile switch via UI, gain controls, record/play and duplex UI. No cross-routing or second headset intercom yet. Do not call this release hardware-accepted before operator testing.
- Keep `main` untouched; no SPI/ST7789, systemd, USB driver, image build or networking changes.


## Headless two-controller intercom test harness — 2026-11-25

User reports Bluetooth TUI still displays nothing on physical Orange Pi; **do not treat TUI as validated** and do not force further TUI troubleshooting before progressing with HFP. New development in `work/uwe5622-wifi-armbian`:

- `platform/bluetooth/medvetalkie-intercom-test.py`: operator-invoked, 5–300 second cross-routing between **two distinct actually connected** HFP headsets assigned to **different** BlueZ controllers. Discover controllers and `devices Connected`, assert unique membership, inspect user `medvetalkie` PipeWire Bluetooth cards for active `headset-head-unit` or `headset-head-unit-cvsd` and exactly one source/sink for each MAC, then create two `pactl load-module module-loopback source=A.mic sink=B.speaker latency_msec=80 ...` / inverse. Unload the two allocated module IDs on completion, Ctrl+C or partial failure, without modifying services, pairing, profiles, display or network. `--dry-run` is non-mutating.
- `tests/test_bt_intercom.py` verifies unique controller assignments, rejection of A2DP/disconnected/same-controller paths, cross-routing, unload order and rollback after partial load failure; linked to `.github/workflows/build.yml`.
- `platform/bluetooth/README.md` adds SSH usage instructions. A second actual headset MAC has not yet been supplied, so **do not claim live dual-HFP intercom success**. First real test should begin with `--dry-run`, then an explicit bounded 30-second run and human hearing/latency feedback. Running test and CI checks must not be conflated.
- CI workflow was launched but completion of new script's test step not confirmed at time of documentation. Container cannot resolve public GitHub raw host to execute independent local tests, so GitHub Actions is the available validation path.


## BlueZ 5.82 CLI incompatibility discovered and fixed — 2026-11-25

Physical Orange Pi user ran `bluetoothctl -i <controller> devices Connected` and BlueZ 5.82 responded `invalid option -- 'i'`. The error originates in our scripts/documentation, not the USB controller or BlueZ installation. This invalid option also explains why controller-scoped device enumeration in the TUI would fail, although TUI display functionality is independently unverified.

Fixes to `work/uwe5622-wifi-armbian`:
- `platform/bluetooth/bluez_cli.py`: read-only per-controller queries run `select <MAC>` followed by `devices [Connected/Paired/Bonded/Trusted]` or `info <MAC>` in **the same bluetoothctl session**. Input is validated. If controller selection cannot be verified, refuse to attribute results to that controller.
- `platform/bluetooth/medvetalkie-intercom-test.py`: headless two-adapter inventory now uses that helper instead of nonexistent `bluetoothctl -i`. `medvetalkie-bt-menu.py` also uses the helper for inventory and device info and selects controller inside interactive PTY for pairing. Legacy TUI compatibility path has unsupported option removed (though it is not the supported UI).
- `tests/test_bluez_cli.py`, `tests/test_bt_intercom.py`, `tests/test_bt_menu.py`, `tests/test_bt_tui.py` and CI updated. Docs corrected to use interactive `bluetoothctl`, then `select F4:4E:FC:57:69:64`, `devices Connected`, `select F4:4E:FC:2D:FD:4B`, `devices Connected`.
- CI succeeded for updated code/test commit `6e3b0afe` (one workflow run); no Orange Pi hardware retest after new checkout yet. `main` not touched.
- Next: user pulls work branch and lists real devices via interactive bluetoothctl; then validate dry-run. Do not start live cross-routing without second headset actually connected to second USB adapter.


## Second real Bluetooth headset: UGREEN Studio Pro — 2026-11-25

Operator discovered `UGREEN Studio Pro` (MAC `B0:F0:0C:63:83:F5`) through USB controller `hci1` / `F4:4E:FC:2D:FD:4B`. Real BlueZ trace confirms pairing success, then brief `BR/EDR disconnected with reason 2`, followed by successful `trust` and `connect`: `Paired=yes, Bonded=yes, Trusted=yes, Connected=yes, ServicesResolved=yes`; `Handsfree` UUID `0000111e` advertised; BlueZ battery `0x50 = 80%`; A2DP SEP endpoints and transport created on `hci1`.

**Blocker:** At the end of operator's transcript `devices Connected` on first controller `F4:4E:FC:57:69:64` is **empty**, whereas second controller lists UGREEN Studio Pro. Therefore simultaneous dual-link connectivity has NOT yet been demonstrated. Reconnect prior AIRIDE N1 (`41:42:63:27:E7:3A`) explicitly on first controller using interactive `bluetoothctl select ...` then `connect ...`, and verify both `devices Connected` lists in the same session. Do not remove pairings or modify BT services.

Next after two concurrent connections: inspect both `bluez_card` entries using `pactl list cards` as audio user; select `headset-head-unit` mSBC for UGREEN if available, restore AIRIDE HFP if reverted, confirm both `bluez_input` and `bluez_output`, run `medvetalkie-intercom-test.py --dry-run`, then explicit bounded 30-second bridge test. A2DP endpoint creation alone does not prove UGREEN HFP SCO input/output or microphone performance.


## Both USB controllers simultaneously hold distinct headset BR/EDR connections — 2026-11-25

Physical operator session explicitly verified `bluetoothctl select F4:4E:FC:57:69:64`; `connect 41:42:63:27:E7:3A` returned `Connection successful` and `devices Connected` listed `AIRIDE N1`. Without disconnecting it, operator selected `F4:4E:FC:2D:FD:4B` and `devices Connected` listed `B0:F0:0C:63:83:F5 UGREEN Studio Pro`. **Dual USB Bluetooth BR/EDR connectivity is now physically demonstrated.** UGREEN Studio Pro earlier reported `Paired/Bonded/Trusted/Connected=yes`, Handsfree UUID and battery 80%.

**Not yet tested:** simultaneous *HFP audio* across both adapters, dual PipeWire cards/sinks/sources, bidirectional bridge or packet continuity. Next request `pactl list cards` for both devices; activate `headset-head-unit` on each if offered, verify two BlueZ microphone and sink nodes, then invoke `medvetalkie-intercom-test.py --a 41:42:63:27:E7:3A --b B0:F0:0C:63:83:F5 --dry-run` before any real loopback test.


## Both real headset HFP sinks and microphones simultaneously present — 2026-11-25

Physical operator re-confirmed both distinct BR/EDR connections on separate controllers and successfully issued `pactl set-card-profile bluez_card.41_42_63_27_E7_3A headset-head-unit` and `pactl set-card-profile bluez_card.B0_F0_0C_63_83_F5 headset-head-unit` with no errors. The user-scoped PipeWire Pulse server exposes **both** Bluetooth HFP outputs concurrently: `bluez_output.41_42_63_27_E7_3A.1` and `bluez_output.B0_F0_0C_63_83_F5.1`, both `s16le 1ch 16000Hz SUSPENDED`. It also exposes **both** input nodes: `bluez_input.41:42:63:27:E7:3A` and `bluez_input.B0:F0:0C:63:83:F5`, both `float32le 1ch 48000Hz SUSPENDED`. Thus simultaneous dual Bluetooth audio graph provisioning is physically confirmed; actual active SCO on both links and cross-headset speech are **not** confirmed yet.

Immediate next: pull updated work branch and run `sudo python3 platform/bluetooth/medvetalkie-intercom-test.py --a 41:42:63:27:E7:3A --b B0:F0:0C:63:83:F5 --dry-run`. If validated, perform explicitly initiated 30-second cross loopback test with `--seconds 30 --latency-ms 80`, observe voice directionality, echo, dropouts, cleanup, and HCI traces. Do not mistake `SUSPENDED` for error; nodes idle until streams are active.


## Physical --dry-run failed due async BlueZ CLI command sequencing — 2026-11-25

Operator executed `sudo python3 platform/bluetooth/medvetalkie-intercom-test.py --a 41:42:63:27:E7:3A --b B0:F0:0C:63:83:F5 --dry-run` after both HFP sources/sinks were physically present. It threw `bluez_cli.BluezCommandError: Controller selection was not confirmed`. Raw stdout showed startup `Waiting to connect to bluetoothd...`, delayed asynchronous `select F4:4E:FC:57:69:64`, then a `devices Connected` list including AIRIDE, indicating `bluetoothctl` stdin commands were delivered without waiting for controller-selection acknowledgement. This is a **script synchronisation bug**, not proof of missing headset connectivity.

Changed `platform/bluetooth/bluez_cli.py` from `subprocess.run(input="select ...\\ndevices ...\\nquit")` to PTY-driven staged commands: await startup prompt; issue select; await explicit `Controller <MAC>` acknowledgement **and next prompt**; issue `devices Connected`; await next prompt before returning; bounded timeout and process cleanup; no controller power, bond or PipeWire changes. Added `tests/test_bluez_cli.py` parsing/timing regression cases. `medvetalkie-intercom-test.py` now formats errors without uncaught traceback. Previous CI pass for core updated script `ea8580a8`; newest tests and final changes require GitHub Actions outcome plus physical validation.

Next: git pull, repeat identical `--dry-run`, capture output. Do not invoke live bridge until dry-run completes with correct two independent controller assignments. `main` untouched.


## Second physical dry-run failure: missing Controller acknowledgement after select — 2026-11-25

Operator re-ran the headless `--dry-run` after synchronized PTY fix; it still returned `NOT READY: controller selection timeout or exited`. Transcript shows `[AIRIDE N1]> select F4:4E:FC:57:69:64`, then a normal shell prompt and controller new_settings events, **but no `Controller <MAC>` acknowledgement** when selecting an already-selected controller. Hence PTY acknowledgment scraping remains unreliable; do not keep adding delays as the only fix.

Replaced `controller_inventory` in `platform/bluetooth/medvetalkie-intercom-test.py` with **read-only BlueZ D-Bus via system `busctl`**. Read `org.bluez` object tree, locate `/org/bluez/hciN` adapters and exact device objects for both supplied headset MACs; read each adapter `org.bluez.Adapter1.Address` and each device `org.bluez.Device1.Connected`. Require each target headset to be connected to exactly one distinct adapter MAC before any audio mutation. No PTY, prompt parsing or `bluetoothctl -i` used in the intercom path. Other legacy/menu CLI tooling is independent and remains hardware-unverified.
Added D-Bus topology mocks and absent/disconnected cases to `tests/test_bt_intercom.py`. CI and real Orange Pi dry-run still must be checked for this latest change. If `busctl` unavailable, install/verify it before accepting an automated bridge. Preserve existing headset bonds and audio profiles.


## First physical dual-headset intercom dry-run PASSED — 2026-11-25

Operator on Orange Pi Zero 3 pulled the D-Bus-based intercom script up to `ce11642` and ran:
`sudo python3 platform/bluetooth/medvetalkie-intercom-test.py --a 41:42:63:27:E7:3A --b B0:F0:0C:63:83:F5 --dry-run`.

The real hardware stdout confirmed success:
- A AIRIDE N1 `41:42:63:27:E7:3A` on USB adapter `F4:4E:FC:57:69:64`, active `headset-head-unit`, `bluez_input.41:42:63:27:E7:3A`, `bluez_output.41_42_63_27_E7_3A.1`.
- B UGREEN Studio Pro `B0:F0:0C:63:83:F5` on USB adapter `F4:4E:FC:2D:FD:4B`, active `headset-head-unit`, `bluez_input.B0:F0:0C:63:83:F5`, `bluez_output.B0_F0_0C_63_83_F5.1`.
- `A microphone -> B speaker; B microphone -> A speaker`; target loopback latency 80 ms; final `DRY RUN: no PipeWire modules were changed.`

This is the **first operator-confirmed physical dry-run success** for both concurrently connected HFP headsets and their scoped cross-routing plan. The D-Bus controller verification fixed the prior false timeout. Do NOT label the intercom's live PCM full-duplex audio as tested yet: user still needs to run an explicit bounded 30s live bridge, listen in both directions, and confirm two modules unloaded on exit, then assess echo, quality, interruption, delay and HCI trace. TUI remains unaccepted; main branch untouched.


## First live intercom test: both headsets silent — 2026-11-25

After both HFP endpoints and a successful physical `--dry-run`, user reports **total silence in both AIRIDE N1 and UGREEN Studio Pro** during attempted live bridge. No console stdout, module IDs, sink-inputs/source-outputs, or HCI trace from that live attempt have been supplied. Do not claim successful audio or assign cause to USB hardware before examining active PipeWire graphs.

Added opt-in `--diagnose` for live `medvetalkie-intercom-test.py`: after two `module-loopback` loads and a short settle interval, print read-only `pactl list short` snapshots of loopback modules, sink-inputs, source-outputs, Bluetooth sinks and sources. Retains module cleanup. Added offline read-only test `test_read_only_live_diagnostics`. Hardware validation pending. Next run bounded 15-second test with `--diagnose`, capture exact terminal output; inspect missing module, missing streams, suspended endpoints or incorrect route and distinguish PipeWire failure from HFP SCO failure. Test headset listening/recording independently if needed. No pairing, gain, driver or profile changes yet.


## First live cross-headset speech: ONE DIRECTION WORKS — 2026-11-25

Operator ran 15-second `medvetalkie-intercom-test.py --diagnose` on physical Orange Pi Zero 3 with AIRIDE N1 on hci0 and UGREEN Studio Pro on hci1. Two loopback modules were loaded (IDs `536870916`, `536870917`), PipeWire showed sink-inputs (231->193, 237->143), source-outputs (232->99, 238->180), and both Bluetooth microphone sources and Bluetooth sinks `RUNNING`. The script correctly unloaded both modules afterward.

Operator reports hearing their own voice **in AIRIDE**, while the opposite direction **from AIRIDE microphone to UGREEN speaker was silent** (interpretation: UGREEN mic -> AIRIDE speaker heard; confirm if subsequently ambiguous). So the first live two-device test demonstrates one-way voice, NOT full-duplex or successful two-way bridge. Source/sink `RUNNING` alone does not prove nonzero PCM.

Next isolation: in the same concurrent HFP state, explicitly record the AIRIDE mic to a standalone WAV (5-6 s) and inspect peak/nonzero speech; separately play known-good `/tmp/airide-msbc.wav` or a generated test tone directly to `bluez_output.B0_F0_0C_63_83_F5.1` without loopbacks; inspect AIRIDE mic source mute/gain and UGREEN sink mute/gain. Do not change codecs, profiles or USB driver until the dead leg is identified. If each endpoint works alone, examine loopback channel conversion (source-outputs and sink-inputs were float32le 2ch 48000 despite 1ch Bluetooth endpoints), resampling/remix, and per-stream mute. No persistent intercom service yet.


## AIRIDE microphone and UGREEN speaker independently verified, cross-route still silent — 2026-11-25

Operator performed isolated AIRIDE N1 mic -> WAV -> direct UGREEN Studio Pro playback. They **heard the AIRIDE-recorded voice on UGREEN**, describing telephone-like quality with possible clipping/distortion. Thus standalone microphone capture and remote headset playback work sequentially, but the live `module-loopback` A->B path remained silent while B->A was audible in the previous two-way experiment. Do NOT conclude that either headset endpoint is broken or that PCM clipping is proved. AIRIDE microphone was previously boosted experimentally to 120%; investigate gain and mute while both devices connected before changing codecs/USB drivers.

Added `--direction a-to-b|b-to-a|both` to the bounded headless intercom tester and read-only `--diagnose` snapshot of per-device source/sink mute and volume in addition to active stream inventory. Route isolation is intended to test AIRIDE->UGREEN without activating the reverse route; test does not change source gain, codec or bonds. First compare direct record/play at AIRIDE source gain 100% against prior 120% while watching subjective distortion. If one-way loopback still silent with functional individual endpoints, inspect stream mute/volume and PipeWire graph conversion and link negotiation. Hardware validation of the new flag pending; tests added.


## AIRIDE -> UGREEN live loopback confirmed silent — 2026-11-25

The operator explicitly confirms **no audible speech in UGREEN Studio Pro** during the isolated 15-second `--direction a-to-b --diagnose` live bridge. Nevertheless PipeWire showed the `module-loopback` (ID `536870916`), source-output `280 -> source 99`, sink-input `279 -> sink 193`, AIRIDE microphone and UGREEN sink in `RUNNING`, both unmuted, and clean unload. AIRIDE microphone was still at **120%** despite a recommendation to lower it (source volume readback); UGREEN sink 87%. Sequential AIRIDE mic WAV -> UGREEN paplay was audibly successful but sounded telephone-like/distorted. Do not report bidirectional voice success.

Next discriminating hardware test (no route module): stream AIRIDE mic directly to UGREEN speaker with `parecord --raw --rate=16000 --channels=1 --format=s16le --device=bluez_input.41:42:63:27:E7:3A | paplay --raw --rate=16000 --channels=1 --format=s16le --device=bluez_output.B0_F0_0C_63_83_F5.1` inside the `medvetalkie` PipeWire user session, bounded at 12 seconds. If live PCM pipe works, prioritize replacing/fixing loopback channel/stream linking; if silent, inspect active simultaneous HFP SCO/eSCO events and signal energy. Do not alter bonds, USB drivers or network.


## Raw parecord|paplay live cross-stream also silent — 2026-11-25

User explicitly reports **continued complete silence** in UGREEN Studio Pro during live raw PCM stream `parecord AIRIDE --raw 16000 mono s16le | paplay UGREEN --raw 16000 mono s16le`, despite previously successful sequential AIRIDE mic WAV recording -> UGREEN WAV playback. Earlier `module-loopback` real-time A->B route also silent with source and sink `RUNNING`. This narrows the problem beyond `module-loopback` topology; active simultaneous headset SCO paths or signal continuity, buffering, stream behavior remain unproven. Do not claim a confirmed adapter defect.

Added operator-invoked `platform/bluetooth/cross_pcm_isolation.py` to independently record a WAV of AIRIDE microphone **while simultaneously playing a quiet 440-Hz reference tone to UGREEN**, with exact Bluetooth source/sink selection, bounded 4-20s, printed capture peak/RMS/clipping and per-0.5s levels, optional raw `btmon` capture. No route, gain/profile, bond or driver changes. If nonzero voice captures while UGREEN tone is heard but the live raw pipe is silent, focus on live PCM graph/stream configuration; if tone is silent or capture is empty during concurrency, investigate HFP/eSCO controller handling and monitor `btmon`. No automatic conclusions from PipeWire `RUNNING`. New offline tests `tests/test_cross_pcm_isolation.py` and CI compile step included, physical run pending. Main untouched.


## Cross-HFP concurrent capture and UGREEN tone playback physically confirmed — 2026-11-25

Operator ran `cross_pcm_isolation.py --seconds 8 --btmon` twice on real Orange Pi with AIRIDE N1 (A) / UGREEN Studio Pro (B), both active `headset-head-unit`. **Short reference pips were audible in UGREEN** concurrently with AIRIDE source capture. Each run reported `Test tone played to UGREEN: True`, WAV duration 6.00 s, nonzero captured PCM and zero clipped 16-bit samples: (1) peak -4.3 dBFS, overall RMS -46.1 dBFS; (2) peak -20.9 dBFS, overall RMS -41.8 dBFS. WAV paths `/tmp/medvetalkie-cross-pcm-43mp6f70/airide-during-ugreen-playback.wav`, `/tmp/medvetalkie-cross-pcm-b60dk24_/airide-during-ugreen-playback.wav`; raw btmon captures `bluetooth.btsnoop` in each respective test folder. **No raw HCI trace or WAV bytes were uploaded for inspection.** User reports AIRIDE live voice was **not** audible in UGREEN, unlike the pips. Nonzero waveform metrics do not by themselves prove recorded speech; earlier *sequential* AIRIDE-WAV-to-UGREEN playback was heard.

This disproves blanket claims of inability to run both USB headset PCM endpoints concurrently: UGREEN output can play test audio while AIRIDE input is recording. It does **not** settle whether captured AIRIDE speech is present during simultaneous sink activity or why low-latency direct live stream and loopback are silent. Avoid claims of actual cross-device full duplex. Introduced opt-in `--replay` for `cross_pcm_isolation.py`: immediately after capture and stats, play recorded AIRIDE WAV on UGREEN and ask operator if the live-window spoken words are audible; no gain, profile, pairing or service changes. Next: operator runs the replay test and reports whether voice is captured; if yes, investigate live buffer scheduling/loopback stream properties, if not, SCO capture silence/low energy during simultaneous HFP activity. Need inspect raw btsnoop or captured WAV if hardware issue persists. Main untouched.


## Cross-HFP simultaneous capture then playback CONFIRMED with real voice — 2026-11-25

Physical operator ran `cross_pcm_isolation.py --seconds 8 --replay`, with AIRIDE N1 mic on hci0 and UGREEN Studio Pro HFP output on hci1, both `headset-head-unit`. During the 6-second simultaneous session (quiet test pips -> UGREEN, microphone recording <- AIRIDE), WAV `/tmp/medvetalkie-cross-pcm-behf9mgb/airide-during-ugreen-playback.wav` contained recorded samples: peak -2.7 dBFS, RMS -40.9 dBFS, zero clipped samples; operator **explicitly confirms that the UGREEN played back the exact words spoken into AIRIDE during that overlapping capture**. This proves usable microphone capture while other headset output active and successful delayed replay of that concurrent capture on the second headset.

**Still FAILING:** real-time AIRIDE->UGREEN playback both with Pulse module-loopback and with an on-the-fly `parecord --raw | paplay --raw` pipe (not audible), whereas UGREEN->AIRIDE was audibly demonstrated earlier. Do **not** treat this as a radio/USB-controller SCO limitation without further evidence. Prioritize examining live buffer/stream scheduling, PipeWire loopback stream state and timing, channel remix (earlier loopback streams showed float32le 2ch 48000 despite mono HFP endpoints), and real-time PCM ingress/egress. Do not disable known-good HFP, reset pairing, or promote the experimental bridge to a daemon. Next test should gather independent byte-flow and playback start information during one-way live stream without interpreting `RUNNING` alone as proof of audible PCM.


## Explicit measured live PCM bridge prototype — 2026-11-25

Following physical operator confirmation that concurrently recorded AIRIDE speech is replayed audibly on UGREEN but continuous `module-loopback` and `parecord | paplay` both stayed silent, added isolated `platform/bluetooth/medvetalkie-pcm-relay.py` in the work branch. This is a **new, bounded experimental transport**, not a replacement to production audio or established HFP profiles. It validates the same two separate BlueZ controllers and active HFP input/output via the proven D-Bus/PipeWire checks, then uses explicitly targeted `parecord --raw` and `paplay --raw` processes with 16kHz/mono/s16le, 20-ms (640-byte) frames and requested 80-ms Pulse latency/process time. A 15-frame (300-ms) queue drops oldest frames when output stalls. Reports read/write KiB/s (expected steady state 31.25 KiB/s), queue length, overflow, input RMS/peak/clipping and startup write delta once per second. Owned audio clients stopped on completion/interrupt; no bond/profile/systemd/network/display modifications.

A-to-B diagnostic entrypoint:
`sudo python3 platform/bluetooth/medvetalkie-pcm-relay.py --direction a-to-b --seconds 12 --latency-ms 80`.
Use `--dry-run` first for safety. `--direction b-to-a|both` supported after one-way hardware verification. New offline tests `tests/test_bt_pcm_relay.py` and CI step added; `platform/bluetooth/README.md` updated.

**Hardware validation and audible speech still pending.** A successful write to `paplay` only proves accepted stdin data, not that PipeWire actually renders the packets into SCO. If persistent silence despite healthy capture/write counters, collect PipeWire graph and investigate active render/scheduling or native `pw-loopback`; do not mark real-time full-duplex as fixed. `main` untouched.


## FIRST AUDIBLE LIVE AIRIDE -> UGREEN INTERCOM PASS — 2026-11-25

Operator ran the new bounded `medvetalkie-pcm-relay.py --direction a-to-b --seconds 12 --latency-ms 80` on physical Orange Pi Zero 3. Explicit subjective report: **live speech from AIRIDE N1 microphone was heard in UGREEN Studio Pro**, telephone-like quality, **approximately 0.5 seconds end-to-end latency**. This is the **first live A->B speech success** after silence with `module-loopback` and raw `parecord | paplay` shell pipeline.

Telemetry at 12 s: read/write both 30.6 KiB/s (steady state; theoretical mono 16kHz S16LE 31.25 KiB/s), cumulative received=forwarded=376320 bytes, queue dropped=0 bytes, peak -2.5 dBFS, RMS -35.2 dBFS, clipped samples=0. Bounded test also reported `startup_ms=2` (time to first attempted stdin write, **NOT** perceived end-to-end delay). `errors=['parecord EOF']` only at shutdown; likely lifecycle artifact but not yet conclusively analyzed. Signal sounded like phone quality; profile was mSBC `headset-head-unit` on both headsets in prior confirmation.

**Not yet verified:** live UGREEN->AIRIDE using this new PCM engine, full simultaneous bi-directional duplex with this engine, long-run stability, measured latency/jitter, HCI SCO packet loss. Do not claim production-ready intercom. Next operator tests: `--direction b-to-a --seconds 12 --latency-ms 80` then (if success) `--direction both --seconds 20 --latency-ms 80`. Compare speech directions, overlapping speech and any drop/underrun; only then address ~500ms latency with controlled measurement and buffer reductions. Keep proven profiles, bonds, display and network untouched; `main` untouched.


## FIRST AUDIBLE LIVE UGREEN -> AIRIDE PCM RELAY PASS — 2026-11-25

Operator ran `medvetalkie-pcm-relay.py --direction b-to-a --seconds 12 --latency-ms 80` with real UGREEN Studio Pro mic on hci1 and AIRIDE N1 speaker on hci0. User expressly confirmed **live voice audible** and **subjectively better speech quality** than earlier AIRIDE->UGREEN test. Per-second telemetry converged to 30.6 KiB/s both read and write at 12 s, 0 bytes dropped, queue generally empty, with a 3-frame transient at t=8s. Final received=forwarded=376320 bytes; RMS -16.5 dBFS; peak 0.0 dBFS; `clipped_samples=191` (samples at/above 32760 magnitude), indicating digital near-full-scale saturation. Warn about level/limiting and check whether UGREEN source gain should be reduced experimentally (read current gain first); higher subjective quality alone does not prove intrinsically better microphone hardware. `errors=['parecord EOF']` again appeared during teardown, likely stop-related, not proven.

**Both one-way directions now audible independently on the NEW bounded PCM bridge.** Simultaneous `--direction both` full duplex is NOT yet verified. Next: read UGREEN mic volume via `pactl get-source-volume bluez_input.B0:F0:0C:63:83:F5`, reduce modestly only if high (e.g. above 100%) and note actual value; run explicitly bounded 20-second full-duplex test with both headsets physically separated, monitor two PCM queues, drops, quality, echo, and level. Do not claim full-duplex before physical test. `main` untouched.


## First real concurrent two-direction PCM relay: 20s stream metrics — 2026-11-25

User ran `sudo python3 platform/bluetooth/medvetalkie-pcm-relay.py --direction both --seconds 20 --latency-ms 80` on Orange Pi Zero 3 with two USB controllers and both HFP mSBC headsets. **Both routes were simultaneously active, both reading and writing PCM through their own processes for 20 seconds without queue overflow.** Final stats: AIRIDE->UGREEN received/forwarded=632320/632320 bytes, dropped=0, RMS=-42.0 dBFS, peak=-15.5 dBFS, clipped_samples=0; UGREEN->AIRIDE received/forwarded=691200/691200 bytes, dropped=0, RMS=-24.3 dBFS, peak=0.0 dBFS, clipped_samples=32. Both show `startup_ms=2` (first write, NOT end-to-end latency) and `errors=['parecord EOF']` on teardown. UGREEN mic source gain confirmed as 100% (0 dB) just before test. Data rates converge near 30.9 and 30.6 KiB/s. The differing byte counts reflect different routes and are NOT necessarily dropped audio bytes, since bytes forwarded equal bytes received inside each route.

**Important:** user supplied terminal logs but **has not yet confirmed audible simultaneous speech in both headsets** in this particular test. Do not mark full duplex accepted without that subjective/physical observation, and do not mistake two running PCM routes for audible sound. Need ask if both directions were heard at the same time, whether echo/dropouts occurred, and estimated speech latency. Potential gain imbalance: UGREEN->AIRIDE RMS ~18 dB higher than reverse, 32 near-clipped samples despite UGREEN source 100%; determine whether due to microphone distance, on-device AGC, gain or source. Consider lower test gain after audible duplex confirmation, but preserve existing working settings until evidence.


## Two-headset FULL-DUPLEX audible on physical hardware — 2026-11-25

Operator explicitly confirms **speech was audible simultaneously in BOTH AIRIDE N1 and UGREEN Studio Pro** during 20-second `medvetalkie-pcm-relay.py --direction both` test, with **acoustic microphone feedback**, **noticeable delay** and **different perceived levels**; the voice from UGREEN sounded better. This upgrades previous metric-only evidence to the FIRST REAL FULL-DUPLEX SPEECH PASS on 2 USB UGREEN ATS2851 controllers. It is a prototype demonstration, NOT stable production intercom or echo-cancelled, low-latency service. Previous metrics: 0 dropped PCM queue bytes on both directions; AIRIDE->UGREEN RMS -42.0 dBFS, UGREEN->AIRIDE RMS -24.3 dBFS and 32 near-clipped samples. User confirmed UGREEN source gain 100%; differences could arise from position/AGC and speech level.

Added experimental per-direction PCM **attenuation** `--gain-a-to-b` / `--gain-b-to-a` (0.25..1.0; defaults 1.0) and adjustable 20ms queue depth `--queue-frames` (2..15; default 15) to PCM relay, without changing the hardware source/sink settings or Bluetooth/BlueZ. Goal: controlled listening for acoustic feedback, subjective balance and latency while retaining known-good defaults. Attenuation is NOT AEC; reducing it can lower loop gain but cannot remove acoustic echo. Queue depth is only a maximum, not actual measured buffering; never claim changing queue alone removes the observed ~0.5s total latency. New offline tests cover gain and queue bounds. Next: separate headsets acoustically, test reduced UGREEN->AIRIDE gain (e.g. 0.5) at same 80ms/15frames, then test target 60ms/5frames if quality remains acceptable. Need per-run subjective delay and interruptions, and later native PipeWire AEC/voice gating evaluation. Main untouched.


## Full-duplex attenuated UGREEN->AIRIDE sounds better — 2026-11-25

Physical operator ran 20 seconds of both-direction PCM relay with `--gain-a-to-b 1.0 --gain-b-to-a 0.5` (original Pulse latency target 80 ms, default 15-frame queue). User explicitly reports **sound in AIRIDE improved** after this change. Both directions stayed active; no queued frame drops. Final metrics: A->B 632320 bytes read/written, RMS -41.5 dBFS, peak -2.8 dBFS, 0 near-clipped input samples; B->A 686080 bytes read/written, RMS -20.3 dBFS, peak 0.0 dBFS, 155 near-clipped **input** samples. The level statistics are measured before per-route PCM attenuation; therefore the B->A peak/clipping numbers do NOT describe the attenuated output, and do not establish whether the hardware/input stage is clipped. Source UGREEN is still set to 100% nominal by previous readback. Perceived improvement might result from lowering acoustic loop gain/feedback but cause not proven.

Recommended next measured step: keep both route gains 1.0/0.5 and compare latency target `--latency-ms 60 --queue-frames 5` against prior 80 ms / 15 frames, bounded to 20 s; report intelligibility, feedback, perceptual delay and any `drop`/underruns. Note queue frames sets MAX queue length, not guaranteed actual latency, and original speech delay roughly 0.5s was subjective. Do not enable permanent service or mark AEC solved.


## Reduced buffering: real two-way voice sounds less delayed, still perceptible — 2026-11-25

Operator ran 20-second physical dual-HFP PCM-relay test with `--direction both --seconds 20 --latency-ms 60 --queue-frames 5 --gain-a-to-b 1.0 --gain-b-to-a 0.5`. They expressly report **less perceptible latency than previous 80-ms Pulse / 15-frame (300-ms max queue) test, but some delay remains**. Telemetry indicates steady concurrent PCM on both routes with zero internal queue overflows (queue reported 0/5 at each 1s snapshot, though instantaneous depths between snapshots are not measured), no dropped bytes, and clean teardown except pre-existing `parecord EOF` noted at stop.

Final A->B: 633600 bytes received/forwarded, RMS -44.0 dBFS, peak -19.0 dBFS, 0 near-clipped input samples, ~30.9 KiB/s near t=20s. Final B->A: 687360 bytes received/forwarded, RMS -24.5 dBFS, peak 0.0 dBFS, 7 near-clipped **input** samples, ~30.4 KiB/s near t=20s. Gains remained A->B 1.0 and B->A 0.5, volume is not changed in PipeWire. `startup_ms` tracks first forwarded bytes only, NOT perceived end-to-end speech latency. Both prior subjective acoustic feedback and level imbalance remain to be rechecked at the new settings.

Next diagnostic choice: cautiously compare `--latency-ms 40 --queue-frames 3` while keeping direction gains and 20s duration; expected benefit is uncertain because queue telemetry was already near zero, and PipeWire/Bluetooth HFP/device buffers may dominate. Watch for stutters/underruns even when queue drop counter is zero. Longer term add end-to-end audio impulse/correlation measurement rather than guessing actual latency from requested parameters. DO NOT mark production-ready; main unchanged.


## Dual-HFP bridge tuned to 40ms target / 60ms maximum queue, perceived ~250ms — 2026-11-25

Operator ran 20-second real full-duplex test with `medvetalkie-pcm-relay.py --direction both --seconds 20 --latency-ms 40 --queue-frames 3 --gain-a-to-b 1.0 --gain-b-to-a 0.5`. **Reports approximate perceived speech latency of one-quarter second (~250ms)**, down from initially ~500ms with 80ms target / 15 frames. This is *subjective, not instrumentally measured*, and no audible quality/dropout report was explicitly supplied for this particular run. Both A->B and B->A continued streaming PCM for 20s; queues showed 0/3 nearly all samples (B->A 1/3 at t=1s) and zero internal queue drops.

Final stats A->B: 632320 bytes captured and forwarded, zero drops, RMS -46.4 dBFS, peak -16.9 dBFS, zero near-clipped input samples, ~30.9 KiB/s at t=20s. Final B->A: 692480 bytes captured and forwarded, zero drops, RMS -22.8 dBFS, peak 0.0 dBFS, 58 near-clipped input samples, ~30.7 KiB/s at t=20s. `startup_ms` 1-2ms measures time from first PCM receive to first local write, NOT end-to-end latency. `parecord EOF` again at end of both routes and may be an unclassified teardown artifact. Gain -6dB B->A applied after input metrics; near-clipped samples are raw capture metrics.

For now use these **experimentally best observed low-buffer settings** as reference, but not as proven production-safe: Pulse latency target 40ms, max PCM queue 3 × 20ms, A->B gain 1.0, B->A gain 0.5, dual headset mSBC HFP via two ATS2851 USB dongles. Next priority is instrumented latency/jitter (audio impulse/correlation or PipeWire node timing), stability >20s, echo/feedback and clean EOF classification, not blindly lowering buffers further. Preserve hardware bonds, screen, networking, main branch.


## Experimental soak telemetry and noise gating added — 2026-11-25

Following physical 40ms/3-frame 20s success and operator-estimated ~250ms perceived speech latency, extended the standalone `platform/bluetooth/medvetalkie-pcm-relay.py` on `work/uwe5622-wifi-armbian`:
- Longer **operator-invoked 5..600 second** audio reliability runs with `--report-interval 1..30`; no background daemon. Tracks local maximum gap between `parecord` read calls (`max_capture_gap_ms`), queue maximum observed occupancy (`queue_high_water`), PCM rate, dropped bytes and existing RMS/peaks. A read-gap number is a scheduling diagnostic, NOT one-way audio or HFP latency.
- Optional quiet-frame RMS **noise gate** `--gate-dbfs -48 --gate-floor 0.15 --gate-hang-ms 300`, default **disabled**. Gate attenuates PCM below the threshold and holds it open 300ms after active speech; may reduce acoustic feedback during silence only. **It does not implement acoustic echo cancellation (AEC)**, nor guarantee prevention of howling while both parties speak. Independent per-direction attenuation remains supported.
- Added offline `tests/test_bt_pcm_relay.py` cases for gate open/closed/hangover, quiet-frame attenuation, read gap, 10-minute duration bound; `platform/bluetooth/README.md` details commands and limitations. Real acoustic end-to-end latency remains **not instrumentally measured**; requires physical acoustic reference/mic capture/correlation, and previous 250ms is subjective.
- Next safe physical tests: first 120-second **ungated** full-duplex baseline at `--latency-ms 40 --queue-frames 3 --gain-a-to-b 1.0 --gain-b-to-a 0.5 --report-interval 5`, observing dropouts, echo and real headset disconnections. Then separate optional **20s gated** test, comparing quiet-room feedback and syllable clipping. Do not enable permanent services or merge to main until hardware acceptance and relevant CI checks. Current work changes only Python experimental relay/tests/docs.


## Physical 120-second dual-HFP soak PASS and 20-second optional noise gate telemetry — 2026-11-25

Operator on Orange Pi Zero 3 pulled branch through `02ea4df`, ran the bounded `medvetalkie-pcm-relay.py` full-duplex baseline `--direction both --seconds 120 --report-interval 5 --latency-ms 40 --queue-frames 3 --gain-a-to-b 1.0 --gain-b-to-a 0.5`. Both directions sustained PCM read/write all 120 s; no queue drops, no early subprocess exits and final `errors: []`. Final A->B: received=forwarded=3,827,200 bytes; 0 drops, RMS -64.3dBFS, peak -30.3dBFS, clipped 0, max_capture_gap_ms=48.8, queue_high_water=2. B->A: received=forwarded=3,897,600 bytes; 0 drops, RMS -42.2dBFS, peak -8.2dBFS, clipped 0, max_capture_gap_ms=50.6, queue_high_water=2. Steady rate ~31.1–31.2 KiB/s. The low RMS values reflect the *content of this test*, possibly quiet sections, and do not demonstrate any new permanent reduction of headset microphone gain. No subjective audio quality/dropout report yet. This is the first real 2-minute process-level stability milestone, NOT a proof of no Bluetooth packet loss or production readiness.

Then operator ran full duplex for 20 s with identical 40ms/3-frame/gains plus `--gate-dbfs -48 --gate-floor 0.15 --gate-hang-ms 300`. Both directions completed; 0 queue drops, no errors, max capture gaps 49.8 and 47.3 ms, queue high-water 2. Gate A->B open/closed frames=587/403 (40.7% attenuated quiet frames), B->A=609/473 (43.7% attenuated). Final A->B received=forwarded=633,600 bytes, raw input RMS -38.3 dBFS, peak -0.8 dBFS, clipped 0; B->A received=forwarded=692,480 bytes, raw input RMS -33.2 dBFS, peak -4.9 dBFS, clipped 0. Gate frame counters confirm signal processing but **do not prove audible feedback suppression or proper speech intelligibility**. Need ask operator whether feedback was reduced and whether quiet word onsets were cut. Do not confuse this optional noise gate with actual adaptive acoustic echo cancellation (AEC).

Current best confirmed baseline still ungated full-duplex at Pulse target 40ms / queue 3 frames / gains 1.0/0.5; estimated delay ~250ms subjective from previous test. AEC and synchronized acoustic latency measurement remain open; CI for changes remains a separate validation and must be checked. No changes to `main`.


## Operator acceptance of optional -48dBFS gate: no perceived feedback or word clipping — 2026-11-25

After the 20-second physical two-way HFP test with `--latency-ms 40 --queue-frames 3 --gain-a-to-b 1.0 --gain-b-to-a 0.5 --gate-dbfs -48 --gate-floor 0.15 --gate-hang-ms 300`, operator explicitly reports **acoustic microphone feedback appears to have disappeared**, and **no clipped word beginnings or endings were perceived**. This is subjective listening acceptance on the tested AIRIDE N1 + UGREEN Studio Pro headset pair, not evidence of adaptive acoustic echo cancellation (AEC), measured echo return loss, or generalization to other headsets/rooms.

Mark this particular optional gated profile as **preferred currently heard configuration** for subsequent operator-led comparison, but keep the software gate disabled by default until longer gated endurance and repeatable acoustic measurements succeed. The preceding ungated 120-second soak was successful with zero relay queue drops; the gated profile has only a 20-second physical trial so far. Suggested next safe acceptance: 120-second gated soak, speaking softly/loudly, overlapping speech, physically moving headsets and inspecting `drop`, `max_capture_gap_ms`, gate-open/closed counts and subjective feedback/word onset. Separate true acoustic end-to-end latency measurement and optional native AEC remain future milestones. Do not modify main or BT pairing.


## Physical gated 120s dual-HFP soak passed — 2026-11-25

Operator executed `sudo python3 platform/bluetooth/medvetalkie-pcm-relay.py --direction both --seconds 120 --report-interval 5 --latency-ms 40 --queue-frames 3 --gain-a-to-b 1.0 --gain-b-to-a 0.5 --gate-dbfs -48 --gate-floor 0.15 --gate-hang-ms 300` on Orange Pi Zero 3 with AIRIDE N1 (hci0) and UGREEN Studio Pro (hci1), using two USB UGREEN ATS2851 controllers. Both independently scoped live PCM subprocess pipelines operated through the full 120s run with **zero dropped bytes in Python relay queues and empty error arrays**.

Final AIRIDE->UGREEN: received=forwarded=3,827,200 B, dropped=0, RMS(input)=-45.9 dBFS, peak(input)=-2.5 dBFS, clipped(input)=0, max_capture_gap_ms=47.1, queue_high_water=2 of 3, gate_open_frames=1415, gate_closed_frames=4565 (76.3% quiet frames attenuated). UGREEN->AIRIDE: received=forwarded=3,893,760 B, dropped=0, RMS(input)=-36.0 dBFS, peak(input)=-8.1 dBFS, clipped(input)=0, max_capture_gap_ms=44.0, queue_high_water=2 of 3, gate_open_frames=1884, gate_closed_frames=4200 (67.4% attenuated). Both streams converged near 31.1–31.2 KiB/s; local startup_ms 2/4 are NOT Bluetooth end-to-end latency.

This extends earlier operator-reported 20s gated listening pass (feedback appeared gone, no clipped syllables) with a real **two-minute process/stream stability pass**. Operator has **not yet described subjective intelligibility, feedback, word clipping or dropout observations for the new 120s gated run**, so do not claim audible perfection. Noise gate is still NOT AEC, and neither no Python queue drops nor nominal pipe writes establish zero Bluetooth SCO loss. Current preferred test settings are 40ms Pulse target, three 20ms frames max queued, 16k mono S16LE HFP mSBC, A->B 1.0 and B->A 0.5, optional gate -48dBFS/floor .15/hang 300ms. Further: acoustic latency measurement, genuine AEC evaluation, input gain/clipping and reconnect lifecycle, beyond short tests. Main untouched.

## Subjective intelligibility on 120s gated full-duplex soak — 2026-11-25

Following successful 120-second full-duplex HFP/PCM run with optional -48 dBFS noise gate, operator explicitly confirms speech was **intelligible** ("разборчив"). This adds listening evidence beyond clean process telemetry, but does not independently confirm absence of acoustic feedback or clipped syllable onsets throughout the full two minutes. Earlier 20s gated test had no perceived feedback or chopped syllables. Retain preferred test parameters: 40ms Pulse request, 3x20ms queue, A->B gain 1.0, B->A gain 0.5, gate -48 dBFS, floor .15, 300ms hangover. Continue with controlled comparison of native PipeWire streaming, retaining working Python PCM relay as rollback. Avoid interpreting subjective ~250ms as measured latency or gate as true AEC.
