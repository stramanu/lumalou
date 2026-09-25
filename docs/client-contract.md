# Strict Python client contract (unreleased)

This change is deliberately incompatible with unsafe 0.1.0 behavior. It adds
session-isolated reads and transport validation, not hardware-certified restore.
Transport behavior is tested with fake BLE. The CURRENT_DATE decoder also uses
the limited read-only target evidence described below; this is not hardware
acceptance of the client or profile restoration.

## Home Assistant connection boundary

Construct `LumalouClient(ble_device, expected_device_fingerprint=...,
client_factory=..., on_response=..., disconnected_callback=...)` when the
application must bind sessions to a specific signed device public key. `ble_device`
can be the current `BLEDevice` supplied by Home Assistant. Even without an
expected fingerprint, the client always requires a valid signed FACTORY token.
After successful connection, `device_fingerprint` exposes the SHA-256 digest
of the signed compressed P-256 public key as 64 lowercase hexadecimal characters.
It is `None` before connection and after invalidation. Store it privately after
user confirmation, then supply it on subsequent clients to reject a different
device before any SESSION/TX writes. Do not display or publish it in diagnostics.
This identifies a signed key, not a SKU, and is not proof of live key possession.
No model code or serial suffix is decoded or exposed by the identity API.
The factory has the normal Bleak constructor shape:
`factory(device, disconnected_callback=callback)` and returns a transport with
async `connect`, `disconnect`, `start_notify`, `read_gatt_char`, and
`write_gatt_char` methods. This supports an HA-aware adapter without changing
global Bleak functions. The callback supplied to `disconnected_callback` is
synchronous and receives the `LumalouClient`, after state has been invalidated.

`connect(timeout=20)` creates a new transport, keys, nonce, sequence and
generation; it does not reuse a disconnected transport. On every connection it
verifies the signed FACTORY token and compares supplied identity pins before
notification, key derivation, SESSION, or TX. Identity failures abort and close
the transport. It then performs the session handshake and ENABLE_RX, never
clock/configuration commands.
Passing a `BLEDevice` avoids Bleak's implicit address lookup. A string address
and the explicitly called standalone `scan()` helper remain for CLI callers;
HA must not use that helper. `connect` itself does not start an independent
scanner.

Connection/handshake failure, cancellation, explicit disconnect and unexpected
transport disconnect invalidate callbacks, clear cached observations and fail
the pending request. Old notification closures retain the old generation and
cannot complete a new session's request. Cleanup attempts a bounded five-second
disconnect; repeated caller cancellation does not abandon that attempt. A BLE
backend that refuses disconnect cannot be forced to release hardware; explicit
`disconnect()` reports cleanup failure rather than promising release.

No command retries or automatic reconnections are added. In particular, an
ambiguous Play or other transient command is never replayed.

## Fresh response envelopes

`await client.request(app_data, expected_opcode, timeout=3)` returns an immutable
`ResponseEnvelope(opcode, args, generation, received_at, sequence)`.
`received_at` is monotonic receive time, not wall-clock/device time. `args`
contains exact raw application bytes, without the opcode or frame overhead.
Only a valid response with the exact expected opcode completes a request. Other
known opcodes remain observable through `on_response` but do not complete it.
Commands and requests share a serialization lock; only one request is active.

`request_named(name)` covers the established named requests, including weekly
times, alarms, playlist and clock settings. `request_day_routine(day)` uses the
explicit seven-day response map, including Friday `90` and Saturday `91`.
`request_state()` remains a convenience returning a fresh decoded dict.
`state` is a detached last observation of the current live session only.
Unsolicited valid GLOBAL_STATE notifications update it and call `on_state`.

`ResponseEnvelope.decode()` returns strict GLOBAL_STATE, CURRENT_DATE,
MUSIC_PLAYLIST, CLOCK_SETTINGS, schedule, routine, or task-status models when a
layout is established. Other presently unimplemented payload decoders raise
`UnsupportedResponseError` instead of guessing fields. Fresh playlist and
clock-settings replies were read from one target and cross-checked against its
observed state; compatibility with other firmware remains untested. Typed reads
do not by themselves implement or verify restore.

### CURRENT_DATE is a transient clock reading

