"""Pure signed-field verification and device-key identity for a FACTORY token.

The 192-byte layout and manufacturing public key are documented by the
independent MIT-licensed gld09-control project at commit
6e3aff894b0065b760ba44f43a36c7e9988cead9. See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

FACTORY_TOKEN_LENGTH = 192
_SIGNED_END = 124
_SIGNATURE_END = 188
_DEVICE_KEY_START = 25
_DEVICE_KEY_END = 58
_KEY_ID_START = 65
_KEY_ID_END = 68
_TOKEN_VERSION = 10

# Public verification key only; the manufacturing private key is not present.
MANUFACTURING_PUBLIC_KEYS: Mapping[int, bytes] = MappingProxyType(
    {
        12: bytes.fromhex(
            "f3d2307c7faafc2884fb306f7ecb6281ecc4871862dfe66d578cf8b6e36f543d"
            "458b6dfd9b8a8be8346fd9f4d3e3ec8836e1135e8d474bd28f151c94b04c0a56"
        )
    }
)


class InvalidFactoryTokenError(ValueError):
    """The FACTORY token cannot be authenticated or safely decoded."""


def parse_factory_device_fingerprint(
    token: bytes, *, keys: Mapping[int, bytes] | None = None
) -> str:
    """Authenticate FACTORY and return SHA-256 of its compressed P-256 device key.

    The 64 lowercase hex characters identify a device key, not a model or SKU.
    Serial fields are neither decoded nor returned. Salt and signature changes
    do not change this identity. ``keys`` may replace the trusted public-key
    table for another verified source or synthetic tests; callers must
    authenticate that source themselves. Treat the fingerprint as a private stable
    identifier, not anonymous telemetry. It does not prove live key possession.
    """
    return hashlib.sha256(_verify_factory_device_key(token, keys=keys)).hexdigest()


def _verify_factory_device_key(
    token: bytes, *, keys: Mapping[int, bytes] | None = None
) -> bytes:
    if not isinstance(token, bytes):
        raise TypeError("factory token must be bytes")
    if len(token) != FACTORY_TOKEN_LENGTH:
        raise InvalidFactoryTokenError("factory token has invalid length")
    if token[0] != _TOKEN_VERSION:
        raise InvalidFactoryTokenError("unsupported factory token version")

    key_id = int.from_bytes(token[_KEY_ID_START:_KEY_ID_END], "big")
    trusted_keys = MANUFACTURING_PUBLIC_KEYS if keys is None else keys
    public_xy = trusted_keys.get(key_id)
    if not isinstance(public_xy, bytes) or len(public_xy) != 64:
        raise InvalidFactoryTokenError("unknown or invalid manufacturing key")
    try:
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), b"\x04" + public_xy
        )
    except ValueError as error:
        raise InvalidFactoryTokenError("invalid manufacturing key") from error

    raw_signature = token[_SIGNED_END:_SIGNATURE_END]
    signature = encode_dss_signature(
        int.from_bytes(raw_signature[:32], "big"),
        int.from_bytes(raw_signature[32:], "big"),
    )
    try:
        public_key.verify(signature, token[:_SIGNED_END], ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as error:
        raise InvalidFactoryTokenError("factory token signature is invalid") from error

    try:
        ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), token[_DEVICE_KEY_START:_DEVICE_KEY_END]
        )
    except ValueError as error:
        raise InvalidFactoryTokenError("factory token device key is invalid") from error

    return token[_DEVICE_KEY_START:_DEVICE_KEY_END]
