"""Golden-vector conformance: the Python binding must match spec/vectors.json.

This is the cross-language contract: every binding runs the same vectors.
"""
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from lumalou import crypto, protocol as P, responses as R

VECTORS = json.loads((Path(__file__).resolve().parents[3] / "spec" / "vectors.json").read_text())


@pytest.mark.parametrize("v", VECTORS["crc8"])
def test_crc8(v):
    assert P.crc8(bytes.fromhex(v["data"]), v["init"]) == v["expected"]


@pytest.mark.parametrize("v", VECTORS["sessionKey"])
def test_session_key(v):
    priv = ec.derive_private_key(int(v["privateScalar"], 16), ec.SECP256R1())
    key = crypto.derive_session_key(priv, bytes.fromhex(v["devicePubCompressed"]))
    assert key.hex() == v["expected"]


@pytest.mark.parametrize("v", VECTORS["encodeCommand"])
def test_encode_command(v):
    assert P.encode_command(bytes.fromhex(v["appData"])).hex() == v["expected"]


@pytest.mark.parametrize("v", VECTORS["txFrame"])
def test_tx_frame(v):
    frame = P.build_tx_frame(bytes.fromhex(v["plaintext"]), v["seq"],
                             bytes.fromhex(v["key"]), bytes.fromhex(v["nonce"]), bytes.fromhex(v["salt"]))
    assert frame.hex() == v["expected"]


@pytest.mark.parametrize("v", VECTORS["rxDecrypt"])
def test_rx_decrypt(v):
    res = P.decrypt_rx_frame(bytes.fromhex(v["frame"]), bytes.fromhex(v["key"]),
                             bytes.fromhex(v["nonce"]), bytes.fromhex(v["salt"]))
    assert res is not None
    assert res["plaintext"].hex() == v["expectedPlaintext"]
    assert res["crc_ok"] == v["expectedCrcOk"]


@pytest.mark.parametrize("v", VECTORS["globalState"])
def test_global_state(v):
    assert R.parse_global_state(bytes.fromhex(v["args"])) == v["expected"]


@pytest.mark.parametrize("v", VECTORS["responseFrame"])
def test_response_frame(v):
    r = P.parse_response_frame(bytes.fromhex(v["plaintext"]))
    assert r["ok"] and r["opcode"] == v["expectedOpcode"]
    assert r["args"].hex() == v["expectedArgs"]
