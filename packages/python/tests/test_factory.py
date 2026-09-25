"""Synthetic signed FACTORY tokens; no real serials, captures, or BLE I/O."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from lumalou import (
    InvalidFactoryTokenError,
    parse_factory_device_fingerprint,
)


def test_device_fingerprint_is_key_hash_independent_of_serial_and_salt():
    import hashlib

    token, keys = _signed_token()
    fingerprint = parse_factory_device_fingerprint(token, keys=keys)
    assert fingerprint == hashlib.sha256(token[25:58]).hexdigest()
    assert (
        parse_factory_device_fingerprint(token[:188] + b"salt", keys=keys)
        == fingerprint
    )
    other, other_keys = _signed_token(b"999999", device_key=token[25:58])
    assert parse_factory_device_fingerprint(other, keys=other_keys) == fingerprint
    different, different_keys = _signed_token()
    assert (
        parse_factory_device_fingerprint(different, keys=different_keys) != fingerprint
    )


@pytest.mark.parametrize("offset", [1, 25, 57, 65, 123, 124, 187])
def test_fingerprint_rejects_tampering(offset):
    token, keys = _signed_token()
    damaged = bytearray(token)
    damaged[offset] ^= 1
    with pytest.raises(InvalidFactoryTokenError):
        parse_factory_device_fingerprint(bytes(damaged), keys=keys)


def test_fingerprint_does_not_interpret_serial_suffix():
    token, keys = _signed_token(b"\xff" * 6)
    assert len(parse_factory_device_fingerprint(token, keys=keys)) == 64


def _signed_token(
    item: bytes = b"ABC123",
    *,
    serial_prefix: bytes = b"ABCDEF0123456789XY",
    key_id: int = 12,
    device_key: bytes | None = None,
) -> tuple[bytes, dict[int, bytes]]:
    manufacturer = ec.generate_private_key(ec.SECP256R1())
    public_key = manufacturer.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    if device_key is None:
        device_key = (
            ec.generate_private_key(ec.SECP256R1())
            .public_key()
            .public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
            )
        )
    token = bytearray(192)
    token[0] = 10
    token[1:25] = serial_prefix + item
    token[25:58] = device_key
    token[65:68] = key_id.to_bytes(3, "big")
    token[188:192] = b"\x01\x02\x03\x04"
    signature = manufacturer.sign(bytes(token[:124]), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(signature)
    token[124:188] = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return bytes(token), {key_id: public_key[1:]}


def test_unknown_signed_key_id_and_version_are_rejected() -> None:
    token, keys = _signed_token(key_id=13)
    with pytest.raises(InvalidFactoryTokenError, match="unknown or invalid"):
        parse_factory_device_fingerprint(token)
    assert len(parse_factory_device_fingerprint(token, keys=keys)) == 64
    changed_version = bytearray(token)
    changed_version[0] = 11
    with pytest.raises(
        InvalidFactoryTokenError, match="unsupported factory token version"
    ):
        parse_factory_device_fingerprint(bytes(changed_version), keys=keys)


@pytest.mark.parametrize("length", [0, 191, 193])
def test_token_length_must_be_exact(length: int) -> None:
    token, keys = _signed_token()
    with pytest.raises(InvalidFactoryTokenError, match="invalid length"):
        parse_factory_device_fingerprint(
            token[:length] if length < 192 else token + b"x", keys=keys
        )


@pytest.mark.parametrize("offset", [0, 1, 20, 30, 65, 123, 124, 187])
def test_tampered_signed_bytes_or_signature_are_rejected(offset: int) -> None:
    token, keys = _signed_token()
    altered = bytearray(token)
    altered[offset] ^= 1
    with pytest.raises(InvalidFactoryTokenError):
        parse_factory_device_fingerprint(bytes(altered), keys=keys)


def test_unknown_and_malformed_manufacturing_keys_are_rejected() -> None:
    token, keys = _signed_token()
    with pytest.raises(InvalidFactoryTokenError, match="signature is invalid"):
        parse_factory_device_fingerprint(
            token
        )  # Synthetic signature is not from Mattel.
    with pytest.raises(InvalidFactoryTokenError, match="unknown or invalid"):
        parse_factory_device_fingerprint(token, keys={})
    with pytest.raises(InvalidFactoryTokenError, match="unknown or invalid"):
        parse_factory_device_fingerprint(token, keys={12: b"x" * 63})
    with pytest.raises(InvalidFactoryTokenError, match="invalid manufacturing key"):
        parse_factory_device_fingerprint(token, keys={12: b"\x00" * 64})
    assert len(keys[12]) == 64


@pytest.mark.parametrize("serial_prefix", [b"\xff" + b"B" * 17, b"B" * 17 + b"\x00"])
def test_serial_encoding_is_not_interpreted_after_valid_signature(
    serial_prefix: bytes,
) -> None:
    token, keys = _signed_token(serial_prefix=serial_prefix)
    assert len(parse_factory_device_fingerprint(token, keys=keys)) == 64


def test_signed_invalid_device_key_is_rejected() -> None:
    token, keys = _signed_token(device_key=b"\x00" * 33)
    with pytest.raises(InvalidFactoryTokenError, match="device key is invalid"):
        parse_factory_device_fingerprint(token, keys=keys)


def test_salt_is_outside_manufacturing_signature() -> None:
    token, keys = _signed_token()
    different_salt = token[:188] + b"\xaa\xbb\xcc\xdd"
    assert parse_factory_device_fingerprint(
        different_salt, keys=keys
    ) == parse_factory_device_fingerprint(token, keys=keys)


def test_error_and_logs_do_not_expose_synthetic_serial(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token, _keys = _signed_token(serial_prefix=b"SECRET0123456789XY")
    with pytest.raises(InvalidFactoryTokenError) as error:
        parse_factory_device_fingerprint(token, keys={})
    assert "SECRET" not in str(error.value)
    assert not caplog.records


def test_non_bytes_input_is_rejected() -> None:
    token, keys = _signed_token()
    with pytest.raises(TypeError, match="must be bytes"):
        parse_factory_device_fingerprint(bytearray(token), keys=keys)  # type: ignore[arg-type]
