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
