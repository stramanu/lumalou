"""SET-only contracts: literal vectors, exhaustive wire domains, no hardware I/O."""

import json
from pathlib import Path

import pytest
from lumalou import commands as C
from lumalou.client import ResponseEnvelope, UnsupportedResponseError
from lumalou.profile import (
    ClockSettings,
    MusicPlaylist,
    OpaqueBlock,
    RoutineMusicSettings,
    decode_clock_settings_set,
    decode_music_playlist_set,
    decode_routine_music_settings_set,
    encode_clock_settings,
    encode_music_playlist,
    encode_routine_music_settings,
)
from lumalou.schedules import (
    decode_daily_routine,
    decode_routine_task_status,
    decode_weekly_times,
    encode_daily_routine,
    encode_routine_task_status,
    encode_weekly_times,
)

V = json.loads(
    (Path(__file__).resolve().parents[3] / "spec/profile-vectors.json").read_text()
)


@pytest.mark.parametrize("v", V["playlists"])
def test_playlist_literals(v):
    value = MusicPlaylist(tuple(v["slots"]))
    assert C.set_music_playlist(value).hex() == v["set"]
    assert decode_music_playlist_set(bytes.fromhex(v["set"])[1:]) == value


@pytest.mark.parametrize("v", V["clockSettings"])
def test_clock_literals(v):
    value = ClockSettings(v["displayOn"], v["brightness"], v["format"])
    assert (
        C.set_clock_settings(value.display_on, value.brightness, value.format).hex()
        == v["set"]
    )
    assert decode_clock_settings_set(bytes.fromhex(v["set"])[1:]) == value


@pytest.mark.parametrize("v", V["routineMusicSettings"])
def test_rewards_literals(v):
    value = RoutineMusicSettings(v["music"], v["taskReward"], v["routineReward"])
    assert C.set_routine_music_settings(value).hex() == v["set"]
    assert decode_routine_music_settings_set(bytes.fromhex(v["set"])[1:]) == value


def test_exhaustive_clock_reserved_and_field_values():
    valid = 0
    for first in range(256):
        for second in range(256):
            raw = bytes((first, second))
            if first in (0, 1) and second >> 4 <= 9 and second & 15 <= 1:
                assert encode_clock_settings(decode_clock_settings_set(raw)) == raw
                valid += 1
            else:
                with pytest.raises(ValueError):
                    decode_clock_settings_set(raw)
                assert OpaqueBlock(raw, 2).data == raw
    assert valid == 40


def test_exhaustive_rewards_preserve_unknown_meanings():
    for music in range(256):
        for rewards in range(256):
            raw = bytes((music, rewards))
            assert (
                encode_routine_music_settings(decode_routine_music_settings_set(raw))
                == raw
            )


def test_every_playlist_byte_in_every_slot():
    for slot in range(12):
        for song in range(256):
            raw = bytes(song if i == slot else 0 for i in range(12))
            if song <= 12:
                assert encode_music_playlist(decode_music_playlist_set(raw)) == raw
            else:
                with pytest.raises(ValueError):
                    decode_music_playlist_set(raw)
                assert OpaqueBlock(raw, 12).data == raw


def test_every_task_status_byte_position_roundtrips():
    for position in range(7):
        for byte in range(256):
            raw = bytes(byte if i == position else 0 for i in range(7))
            assert encode_routine_task_status(decode_routine_task_status(raw)) == raw


def test_all_bcd_pairs():
    valid = 0
    for hour in range(256):
        for minute in range(256):
            raw = bytes((hour, minute)) + bytes(12)
            good = (hour == minute == 255) or (
                hour >> 4 <= 2
                and hour & 15 <= 9
                and (hour >> 4) * 10 + (hour & 15) <= 23
                and minute >> 4 <= 5
                and minute & 15 <= 9
            )
            if good:
                assert encode_weekly_times(decode_weekly_times(raw)) == raw
                valid += 1
            else:
                with pytest.raises(ValueError):
                    decode_weekly_times(raw)
    assert valid == 1441


def test_every_routine_task_byte_in_every_slot():
    for slot in range(12):
        for byte in range(256):
            raw = bytes(2) + bytes(byte if i == slot else 0 for i in range(12))
            if byte == 0 or (1 <= byte >> 4 <= 12 and byte & 15 <= 11):
                assert encode_daily_routine(decode_daily_routine(raw)) == raw
            else:
                with pytest.raises(ValueError):
                    decode_daily_routine(raw)


