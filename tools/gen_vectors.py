#!/usr/bin/env python3
"""
Generate spec/vectors.json — the language-agnostic golden test vectors.

These are produced by a reference implementation validated bit-exact against the
device's native library. Every language binding runs its own implementation against
this file and must match, guaranteeing cross-language parity.

    python tools/gen_vectors.py
"""
import base64
import json
import os
import struct
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

OUT = Path(__file__).resolve().parent.parent / "spec" / "vectors.json"

# ---- reference primitives (validated) ----
_CRC8 = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = ((_c << 1) ^ 0x07) & 0xFF if (_c & 0x80) else (_c << 1) & 0xFF
    _CRC8.append(_c)


def crc8(data, init=0xFF):
    c = init
    for b in data:
        c = _CRC8[(b ^ c) & 0xFF]
    return c


def aes_ctr(key, iv, data):
    return Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor().update(data)


def stretch(shared):
    s = bytearray(shared)
    for cnt in range(100):
        iv = bytes([0, 0, 0, 0, 0, 0, 0, cnt, 0, 0x6D, 0x61, 0x74, 0x74, 0x65, 0x6C, 0])
        s = bytearray(aes_ctr(bytes(s[:16]), iv, bytes(s)))
    return bytes(s)


def derive_session_key(scalar_hex, device_pub_hex):
    priv = ec.derive_private_key(int(scalar_hex, 16), ec.SECP256R1())
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(device_pub_hex))
    shared = priv.exchange(ec.ECDH(), peer)
    return stretch(shared)


def compose_request(app):
    xor = len(app) & 0xFF
    for b in app:
        xor ^= b
    return bytes([0xFE, len(app) & 0xFF]) + app + bytes([xor & 0xFF])


def encode_command(app):
    return bytes([0x01, 0x10]) + compose_request(app)


def _iv(seq, a, b):
    return struct.pack(">I", seq) + a + b + b"\x00\x00\x00\x00"


def tx_frame(plaintext, seq, key, nonce, salt):
    h0 = bytes([0x7E]) + struct.pack(">I", seq) + struct.pack(">H", len(plaintext) + 1)
    header = h0 + bytes([crc8(h0)])
    body = plaintext + bytes([crc8(plaintext)])
    return header + aes_ctr(key, _iv(seq, nonce, salt), body)


def rx_frame(plaintext, seq, key, nonce, salt):
    h0 = bytes([0x7E]) + struct.pack(">I", seq) + struct.pack(">H", len(plaintext) + 1)
    header = h0 + bytes([crc8(h0)])
    body = plaintext + bytes([crc8(plaintext)])
    return header + aes_ctr(key, _iv(seq, salt, nonce), body)  # swapped IV for device->app


def parse_global_state(args):
    n = []
    for byte in args:
        n += [byte >> 4, byte & 0x0F]
    while len(n) < 26:
        n.append(0)
    keys = ["operationMode", "activityState", "musicStatus", None, "currentVolume",
            "playlistDuration", "lightStatus", "lightBrightness", "lightColor",
            "napTimeStatus", "napDuration", "ready2RiseStatus", "ready2RiseAlarmStatus",
            "timePrescaler", "currentStage", "clockDisplay", "clockBrightness",
            "clockFormat", "routineMusicStatus", "taskRewardSfx", "routineRewardSfx",
            "lightDuration", "routineVolume", "routineModeStatus", "alarmExecuting"]
    out = {"operationMode": n[0], "activityState": n[1], "musicStatus": n[2],
           "currentSong": (n[3] << 4) | n[4], "currentVolume": n[5], "playlistDuration": n[6],
           "lightStatus": n[7], "lightBrightness": n[8], "lightColor": n[9],
           "napTimeStatus": n[10], "napDuration": n[11], "ready2RiseStatus": n[12],
           "ready2RiseAlarmStatus": n[13], "timePrescaler": n[14], "currentStage": n[15],
           "clockDisplay": n[16], "clockBrightness": n[17], "clockFormat": n[18],
           "routineMusicStatus": n[19], "taskRewardSfx": n[20], "routineRewardSfx": n[21],
           "lightDuration": n[22], "routineVolume": n[23], "routineModeStatus": n[24],
           "alarmExecuting": n[25]}
    return out


