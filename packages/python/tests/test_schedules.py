"""Schedule golden vectors and malformed-input tests; no BLE access."""

import json
from pathlib import Path

import pytest
from lumalou import commands as C
from lumalou import responses as R
from lumalou._generated import COMMANDS, RESPONSES, Alarm
from lumalou.schedules import (
    DAY_ROUTINE_RESPONSES,
    ClockTime,
    DailyRoutine,
    RoutineTask,
    RoutineTaskStatus,
    WeeklyAlarms,
    WeeklyTimes,
    decode_daily_routine,
    decode_routine_task_status,
    decode_weekly_alarms,
    decode_weekly_times,
    encode_daily_routine,
    encode_weekly_alarms,
    encode_weekly_times,
)

VECTORS = json.loads(
    (Path(__file__).resolve().parents[3] / "spec" / "schedule-vectors.json").read_text()
)


def time(value):
    return None if value is None else ClockTime(*value)


@pytest.mark.parametrize("v", VECTORS["weeklyTimes"])
def test_weekly_vectors(v):
    expected = WeeklyTimes(tuple(time(value) for value in v["days"]))
    raw = bytes.fromhex(v["args"])
    assert decode_weekly_times(raw) == expected
    assert R.parse_r2r_times(raw) == R.parse_sleepy_times(raw) == expected
    assert encode_weekly_times(expected) == raw
    for opcode, setter in ((0x46, C.set_r2r_times), (0x48, C.set_sleepy_times)):
        assert setter(expected) == bytes([opcode]) + raw
    assert R.parse_schedule_response(0x22, raw) == expected
    assert R.parse_schedule_response(0x23, raw) == expected


@pytest.mark.parametrize("v", VECTORS["alarms"])
def test_alarm_vectors(v):
    expected = WeeklyAlarms(tuple(Alarm(value) for value in v["days"]), v["sound"])
    raw = bytes.fromhex(v["args"])
    assert decode_weekly_alarms(raw) == expected
    assert R.parse_r2r_alarms(raw) == R.parse_schedule_response(0x27, raw) == expected
    assert encode_weekly_alarms(expected) == raw
    assert C.set_r2r_alarms(expected) == b"\x4a" + raw


@pytest.mark.parametrize("v", VECTORS["routines"])
def test_routine_vectors_preserve_every_slot(v):
    expected = DailyRoutine(
        time(v["time"]),
        tuple(None if value is None else RoutineTask(*value) for value in v["slots"]),
    )
    raw = bytes.fromhex(v["args"])
    assert decode_daily_routine(raw) == R.parse_day_routine(raw) == expected
    assert encode_daily_routine(expected) == raw


@pytest.mark.parametrize("v", VECTORS["taskStatus"])
def test_task_status_vectors_without_invented_enums(v):
    expected = RoutineTaskStatus(v["currentStep"], tuple(v["taskStates"]))
    raw = bytes.fromhex(v["args"])
    assert decode_routine_task_status(raw) == expected
    assert (
        R.parse_routine_task_status(raw)
        == R.parse_schedule_response(0x94, raw)
        == expected
    )


@pytest.mark.parametrize("v", VECTORS["dayOpcodes"])
def test_all_day_opcodes(v):
    routine = DailyRoutine.from_steps(ClockTime(0, 0), ((0, 11), (3,)))
    raw = bytes.fromhex("0000101b23000000000000000000")
    assert C.set_day_routine(v["day"], routine) == bytes([v["set"]]) + raw
    assert C.request_day_routine(v["day"]) == bytes([v["request"]])
    assert DAY_ROUTINE_RESPONSES[v["day"]] == v["response"]
    assert RESPONSES[v["response"]] == v["day"].upper() + "_ROUTINE"
    assert R.parse_schedule_response(v["response"], raw) == routine


@pytest.mark.parametrize(
    ("name", "opcode"),
    [
        ("r2r_times", 0x47),
        ("sleepy_times", 0x49),
        ("r2r_alarms", 0x4C),
        ("routine_task_status", 0x68),
    ],
)
def test_requests(name, opcode):
    assert C.request(name) == bytes([opcode])
    assert "SET_ROUTINE_TASK_STATUS" not in COMMANDS


@pytest.mark.parametrize(
    ("decoder", "length"),
    [
        (decode_weekly_times, 14),
        (decode_daily_routine, 14),
        (decode_weekly_alarms, 4),
        (decode_routine_task_status, 7),
    ],
)
def test_exact_lengths_and_bytes_only(decoder, length):
    for size in range(30):
        if size != length:
            with pytest.raises(ValueError):
                decoder(bytes(size))
    for value in (None, [0] * length, "00" * length, bytearray(length)):
        with pytest.raises(ValueError):
            decoder(value)


