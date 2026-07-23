"""Command builders. Each returns the app-level payload: [opcode] + args."""
from __future__ import annotations

from ._generated import COMMANDS, DAY_ROUTINE, Color, Audio, Song, LightDuration, \
    PlaylistDuration, NapDuration, Alarm, RoutineControl, ClockFormat

NO_MODIFY = 0x0F  # "leave unchanged" sentinel for SET_GLOBAL_STATE fields

_u8 = lambda *a: bytes(a)


def bcd(n) -> int:
    return 0xFF if n is None else (((n // 10) << 4) | (n % 10)) & 0xFF


def reduce_low_nibbles(values) -> bytes:
    v = list(values)
    if len(v) % 2:
        v = [0] + v
    return bytes(((v[i] << 4) | (v[i + 1] & 0x0F)) & 0xFF for i in range(0, len(v), 2))


# ---- light ----
def set_light_color(color) -> bytes:
    return _u8(COMMANDS["SET_LIGHT_COLOR"], int(color))


def set_led_brightness(level: int) -> bytes:
    return _u8(COMMANDS["SET_LED_BRIGHTNESS"], level & 0xFF)


def set_light_duration(duration) -> bytes:
    return _u8(COMMANDS["SET_SOOTHER_MODE_LIGHT_DURATION"], int(duration))


def turn_off_backlight() -> bytes:
    return _u8(COMMANDS["TURN_OFF_CLOUD_BACKLIGHT"])


# ---- audio ----
def play_audio(source) -> bytes:
    return _u8(COMMANDS["PLAY_AUDIO"], int(source))


def turn_off_audio() -> bytes:
    return _u8(COMMANDS["TURN_OFF_AUDIO"])


def set_playlist_duration(duration) -> bytes:
    return _u8(COMMANDS["SET_PLAYLIST_DURATION"], int(duration))


def set_music_playlist(song_ids) -> bytes:
    ids = [int(s) for s in song_ids if int(s) != 0][:12]
    ids += [0] * (12 - len(ids))
    return bytes([COMMANDS["SET_MUSIC_PLAYLIST"], *ids])


# ---- volume ----
def set_volume(level: int) -> bytes:
    return _u8(COMMANDS["SET_VOLUME"], level & 0xFF)


def set_routine_volume(level: int) -> bytes:
    return _u8(COMMANDS["SET_ROUTINE_MODE_VOLUME"], level & 0xFF)


# ---- system ----
def set_global_on(on: bool) -> bytes:
    return _u8(COMMANDS["SET_GLOBAL_ON"], 1 if on else 0)


def set_global_state(*, lights_on=None, brightness=None, music_on=None, volume=None,
                     r2r=None, r2r_alarm=None, nap_alarm=None, routine=None) -> bytes:
    f = lambda x: NO_MODIFY if x is None else (int(x) & 0x0F)
    return bytes([COMMANDS["SET_GLOBAL_STATE"], *reduce_low_nibbles(
        [f(lights_on), f(brightness), f(music_on), f(volume),
         f(r2r), f(r2r_alarm), f(nap_alarm), f(routine)])])


def set_current_date(hour, minute, second, weekday) -> bytes:
    return _u8(COMMANDS["SET_CURRENT_DATE"], bcd(hour), bcd(minute), bcd(second), bcd(weekday))


def set_clock_settings(display_on, brightness, fmt) -> bytes:
    return bytes([COMMANDS["SET_CLOCK_SETTINGS"],
                  *reduce_low_nibbles([0, int(bool(display_on)), brightness & 0x0F, int(fmt)])])


# ---- timers ----
def set_r2r_status(on: bool) -> bytes:
    return _u8(COMMANDS["SET_R2R_STATUS"], 1 if on else 0)


def start_nap(duration) -> bytes:
    return _u8(COMMANDS["START_NAP_TIME"], int(duration))


def set_nap_alarm(alarm) -> bytes:
    return _u8(COMMANDS["SET_NAP_TIME_ALARM"], int(alarm))


# ---- routine ----
def set_routine_status(on: bool) -> bytes:
    return _u8(COMMANDS["SET_ROUTINE_MODE_STATUS"], 1 if on else 0)


def start_routine_mode() -> bytes:
    return _u8(COMMANDS["START_ROUTINE_MODE"])


def routine_control(ctrl) -> bytes:
    return _u8(COMMANDS["ROUTINE_CONTROL_COMMAND"], int(ctrl))


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
}


def request(name: str) -> bytes:
    return _u8(COMMANDS[_REQUESTS[name]])


# transport-level: enable the toy-IC to stream responses (raw SSI0 ENABLE_RX)
ENABLE_RX = bytes([0x01, 0x50, 0x01])
