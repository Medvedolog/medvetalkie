# Control IPC and state model — draft protocol v1

**Implementation status (2026-11-24):** read-only Core API Alpha is implemented
in `medvetalkied`, with a separate loopback-only `medvetalkie-web`
adapter. The full command engine, persistent state, events, SQLite, Android
BLE and authenticated network UI remain planned. Alpha is not a usable HFP
intercom and must not be exposed to an untrusted network.

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


## Implemented API Alpha (read-only)

The core starts explicitly using `medvetalkied --ipc-socket /run/medvetalkie/control.sock`.
The parent directory must be created by the operator or a future systemd
`RuntimeDirectory`. The server deliberately refuses to remove stale socket
paths on startup. The socket is `0600` and requires matching `SO_PEERCRED`
UID; run `medvetalkie-web` under the same trusted UID during Alpha.
Dedicated groups, privilege separation and per-action policies are prerequisites
before enabling remote writes or separate service accounts.

The first frame from a client must be a versioned `query`. The bounded
client library `src/common/ipc.c` implements the network-order 4-byte
length, 64-KiB maximum, complete reads/writes, 1.5-second client timeouts,
and frame rejection on truncation, embedded NUL or oversize length.
The server processes at most eight concurrent peer connections, with a
500-ms I/O timeout per peer; this is **not** an event streaming API yet.

| Query action | Reply | Semantics |
| --- | --- | --- |
| `health` or `system.health` | `type=health` | Core IPC health only, no physical hardware assertion |
| `system.status` | `type=snapshot` | Explicit `UNKNOWN` / `NOT_READY` placeholders, revision 0 |
| `system.capabilities` | `type=capabilities` | Honest implemented / unimplemented feature flags |

Any other query returns `NOT_SUPPORTED`. Every `command` with a syntactically
valid request ID returns `rejected` / `NOT_READY` **without changing state**.
Malformed requests return `BAD_REQUEST` and unknown protocol versions return
`UNSUPPORTED_VERSION`. Oversize or truncated frames are dropped.

`medvetalkie-web --ipc-socket /run/medvetalkie/control.sock` exposes only
`127.0.0.1:8765`: `/` (read-only status page), `GET /api/v1/health`,
`GET /api/v1/status` and `GET /api/v1/capabilities`. It returns HTTP 503
when core is unreachable and HTTP 405 for non-GET requests. No login,
remote listener, write API, BLE gateway or user-configurable settings exist yet.

The planned mutation, operation ID, authenticated HTTP, SQLite, subscriptions,
WebSocket and BLE behaviors described earlier in this document are **not yet
implemented**. Never infer HFP readiness or active audio from a healthy core,
two enumerated USB adapters or a running web page.
