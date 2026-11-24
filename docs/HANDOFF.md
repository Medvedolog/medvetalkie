# MedveTalkie — development handoff

**As of:** 2026-11-24  
**Canonical handoff:** `docs/HANDOFF.md` on `work/uwe5622-wifi-armbian`.  
**Status:** Core/Web/UI source code now integrated into the Armbian work branch (2026-11-24). Joint CI gate must pass; **integrated image deployment and full-duplex HFP have NOT been proven**.

## 1. Working agreement — do not create branches for each iteration

- **Primary hardware/image/display integration:** `work/uwe5622-wifi-armbian` ([Draft PR #1](https://github.com/Medvedolog/medvetalkie/pull/1)).
- **Core API / Web Alpha / SQLite / BlueZ / display status producer:** copied and reconciled into `work/uwe5622-wifi-armbian` with the ST7789 renderer. The historic `feature/web-alpha-usb-diagnostics` ([PR #2](https://github.com/Medvedolog/medvetalkie/pull/2)) must not receive further implementation commits.
- `main` stays untouched until integrated tests and agreed release gates pass. `experimental/armbian-wifi-backport` is retained historical experimentation, **not** a branch for new display/API work.
- **Do not spawn a branch per iteration, test or subsystem.** All new MedveTalkie work goes into `work/uwe5622-wifi-armbian` until the release gate. PR #2 was not automatically mergeable; files were deliberately ported while preserving Armbian-specific image and SPI code. Close PR #2 as superseded by this integration after green combined CI; avoid trying to auto-merge duplicate history.
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
- The code from both separate checkouts has since been ported to the same existing Armbian work branch, including a new `core_display_ppm_e2e` regression test. **Combined CI result is pending verification at the time of this handoff update.** No end-to-end physical hardware proof is claimed.

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

1. **Verify integrated code and close redundant PR #2** after successful combined CI. Sources, CMake, workflow, README, architecture, IPC and TZ are reconciled in `work/uwe5622-wifi-armbian`; original Bjorni launcher and onboard-module blacklist are preserved.
2. In unified CI, run **both** `ctest` and `platform/display/screensaver/test-screensaver.py`. The automatic `core_display_ppm_e2e` smoke test now covers `Core API -> display-status producer -> MTSTATUS1 -> ST7789 PPM preview` and fault after Core termination. Monitor CI until all test suites pass; correct regressions before any deployment.
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
- **Gate remains:** green combined CI, independent display test, no mutation of live Orange Pi or `main`, then physical tests of one SPI owner, UGREEN+BlueZ status and Bjorni status transition.

