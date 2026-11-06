# UWE5622 Wi-Fi: OpenWrt → Armbian patch review

**Scope:** 30 patches in
[`opiz3-wlan-backport/package/kernel/uwe5622/patches`](https://github.com/Medvedolog/opiz3-wlan-backport/tree/main/package/kernel/uwe5622/patches).
Reviewed against the *source* tree of Armbian
[`bbb8aac1d7cf...`](https://github.com/armbian/uwe5622/tree/bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880).
OpenWrt package source instead pins `cc2835a3f935...`.
**Neither commit is yet established as the source of the installed Armbian
6.18.60-current-sunxi64 modules.**

## Scope decisions

- `010`, `080`: OpenWrt cfg80211 backport guards. **Do not port** to the
  native Armbian 6.18 kernel unless a concrete API mismatch is demonstrated.
- `110`: optional OpenWrt lean profile. **Do not port** in the first stage;
  performance and retained capabilities need separate measurements.
- `020`: optional external Kbuild bind-verification flag. Review separately.
- `210`, `230`, `260`, `300`: debugfs diagnostics, including internal CP
  memory access. **Do not deploy by default** on the end-user platform.

## 30-patch inventory

Each file location refers to the driver *source*, not kernel tree code. The
status column is an inspection decision, **not proof of successful patch apply**.

| ID | Area / purpose | Priority | Decision / risk | Validation |
|---|---|---|---|---|
| 010 | cfg80211 change_beacon OpenWrt backport | — | Skip: OpenWrt only | Native 6.18 API compile |
| 020 | unisocwcn/Makefile external bind flag | P2 | Optional; Kbuild variant | Compare build flags |
| 030 | cfg80211.c, main.c, sprdwl.h virtual-interface locking | P0 | Port candidate; deadlock risk | AP creation/deletion |
| 060 | cfg80211.c, main.c, sprdwl.h dump_station | P2 | Optional stats | `iw station dump` |
| 070 | cmdevt.c, vendor.c VLA removal | P1 | Port candidate; compile warning | `-Werror=vla` build |
| 080 | cfg80211 set_wiphy_params OpenWrt backport | — | Skip: OpenWrt only | Native 6.18 API compile |
| 090 | cfg80211.c, sprdwl.h get_channel/station | P2 | Optional statistics | `iw dev ... info` |
| 110 | Makefile, main.c lean profile | — | Skip initial port | Footprint A/B |
| 120 | cfg80211.c, sprdwl.h AP station accuracy | P2 | Stats-only | AP client telemetry |
| 130 | tx_msg.c, tx_msg.h, wl_core.c atomic TX pool | P0 | Port candidate; TX atomicity | Stress TX, KASAN |
| 140 | cfg80211.c station flags | P2 | Stats correctness | STA station flags |
| 150 | tx_msg.c, txrx.c, wl_core.c, wl_core.h, wl_intf.c LUT accounting | P2 | Counters; depends on TX structures | AP+STA traffic |
| 160 | tx_msg.c ADDBA pre-enqueue | P0 | Port candidate; UAF/race | High-rate TX |
| 170 | cfg80211.c START_AP IE logging | P2 | Debug only | AP setup logs |
| 180 | cfg80211.c 5 GHz DS params | P1 | Port candidate; firmware-specific | Channel 36 AP |
| 190 | tx_msg.c, wl_core.h per-TID time array | P0 | Port candidate; OOB risk | TX ADDBA/TID |
| 200 | cfg80211.c verified width/channel clamp | P1 | Port candidate; channel/DFS policy | 2.4/5 GHz channel list |
| 210 | debugfs RX descriptor dump | P2 | Defer: raw debugfs surface | Controlled debug build |
| 220 | sdiohal_main.c failed-I/O unlock | P0 | Port candidate; SDIO deadlock | Fault injection |
| 230 | debugfs CP station table | P2 | Defer: firmware introspection | Controlled debug build |
| 240 | cfg80211.c, wl_core.c, wl_core.h TX rate | P2 | Optional FW statistics | Traffic + rate comparison |
| 250 | sdiohal_main.c SDIO unregister | P0 | Port candidate; BSP reload prerequisite | Repeated unload/load |
| 260 | wl_core.c CP firmware memory debugfs | P2 | Defer: raw firmware memory | Restricted debug build |
| 270 | cfg80211.c, wl_core.c, wl_core.h station byte counters | P2 | Optional statistics | AP client counters |
| 280 | cfg80211.c, main.c capability/reporting fixes | P2 | Optional; hardware ID stability | `iw phy` and Wi-Fi logs |
| 290 | cfg80211.c, main.c per-interface MAC | P1 | For concurrent AP+STA; firmware assumptions | Dual interface MAC/WPA |
| 300 | wl_core.c debugfs Wi-Fi RAM tables | P2 | Defer: low-level debug access | Controlled debug build |
| 310 | cfg80211.c disconnect-event wait | P1 | Port candidate; STA+AP sequencing | Roaming / context teardown |
| 320 | cfg80211.c, cmdevt.c context lifecycle logs | P2 | Debug only; log volume risk | Long run log count |
| 330 | loopcheck.c self-cancel prevention | P0 | Port candidate; self-deadlock | Firmware assert test |

**Confirmed by direct source inspection** on upstream `bbb8aac1`:
`130`: `tx_msg.c` still uses `GFP_KERNEL` in data TX pool allocation;
`160`: `prepare_addba()` still follows `sprdwl_queue_data_msg_buf()`;
`190`: `wl_core.h` still declares `time[6 + 1]`;
`220`: `sdiohal_main.c` retains `dt_rw_fail` early return paths without unlock;
`250`: no `sdiohal_drv_registered` tracking is present;
`330`: loopcheck work still calls `stop_loopcheck()` in its own work callback.

These observations warrant a patch review; they do not establish functional
equivalence or actual deployed-module provenance.

## Actual static audit result (pinned sources)

GitHub Actions `UWE5622 upstream patch audit` was run with upstream
`bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880` and OpenWrt patch tree
`29b6faf6b08a2b62097e509eb0fa62720ab48996`.

| Outcome | Patch IDs | Count |
|---|---|---:|
| Cumulative `git apply` accepted | 020, 030 (Armbian-rebased), 060, 090, 120, 130, 140, 150, 160, 170, 180, 190, 200, 220, 250, 280, 290 (Armbian-rebased), 310, 320, 330 | 20 |
| Reverse check accepted (present) | 070 | 1 |
| Conflicted | 210, 230, 240, 260, 270, 300 | 6 |
| Intentionally excluded | 010, 080, 110 | 3 |

The conflicts describe this **cumulative order** only. Several diagnostic
patches alter the same `wl_core.c` debugfs block; apply order and dependencies
must be reviewed before deciding whether to rebase them.

**P0 improvement:** The Armbian-specific adaptation of `030` now passes the
pristine upstream check and cumulative patch application. This addresses the
previous source conflict, not the need for a kernel compile and hardware AP
lifecycle test. `130`, `160`, `190`, `220`, `250` and `330` also pass source
patch application checks, but are not compiled or tested on hardware.

**AP+STA improvement:** Rebased `290` on the native Armbian source by removing
its dependency on OpenWrt-only lean profile `110`. The rebase also lets `320`
apply in series. Validate AP and STA interface MACs and WPA negotiation on
the board before enabling a repeater mode.

## Automated audit

The `UWE5622 upstream patch audit` workflow checks out both repositories
at immutable commits and generates a 30-row artifact using
`tests/audit-patches.sh`. It reports cumulative `git apply` status, not
module compile results or installed ABI compatibility. An earlier unresolved
patch may cause subsequent conflicts.

## ABI gate — required before .ko build/install

1. Capture the **actual** `uname -r` and hash/path/vermagic of both installed
   `uwe5622_bsp_sdio.ko` and `sprdwl_ng.ko`.
2. Capture matching Armbian kernel headers/build tree, `Module.symvers`,
   `.config`, compiler identity and any vendor symbol dependencies.
3. Ensure the source for the installed modules and chosen base commit is known.
4. Build **only WLAN+BSP**, never replace `sprdbt_tty` or BT firmware.
5. Compare the two module `vermagic` strings, export symbol availability,
   build ID and dependency closure; publish experimental artifacts only.
6. Keep old modules and wired rescue channel; activation requires local
   hardware testing with rollback verified.

Passing a source patch check, including all 30 patches, is **not** proof of
correct functionality, valid ABI, or safe SDIO reset.