@pytest.mark.parametrize(
    "raw", ["ff00", "00ff", "2400", "0060", "0a00", "000a", "fa00", "123f"]
)
def test_invalid_bcd_never_becomes_defaults(raw):
    data = bytes.fromhex(raw) + bytes(12)
    with pytest.raises(ValueError):
        decode_weekly_times(data)
    with pytest.raises(ValueError):
        decode_daily_routine(data)


@pytest.mark.parametrize("value", [-1, 24, True, 1.0, "1", None])
def test_invalid_hour(value):
    with pytest.raises(ValueError):
        ClockTime(value, 0)


@pytest.mark.parametrize("value", [-1, 60, True, 1.0, "1", None])
def test_invalid_minute(value):
    with pytest.raises(ValueError):
        ClockTime(0, value)


@pytest.mark.parametrize("size", [0, 6, 8])
def test_week_sizes(size):
    with pytest.raises(ValueError):
        WeeklyTimes((None,) * size)
    with pytest.raises(ValueError):
        WeeklyAlarms((Alarm.ACTIVE,) * size, 0)


@pytest.mark.parametrize("value", [-1, 11, 15, True, "0", 1.0])
def test_invalid_alarm_values(value):
    with pytest.raises(ValueError):
        WeeklyAlarms((value,) * 7, 0)


@pytest.mark.parametrize("raw", ["ffffffff", "b0000000", "000000c0"])
def test_invalid_alarm_response(raw):
    with pytest.raises(ValueError):
        decode_weekly_alarms(bytes.fromhex(raw))


@pytest.mark.parametrize("value", [-1, 16, True, 1.0])
def test_invalid_sound(value):
    with pytest.raises(ValueError):
        WeeklyAlarms((Alarm.ACTIVE,) * 7, value)


@pytest.mark.parametrize("raw", [0x01, 0x1C, 0x1F, 0xD1, 0xFF])
def test_invalid_routine_slot_preserves_no_partial_result(raw):
    with pytest.raises(ValueError):
        decode_daily_routine(bytes([0, 0, raw]) + bytes(11))


def test_canonical_builder_preserves_order_duplicates_and_task_zero():
    routine = DailyRoutine.from_steps(ClockTime(7, 30), ((11, 0, 11), (3, 1)))
    assert encode_daily_routine(routine) == bytes.fromhex(
        "07301b101b232100000000000000"
    )
    assert encode_daily_routine(
        DailyRoutine.from_steps(None, ())
    ) == b"\xff\xff" + bytes(12)
    assert encode_daily_routine(DailyRoutine.from_steps(ClockTime(0, 0), ())) == bytes(
        14
    )
    maximum = DailyRoutine.from_steps(None, ((n % 12,) for n in range(12)))
    assert maximum.slots[-1] == RoutineTask(12, 11)


@pytest.mark.parametrize(
    "steps", [((),), ((1,), ()), ((1,) * 13,), ((1,),) * 13, ((12,),), ((True,),)]
)
def test_invalid_builder_steps(steps):
    with pytest.raises(ValueError):
        DailyRoutine.from_steps(None, steps)


@pytest.mark.parametrize("day", ["Friday", "funday", -1, 7, True, None, []])
def test_invalid_day(day):
    with pytest.raises(ValueError):
        C.request_day_routine(day)
    with pytest.raises(ValueError):
        C.set_day_routine(day, DailyRoutine.from_steps(None, ()))


@pytest.mark.parametrize("opcode", [0x30, 0x31, 0x68, 0xFF, True, "144", None])
def test_unknown_response_opcode(opcode):
    with pytest.raises(ValueError):
        R.parse_schedule_response(opcode, bytes(14))


def test_models_cannot_hide_mutable_or_invalid_children():
    for factory in (
        lambda: WeeklyTimes([None] * 7),
        lambda: WeeklyTimes(((0, 0),) * 7),
        lambda: DailyRoutine(None, (None,) * 11),
        lambda: DailyRoutine(None, (1,) * 12),
        lambda: DailyRoutine((0, 0), (None,) * 12),
        lambda: RoutineTask(True, 1),
        lambda: RoutineTask(1, -1),
        lambda: RoutineTaskStatus(True, (0,) * 12),
        lambda: RoutineTaskStatus(0, (16,) * 12),
        lambda: RoutineTaskStatus(0, (0,) * 11),
    ):
        with pytest.raises(ValueError):
            factory()


@pytest.mark.parametrize(
    "encoder", [encode_weekly_times, encode_weekly_alarms, encode_daily_routine]
)
def test_encoders_require_typed_validated_models(encoder):
    for value in (None, {}, [], bytes(14)):
        with pytest.raises(TypeError):
            encoder(value)


def test_all_valid_bcd_times_round_trip():
    for hour in range(24):
        for minute in range(60):
            expected = WeeklyTimes((ClockTime(hour, minute),) * 7)
            assert decode_weekly_times(encode_weekly_times(expected)) == expected
