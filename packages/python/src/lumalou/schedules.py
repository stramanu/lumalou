"""Strict codecs for the schedule blocks observed in the deployed web client.

These are wire representations, not hardware-verified restore operations.
Routine slots retain their original positions and step numbers; never group or
sort them when backing up a device. Unknown encodings raise instead of becoming
defaults. See docs/schedule-codecs.md for provenance and remaining ambiguity.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum
from typing import Literal

from ._generated import Alarm

Day = Literal[
    "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"
]
DAYS: tuple[Day, ...] = (
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
)
# Friday/Saturday are not contiguous with the other response IDs.
DAY_ROUTINE_RESPONSES: dict[Day, int] = dict(
    zip(DAYS, (0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x90, 0x91))
)


def _integer(value: int, low: int, high: int, name: str) -> int:
    if (
        type(value) is not int and not isinstance(value, IntEnum)
    ) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def _payload(data: bytes, length: int) -> bytes:
    if not isinstance(data, bytes) or len(data) != length:
        raise ValueError(f"payload must be exactly {length} bytes")
    return data


def _tuple(value: tuple, length: int, name: str) -> None:
    if not isinstance(value, tuple) or len(value) != length:
        raise ValueError(f"{name} must be a tuple of {length} entries")


@dataclass(frozen=True)
class ClockTime:
    hour: int
    minute: int

    def __post_init__(self) -> None:
        _integer(self.hour, 0, 23, "hour")
        _integer(self.minute, 0, 59, "minute")


def _time(value: ClockTime | None) -> None:
    if value is not None and not isinstance(value, ClockTime):
        raise ValueError("time must be ClockTime or None")


def _encode_time(value: ClockTime | None) -> bytes:
    _time(value)
    if value is None:
        return b"\xff\xff"
    return bytes(
        (
            (value.hour // 10) << 4 | value.hour % 10,
            (value.minute // 10) << 4 | value.minute % 10,
        )
    )


def _decode_time(data: bytes) -> ClockTime | None:
    if data == b"\xff\xff":
        return None
    if any(byte >> 4 > 9 or byte & 0x0F > 9 for byte in data):
        raise ValueError("invalid BCD time (only FF FF means no time)")
    return ClockTime(*(10 * (byte >> 4) + (byte & 0x0F) for byte in data))


@dataclass(frozen=True)
class WeeklyTimes:
    """Seven Sunday-first times; None and midnight are distinct."""

    days: tuple[ClockTime | None, ...]

    def __post_init__(self) -> None:
        _tuple(self.days, 7, "week")
        for value in self.days:
            _time(value)


def encode_weekly_times(week: WeeklyTimes) -> bytes:
    if not isinstance(week, WeeklyTimes):
        raise TypeError("week must be WeeklyTimes")
    return b"".join(_encode_time(value) for value in week.days)


def decode_weekly_times(data: bytes) -> WeeklyTimes:
    _payload(data, 14)
    return WeeklyTimes(
        tuple(_decode_time(data[index : index + 2]) for index in range(0, 14, 2))
    )


@dataclass(frozen=True)
class WeeklyAlarms:
    """Seven Sunday-first alarm offsets and an uninterpreted sound nibble."""

    days: tuple[Alarm, ...]
    sound: int

    def __post_init__(self) -> None:
        _tuple(self.days, 7, "alarms")
        for value in self.days:
            _integer(value, 0, 10, "alarm")
        object.__setattr__(self, "days", tuple(Alarm(value) for value in self.days))
        _integer(self.sound, 0, 15, "sound")


def encode_weekly_alarms(alarms: WeeklyAlarms) -> bytes:
    if not isinstance(alarms, WeeklyAlarms):
        raise TypeError("alarms must be WeeklyAlarms")
    values = (*alarms.days, alarms.sound)
    return bytes(values[index] << 4 | values[index + 1] for index in range(0, 8, 2))


def decode_weekly_alarms(data: bytes) -> WeeklyAlarms:
    _payload(data, 4)
    values = tuple(value for byte in data for value in (byte >> 4, byte & 0x0F))
    return WeeklyAlarms(values[:7], values[7])


@dataclass(frozen=True)
class RoutineTask:
    """A task in its original wire slot (step numbering starts at one)."""

    step: int
    task: int

    def __post_init__(self) -> None:
        _integer(self.step, 1, 12, "step")
        _integer(self.task, 0, 11, "task")


@dataclass(frozen=True)
class DailyRoutine:
    """Time plus exactly twelve wire slots, including every zero/padding slot.

    A None time is FF FF, not 00 00. None slots encode 00; task zero with
    step one encodes 10, so an empty slot and task zero remain distinct.
    """

    time: ClockTime | None
    slots: tuple[RoutineTask | None, ...]

    def __post_init__(self) -> None:
        _time(self.time)
        _tuple(self.slots, 12, "routine slots")
        if any(
            value is not None and not isinstance(value, RoutineTask)
            for value in self.slots
        ):
            raise ValueError("routine slots must contain RoutineTask or None")

    @classmethod
    def from_steps(
        cls, time: ClockTime | None, steps: Iterable[Iterable[int]]
    ) -> DailyRoutine:
        """Build canonical slots for an explicit edit, preserving task order."""
        slots: list[RoutineTask | None] = []
        for number, values in enumerate(steps, 1):
            tasks = tuple(values)
            if not tasks:
                raise ValueError("a routine step must not be empty")
            for task in tasks:
                if len(slots) == 12:
                    raise ValueError("a routine holds at most twelve tasks")
                slots.append(RoutineTask(number, task))
        return cls(time, tuple(slots + [None] * (12 - len(slots))))


def encode_daily_routine(routine: DailyRoutine) -> bytes:
    if not isinstance(routine, DailyRoutine):
        raise TypeError("routine must be DailyRoutine")
    return _encode_time(routine.time) + bytes(
        0 if slot is None else slot.step << 4 | slot.task for slot in routine.slots
    )


def decode_daily_routine(data: bytes) -> DailyRoutine:
    _payload(data, 14)
    return DailyRoutine(
        _decode_time(data[:2]),
        tuple(
            None if byte == 0 else RoutineTask(byte >> 4, byte & 0x0F)
            for byte in data[2:]
        ),
    )


@dataclass(frozen=True)
class RoutineTaskStatus:
    """Runtime-only status: enum meanings and current-step sentinels unknown."""

    current_step: int
    task_states: tuple[int, ...]

    def __post_init__(self) -> None:
        _integer(self.current_step, 0, 255, "current step byte")
        _tuple(self.task_states, 12, "task states")
        for value in self.task_states:
            _integer(value, 0, 15, "task state nibble")


def decode_routine_task_status(data: bytes) -> RoutineTaskStatus:
    _payload(data, 7)
    return RoutineTaskStatus(
        data[0], tuple(value for byte in data[1:] for value in (byte >> 4, byte & 0x0F))
    )


def encode_routine_task_status(status: RoutineTaskStatus) -> bytes:
    """Lossless runtime-status serialization, NOT a SET command (0x68 is REQUEST)."""
    if not isinstance(status, RoutineTaskStatus):
        raise TypeError("status must be RoutineTaskStatus")
    return bytes((status.current_step,)) + bytes(
        status.task_states[index] << 4 | status.task_states[index + 1]
        for index in range(0, 12, 2)
    )