Response `13` now decodes to immutable `CurrentDate(hour, minute, second,
weekday)` through `lumalou.responses.parse_current_date` or envelope `decode()`.
It requires exactly four BCD bytes, with hour 0–23, minute/second 0–59 and weekday
0–6 (Sunday first). Invalid BCD, out-of-range values, truncated/extra bytes and
`FF` sentinels are rejected; a malformed live reply retires the session just as
other known typed responses do. Model construction also rejects coercion and
booleans in integer fields.

Read-only target observations supplied on 2026-09-17 established the reply's
four-byte layout and a midnight transition: `23 59 00 03` (23:59:00, weekday 3)
to `00 00 00 04` (00:00:00, weekday 4). This agrees with the existing Python
`set_current_date` encoding and the pinned bundle's `id` setter, whose explicit
ranges are 23/59/59/6. The bundle setter alone was insufficient proof; these
target observations supply the missing response-layout evidence. The target
product code and firmware version remain **unconfirmed**. No calendar date or
timezone was transmitted or inferred, and this evidence does not certify other
firmware or SET behavior.

Despite the protocol name, `CurrentDate` is not a calendar date or a persistent
profile field. Do not save and replay it during restore. It is observable
through response envelopes, does not replace cached GLOBAL_STATE, and retains
the normal same-opcode freshness guard. Tests include the two observed payloads,
synthetic boundaries, all 604800 clock/weekday combinations against the existing
SET encoder, every possible byte value per field, and malformed BLE responses.
Implementation and automated tests made no new hardware/browser connection or
SET call to a device.

### Exhaustive read-only query surface

Python and JavaScript named command builders cover all 28 `REQUEST_*` constants
in `spec/protocol.json`; the seven day-routine requests use their separate day
map. Python `request_named` supplies the exact response opcode for every name.
`spec/read-requests.json` records independent literal command/response vectors
and the pinned deployed bundle URL and SHA-256. Pairings are source-table
semantic matches, not newly observed hardware-correlated exchanges.

The additional query names and hexadecimal IDs are:

| Name | Request | Response |
| --- | --- | --- |
| `routine_mode_status` | `59` | `92` |
| `routine_music_status` | `6A` | `93` |
| `r2r_status` | `45` | `21` |
| `r2r_alarm_status` | `4B` | `26` |
| `nap_current_status` | `4E` | `1C` |
| `nap_alarm_status` | `50` | `24` |
| `nap_alarm` | `51` | `25` |
| `time_prescaler` | `73` | `28` |

The bundle's `te`/`ph` command/response tables establish those IDs; `Oa` contains
all friendly names except the two nap-alarm names, which this library adds from
the explicit `REQUEST_NAP_TIME_ALARM_STATUS` / `NAP_TIME_ALARM_STATUS` and
`REQUEST_NAP_TIME_ALARM` / `NAP_TIME_ALARM_TIME` table labels. Reading the time
prescaler is distinct from unsafe `SET_TIME_PRESCALER` (`52`); the named query
API cannot produce that write or pairing-complete.

No new typed decoders are added for these replies. The deployed notification
dispatcher decodes only global state, daily routines, task status, weekly times
and weekly alarms. Existing setters and fields in GLOBAL_STATE prove their own
encodings, not the byte length or nibble placement of the standalone responses.
The `19` response was freshly read as twelve ordered song IDs, all within the
device's supported `0..12` playlist range. The `99` response was freshly read as
two bytes matching the clock's display flag and packed brightness/format. The
decoders enforce these exact observed shapes. A correctly framed raw envelope
for any other response can contain arbitrary-length bytes: transport
validation is not validation or restore approval for that configuration.

Tests check every literal query opcode, completeness against the declared
request constants, every Python response mapping, and exact outgoing encrypted
query plaintext with a fake BLE transport. They also verify raw preservation,
fresh-session enforcement and rejected unknown/unsafe names. Hardware reads
established the current playlist and clock response lengths; no settings write
was issued for those observations.

## No invented request correlation

The MPID RX sequence is not proven to echo the outgoing request sequence. It
is used only to suppress duplicate RX sequence numbers, never as a request ID.
The client retains up to 4096 sequence numbers in one session, then invalidates
the session instead of allowing unbounded growth or silently forgetting them.

Each expected response opcode may be requested only once per session, and only
if that opcode has not already been observed in the current session. This includes
unsolicited observations during handshake and valid wrong-opcode responses while
waiting for another block. Every validated observation consumes eligibility,
before invoking user callbacks. A new query then raises
`FreshSessionRequiredError` before sending anything; callers must reconnect and
obtain a new generation. The client also rechecks immediately before installing
its waiter and calling the transport write, covering notifications received while
the exchange coroutine is being scheduled. A delayed duplicate carrying a new RX
sequence cannot otherwise be distinguished from a response to the first explicit
query after an unsolicited observation. Different, previously unseen profile
blocks can be read sequentially within one session.

