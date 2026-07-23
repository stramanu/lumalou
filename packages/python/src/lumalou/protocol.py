"""MPID framing and AES-128-CTR data channel. See docs/protocol.md."""
from __future__ import annotations

import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

SSI0_ID = 0x01
SPI_WRITE = 0x01

# CRC-8, polynomial 0x07
_CRC8 = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = ((_c << 1) ^ 0x07) & 0xFF if (_c & 0x80) else (_c << 1) & 0xFF
    _CRC8.append(_c)


def crc8(data: bytes, init: int = 0xFF) -> int:
    c = init
    for b in data:
        c = _CRC8[(b ^ c) & 0xFF]
    return c


def aes128_ctr(key16: bytes, iv16: bytes, data: bytes) -> bytes:
    return Cipher(algorithms.AES(key16), modes.CTR(iv16)).encryptor().update(bytes(data))


# ---- application framing ----
def compose_request(app_data: bytes) -> bytes:
    """FE-frame: 0xFE | len | app_data | XOR(len ^ app_data...)."""
    xor = len(app_data) & 0xFF
    for b in app_data:
        xor ^= b
    return bytes([0xFE, len(app_data) & 0xFF]) + bytes(app_data) + bytes([xor & 0xFF])


def ssi0_wrap(fe_frame: bytes, address: int = 0) -> bytes:
    return bytes([SSI0_ID, ((SPI_WRITE << 4) & 0xF0) | (address & 0x0F)]) + fe_frame


def encode_command(app_data: bytes) -> bytes:
    """[opcode] + args  ->  MPID plaintext (01 10 | FE-frame)."""
    return ssi0_wrap(compose_request(app_data))


def parse_response_frame(plaintext: bytes) -> dict:
    """Decode an MPID plaintext response: strip SSI header, then the FE-frame."""
    d = plaintext
    ssi = None
    if len(d) >= 2 and d[0] in (0x01, 0x02):
        ssi = d[:2].hex()
        d = d[2:]
    fe = d.find(b"\xFE")
    if fe >= 0 and len(d) >= fe + 3:
        d = d[fe:]
        length = d[1]
        body = d[2:2 + length]
        return {"ssi": ssi, "ok": True,
                "opcode": body[0] if body else None,
                "args": bytes(body[1:]) if len(body) > 1 else b""}
    return {"ssi": ssi, "ok": False}


# ---- MPID frame + AES-128-CTR ----
def _iv(seq: int, a4: bytes, b4: bytes) -> bytes:
    return struct.pack(">I", seq & 0xFFFFFFFF) + a4 + b4 + b"\x00\x00\x00\x00"


def build_tx_frame(plaintext: bytes, seq: int, key16: bytes, nonce4: bytes, dev_salt4: bytes) -> bytes:
    """App -> device frame. IV = seq || appNonce || deviceSalt || 0."""
    h0 = bytes([0x7E]) + struct.pack(">I", seq & 0xFFFFFFFF) + struct.pack(">H", (len(plaintext) + 1) & 0xFFFF)
    header = h0 + bytes([crc8(h0)])
    body = bytes(plaintext) + bytes([crc8(plaintext)])
    return header + aes128_ctr(key16, _iv(seq, nonce4, dev_salt4), body)


def decrypt_rx_frame(frame: bytes, key16: bytes, nonce4: bytes, dev_salt4: bytes) -> dict | None:
    """Device -> app frame. IV = seq || deviceSalt || appNonce || 0."""
    if len(frame) < 9 or frame[0] != 0x7E:
        return None
    seq = struct.unpack(">I", frame[1:5])[0]
    dec = aes128_ctr(key16, _iv(seq, dev_salt4, nonce4), frame[8:])
    plaintext, crc = dec[:-1], (dec[-1] if dec else 0)
    return {"seq": seq, "plaintext": plaintext, "crc_ok": crc8(plaintext) == crc}
