# UWE5622 / AW859A HFP investigation: patch series

**Status:** code-review candidates only. **Not compiled against the test SBC kernel and not deployed or audio-validated.** The test environment still has working A2DP; preserve it.

## Reference source

Patch context based on `armbian/uwe5622`, commit
`bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880` (upstream master as checked on 2026-11-06).

https://github.com/armbian/uwe5622/tree/bbb8aac1d7cf671af8dd07d3d9a17e0fd35ea880/tty-sdio

The **actual source revision used to build** the installed
`6.18.60-current-sunxi64` module has not been established. The source-level patch application check is not binary equivalence and not a kernel-module build test.

The Orange Pi currently runs `/usr/bin/hciattach_opi -s 1500000 /dev/ttyBT0 sprd`, which depends on the working WCN BSP and `sprdbt_tty`. No change is made to the firmware, attaching speed, rfkill, the original module or systemd service by this repository.

## Patch order

1. `patches/0001-sprdbt-tty-add-hci-rx-sdio-counters.patch` adds cumulative, read-only sysfs counters: received SDIO blocks, first H4 type 0x02/0x03/0x04/other, partial TTY insertions, backlog use and backlog allocation failure. No per-packet logging. **Limitation:** first H4 byte of each SDIO block only; this does not parse multiple HCI frames within one block or independently verify block length, so type counts are indicators, not a complete packet census. Source-side instrumentation does not itself enable SCO.
2. `patches/0002-sprdbt-tty-fix-rx-queue-ownership.patch` prevents the overflow queue from overwriting a bus-owned `mbuf_t` and returning that altered structure to the SDIO pool. The queued bytes get their own allocation and are freed by the worker. It also replaces an unbounded tight loop on full TTY buffers with up to ten bounded, sleepable attempts, then emits a rate-limited warning for discarded remainder. **Risk:** an exhausted TTY can still result in dropped HCI frame bytes and framing loss; this patch does not solve flow control. It must be reviewed under sustained load.

These are not proofs of the root cause of **595 SCO TX vs 0 SCO RX**. Static inspection found no explicit inbound type-0x03 filter in `mtty_rx_cb`; failure may occur earlier in WCN/SDIO voice routing.

## Non-invasive verification

From a checkout of this repository:

```sh
# Use an existing checkout of armbian/uwe5622 at the reference commit.
sh platform/uwe5622/tests/verify-patches.sh /path/to/uwe5622
```

This copies only `tty-sdio/tty.c` into a temporary directory; it does not modify the source. The two patches must apply in order. A successful result is a **patch-context check only**.

## Build/deployment gate

Before compiling or loading either patch:

- Obtain exact Armbian board/kernel driver source revision and matching 6.18.60 headers, configuration and symbol version files.
- Review patch 0002's handling of backpressure, locking and lifecycle against the actual source.
- Build the module using the matching Armbian kernel build tree; confirm unchanged firmware/BSP ABI, module dependencies, and `vermagic`.
- Back up installed `sprdbt_tty.ko` and preserve SSH-over-Ethernet recovery. Do **not** hot-unload the active Bluetooth driver while `hciattach_opi` is attached.
- Validate HFP diagnostics on a test image or maintenance window, first A2DP regression, then CVSD/mSBC and raw HCI counters.

## Hardware validation after instrumented test build

```sh
# The exact path of the device may vary; discover it after loading.
find /sys/devices -name hci_rx_stats -print
# Read discovered read-only sysfs counter file before/after ~5 s HFP attempt.
# Compare to:
hciconfig -a hci0 | grep -E 'RX bytes:|TX bytes:'
```

If `first_h4_sco` increases, debug TTY delivery/HCI reception. If it stays zero, the SDIO first-frame proxy received no SCO type; probe the raw channel and verify WCN routing before concluding firmware fails. The source counters cannot prove no SCO frames elsewhere in a multi-frame SDIO block.

Bench report: [docs/HARDWARE-BENCH-2026-11-06.md](../../../docs/HARDWARE-BENCH-2026-11-06.md).
