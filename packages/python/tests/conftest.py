import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def synthetic_factory_tokens():
    """Build synthetic signed manufacturing tokens and a fake public key."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    from lumalou import crypto

    manufacturer = ec.generate_private_key(ec.SECP256R1())
    public_key = manufacturer.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    _, device_key = crypto.generate_keypair()

    def signed_token(
        item_code: str = "abc123", *, public_key: bytes = device_key
    ) -> bytes:
        if len(item_code) != 6 or not item_code.isascii():
            raise ValueError("synthetic item code must be six ASCII characters")
        token = bytearray(192)
        token[0] = 10
        token[1:25] = b"SYNTHETIC-SERIAL-0" + item_code.encode("ascii")
        token[25:58] = public_key
        token[65:68] = (12).to_bytes(3, "big")
        token[188:192] = b"\x01\x02\x03\x04"
        signature = manufacturer.sign(bytes(token[:124]), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(signature)
        token[124:188] = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return bytes(token)

    return signed_token, {12: public_key[1:]}
