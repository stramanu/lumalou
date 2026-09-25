"""Literal source-backed query vectors; no guessed response layouts."""

import json
from pathlib import Path

import pytest
from lumalou import client, commands
from lumalou._generated import COMMANDS, RESPONSES
from lumalou.client import ResponseEnvelope, UnsupportedResponseError

VECTORS = json.loads(
    (Path(__file__).resolve().parents[3] / "spec" / "read-requests.json").read_text()
)["requests"]


def test_all_declared_queries_are_covered_without_write_opcodes():
    names = {v["name"] for v in VECTORS}
    assert len(names) == len(VECTORS) == 28
    assert names == set(commands._REQUESTS) == set(client._REQUEST_RESPONSES)
    assert {v["command"] for v in VECTORS} == {
        name for name in COMMANDS if name.startswith("REQUEST_")
    }
    assert len({v["response"] for v in VECTORS}) == len(VECTORS)


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["name"])
def test_exact_query_and_response_ids(vector):
    name = vector["name"]
    assert commands.request(name) == bytes.fromhex(vector["request"])
    assert COMMANDS[vector["command"]] == int(vector["request"], 16)
    assert client._REQUEST_RESPONSES[name] == int(vector["response"], 16)
    assert int(vector["response"], 16) in RESPONSES


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["name"])
def test_only_proven_response_layouts_have_decoders(vector):
    opcode = int(vector["response"], 16)
    if opcode in {0x02, 0x13, 0x19, 0x22, 0x23, 0x27, 0x94, 0x99}:
        return
    # Deliberately arbitrary bytes: preserving raw is not validating semantics.
    raw = b"\x00\xff\x01\x89"
    envelope = ResponseEnvelope(opcode, raw, 1, 1.0, 1)
    with pytest.raises(UnsupportedResponseError):
        envelope.decode()
    assert envelope.args == raw


@pytest.mark.parametrize(
    "name",
    [
        "SET_TIME_PRESCALER",
        "set_time_prescaler",
        "SEND_PAIRING_COMPLETE",
        "unknown",
        "",
    ],
)
def test_query_builder_rejects_writes_and_unknown_names(name):
    with pytest.raises(KeyError):
        commands.request(name)