@pytest.mark.parametrize(
    "decoder,length",
    [
        (decode_music_playlist_set, 12),
        (decode_clock_settings_set, 2),
        (decode_routine_music_settings_set, 2),
    ],
)
def test_all_wrong_lengths(decoder, length):
    for actual in range(256):
        if actual != length:
            with pytest.raises(ValueError):
                decoder(bytes(actual))
    for data in (None, [], bytearray(length), "0" * length):
        with pytest.raises(ValueError):
            decoder(data)


@pytest.mark.parametrize("bad", [-1, 256, 1.5, "1", True, None])
def test_music_byte_rejects_coercion(bad):
    with pytest.raises(ValueError):
        RoutineMusicSettings(bad, 0, 0)


@pytest.mark.parametrize("bad", [-1, 16, 1.5, "1", True, None])
def test_reward_nibbles_reject_coercion(bad):
    with pytest.raises(ValueError):
        RoutineMusicSettings(0, bad, 0)
    with pytest.raises(ValueError):
        RoutineMusicSettings(0, 0, bad)


def test_playlist_edit_rejects_overflow_and_keeps_duplicates():
    assert C.set_music_playlist([1, 0, 1]) == b"\x40\x01\x01" + bytes(10)
    assert C.set_music_playlist([0] * 30) == b"\x40" + bytes(12)
    with pytest.raises(ValueError):
        C.set_music_playlist([1] * 13)
    for bad in (-1, 19, 1.5, "1", True):
        with pytest.raises(ValueError):
            C.set_music_playlist([bad])
    for slots in ((0,) * 11, (0,) * 13, [0] * 12):
        with pytest.raises(ValueError):
            MusicPlaylist(slots)


@pytest.mark.parametrize(
    "builder,maximum",
    [
        (C.set_light_color, 9),
        (C.set_led_brightness, 9),
        (C.set_light_duration, 5),
        (C.set_playlist_duration, 6),
        (C.set_volume, 9),
        (C.set_routine_volume, 255),
        (C.set_nap_alarm, 10),
    ],
)
def test_persistent_scalar_builders_never_wrap(builder, maximum):
    assert builder(0)[1] == 0
    assert builder(maximum)[1] == maximum
    for bad in (-1, maximum + 1, 1.5, "1", True, None):
        with pytest.raises(ValueError):
            builder(bad)


def test_clock_rejects_bool_coercion_and_masking():
    for bad in (0, 1, None, "false", []):
        with pytest.raises(ValueError):
            C.set_clock_settings(bad, 0, 0)
    for bad in (-1, 10, True, 1.5, "1"):
        with pytest.raises(ValueError):
            C.set_clock_settings(True, bad, 0)
    for bad in (-1, 2, True, 1.5, "1"):
        with pytest.raises(ValueError):
            C.set_clock_settings(True, 0, bad)


@pytest.mark.parametrize(
    "builder,opcode", [(C.set_r2r_status, 0x44), (C.set_routine_status, 0x58)]
)
def test_mode_flags_require_explicit_booleans(builder, opcode):
    assert builder(False) == bytes((opcode, 0))
    assert builder(True) == bytes((opcode, 1))
    for bad in (0, 1, None, "false", []):
        with pytest.raises(ValueError):
            builder(bad)


@pytest.mark.parametrize(
    "opcode,args",
    [
        (0x93, bytes(2)),
        (0x12, b"1.2"),
    ],
)
def test_unimplemented_response_layouts_are_not_guessed(opcode, args):
    envelope = ResponseEnvelope(opcode, args, 1, 0.0, 1)
    with pytest.raises(UnsupportedResponseError):
        envelope.decode()
    assert envelope.args == args


def test_opaque_requires_explicit_exact_length_and_bytes():
    for size in range(255):
        raw = bytes(i % 256 for i in range(size))
        assert OpaqueBlock(raw, size).data == raw
        with pytest.raises(ValueError):
            OpaqueBlock(raw, size + 1)
    for invalid in (-1, 255, True, 2.0):
        with pytest.raises(ValueError):
            OpaqueBlock(b"", invalid)
    with pytest.raises(ValueError):
        OpaqueBlock(bytearray(2), 2)
