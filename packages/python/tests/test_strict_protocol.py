"""Strict envelope validation using existing independent golden vectors."""

import json
from pathlib import Path

import pytest

from lumalou import protocol as P
from lumalou import responses as R

VECTORS = json.loads(
    (Path(__file__).resolve().parents[3] / "spec" / "vectors.json").read_text()
)
VECTOR = VECTORS["rxDecrypt"][1]
KEY, NONCE, SALT = (bytes.fromhex(VECTOR[name]) for name in ("key", "nonce", "salt"))
FRAME = bytes.fromhex(VECTOR["frame"])


@pytest.mark.parametrize("length", [0, 1, 7, 8, len(FRAME) - 1, len(FRAME) + 1])
def test_mpip_exact_declared_length(length):
    frame = (FRAME + b"\x00")[:length]
    assert P.decrypt_rx_frame(frame, KEY, NONCE, SALT) is None


@pytest.mark.parametrize("index", list(range(8)))
def test_header_crc_covers_every_header_byte(index):
    frame = bytearray(FRAME)
    frame[index] ^= 1
    assert P.decrypt_rx_frame(bytes(frame), KEY, NONCE, SALT) is None


def test_declared_length_checked_even_with_valid_header_crc():
    frame = bytearray(FRAME)
    frame[6] += 1
    frame[7] = P.crc8(frame[:7])
    assert P.decrypt_rx_frame(bytes(frame), KEY, NONCE, SALT) is None


def test_bad_encrypted_body_crc_is_not_success():
    frame = bytearray(FRAME)
    frame[-1] ^= 1
    result = P.decrypt_rx_frame(bytes(frame), KEY, NONCE, SALT)
    assert result is not None and result["crc_ok"] is False


@pytest.mark.parametrize(
    "plaintext",
    [
        "",
        "01",
        "0150",
        "0150fe",
        "0150fe00",
        "0150fe0000",
        "0150fe0218",
        "0150fe021805",
        "0150fe0218051e",
        "0150fe0218051f00",
        "fe021805",
        "00fe0218051f",
        "0150feff18051f",
    ],
)
def test_malformed_fe_frame(plaintext):
    result = P.parse_response_frame(bytes.fromhex(plaintext))
    assert not result["ok"]
    assert result["error"] != "unsupported_transport"


def test_known_non_fe_transport_notification_is_not_an_application_response():
    assert P.parse_response_frame(bytes.fromhex("015002001e001c")) == {
        "ssi": "0150",
        "ok": False,
        "error": "unsupported_transport",
    }


@pytest.mark.parametrize(
    "ack",
    [
        "00 7f 01 03 00 00 00 00 00",
        "00 7f 01 06 00 00 00 00 00",
        "00 7f 01 07 00 00 00 00 00",
        "00 7f 01 12 00 00 00 00 00",
        "01 10 04 00",
        "01 10 05 00",
        "01 10 10 00",
    ],
)
def test_live_transport_acks_on_007f_route_are_ignored_not_fatal(ack):
    """Exact ACKs observed on the target are not application responses."""
    assert P.parse_response_frame(bytes.fromhex(ack)) == {
        "ssi": bytes.fromhex(ack)[:2].hex(),
        "ok": False,
        "error": "unsupported_transport",
    }
    for malformed in (
        "00 7f 01 03",
        "00 7f 01 06 00 00 00 00 01",
        "00 7f 01 07 00 00 00 00 01",
        "00 7f 01 12 00 00 00 00 01",
        "01 10 04 01",
        "01 10 05 01",
        "01 10 10 01",
    ):
        result = P.parse_response_frame(bytes.fromhex(malformed))
        assert not result["ok"]
        assert result["error"] == "unsupported_route"


def test_no_search_for_fe_inside_unrecognized_transport_payload():
    assert not P.parse_response_frame(bytes.fromhex("015000fe0218051f"))["ok"]


def test_exact_fe_packet_on_confirmed_receive_route():
    result = P.parse_response_frame(bytes.fromhex("0150fe0218051f"))
    assert result["ok"] and result["opcode"] == 0x18 and result["args"] == b"\x05"


@pytest.mark.parametrize(
    "prefix", [b"", b"\x01\x10", b"\x01\x00", b"\x01\x51", b"\x02\x50", b"\x02\xff"]
)
def test_bare_fe_and_unconfirmed_ssi_routes_are_not_application_responses(prefix):
    result = P.parse_response_frame(prefix + bytes.fromhex("fe0218051f"))
    assert not result["ok"]
    assert result["error"] == "unsupported_route"


def test_only_source_backed_receive_route_is_allowlisted():
    payload = bytes.fromhex("fe0218051f")
    for first in range(256):
        for second in range(256):
            result = P.parse_response_frame(bytes([first, second]) + payload)
            assert result["ok"] is (first == 1 and second == 0x50)


@pytest.mark.parametrize("length", [0, 1, 12, 14, 26])
def test_global_state_never_pads_or_truncates(length):
    with pytest.raises(ValueError):
        R.parse_global_state(bytes(length))


@pytest.mark.parametrize("data", [b"", bytes(256), [], "53"])
def test_fe_builder_rejects_unsafe_length_or_type(data):
    with pytest.raises(ValueError):
        P.compose_request(data)
