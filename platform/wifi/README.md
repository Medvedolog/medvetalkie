# UWE5622 / AW859A Wi-Fi stabilization for Armbian (experimental)

**Goal:** port selected proven OpenWrt reliability fixes to Orange Pi Zero 3 Armbian 26.11.0 / Linux 6.18.60, without changing the stock image or firmware.

**Baseline source:** `armbian/uwe5622` commit `bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880`. The precise source revision used to build the *installed* kernel modules still needs verification.

**Patch provenance:** [Medvedolog/opiz3-wlan-backport](https://github.com/Medvedolog/opiz3-wlan-backport/tree/main/package/kernel/uwe5622/patches).

## Stage A: isolated source-level port

| Original patch | Problem addressed | Review requirement |
| --- | --- | --- |
| 220 | Sunxi SDIO card lock not released on failed direct I/O | Shared WCN/Bluetooth core: check fault and recovery behavior |
| 330 | WCN loopcheck callback synchronously cancels its own work | Check device heartbeat failure handling |
| 310 | STA disconnect returns before WCN firmware confirms disconnect; impacts AP+STA | Wait up to 1 second, test station/AP teardown |

These are **candidate patches, not built or deployed kernel modules**. They are taken verbatim from our own OpenWrt patch series so each original is traceable, and verified for patch-context applicability by CI. Patch 310 is intentionally more behavior-changing and should be deployed only after the first two are validated.

## Deferred pending exact-driver rebase

- OpenWrt compatibility/cfg80211 shims, netifd-specific adjustments, build options: **do not port**.
- 130 TX allocation from atomic context: useful, but separate correctness change and telemetry patch.
- 160 ADDBA race and 190 TID array bounds: rebase together with the dependent TX/accounting changes; inspect independently before applying.
- 180 5 GHz DS Params and 200 channel-width clamping: evaluate AP behavior and buffer capacity separately; avoid imposing OpenWrt-specific channel policy on Armbian.
- 250 SDIO unregister: broader WCN lifecycle change, do not mix with initial work.
- Debugfs probes: optional after actual fault reproduction.

## CI verification

```sh
sh platform/wifi/tests/verify-source-patches.sh /path/to/armbian-uwe5622
```

The script copies three target files to a temporary directory and applies the three patches sequentially with fuzz disabled. It does not change the supplied source checkout or any installed kernel module.

After source-context validation, next gate is **compilation against exact Armbian headers + Module.symvers**, then recording `modinfo`, exported symbol dependencies and build source commit. Only then consider a reversible module override on the physical board, keeping SSH over wired Ethernet. **Never hot-reload shared WCN/SDIO while Wi-Fi is the only access path.**

Built-in AW859A Bluetooth SCO research is paused; MedveTalkie voice will be tested with two independent UGREEN CM390 controllers. No HFP claims should be derived from this Wi-Fi work.
