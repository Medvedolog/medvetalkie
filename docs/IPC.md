# Control IPC and state model — draft protocol v1

**Design proposal; not implemented by the initial C skeleton.**

## Transport

- Unix domain stream sockets under `/run/medvetalkie/`, restricted filesystem permissions, `SO_PEERCRED` authorization.
- Four-byte network-order unsigned payload length, then UTF-8 JSON bytes. Maximum frame 65,536 bytes. Reject oversized/malformed frames.
- Protocol field `v: 1` mandatory; unknown major versions rejected.
- Every mutating request contains a stable `id`. Never confuse an **accepted** command with a **completed** hardware operation.
- Per-connection subscription receives initial full state snapshot then sequenced events; on missed sequence or reconnect, request a fresh snapshot.

Example command:

```json
{"v":1,"type":"command","id":"12a","action":"mode.set","args":{"mode":"INTERCOM"}}
```

Acceptance:

```json
{"v":1,"type":"accepted","id":"12a","operation":"op-184"}
```

Later completion:

```json
{"v":1,"type":"result","operation":"op-184","ok":false,"error":{"code":"HEADSET_AUDIO_NOT_READY","message":"HFP microphone is unavailable"}}
```

State:

```json
{"v":1,"type":"snapshot","revision":201,"state":{"desired_mode":"INTERCOM","effective_mode":"DEGRADED","headsets":[{"role":"headset_1","state":"HFP_READY"},{"role":"headset_2","state":"RECOVERING"}]}}
```

## State machine

Each logical headset follows:

```text
UNASSIGNED --configure--> DISCONNECTED --connect--> CONNECTING
CONNECTING --ACL connected--> CONNECTED_NO_AUDIO
CONNECTED_NO_AUDIO --select profile--> PROFILE_PENDING
PROFILE_PENDING --SCO+PW source/sink available--> HFP_READY
PROFILE_PENDING --A2DP sink available--> A2DP_READY
any connected state --lost link--> RECOVERING --> CONNECTING
recover retries exhausted --> ERROR (retry/manual recovery available)
```

Identity, Bluetooth ACL, profile control connection, SCO transport, PipeWire input/output and audio route **must be tracked separately**. `HFP_READY` requires usable audio in both directions; `CONNECTED_NO_AUDIO` is not success.

## Global mode policy

| Mode | Preconditions | Failure behavior |
| --- | --- | --- |
| INTERCOM | Two compatible roles, two active HFP/SCO channels | DEGRADED, reconnect with backoff |
| SOLO_STEREO | One A2DP-capable headset | Preserve previous route or report failure |
| ANDROID_MEDIA | Phone A2DP source + Linux sink + helmet A2DP | Capability gate; no implied HFP |
| ANDROID_BRIDGE_CALL | Phone-facing HFP HF + headset-facing HFP AG | Experimental, disabled until verified |
| PHONE_DIRECT | Release helmet bond/session to phone | Suspend automatic capture |
| RADIO / GAME | Source available + audio graph route | Intercom remains highest priority |

Operations should not run concurrently when they mutate the same controller or audio route. Mode transitions require timeouts and cancellation rules. The core owns the requested state; hardware services report the observed state. After process restart, never synthesize success from persisted mode settings.

## Web mapping

Planned `GET /api/v1/state`, `GET/PATCH /api/v1/settings`, `POST /api/v1/mode`, `POST /api/v1/wifi/ap`, `GET /api/v1/diagnostics`, `WS /api/v1/events`. These are not live endpoints yet.

Authenticated sessions required even when the AP is private. CSRF protection for mutable HTTP calls, input validation, operation audit trail without storing PSKs/bond keys. WebSockets must be authenticated and rate-limited. All local/remote clients share one command policy.
