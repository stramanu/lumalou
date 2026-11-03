"""Decode device responses.

Two layers. The ``parse_*`` functions are the 0.2.0 API and return plain dicts/lists of
raw integers (use label() for names). The ``decode_*`` functions are strict and typed
(PR #2): exact lengths, valid BCD, frozen dataclasses; the strict client uses them."""

from __future__ import annotations

from dataclasses import dataclass

from ._generated import RESPONSES, Color, OperationMode, Stage
from .profile import ClockSettings, MusicPlaylist
from .schedules import (
    DAY_ROUTINE_RESPONSES,
    DailyRoutine,
    RoutineTaskStatus,
    WeeklyAlarms,
    WeeklyTimes,
    decode_daily_routine,
    decode_routine_task_status as _decode_task_status,
    decode_weekly_alarms,
    decode_weekly_times,
)


@dataclass(frozen=True)
class CurrentDate:
    """Transient device clock reading, not a calendar date or zoned timestamp.

    Weekday uses the source-backed Sunday=0 through Saturday=6 convention.
    No calendar date, timezone or persistence can be inferred from this reply.
    """

    hour: int
    minute: int
    second: int
    weekday: int

    def __post_init__(self) -> None:
        for name, maximum in (
            ("hour", 23),
            ("minute", 59),
            ("second", 59),
            ("weekday", 6),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError(f"{name} must be an integer from 0 to {maximum}")


def decode_current_date(args: bytes) -> CurrentDate:
    """Decode exactly four BCD bytes: hour, minute, second, weekday (0x13)."""
    if not isinstance(args, bytes) or len(args) != 4:
        raise ValueError("CURRENT_DATE must contain exactly 4 bytes")
    if any(byte >> 4 > 9 or byte & 0x0F > 9 for byte in args):
        raise ValueError("CURRENT_DATE contains invalid BCD")
    return CurrentDate(*(10 * (byte >> 4) + (byte & 0x0F) for byte in args))


def parse_music_playlist(args: bytes) -> MusicPlaylist:
    """Decode the observed ordered 12-byte playlist response (0x19)."""
    if not isinstance(args, bytes) or len(args) != 12:
        raise ValueError("MUSIC_PLAYLIST must contain exactly 12 bytes")
    if any(song > 12 for song in args):
        raise ValueError("MUSIC_PLAYLIST contains a song ID outside 0..12")
    return MusicPlaylist(tuple(args))


def decode_clock_settings(args: bytes) -> ClockSettings:
    """Decode the target-observed two-byte clock settings response (0x99)."""
    if not isinstance(args, bytes) or len(args) != 2:
        raise ValueError("CLOCK_SETTINGS must contain exactly 2 bytes")
    if args[0] not in (0, 1):
        raise ValueError("CLOCK_SETTINGS has an unknown display value")
    brightness, clock_format = args[1] >> 4, args[1] & 0x0F
    if brightness > 9 or clock_format > 1:
        raise ValueError("CLOCK_SETTINGS has unsupported reserved bits")
    return ClockSettings(bool(args[0]), brightness, clock_format)


def decode_r2r_times(args: bytes) -> WeeklyTimes:
    return decode_weekly_times(args)


def decode_sleepy_times(args: bytes) -> WeeklyTimes:
    return decode_weekly_times(args)


def decode_r2r_alarms(args: bytes) -> WeeklyAlarms:
    return decode_weekly_alarms(args)


def decode_day_routine(args: bytes) -> DailyRoutine:
    return decode_daily_routine(args)


def decode_routine_task_status(args: bytes) -> RoutineTaskStatus:
    return _decode_task_status(args)


def decode_schedule_response(
    opcode: int, args: bytes
) -> WeeklyTimes | WeeklyAlarms | DailyRoutine | RoutineTaskStatus:
    """Decode a known schedule/status response; never infer an unknown layout."""
    if type(opcode) is not int:
        raise ValueError("response opcode must be an integer")
    if opcode in (0x22, 0x23):
        return decode_weekly_times(args)
    if opcode == 0x27:
        return decode_weekly_alarms(args)
    if opcode in DAY_ROUTINE_RESPONSES.values():
        return decode_daily_routine(args)
    if opcode == 0x94:
        return decode_routine_task_status(args)
    raise ValueError(f"unsupported schedule response: {opcode:#x}")


def _nibbles(data: bytes):
    out = []
    for b in data:
        out.append(b >> 4)
        out.append(b & 0x0F)
    return out


def decode_global_state(args: bytes) -> dict:
    """Strict GLOBAL_STATE (0x02): exactly the 13 bytes the device sends."""
    if not isinstance(args, bytes) or len(args) != 13:
        raise ValueError("GLOBAL_STATE must contain exactly 13 bytes")
    return parse_global_state(args)


def parse_global_state(args: bytes) -> dict:
    """Decode the GLOBAL_STATE snapshot (response 0x02) into raw integer fields.

    0.2.0 behaviour, kept: a short payload is zero-padded rather than rejected. The
    strict client uses decode_global_state instead."""
    n = _nibbles(args)
    while len(n) < 26:
        n.append(0)
    return {
        "operationMode": n[0],
        "activityState": n[1],
        "musicStatus": n[2],
        "currentSong": (n[3] << 4) | n[4],
        "currentVolume": n[5],
        "playlistDuration": n[6],
        "lightStatus": n[7],
        "lightBrightness": n[8],
        "lightColor": n[9],
        "napTimeStatus": n[10],
        "napDuration": n[11],
        "ready2RiseStatus": n[12],
        "ready2RiseAlarmStatus": n[13],
        "timePrescaler": n[14],
        "currentStage": n[15],
        "clockDisplay": n[16],
        "clockBrightness": n[17],
        "clockFormat": n[18],
        "routineMusicStatus": n[19],
        "taskRewardSfx": n[20],
        "routineRewardSfx": n[21],
        "lightDuration": n[22],
        "routineVolume": n[23],
        "routineModeStatus": n[24],
        "alarmExecuting": n[25],
    }


def _unbcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def parse_day_routine(args: bytes) -> dict:
    """Inverse of the day-routine encoder. Confirmed on hardware: the device
    echoes back exactly the bytes that were written."""
    if len(args) != 14:
        raise ValueError(f"a day routine is 14 bytes, got {len(args)}")
    if args[0] == 0xFF and args[1] == 0xFF:
        time = None
    else:
        time = (_unbcd(args[0]), _unbcd(args[1]))
    steps: dict[int, list[int]] = {}
    for byte in args[2:]:
        if byte == 0x00:
            continue                    # padding
        steps.setdefault(byte >> 4, []).append(byte & 0x0F)
    return {"time": time, "steps": [steps[k] for k in sorted(steps)]}


def parse_weekly_times(args: bytes) -> list:
    """Decode READY_TO_RISE_TIMES / SLEEPY_TIME_TIMES: seven BCD pairs,
    Sunday first. FF FF means the day is disabled."""
    if len(args) != 14:
        raise ValueError(f"weekly times are 14 bytes, got {len(args)}")
    out = []
    for i in range(0, 14, 2):
        hour, minute = args[i], args[i + 1]
        out.append(None if hour == 0xFF and minute == 0xFF else (_unbcd(hour), _unbcd(minute)))
    return out


def response_name(opcode: int) -> str:
    return RESPONSES.get(opcode, f"0x{opcode:02x}")


def label(state: dict) -> dict:
    """Add human-readable labels to a decoded GLOBAL_STATE (non-destructive)."""
    out = dict(state)
    try:
        out["operationModeLabel"] = OperationMode(state["operationMode"]).name
    except ValueError:
        pass
    try:
        out["currentStageLabel"] = Stage(state["currentStage"]).name
    except ValueError:
        pass
    try:
        out["lightColorLabel"] = Color(state["lightColor"]).name
    except ValueError:
        pass
    return out


def parse_r2r_alarms(args: bytes) -> dict:
    """Decode READY_TO_RISE_ALARM_TIMES: seven Alarm ids then the sfx id,
    nibble-packed. Observed on hardware: 99999990 = every day INACTIVE, sfx 0."""
    if len(args) != 4:
        raise ValueError(f"alarm times are 4 bytes, got {len(args)}")
    n = _nibbles(args)
    return {"days": n[:7], "sfx": n[7]}


def parse_routine_music_status(args: bytes) -> dict:
    if len(args) != 2:
        raise ValueError(f"routine music status is 2 bytes, got {len(args)}")
    return {"music": args[0],
            "task_rewards": args[1] >> 4,
            "routine_rewards": args[1] & 0x0F}


def parse_clock_settings(args: bytes) -> dict:
    """Decode CLOCK_SETTINGS. Nibbles are [reserved, display, brightness, format]."""
    if len(args) != 2:
        raise ValueError(f"clock settings are 2 bytes, got {len(args)}")
    n = _nibbles(args)
    return {"display": n[1], "brightness": n[2], "format": n[3]}


def parse_current_date(args: bytes) -> dict:
    """Decode CURRENT_DATE: BCD hour, minute, second, then the weekday (0 = Sunday)."""
    if len(args) != 4:
        raise ValueError(f"current date is 4 bytes, got {len(args)}")
    return {"hour": _unbcd(args[0]), "minute": _unbcd(args[1]),
            "second": _unbcd(args[2]), "weekday": args[3]}


def parse_routine_task_status(args: bytes) -> dict:
    """Best-effort decode of ROUTINE_TASK_STATUS (7 bytes).

    The internal layout is not yet confirmed: on hardware the response was
    all-zero because no routine was running. The working hypothesis, matching
    the app's RoutineTaskStatus(sequence, map) shape, is one byte of current
    step followed by twelve nibbles of per-task state. The raw bytes are always
    returned so callers can fall back to showing them.
    """
    out = {"raw": args.hex()}
    if len(args) == 7:
        out["current_step"] = args[0]
        out["task_states"] = _nibbles(args[1:])
    return out


# opcode -> parser. Day-routine responses share one layout.
_PARSERS = {
    0x02: parse_global_state,
    0x13: parse_current_date,
    0x22: parse_weekly_times,
    0x23: parse_weekly_times,
    0x27: parse_r2r_alarms,
    0x93: parse_routine_music_status,
    0x94: parse_routine_task_status,
    0x99: parse_clock_settings,
    **{op: parse_day_routine for op in (0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x90, 0x91)},
}


def parse_response(opcode: int, args: bytes):
    """Decode a response when its layout is known, else return the raw bytes."""
    parser = _PARSERS.get(opcode)
    return parser(args) if parser else args
