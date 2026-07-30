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
