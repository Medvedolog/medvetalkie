# bt-intercom engineering review and MedveTalkie adoption plan

Reviewed 2026-11-06: [phieri/bt-intercom](https://github.com/phieri/bt-intercom).
This is a **design comparison**, not a code port. Its `LICENSE` is
non-standard and explicitly restricts commercial use and commercial derivatives.
**Do not copy or translate source files, tests, docs or algorithms line by line.**
Implement independent requirements against BlueZ, PipeWire and kernel APIs.

## Actual scope and differences

The external project is a Linux Bluetooth Classic headset intercom using BlueZ
and PipeWire/WirePlumber, with selectable half/full duplex, per-controller
SCO and A2DP capacity budgets, profile switching, PTT, reconnection and
interactive/passive hardware diagnostics. Its current half-duplex default can
place a talker on HFP and a listener on A2DP; this is **not full-duplex**.
MedveTalkie v1.4 explicitly requires **always-open, two-way HFP** between two
helmet users. Do not silently substitute A2DP half-duplex for that requirement.

## Adopted engineering requirements (priority order)

| Priority | Idea | Independent MedveTalkie implementation | Evidence needed |
|---|---|---|---|
| P0 | Per-controller resource budget | Stable controller identity with `sco_budget=1` assumed until measured; reserve one active HFP slot for each helmet; reject unavailable full-duplex configurations | Both eSCO links and actual mic-to-speaker audio simultaneously |
| P0 | Hardware diagnostics before routing | Separate `diagnose --passive` and disruptive `diagnose --active`; passive must never pair, switch profiles or interrupt current audio; active needs explicit opt-in | Timings, HCI events, sample energy and results per controller/headset |
| P0 | Controller-aware pairing | Persist headset-to-controller identity, not `hci0`, PipeWire object ID or USB bus address. Do not migrate bonds or trust unknown devices implicitly | Unplug/replug and restart tests |
| P0 | Full-duplex graph | Headset 1 microphone -> headset 2 output, and reverse, with **no self-monitor**; detect silent mic even when HFP reports ready | Nonzero capture energy and audible signal both directions |
| P1 | Transactional audio graph ownership | Create only uniquely tagged own links; stop/failure releases only those links, never third-party routes; detect contested routes | Synthetic graph tests and process termination |
| P1 | Reconcile, not blind retry | Observe BlueZ and PipeWire; bounded retry with jitter; distinguish paired, connected, profile-selected, SCO-established and verified audio | Disconnects, rfkill, profile disappearance |
| P1 | Controller/seat/session policy | Headless WirePlumber seat policy, correct session owner; per-controller capacity admission before profile switch | Two external USB controllers |
| P1 | PTT/half-duplex optional mode | Press/release state, optional queued request and cancellation, no unbounded microphone-open state across reconnect; **not** the default | Headset button events on tested models |
| P2 | A2DP listener optimization | Explicit optional half-duplex fallback when a controller lacks two SCO channels, with latency and audible gap warnings | A2DP/HFP switching latency, headset-specific behavior |
| P2 | Media priority and notification cues | Unique source routes; reduce media gain while speech detected; avoid confirmation beep as evidence of bidirectional SCO | Level-meter and acoustic tests |
| P2 | Host audio | Separate optional wired mic/speaker control with clear privacy policy; do not mix into full-duplex graph unintentionally | Real speakers/mics |

## Stage gates: two helmet HFP sessions

1. For each controller, enumerate adapter identity and bound helmets; confirm
   the selected HFP profile and its mic/output PipeWire ports.
2. Establish HFP/eSCO and observe HCI `Synchronous Connect Complete` per
   helmet, record synchronous handles and controller index. Success status
   confirms link setup, **not** audio delivery.
3. Capture genuine microphone samples and measure nonzero energy while speaking
   and near-silence while quiet. Record SCO RX/TX and controller errors.
4. Route each microphone to the **other** output; check actual audibility and
   latency, including after both routes are active simultaneously.
5. Only then persist a measured controller capacity; never infer from pairing,
   profile names, the Bluetooth version or the advertised multipoint feature.

## Current Orange Pi Zero 3 evidence

AW859A/UWE5622 internal controller: A2DP playback passes. HFP CVSD and mSBC
both select and eSCO connection completion returns success, but helmet playback
is silent, HCI SCO TX advances and SCO RX remains zero. Experimental module
provides first-H4 RX counters showing no inbound SCO in the observed test.
**Therefore measured bidirectional HFP capacity is zero on this testbed.**
This is not proof that every UWE5622 device or firmware fails.

## Concrete deliverables

- [x] `platform/bluetooth/diagnose-passive.sh`: read-only inventory for BlueZ,
  PipeWire and experimental SDIO RX counters; no audio profile mutation.
- [ ] C daemon controller identity and reservation state; atomic admission of
  two HFP resources in INTERCOM mode.
- [ ] Active diagnostic tool with bounded duration, state restoration and a
  no-audio-by-default report. Human approval before disruption.
- [ ] Per-headset active SCO/PCM energy probe with reproducible test fixtures.
- [ ] Core-owned PipeWire graph lifecycle with rollback for failed transactions.
- [ ] Multi-controller pairing workflow that never silently changes bonds.
- [ ] Failure-injection tests: USB removal, BT reset, headset power loss,
  service restart, partial graph failure.
- [ ] Optional half-duplex A2DP listener mode kept distinct from INTERCOM.

Keep actual device test results in `docs/VALIDATION.md`. In particular, a
clean PipeWire route, HFP profile or beep is never a substitute for validated
two-way voice.
