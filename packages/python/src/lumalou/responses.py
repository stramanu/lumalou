"""Decode device responses. Values are raw integers (canonical); use label() for names."""
from __future__ import annotations

from ._generated import RESPONSES, OperationMode, Stage, Color


def _nibbles(data: bytes):
    out = []
    for b in data:
        out.append(b >> 4)
        out.append(b & 0x0F)
    return out


def parse_global_state(args: bytes) -> dict:
    """Decode the GLOBAL_STATE snapshot (response 0x02) into raw integer fields."""
    n = _nibbles(args)
    while len(n) < 26:
        n.append(0)
    return {
        "operationMode": n[0], "activityState": n[1], "musicStatus": n[2],
        "currentSong": (n[3] << 4) | n[4], "currentVolume": n[5], "playlistDuration": n[6],
        "lightStatus": n[7], "lightBrightness": n[8], "lightColor": n[9],
        "napTimeStatus": n[10], "napDuration": n[11], "ready2RiseStatus": n[12],
        "ready2RiseAlarmStatus": n[13], "timePrescaler": n[14], "currentStage": n[15],
        "clockDisplay": n[16], "clockBrightness": n[17], "clockFormat": n[18],
        "routineMusicStatus": n[19], "taskRewardSfx": n[20], "routineRewardSfx": n[21],
        "lightDuration": n[22], "routineVolume": n[23], "routineModeStatus": n[24],
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
