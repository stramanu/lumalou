"""Command builders. Each returns the app-level payload: [opcode] + args."""
from __future__ import annotations

from ._generated import COMMANDS, DAY_ROUTINE, Color, Audio, Song, LightDuration, \
    PlaylistDuration, NapDuration, Alarm, RoutineControl, ClockFormat

NO_MODIFY = 0x0F  # "leave unchanged" sentinel for SET_GLOBAL_STATE fields

_u8 = lambda *a: bytes(a)


def _check(name: str, value, lo: int, hi: int) -> int:
    """Reject out-of-range arguments instead of masking them.

    Masking turns an invalid id into a different *valid* one: 16 & 0x0F is 0,
    which for an alarm means ACTIVE, so a bad id used to arm the alarm silently.
    The same silent-conversion class also hides in truncation: int(9.5) is 9
    and int(-0.5) is 0 (0 = Alarm.ACTIVE again), so non-integers are rejected
    outright rather than coerced, mirroring Number.isInteger in the TS binding.
    bool is excluded even though it is an int subclass in Python, because
    Number.isInteger(true) is false in JS: accepting it here would reopen the
    exact asymmetry this check exists to close.
    """
    ok = isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi
    if not ok:
        raise ValueError(f"got {value}: {name} must be {lo}-{hi}")
    return value


