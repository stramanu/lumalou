"""Read-response codecs from non-sensitive one-target validation evidence."""

from __future__ import annotations

import pytest
from lumalou import ClockSettings, MusicPlaylist
from lumalou.client import ResponseEnvelope
from lumalou.responses import parse_clock_settings, parse_music_playlist


def test_observed_playlist_response_retains_all_ordered_slots() -> None:
    slots = tuple(range(1, 13))
    assert parse_music_playlist(bytes(slots)) == MusicPlaylist(slots)
    envelope = ResponseEnvelope(0x19, bytes(slots), 1, 1.0, 1)
    assert envelope.decode() == MusicPlaylist(slots)


@pytest.mark.parametrize("payload", [b"", bytes(11), bytes(13)])
def test_playlist_response_requires_exact_observed_length(payload: bytes) -> None:
    with pytest.raises(ValueError, match="exactly 12"):
        parse_music_playlist(payload)
    envelope = ResponseEnvelope(0x19, payload, 1, 1.0, 1)
    with pytest.raises(ValueError):
        envelope.decode()


@pytest.mark.parametrize("slot", range(13, 256))
def test_playlist_response_rejects_song_ids_outside_verified_range(slot: int) -> None:
    with pytest.raises(ValueError, match="outside 0..12"):
        parse_music_playlist(bytes((slot, *([0] * 11))))


def test_clock_settings_response_matches_observed_target_state() -> None:
    decoded = parse_clock_settings(bytes((1, 0x21)))
    assert decoded == ClockSettings(display_on=True, brightness=2, format=1)
    assert ResponseEnvelope(0x99, bytes((1, 0x21)), 1, 1.0, 1).decode() == decoded


@pytest.mark.parametrize("payload", [b"", b"\x01", b"\x01\x21\x00"])
def test_clock_settings_response_requires_exact_length(payload: bytes) -> None:
    with pytest.raises(ValueError, match="exactly 2"):
        parse_clock_settings(payload)
    with pytest.raises(ValueError):
        ResponseEnvelope(0x99, payload, 1, 1.0, 1).decode()


@pytest.mark.parametrize("payload", [b"\x02\x21", b"\x01\xa1", b"\x01\x2f"])
def test_clock_settings_response_rejects_unknown_bits(payload: bytes) -> None:
    with pytest.raises(ValueError):
        parse_clock_settings(payload)