If firmware always pushes a required opcode during handshake, that opcode cannot
be actively queried under this conservative contract. The unsolicited envelope
remains a current-session observation, not a solicited verification result. Do
not implement an unbounded reconnect loop or relax the guard to conceal this
limitation; reliable correlation would require additional protocol evidence.

Timeout, malformed response or cancellation invalidates the entire session and
waits for cleanup. A late old-session response cannot complete the next request.
No cached-state fallback remains. Arrival in a current session proves a fresh
transport observation, not causal acknowledgement of a particular write. An
unsolicited same-type observation during a request cannot be distinguished by
this wire format; callers must compare the decoded values and must not infer a
write acknowledgement or full-profile verification merely from arrival.

## Errors and framing

| Error | Meaning |
| --- | --- |
| `RequestTimeoutError` | Response deadline expired; session invalidated |
| `DisconnectedError` | No usable session, interrupted connection or failed cleanup |
| `MalformedResponseError` | Invalid MPID/FE frame or known typed payload |
| `UnsupportedResponseError` | Unknown opcode/request or unavailable typed decoder |
| `FreshSessionRequiredError` | Repeated response opcode, sequence exhaustion or bounded receive history exhausted |

Transport backend exceptions are retained for connect/write failures. Cancellation
still raises `CancelledError` after cleanup, including when cleanup itself fails.
The common application-error base is `LumalouError`.

The frame format is source-backed by `docs/protocol.md`, `docs/reversing.md`, the
original builders and shared independent golden vectors: eight-byte MPID header,
declared encrypted-body length including CRC byte, header CRC-8 and decrypted
body CRC-8. An FE frame has an exact nonzero declared application length and
the documented XOR checksum. Application responses use the `01 50` route,
present in both the independent `rxDecrypt` / `responseFrame` golden vectors
and their generator. Exact target-observed transport acknowledgements
(`00 7f 01 XX 00 00 00 00 00`, XX = `03`, `06`, `07`, `12`;
`01 10 XX 00`, XX = `04`, `05`, `10`) are ignored
and cannot satisfy a request. Bare FE data, other transmit-route `01 10` payloads, and all other SSI routes are rejected, not guessed from channel
bytes. This is the supported application receive allowlist, not a claim that no
other firmware route can ever exist. New routes require source-backed vectors
before support. Parsing never searches
arbitrary bytes for a later FE marker or accepts trailing/truncated bytes. Valid
non-FE events on the confirmed `01 50` route
(such as the existing `01 50 02 ...` golden vector) are ignored as non-application
events. No fragmentation or reassembly format has been invented; a truncated
notification fails validation and retires the session.

GLOBAL_STATE is exactly thirteen bytes (26 nibbles). Short payloads are no longer
zero-padded and long payloads are no longer truncated. The original 14-byte
positive vector, whose final `0A` was previously ignored, is retained as a
negative vector. The new positive sample explicitly contains its 13-byte prefix;
this is a synthetic fixture correction, not a changed hardware capture.

## Breaking changes and tests

See [profile contract](profile-contract.md) for strict configuration SET models
and the remaining unsupported standalone response layouts. These additions do
not change this client's conservative freshness rules or establish full readback.

- Cache fallback on timeout removed; missing data raises.
- A previously requested or observed response opcode requires a new session.
- Bare FE and SSI routes other than confirmed `01 50` are no longer accepted.
- Invalid GLOBAL_STATE / frame lengths and checksums are rejected.
- Old-session state is cleared on disconnect; `state` returns a copy.
- Factory receives the standard `disconnected_callback` keyword.
- Private `_on_rx` now binds a generation; consumers must use public callbacks.
- Raw undecoded envelope data is not presented as typed profile configuration.

Run Python tests with the asyncio pytest plugin. When using an environment that
also contains Home Assistant's autoloaded pytest plugin, isolate plugin loading:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=packages/python/src \
python -m pytest -p pytest_asyncio.plugin packages/python/tests
```

Tests use only fake BLE transports: disconnect, cancelled/failed handshake,
repeated cancellation, stale/late/duplicate/wrong-opcode frames, timeout without
cache fallback, malformed frames, reconnect and independent raw/typed blocks.
