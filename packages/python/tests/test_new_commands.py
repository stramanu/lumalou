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


def test_set_day_routine_rejects_empty_step():
    with pytest.raises(ValueError):
        C.set_day_routine("sunday", (7, 0), [[1], [], [3]])


def test_set_day_routine_rejects_step_index_overflow_via_empty_steps():
    # Without the empty-step guard, 14 empty steps would push the task at the
    # end past step 15 and the nibble would wrap, inverting the task order.
    steps = [[1]] + [[] for _ in range(14)] + [[3]]
    with pytest.raises(ValueError):
        C.set_day_routine("sunday", (7, 0), steps)


def test_set_day_routine_boundary_twelve_steps_round_trip():
    steps = [[1] for _ in range(12)]
    payload = C.set_day_routine("sunday", (7, 0), steps)[1:]
    assert payload.hex() == "0700112131415161718191a1b1c1"
    assert payload[-1] == 0xC1                    # step 12, task 1
    assert R.parse_day_routine(payload) == {"time": (7, 0), "steps": steps}


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


# --- weekly times ---

WEEK = [(7, 0), (7, 30), None, (7, 30), (7, 30), (7, 30), (9, 0)]


def test_set_r2r_times_encodes_seven_pairs():
    out = C.set_r2r_times(WEEK)
    assert out[0] == 0x46
    assert out[1:].hex() == "0700" "0730" "ffff" "0730" "0730" "0730" "0900"
    assert len(out) == 15


def test_set_sleepy_times_uses_its_own_opcode():
    out = C.set_sleepy_times(WEEK)
    assert out[0] == 0x48
    assert out[1:] == C.set_r2r_times(WEEK)[1:]      # same body format


def test_set_r2r_times_rejects_wrong_day_count():
    with pytest.raises(ValueError, match="7"):
        C.set_r2r_times([(7, 0)] * 6)


def test_parse_weekly_times_round_trips():
    body = C.set_r2r_times(WEEK)[1:]
    assert R.parse_weekly_times(body) == WEEK


def test_parse_weekly_times_all_zero_is_midnight():
    assert R.parse_weekly_times(bytes(14)) == [(0, 0)] * 7


def test_parse_weekly_times_rejects_wrong_length():
    with pytest.raises(ValueError, match="14"):
        R.parse_weekly_times(bytes(12))
