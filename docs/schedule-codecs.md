# Python schedule codecs (unreleased)

JavaScript now exposes the equivalent strict schedule codecs and runs the same
literal vectors. See [profile contract](profile-contract.md) for additional
SET-only models, the exact response-schema gaps, and hardware-proof limits.

These codecs add typed, immutable representations and strict validation, not a
complete snapshot transaction or restore implementation. They do not connect to
hardware. Hardware compatibility and side effects remain unverified.

## Evidence

Base source commit: `9fa5ecfc7f6e82ec02e13d01f00fca7be6852567`.
Wire layouts were independently transcribed from the deployed web client:
<https://lumalou.emanuelestrazzullo.dev/assets/index-CP__DzxD.js>, SHA-256
`30bef51fe4ed6728ccd4a811b7f855368cc587d804a578660da368c2ece70b09`.
The bundle's source commit is unknown. Its builder and parser behavior are
evidence of software encoding, not hardware acceptance. No crypto or protocol
framing was copied or changed. Existing project MIT attribution is retained.

## Layout and API

`lumalou.schedules.ClockTime(hour, minute)` validates 0..23 and 0..59 without
coercing strings, floats or booleans. `None` is encoded as `FF FF`; `00 00`
remains midnight and must never be silently rewritten as disabled.

| Block | Set / request / response | Payload |
| --- | --- | --- |
| Ready-to-rise week | `46 / 47 / 22` | Seven Sunday-first BCD time pairs |
| Sleepy-time week | `48 / 49 / 23` | Seven Sunday-first BCD time pairs |
| Alarm week | `4A / 4C / 27` | Seven high-first alarm nibbles, sound nibble |
| Sunday–Thursday routine | `5A/5B/2B` through `62/63/2F` | BCD time plus twelve task slots |
| Friday routine | `64 / 65 / 90` | Same routine layout |
| Saturday routine | `66 / 67 / 91` | Same routine layout |
| Routine task status | `— / 68 / 94` | Current-step byte plus twelve high-first status nibbles |

Use `WeeklyTimes`, `WeeklyAlarms`, and `DailyRoutine` with the corresponding
`commands.set_r2r_times`, `set_sleepy_times`, `set_r2r_alarms`, and
`set_day_routine` builders. Read requests use `commands.request` and
`request_day_routine`. Responses have individual `responses.parse_*` functions
and a strict `parse_schedule_response(opcode, args)` dispatcher. The caller
must retain the response opcode/day and enforce request freshness/session
identity; a decoded payload alone does not prove those properties.

`0x68` was previously named `SET_ROUTINE_TASK_STATUS` in the specification. The
audited client sends it without arguments to request status. The spec and both
generated bindings now use `REQUEST_ROUTINE_TASK_STATUS`. The old incorrectly
named constant is removed; no setter is exposed. This wire-direction correction
is source-backed, not hardware-verified.

Alarms use the existing `Alarm` enum: 0 active, 1..8 offsets 15..120 minutes,
9 inactive, 10 offset one minute. All sound nibbles 0..15 remain representable;
the code does not claim every sound works on every firmware.

## Routine preservation and limits

A `DailyRoutine` holds exactly twelve `RoutineTask(step, task)` or `None` slots.
`None` encodes `00`; task zero at step one encodes `10` and is not padding.
Steps 1..12 and tasks 0..11 are supported. A raw nonzero step-zero slot, step
13..15, or task 12..15 is rejected as unsupported, not normalized or discarded.
Do not overwrite a device or backup after a parse error; retain the original
bytes outside the decoded model for manual investigation.

Valid raw layouts preserve slot positions, holes, duplicates, nonmonotonic
step order and original step numbers exactly on decode/encode. Unlike the web
decoder, no grouping, sorting or renumbering occurs. `DailyRoutine.from_steps`
is for explicit user edits: it numbers supplied steps from one, keeps task
order, rejects empty steps and more than twelve total tasks, and pads the tail.
Do not pass an imported raw routine through that canonical builder.

All-zero routine bytes mean a midnight time and twelve empty slots. `FF FF`
plus twelve zero slots is a different clear representation. The physical
meaning of empty routines or midnight remains a hardware-validation question.

`RoutineTaskStatus` is runtime only, never persistent replay configuration.
Status nibbles retain values 0..15 without invented enum names. The current-step
byte retains all values 0..255 because its sentinels/range are not established.

## Verification

Shared, synthetic golden vectors live in `spec/schedule-vectors.json`; Python
tests exercise them, malformed sizes/BCD/ranges, every day mapping, the FF/00
distinction, all 1440 valid clock times, and lossless supported slot layouts.
No device addresses, family schedules, captures or secrets are included.
Run `PYTHONPATH=packages/python/src python -m pytest packages/python/tests` with
the package's dev dependencies. See [client contract](client-contract.md) for
session freshness and test-environment isolation.