def bcd(n) -> int:
    return 0xFF if n is None else (((n // 10) << 4) | (n % 10)) & 0xFF


def reduce_low_nibbles(values) -> bytes:
    v = list(values)
    if len(v) % 2:
        v = [0] + v
    return bytes(((v[i] << 4) | (v[i + 1] & 0x0F)) & 0xFF for i in range(0, len(v), 2))


# ---- light ----
def set_light_color(color) -> bytes:
    return _u8(COMMANDS["SET_LIGHT_COLOR"], _check("color", color, 0, 9))


def set_led_brightness(level: int) -> bytes:
    return _u8(COMMANDS["SET_LED_BRIGHTNESS"], _check("brightness", level, 0, 9))


def set_light_duration(duration) -> bytes:
    return _u8(COMMANDS["SET_SOOTHER_MODE_LIGHT_DURATION"], _check("light duration", duration, 0, 5))


def turn_off_backlight() -> bytes:
    return _u8(COMMANDS["TURN_OFF_CLOUD_BACKLIGHT"])


# ---- audio ----
def play_audio(source) -> bytes:
    return _u8(COMMANDS["PLAY_AUDIO"], _check("audio", source, 0, 7))


def turn_off_audio() -> bytes:
    return _u8(COMMANDS["TURN_OFF_AUDIO"])


def set_playlist_duration(duration) -> bytes:
    return _u8(COMMANDS["SET_PLAYLIST_DURATION"], _check("playlist duration", duration, 0, 6))


def set_music_playlist(song_ids) -> bytes:
    checked = [_check("song id", s, 0, 18) for s in song_ids]
    ids = [s for s in checked if s != 0][:12]
    ids += [0] * (12 - len(ids))
    return bytes([COMMANDS["SET_MUSIC_PLAYLIST"], *ids])


# ---- volume ----
def set_volume(level: int) -> bytes:
    return _u8(COMMANDS["SET_VOLUME"], _check("volume", level, 0, 9))


def set_routine_volume(level: int) -> bytes:
    return _u8(COMMANDS["SET_ROUTINE_MODE_VOLUME"], _check("routine volume", level, 0, 9))


# ---- system ----
def set_global_on(on: bool) -> bytes:
    return _u8(COMMANDS["SET_GLOBAL_ON"], 1 if on else 0)


def set_global_state(*, lights_on=None, brightness=None, music_on=None, volume=None,
                     r2r=None, r2r_alarm=None, nap_alarm=None, routine=None) -> bytes:
    def f(name, x, lo, hi):
        return NO_MODIFY if x is None else _check(name, x, lo, hi)
    return bytes([COMMANDS["SET_GLOBAL_STATE"], *reduce_low_nibbles([
        f("lights_on", lights_on, 0, 1),
        f("brightness", brightness, 0, 9),
        f("music_on", music_on, 0, 1),
        f("volume", volume, 0, 9),
        f("r2r", r2r, 0, 1),
        f("r2r_alarm", r2r_alarm, 0, 10),
        f("nap_alarm", nap_alarm, 0, 11),
        f("routine", routine, 0, 1)])])


def set_current_date(hour, minute, second, weekday) -> bytes:
    return _u8(COMMANDS["SET_CURRENT_DATE"],
               bcd(_check("hour", hour, 0, 23)), bcd(_check("minute", minute, 0, 59)),
               bcd(_check("second", second, 0, 59)), bcd(_check("weekday", weekday, 0, 6)))


def set_clock_settings(display_on, brightness, fmt) -> bytes:
    return bytes([COMMANDS["SET_CLOCK_SETTINGS"],
                  *reduce_low_nibbles([0, int(bool(display_on)),
                                       _check("brightness", brightness, 0, 9),
                                       _check("clock format", fmt, 0, 1)])])


# ---- timers ----
def set_r2r_status(on: bool) -> bytes:
    return _u8(COMMANDS["SET_R2R_STATUS"], 1 if on else 0)


def start_nap(duration) -> bytes:
    return _u8(COMMANDS["START_NAP_TIME"], _check("nap duration", duration, 0, 11))


def set_nap_alarm(alarm) -> bytes:
    return _u8(COMMANDS["SET_NAP_TIME_ALARM"], _check("alarm", alarm, 0, 10))


# ---- routine ----
DAYS = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")

_MAX_TASK_BYTES = 12          # 14-byte payload minus the 2 time bytes


def _encode_day_routine(time, steps) -> bytes:
    """Body of a day-routine command: time + one byte per task.

    Mirrors FPLumaModel.encodeDayRoutineRequestBytes. High nibble is the 1-based
    step index, low nibble the task id, so several tasks can share one step.
    Verified against hardware: 07:30 + [[1],[3],[6]] -> 0730112336 + zero padding.
    """
    if time is None:
        out = bytearray([0xFF, 0xFF])
    else:
        hour, minute = time
        out = bytearray([bcd(_check("hour", hour, 0, 23)), bcd(_check("minute", minute, 0, 59))])
    for index, step in enumerate(steps, start=1):
        if not step:
            raise ValueError(f"a day routine step must have at least one task, step {index} is empty")
        for task_id in step:
            out.append(((index << 4) & 0xF0) | _check("task id", task_id, 0, 11))
    if len(out) - 2 > _MAX_TASK_BYTES:
        raise ValueError(f"a day routine holds at most {_MAX_TASK_BYTES} tasks, got {len(out) - 2}")
    out.extend(bytes(14 - len(out)))
    return bytes(out)


def set_day_routine(day: str, time, steps) -> bytes:
    """Program one day's routine.

    day:   one of DAYS
    time:  (hour, minute), or None to leave the start time unset
    steps: list of steps; each step is a list of task ids (see Task enum ids 1-11)
    """
    return bytes([DAY_ROUTINE["SET"][day], *_encode_day_routine(time, steps)])


def request_day_routine(day: str) -> bytes:
    return bytes([DAY_ROUTINE["REQUEST"][day]])


def set_routine_status(on: bool) -> bytes:
    return _u8(COMMANDS["SET_ROUTINE_MODE_STATUS"], 1 if on else 0)


def start_routine_mode() -> bytes:
    return _u8(COMMANDS["START_ROUTINE_MODE"])


def routine_control(ctrl) -> bytes:
    return _u8(COMMANDS["ROUTINE_CONTROL_COMMAND"], _check("routine control", ctrl, 0, 4))


# ---- weekly times ----
def _encode_weekly_times(times) -> bytes:
    """Seven (hour, minute) pairs as BCD, Sunday first. None disables a day (FF FF)."""
    if len(times) != 7:
        raise ValueError(f"weekly times need exactly 7 entries (Sunday first), got {len(times)}")
    out = bytearray()
    for entry in times:
        if entry is None:
            out += b"\xff\xff"
        else:
            hour, minute = entry
            out += bytes([bcd(_check("hour", hour, 0, 23)), bcd(_check("minute", minute, 0, 59))])
    return bytes(out)


def set_r2r_times(times) -> bytes:
    """Weekly ready-to-rise (wake) times. Sends all seven days in one frame."""
    return bytes([COMMANDS["SET_R2R_TIMES"], *_encode_weekly_times(times)])


def set_sleepy_times(times) -> bytes:
    """Weekly sleepy times. Same body format as set_r2r_times."""
    return bytes([COMMANDS["SET_SLEEPY_TIMES"], *_encode_weekly_times(times)])


def set_r2r_alarms(per_day, sfx) -> bytes:
    """Ready-to-rise alarm per day plus the sound-effect id.

    per_day: seven Alarm ids (Sunday first); Alarm.INACTIVE (9) disables a day.
    """
    if len(per_day) != 7:
        raise ValueError(f"alarms need exactly 7 entries (Sunday first), got {len(per_day)}")
    values = [_check("alarm", a, 0, 10) for a in per_day] + [_check("sfx", sfx, 0, 15)]
    return bytes([COMMANDS["SET_R2R_ALARMS"], *reduce_low_nibbles(values)])


def set_routine_music_status(music, task_rewards, routine_rewards) -> bytes:
    """Routine soundtrack plus the two reward-sound toggles."""
    return bytes([COMMANDS["SET_ROUTINE_MUSIC_STATUS"],
                  _check("music", music, 0, 255),
                  (_check("task rewards", task_rewards, 0, 15) << 4) |
                  _check("routine rewards", routine_rewards, 0, 15)])


# ---- read-only queries ----
_REQUESTS = {
    "global_state": "REQUEST_GLOBAL_STATE", "current_date": "REQUEST_CURRENT_DATE",
    "toyic_fw_version": "REQUEST_TOYIC_FW_VERSION", "led_brightness": "REQUEST_LED_BRIGHTNESS",
    "light_color": "REQUEST_LIGHT_COLOR", "light_duration": "REQUEST_SOOTHER_MODE_LIGHT_DURATION",
    "volume": "REQUEST_VOLUME", "routine_volume": "REQUEST_ROUTINE_MODE_VOLUME",
    "song_playing": "REQUEST_SONG_PLAYING", "music_playlist": "REQUEST_MUSIC_PLAYLIST",
    "playlist_duration": "REQUEST_PLAYLIST_DURATION", "operation_mode": "REQUEST_OPERATION_MODE",
    "activity_state": "REQUEST_ACTIVITY_STATE", "current_stage": "REQUEST_CURRENT_STAGE",
    "clock_settings": "REQUEST_CLOCK_SETTINGS", "transmission_mode": "REQUEST_TRANSMISSION_MODE",
    "routine_mode_status": "REQUEST_ROUTINE_MODE_STATUS",
    "routine_task_status": "REQUEST_ROUTINE_TASK_STATUS",
    "routine_music_status": "REQUEST_ROUTINE_MUSIC_STATUS",
    "r2r_status": "REQUEST_R2R_STATUS",
    "r2r_times": "REQUEST_R2R_TIMES",
    "sleepy_times": "REQUEST_SLEEPY_TIMES",
    "r2r_alarm_status": "REQUEST_R2R_ALARM_STATUS",
    "r2r_alarms": "REQUEST_R2R_ALARMS",
    "nap_current_status": "REQUEST_CURRENT_NAP_TIME_STATUS",
    "time_prescaler": "REQUEST_TIME_PRESCALER",
}

REQUESTS = _REQUESTS


def request(name: str) -> bytes:
    return _u8(COMMANDS[_REQUESTS[name]])


# transport-level: enable the toy-IC to stream responses (raw SSI0 ENABLE_RX)
ENABLE_RX = bytes([0x01, 0x50, 0x01])
