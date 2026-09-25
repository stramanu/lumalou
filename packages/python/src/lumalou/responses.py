"""Decode device responses. Values are raw integers (canonical); use label() for names."""

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
    decode_routine_task_status,
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


def parse_current_date(args: bytes) -> CurrentDate:
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


def parse_clock_settings(args: bytes) -> ClockSettings:
    """Decode the target-observed two-byte clock settings response (0x99)."""
    if not isinstance(args, bytes) or len(args) != 2:
        raise ValueError("CLOCK_SETTINGS must contain exactly 2 bytes")
    if args[0] not in (0, 1):
        raise ValueError("CLOCK_SETTINGS has an unknown display value")
    brightness, clock_format = args[1] >> 4, args[1] & 0x0F
    if brightness > 9 or clock_format > 1:
        raise ValueError("CLOCK_SETTINGS has unsupported reserved bits")
    return ClockSettings(bool(args[0]), brightness, clock_format)


def parse_r2r_times(args: bytes) -> WeeklyTimes:
    return decode_weekly_times(args)


def parse_sleepy_times(args: bytes) -> WeeklyTimes:
    return decode_weekly_times(args)


def parse_r2r_alarms(args: bytes) -> WeeklyAlarms:
    return decode_weekly_alarms(args)


def parse_day_routine(args: bytes) -> DailyRoutine:
    return decode_daily_routine(args)


def parse_routine_task_status(args: bytes) -> RoutineTaskStatus:
    return decode_routine_task_status(args)


def parse_schedule_response(
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


def parse_global_state(args: bytes) -> dict:
    """Decode the GLOBAL_STATE snapshot (response 0x02) into raw integer fields."""
    if not isinstance(args, bytes) or len(args) != 13:
        raise ValueError("GLOBAL_STATE must contain exactly 13 bytes")
    n = _nibbles(args)
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
