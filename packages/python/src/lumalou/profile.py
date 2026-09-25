"""Source-backed configuration *write* layouts, not inferred response schemas.

The deployed web client has no decoder for responses 0x19, 0x93 or 0x99.
Do not use these SET codecs to interpret their payloads. Encoding support does
not establish persistence, idempotency, or safe automatic restoration.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .schedules import _integer, _payload, _tuple


@dataclass(frozen=True)
class MusicPlaylist:
    """Twelve exact SET slots; preserve order, duplicates and zero padding."""

    slots: tuple[int, ...]

    def __post_init__(self) -> None:
        _tuple(self.slots, 12, "playlist slots")
        for value in self.slots:
            _integer(value, 0, 12, "playlist song")

    @classmethod
    def from_songs(cls, songs: Iterable[int]) -> MusicPlaylist:
        """Build an explicit edit; reject overflow instead of truncating it.

        As in the deployed builder, zero means no song and is filtered. Use
        slots directly to preserve an existing exact SET representation.
        """
        slots = []
        for song in songs:
            _integer(song, 0, 12, "playlist song")
            if song:
                if len(slots) == 12:
                    raise ValueError("playlist holds at most twelve songs")
                slots.append(song)
        return cls(tuple(slots + [0] * (12 - len(slots))))


def encode_music_playlist(value: MusicPlaylist) -> bytes:
    if not isinstance(value, MusicPlaylist):
        raise TypeError("playlist must be MusicPlaylist")
    return bytes(value.slots)


def decode_music_playlist_set(data: bytes) -> MusicPlaylist:
    """Decode SET arguments only; the response layout remains unknown."""
    return MusicPlaylist(tuple(_payload(data, 12)))


@dataclass(frozen=True)
class ClockSettings:
    display_on: bool
    brightness: int
    format: int

    def __post_init__(self) -> None:
        if type(self.display_on) is not bool:
            raise ValueError("display_on must be a boolean")
        _integer(self.brightness, 0, 9, "clock brightness")
        _integer(self.format, 0, 1, "clock format")


def encode_clock_settings(value: ClockSettings) -> bytes:
    if not isinstance(value, ClockSettings):
        raise TypeError("settings must be ClockSettings")
    return bytes((int(value.display_on), value.brightness << 4 | value.format))


def decode_clock_settings_set(data: bytes) -> ClockSettings:
    """Decode SET arguments, rejecting nonzero reserved bits, not discarding them."""
    _payload(data, 2)
    if data[0] not in (0, 1):
        raise ValueError("clock SET reserved bits or display value are unsupported")
    return ClockSettings(bool(data[0]), data[1] >> 4, data[1] & 15)


@dataclass(frozen=True)
class RoutineMusicSettings:
    """Music byte and reward nibbles; meaning beyond the wire range is unknown.

    In particular, music is not asserted to be a song ID or boolean, and reward
    values are not asserted to be booleans or named sound IDs.
    """

    music: int
    task_reward: int
    routine_reward: int

    def __post_init__(self) -> None:
        _integer(self.music, 0, 255, "routine music byte")
        _integer(self.task_reward, 0, 15, "task reward nibble")
        _integer(self.routine_reward, 0, 15, "routine reward nibble")


def encode_routine_music_settings(value: RoutineMusicSettings) -> bytes:
    if not isinstance(value, RoutineMusicSettings):
        raise TypeError("settings must be RoutineMusicSettings")
    return bytes((value.music, value.task_reward << 4 | value.routine_reward))


def decode_routine_music_settings_set(data: bytes) -> RoutineMusicSettings:
    """Decode SET arguments only; do not infer the 0x93 response layout."""
    _payload(data, 2)
    return RoutineMusicSettings(data[0], data[1] >> 4, data[1] & 15)


@dataclass(frozen=True)
class OpaqueBlock:
    """Exact-length lossless bytes with explicitly unsupported field semantics.

    ``length`` is an explicit caller-provided constraint, not a discovered
    response schema. Useful for retaining unknown/reserved encodings of blocks
    with an independently established length. No command builder accepts it.
    """

    data: bytes
    length: int

    def __post_init__(self) -> None:
        _integer(self.length, 0, 254, "payload length")
        _payload(self.data, self.length)
