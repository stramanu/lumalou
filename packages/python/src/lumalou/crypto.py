"""
Session-key handshake — pure Python.

Reimplements the device's native MPID handshake (ECDH P-256 + a 100-round
AES-128-CTR "mattel" stretch), validated bit-exact against golden vectors.
Depends only on `cryptography`.
"""
from __future__ import annotations

import os

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

_CURVE = ec.SECP256R1()
_MATTEL = bytes([0x6D, 0x61, 0x74, 0x74, 0x65, 0x6C])  # "mattel"


def _aes_ctr(key16: bytes, iv16: bytes, data: bytes) -> bytes:
    return Cipher(algorithms.AES(key16), modes.CTR(iv16)).encryptor().update(bytes(data))


def generate_keypair():
    """Ephemeral P-256 keypair. Returns (private_key, compressed_pubkey_33B)."""
    priv = ec.generate_private_key(_CURVE)
    pub = priv.public_key().public_bytes(Encoding.X962, PublicFormat.CompressedPoint)
    return priv, pub


def ecdh_shared_secret(private_key, peer_pub_compressed: bytes) -> bytes:
    """ECDH shared secret (X coordinate, 32B). Accepts the peer's compressed public key."""
    peer = ec.EllipticCurvePublicKey.from_encoded_point(_CURVE, bytes(peer_pub_compressed))
    return private_key.exchange(ec.ECDH(), peer)


def stretch(shared32: bytes) -> bytes:
    """100 rounds of AES-128-CTR: key = shared[:16], IV = counter + 'mattel'."""
    s = bytearray(shared32)
    for counter in range(100):
        iv = bytes([0, 0, 0, 0, 0, 0, 0, counter, 0]) + _MATTEL + bytes([0])
        s = bytearray(_aes_ctr(bytes(s[:16]), iv, bytes(s)))
    return bytes(s)


def derive_session_key(private_key, device_pub_compressed: bytes) -> bytes:
    """32-byte session key (first 16 bytes are the AES-128 data-channel key)."""
    return stretch(ecdh_shared_secret(private_key, device_pub_compressed))


def new_nonce() -> bytes:
    """4 random bytes (the app 'salt' sent in the SESSION payload)."""
    return os.urandom(4)


def token_device_pubkey(token: bytes) -> bytes:
    """Device compressed public key: bytes [25:58] of the MFG token."""
    return bytes(token[25:58])


def token_device_salt(token: bytes) -> bytes:
    """Device salt: last 4 bytes of the MFG token."""
    return bytes(token[-4:])