def jwk_for(scalar_hex):
    d = int(scalar_hex, 16)
    priv = ec.derive_private_key(d, ec.SECP256R1())
    pn = priv.public_key().public_numbers()
    b64 = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode()
    return {"kty": "EC", "crv": "P-256",
            "d": b64(d.to_bytes(32, "big")),
            "x": b64(pn.x.to_bytes(32, "big")),
            "y": b64(pn.y.to_bytes(32, "big"))}


def h(b):
    return b.hex()


def main():
    KEY = "b95d24386f1ac5d4cd2239eafc87dbc4"
    NONCE = "11223344"
    SALT = "8fb32ecf"

    vectors = {"crc8": [], "sessionKey": [], "encodeCommand": [], "txFrame": [],
               "rxDecrypt": [], "globalState": [], "responseFrame": []}

    for data, init in [("313233343536373839", 0), ("fe0153", 0xFF), ("", 0xFF), ("00", 0xFF)]:
        vectors["crc8"].append({"data": data, "init": init, "expected": crc8(bytes.fromhex(data), init)})

    for scalar, dev in [
        ("7507b6b825bc2b1478ca392bde774b4c1c354a46b9f236388f9bf4b3a583d1a3",
         "02bdc752ada111313522fb57e16325c213383c11b378965e5e5511361889f13f5d"),
        ("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
         "02bdc752ada111313522fb57e16325c213383c11b378965e5e5511361889f13f5d"),
    ]:
        vectors["sessionKey"].append({
            "privateScalar": scalar, "jwk": jwk_for(scalar),
            "devicePubCompressed": dev, "expected": h(derive_session_key(scalar, dev))})

    for app in ["3c05", "0301", "3a09", "53", "3016455303"]:
        vectors["encodeCommand"].append({"appData": app, "expected": h(encode_command(bytes.fromhex(app)))})

    for pt, seq in [("01020304", 1), ("0110fe015352", 2), ("011005", 255)]:
        vectors["txFrame"].append({
            "plaintext": pt, "seq": seq, "key": KEY, "nonce": NONCE, "salt": SALT,
            "expected": h(tx_frame(bytes.fromhex(pt), seq, bytes.fromhex(KEY), bytes.fromhex(NONCE), bytes.fromhex(SALT)))})

    for pt, seq in [("015002001e001c", 7), ("0150fe0218001a", 5)]:
        frame = rx_frame(bytes.fromhex(pt), seq, bytes.fromhex(KEY), bytes.fromhex(NONCE), bytes.fromhex(SALT))
        vectors["rxDecrypt"].append({
            "frame": h(frame), "key": KEY, "nonce": NONCE, "salt": SALT,
            "expectedPlaintext": pt, "expectedCrcOk": True})

    for args in ["00000550500400001201114500", "020105505004000012011145000a"]:
        vectors["globalState"].append({"args": args, "expected": parse_global_state(bytes.fromhex(args))})

    for opcode, arg in [(0x18, "05"), (0x02, "00")]:
        fe = compose_request(bytes([opcode]) + bytes.fromhex(arg))
        plain = bytes([0x01, 0x50]) + fe
        vectors["responseFrame"].append({"plaintext": h(plain), "expectedOpcode": opcode, "expectedArgs": arg})

    OUT.write_text(json.dumps(vectors, indent=2) + "\n")
    total = sum(len(v) for v in vectors.values())
    print(f"wrote {OUT} — {total} vectors across {len(vectors)} categories")


if __name__ == "__main__":
    main()
