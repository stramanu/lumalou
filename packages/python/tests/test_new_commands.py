"""Unit tests for the routine and schedule builders/parsers."""
import pytest

from lumalou import commands as C, responses as R


# --- day routine: encoder ---

def test_set_day_routine_matches_hardware_vector():
    """Byte-for-byte the payload the device echoed back on 2026-07-30."""
    out = C.set_day_routine("sunday", (7, 30), [[1], [3], [6]])
    assert out[0] == 0x5A                       # SET_SUNDAY_ROUTINE
    assert out[1:].hex() == "0730112336000000000000000000"


def test_set_day_routine_no_time_uses_ff():
    out = C.set_day_routine("monday", None, [[1]])
    assert out[0] == 0x5C
    assert out[1:3].hex() == "ffff"


def test_set_day_routine_multiple_tasks_share_a_step():
    out = C.set_day_routine("sunday", (7, 0), [[1, 2], [3]])
    # step 1 holds tasks 1 and 2, step 2 holds task 3
    assert out[1:6].hex() == "0700111223"


def test_set_day_routine_pads_to_14_bytes():
    out = C.set_day_routine("sunday", (7, 0), [[1]])
    assert len(out) == 15                       # opcode + 14


def test_set_day_routine_accepts_exactly_12_tasks():
    steps = [[1] for _ in range(12)]
    out = C.set_day_routine("sunday", (7, 0), steps)
    assert len(out) == 15


def test_set_day_routine_rejects_13_tasks():
    steps = [[1] for _ in range(13)]
    with pytest.raises(ValueError, match="12"):
        C.set_day_routine("sunday", (7, 0), steps)


def test_set_day_routine_rejects_unknown_day():
    with pytest.raises(KeyError):
        C.set_day_routine("caturday", (7, 0), [[1]])


def test_request_day_routine_opcodes():
    assert C.request_day_routine("sunday")[0] == 0x5B
    assert C.request_day_routine("saturday")[0] == 0x67


# --- day routine: decoder ---

def test_parse_day_routine_hardware_vector():
    got = R.parse_day_routine(bytes.fromhex("0730112336000000000000000000"))
    assert got == {"time": (7, 30), "steps": [[1], [3], [6]]}


def test_parse_day_routine_empty_is_midnight_no_steps():
    got = R.parse_day_routine(bytes(14))
    assert got == {"time": (0, 0), "steps": []}


def test_parse_day_routine_ff_time_is_none():
    got = R.parse_day_routine(bytes.fromhex("ffff110000000000000000000000"))
    assert got["time"] is None
    assert got["steps"] == [[1]]


def test_day_routine_round_trips():
    steps = [[1, 2], [3], [6]]
    payload = C.set_day_routine("sunday", (7, 30), steps)[1:]
    assert R.parse_day_routine(payload) == {"time": (7, 30), "steps": steps}


def test_parse_day_routine_rejects_wrong_length():
    with pytest.raises(ValueError, match="14"):
        R.parse_day_routine(bytes(13))
