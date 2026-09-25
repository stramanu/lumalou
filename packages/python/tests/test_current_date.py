"""CURRENT_DATE: target-observed transition and exhaustive synthetic validation."""

from dataclasses import FrozenInstanceError

import pytest
from lumalou import CurrentDate, commands
from lumalou.client import MalformedResponseError, ResponseEnvelope
from lumalou.responses import parse_current_date


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Read-only target evidence supplied 2026-09-17; no device identifier.
        ("23590003", CurrentDate(23, 59, 0, 3)),
        ("00000004", CurrentDate(0, 0, 0, 4)),
        # Synthetic boundary vectors, not additional hardware observations.
        ("23595906", CurrentDate(23, 59, 59, 6)),
        ("00000000", CurrentDate(0, 0, 0, 0)),
    ],
)
def test_current_date_vectors_and_envelope(raw, expected):
    args = bytes.fromhex(raw)
    assert parse_current_date(args) == expected
    envelope = ResponseEnvelope(0x13, args, 1, 1.0, 1)
    assert envelope.decode() == expected
    assert envelope.args == args


def test_every_clock_and_weekday_value_matches_existing_set_encoding():
    # All 604800 representable time/weekday combinations; pure codec operations.
    # No commands are sent and this does not establish SET side effects.
    for weekday in range(7):
        for hour in range(24):
            for minute in range(60):
                for second in range(60):
                    args = commands.set_current_date(hour, minute, second, weekday)[1:]
                    assert parse_current_date(args) == CurrentDate(
                        hour, minute, second, weekday
                    )


@pytest.mark.parametrize("index,maximum", [(0, 23), (1, 59), (2, 59), (3, 6)])
def test_all_byte_encodings_accept_exactly_valid_bcd_and_field_ranges(index, maximum):
    for byte in range(256):
        args = bytes(byte if position == index else 0 for position in range(4))
        decimal = 10 * (byte >> 4) + (byte & 0x0F)
        if byte >> 4 <= 9 and byte & 0x0F <= 9 and decimal <= maximum:
            fields = [0, 0, 0, 0]
            fields[index] = decimal
            assert parse_current_date(args) == CurrentDate(*fields)
        else:
            with pytest.raises(ValueError):
                parse_current_date(args)
            with pytest.raises(MalformedResponseError):
                ResponseEnvelope(0x13, args, 1, 1.0, 1).decode()


def test_exact_length_no_padding_truncation_or_ff_sentinel():
    for length in range(256):
        if length == 4:
            continue
        with pytest.raises(ValueError, match="exactly 4 bytes"):
            parse_current_date(bytes(length))
    with pytest.raises(ValueError, match="invalid BCD"):
        parse_current_date(b"\xff" * 4)


@pytest.mark.parametrize(
    "invalid", [None, "00000000", [0, 0, 0, 0], bytearray(4), memoryview(bytes(4))]
)
def test_parser_requires_immutable_bytes(invalid):
    with pytest.raises(ValueError):
        parse_current_date(invalid)


def test_model_is_immutable_and_has_no_calendar_or_timezone():
    reading = CurrentDate(1, 2, 3, 4)
    with pytest.raises(FrozenInstanceError):
        reading.hour = 5
    assert set(reading.__dataclass_fields__) == {"hour", "minute", "second", "weekday"}


@pytest.mark.parametrize("index,maximum", [(0, 23), (1, 59), (2, 59), (3, 6)])
def test_direct_model_construction_is_strict(index, maximum):
    for invalid in (-1, maximum + 1, True, False, 0.0, "0", None, []):
        fields = [0, 0, 0, 0]
        fields[index] = invalid
        with pytest.raises(ValueError):
            CurrentDate(*fields)
