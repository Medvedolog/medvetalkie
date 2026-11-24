# Control IPC and state model — draft protocol v1

**Implementation status (2026-11-24):** Core API Alpha has read-only health,
capabilities and state queries plus an **opt-in SQLite desired-settings**
prototype. The separate `medvetalkie-web` remains loopback-only and read-only.
Actual display control, HFP/audio, Bluetooth commands, subscriptions,
Android BLE and authenticated remote access are **not** implemented.
This is not a usable intercom and must not be exposed to an untrusted network.

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

Other queries return `NOT_SUPPORTED`. Hardware commands still return
`rejected` / `NOT_READY` **without changing hardware**. The one exception,
`settings.patch`, saves desired configuration in SQLite only when both an
explicit database path and `--allow-local-settings` have been supplied.
Malformed requests return `BAD_REQUEST` and unknown protocol versions return
`UNSUPPORTED_VERSION`. Oversize or truncated frames are dropped.

`medvetalkie-web --ipc-socket /run/medvetalkie/control.sock` exposes only
`127.0.0.1:8765`: `/` (read-only status page), `GET /api/v1/health`,
`GET /api/v1/status` and `GET /api/v1/capabilities`. It returns HTTP 503
when core is unreachable and HTTP 405 for non-GET requests. Additional
read-only endpoints `GET /api/v1/settings` and `GET /api/v1/display` expose
saved desired configuration, not hardware state. No login, remotely accessible
listener, HTTP write API or BLE gateway exists.

The planned general asynchronous hardware operations, authorized HTTP mutations,
event subscriptions, WebSocket and BLE behaviors described earlier are **not yet
implemented**. Never infer HFP readiness or active audio from a healthy core,
two enumerated USB adapters or a running web page.


## Passive USB/HCI observation (2026-11-24)

Core query `bt.controllers` and the loopback-only Web Alpha
`GET /api/v1/bt/controllers` enumerate kernel HCI devices under
`/sys/class/bluetooth/hci*` and discover their USB ancestor's
VID/PID, product and physical-port topology. This is **read-only**;
it never scans, pairs, reloads drivers, starts a voice profile, or
modifies the BlueZ database.

The JSON reply contains `source:"kernel_sysfs"`,
`bluez_state:"NOT_CHECKED"`, `status:"KERNEL_ENUMERATED"`,
`controller_count`, `usb_controller_count`, and a sorted
`controllers` array. A controller includes its temporary `hciN`,
optional address, `transport`, USB port/VID/PID when mapped, and
`hfp_observed:"NOT_CHECKED"`. `identity_verified=false`
until role binding is separately confirmed; **do not** save `hciN`
as stable device identity. USB serials are not returned through HTTP.
An inaccessible sysfs returns `NOT_READY` instead of a fabricated
zero-controller result. Kernel inventory does **not** prove BlueZ
Adapter1 availability, HFP profile readiness or SCO audio.

Host fixture tests use only `--bluetooth-sysfs-root ABS_PATH` on
`medvetalkied` to simulate identical UGREEN ATS2851 devices
(`10d7:b012`) behind different USB ports. That argument is a
local test/developer override, not an API exposed to remote clients.

## Local display startup adapter (2026-11-24)

The `medvetalkie-display-runner` binary reads `settings.get`
from the same Unix IPC contract. It does not modify SQLite or display
settings. The operator supplies an **explicit absolute path** to a
local, non-symlink, non-group/world-writable copy of the verified
`platform/display/medvetalkie-screensaver.sh` from
`work/uwe5622-wifi-armbian`. When run as root it requires that
script to be root-owned.

```sh
./build/medvetalkie-display-runner \
  --ipc-socket /tmp/medvetalkie-api/core.sock \
  --script /opt/medvetalkie/medvetalkie-screensaver.sh --dry-run
```

With `screensaver_enabled=false`, the program does not start the
renderer. Otherwise it prints the validated SPI MHz and FPS it would
use. Only the explicit `--run` option replaces the process with
`/bin/bash` and the script, passing exactly `--spi-mhz N --fps N`;
there is no interpolated shell command. This is **local startup only**:
not systemd autostart, not hot reload, not a WebUI control, and not
yet validated with physical ST7789 hardware as an integrated service.
The hardware screensaver lives in another development branch and is
not silently copied or auto-installed.

## SQLite desired-settings Alpha (local developer interface)

To enable durable settings explicitly, create a **private** state directory
owned by the account running the core. The database is created with permission
`0600`; existing world/group-accessible files and symlinks are rejected.
No fallback to volatile configuration occurs if the database is invalid.
The caller creates the parent directory; the project does not yet ship a
systemd service with `StateDirectory`.

```sh
mkdir -p -m 700 /tmp/medvetalkie-api
./build/medvetalkied \
  --ipc-socket /tmp/medvetalkie-api/core.sock \
  --db-path /tmp/medvetalkie-api/settings.db
```

Without `--db-path`, reads return `NOT_READY` and writes are rejected.
With `--db-path`, `settings.get` and `display.status` are read-only.
**Only for local development**, adding `--allow-local-settings` allows the
same-UID IPC client to save settings. The privilege model is not suitable
for a remotely accessible WebUI until distinct service identities,
fine-grained authorization and authentication are implemented.

SQLite schema `user_version=1` persists one revisioned desired configuration:
`device_name` (1–64 UTF-8 bytes, no control characters), `display.spi_mhz`
(integer 1–16), `display.fps` (integer 1–60), and
`display.screensaver_enabled` (boolean). Defaults are MedveTalkie,
1 MHz, 25 FPS, screensaver disabled. The 1 MHz default is deliberately more
conservative than the 4 MHz speed validated on the real bench. An unsupported
future schema version fails startup rather than silently downgrading.

A same-UID authorized IPC client can send a **single-frame, synchronous**
metadata-only command:

```json
{"v":1,"type":"command","id":"cfg-1","action":"settings.patch",
 "args":{"expected_revision":0,"device_name":"MedveTalkie",
         "display":{"spi_mhz":4,"fps":25,"screensaver_enabled":true}}}
```

The response is a terminal `type=result` with `ok:true`, a new
`revision`, an `operation` identifier, `applied:"saved_only"` and
`hardware_applied:false`. This exception does not change the async
accepted/result design required for future hardware operations. Each patch
validates **all** supplied fields before an atomic SQLite transaction;
unknown settings and malformed types are rejected. Every write requires
`expected_revision`: two clients writing the same revision cause one
success and one `REVISION_CONFLICT`; retries must first read the latest
revision. This implements compare-and-swap safety, not a fully durable
deduplication journal for operation IDs.

The actual ST7789 process is not yet a subscriber to this configuration:
saving `screensaver_enabled=true` does **not** start animation.
`display.status` intentionally reports `observed:"UNKNOWN"` and
`hardware_applied:false`. BlueZ and PipeWire observations are likewise
not inferred from saved values. Tests cover persistence across restart,
concurrent CAS, schema compatibility, read-only mode and input rejection.
