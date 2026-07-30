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


# --- ready-to-rise alarms ---

def test_set_r2r_alarms_nibble_packs_days_and_sfx():
    out = C.set_r2r_alarms([9, 9, 9, 9, 9, 9, 9], 0)
    assert out[0] == 0x4A
    assert out[1:].hex() == "99999990"          # exactly what the device reported


def test_set_r2r_alarms_rejects_wrong_day_count():
    with pytest.raises(ValueError, match="7"):
        C.set_r2r_alarms([0] * 8, 0)


def test_parse_r2r_alarms_hardware_vector():
    got = R.parse_r2r_alarms(bytes.fromhex("99999990"))
    assert got == {"days": [9, 9, 9, 9, 9, 9, 9], "sfx": 0}


def test_r2r_alarms_round_trips():
    body = C.set_r2r_alarms([0, 1, 2, 3, 4, 5, 6], 7)[1:]
    assert R.parse_r2r_alarms(body) == {"days": [0, 1, 2, 3, 4, 5, 6], "sfx": 7}


# --- routine music status ---

def test_set_routine_music_status_packs_rewards():
    out = C.set_routine_music_status(1, 1, 1)
    assert out[0] == 0x69
    assert out[1:].hex() == "0111"               # observed on the device


def test_parse_routine_music_status_hardware_vector():
    assert R.parse_routine_music_status(bytes.fromhex("0111")) == {
        "music": 1, "task_rewards": 1, "routine_rewards": 1}


# --- clock settings / date / task status ---

def test_parse_clock_settings_hardware_vector():
    assert R.parse_clock_settings(bytes.fromhex("0120")) == {
        "display": 1, "brightness": 2, "format": 0}


def test_parse_clock_settings_round_trips_with_encoder():
    body = C.set_clock_settings(True, 2, 0)[1:]
    assert R.parse_clock_settings(body) == {"display": 1, "brightness": 2, "format": 0}


def test_parse_current_date_hardware_vector():
    assert R.parse_current_date(bytes.fromhex("05002400")) == {
        "hour": 5, "minute": 0, "second": 24, "weekday": 0}


def test_parse_routine_task_status_keeps_raw_bytes():
    got = R.parse_routine_task_status(bytes(7))
    assert got["current_step"] == 0
    assert got["task_states"] == [0] * 12
    assert got["raw"] == "00000000000000"


def test_parse_routine_task_status_tolerates_unexpected_length():
    got = R.parse_routine_task_status(bytes(3))
    assert got["raw"] == "000000"
    assert "current_step" not in got


# --- request() coverage and dispatch ---

@pytest.mark.parametrize("name", [
    "routine_mode_status", "routine_task_status", "routine_music_status",
    "r2r_status", "r2r_times", "sleepy_times", "r2r_alarm_status",
    "r2r_alarms", "nap_current_status", "time_prescaler",
])
def test_request_supports_new_names(name):
    assert len(C.request(name)) == 1


def test_request_omits_unanswered_nap_alarm_opcodes():
    """0x50 and 0x51 returned no data on hardware, so they are not exposed."""
    assert "nap_alarm" not in C.REQUESTS
    assert "nap_alarm_status" not in C.REQUESTS


def test_parse_response_dispatches_day_routine():
    got = R.parse_response(0x2B, bytes.fromhex("0730112336000000000000000000"))
    assert got["steps"] == [[1], [3], [6]]


def test_parse_response_dispatches_clock_settings():
    assert R.parse_response(0x99, bytes.fromhex("0120"))["brightness"] == 2


def test_parse_response_returns_raw_for_unknown_opcode():
    assert R.parse_response(0xEE, b"\x01\x02") == b"\x01\x02"


# --- input validation ---

@pytest.mark.parametrize("call", [
    lambda: C.set_light_color(10),
    lambda: C.set_led_brightness(10),
    lambda: C.set_volume(-1),
    lambda: C.play_audio(8),
    lambda: C.set_r2r_alarms([16] * 7, 0),
    lambda: C.set_r2r_alarms([0] * 7, 16),
    lambda: C.set_routine_volume(10),
    lambda: C.routine_control(5),
    lambda: C.set_day_routine("sunday", (24, 0), [[1]]),
    lambda: C.set_day_routine("sunday", (7, 60), [[1]]),
    lambda: C.set_day_routine("sunday", (7, 0), [[12]]),
    lambda: C.set_r2r_times([(24, 0)] * 7),
])
def test_out_of_range_is_rejected(call):
    with pytest.raises(ValueError):
        call()


def test_error_message_names_value_and_range():
    with pytest.raises(ValueError, match="10.*0.*9"):
        C.set_led_brightness(10)


def test_alarm_16_no_longer_silently_arms():
    """16 & 0x0F used to become 0 = Alarm.ACTIVE: an invalid id armed the alarm."""
    with pytest.raises(ValueError):
        C.set_r2r_alarms([16] * 7, 0)


@pytest.mark.parametrize("call", [
    lambda: C.set_light_color(9),
    lambda: C.set_led_brightness(0),
    lambda: C.set_r2r_alarms([9] * 7, 0),
    lambda: C.set_day_routine("sunday", (23, 59), [[11]]),
    lambda: C.set_r2r_times([(0, 0)] * 7),
])
def test_boundary_values_still_accepted(call):
    assert isinstance(call(), bytes)


def test_set_global_state_no_modify_sentinel_still_accepted():
    """0x0F means "leave this field unchanged" and sits outside every field's own range."""
    out = C.set_global_state()
    assert out[1:].hex() == "ffffffff"
