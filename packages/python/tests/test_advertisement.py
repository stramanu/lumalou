"""Strict passive advertisement codec tests."""

import pytest
from lumalou import (
    MANUFACTURER_ID,
    MANUFACTURER_PREFIX,
    LumalouAdvertisement,
    is_lumalou_advertisement,
    parse_advertisement,
)


def test_public_advertisement_constants() -> None:
    assert MANUFACTURER_ID == 950
    assert MANUFACTURER_PREFIX == b"MB"


def test_parse_advertisement_states_and_firmware() -> None:
    assert parse_advertisement(b"MB\x01\x000.3.7") == LumalouAdvertisement(
        format_version=1,
        connection_state="idle",
        firmware_version="0.3.7",
    )
    assert parse_advertisement(b"MB\x01\x40build-7") == LumalouAdvertisement(
        format_version=1,
        connection_state="pairing",
        firmware_version="build-7",
    )
    assert parse_advertisement(b"MB\x01\x80v2.4.1\x00") == LumalouAdvertisement(
        format_version=1,
        connection_state="connected",
        firmware_version="v2.4.1",
    )


def test_connection_flags_follow_published_parser_precedence() -> None:
    assert parse_advertisement(b"MB\x01\xc0").connection_state == "connected"
    assert parse_advertisement(b"MB\x01\x81").connection_state == "connected"
    assert parse_advertisement(b"MB\x01\x41").connection_state == "pairing"
    assert parse_advertisement(b"MB\x01\x20").connection_state == "unknown"
    assert parse_advertisement(b"MB\x01\x00").firmware_version is None
    assert parse_advertisement(b"MB\x01\x00\x00").firmware_version is None
    assert parse_advertisement(b"MB\x00\x000.3.7").format_version == 0
    assert parse_advertisement(b"MB\xff\x000.3.7").format_version == 255


def test_firmware_boundary_and_padding_policy() -> None:
    assert parse_advertisement(b"MB\x01\x00" + b"a" * 32).firmware_version == ("a" * 32)
    assert parse_advertisement(
        b"MB\x01\x00" + b"a" * 31 + b"\x00"
    ).firmware_version == ("a" * 31)


@pytest.mark.parametrize(
    "payload, error",
    [
        (b"", "prefix"),
        (b"XX\x01\x00", "prefix"),
        (b"MB", "format and flags"),
        (b"MB\x01\x00bad value", "invalid characters"),
        (b"MB\x01\x00v1\x1f", "invalid characters"),
        (b"MB\x01\x00v1\x00hidden", "embedded NUL"),
        (b"MB\x01\x00\xff", "ASCII"),
        (b"MB\x01\x00" + b"a" * 33, "too long"),
        (b"MB\x01\x00" + b"a" * 32 + b"\x00", "too long"),
    ],
)
def test_reject_malformed_advertisements(payload: bytes, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        parse_advertisement(payload)


def test_reject_non_bytes_and_prefix_match_is_non_decoding() -> None:
    with pytest.raises(TypeError, match="must be bytes"):
        parse_advertisement(bytearray(b"MB\x01\x00"))  # type: ignore[arg-type]

    assert is_lumalou_advertisement(b"MB") is True
    assert is_lumalou_advertisement(b"XX") is False
    assert is_lumalou_advertisement(bytearray(b"MB")) is False
