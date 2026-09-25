"""Client sessions and fresh response contract, using a fake Bleak transport."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bleak.backends.device import BLEDevice

from lumalou import client as module
from lumalou import commands as C
from lumalou import protocol as P
from lumalou.client import (
    DisconnectedError,
    FactoryIdentityError,
    FactoryIdentityMismatchError,
    FreshSessionRequiredError,
    LumalouClient,
    MalformedResponseError,
    RequestTimeoutError,
    UnsupportedResponseError,
)
from lumalou.factory import parse_factory_device_fingerprint

pytestmark = pytest.mark.asyncio

READ_REQUESTS = json.loads(
    (Path(__file__).resolve().parents[3] / "spec" / "read-requests.json").read_text()
)["requests"]


@pytest.fixture
def rig(monkeypatch, synthetic_factory_tokens):
    real_sleep = asyncio.sleep

    async def fast_sleep(_delay):
        await real_sleep(0)

    monkeypatch.setattr(module.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(
        module.BleakScanner,
        "discover",
        Mock(side_effect=AssertionError("no scanner allowed")),
    )
    make_factory_token, factory_keys = synthetic_factory_tokens
    token = make_factory_token()
    monkeypatch.setattr(
        module,
        "parse_factory_device_fingerprint",
        lambda raw: parse_factory_device_fingerprint(raw, keys=factory_keys),
    )
    device = BLEDevice("synthetic-device", "test", {})
    transports = []
    envelopes, states = [], []
    disconnected = Mock()
    owner = None

    class Transport:
        def __init__(self, received_device, *, disconnected_callback):
            assert received_device is device
            self.disconnected_callback = disconnected_callback
            self.is_connected = False
            self.writes = []
            self.disconnect_count = 0
            self.sequence = 1
            self.on_write = None
            self.notify_callback = None
            self.keys = None
            transports.append(self)

        async def connect(self):
            self.is_connected = True

        async def read_gatt_char(self, characteristic):
            assert characteristic == module.FACTORY
            return token

        async def start_notify(self, characteristic, callback):
            assert characteristic == module.RX
            self.notify_callback = callback

        async def write_gatt_char(self, characteristic, payload, *, response):
            self.writes.append((characteristic, payload, response))
            if characteristic == module.TX and self.on_write is not None:
                await self.on_write(payload)

        async def disconnect(self):
            self.disconnect_count += 1
            self.is_connected = False
            self.disconnected_callback(self)

        def lose_connection(self):
            self.is_connected = False
            self.disconnected_callback(self)

        def frame(self, opcode, args, *, sequence=None, plaintext=None):
            key, nonce, salt = self.keys or (owner._key, owner._nonce, owner._salt)
            seq = self.sequence if sequence is None else sequence
            self.sequence += 1
            payload = (
                plaintext
                if plaintext is not None
                else b"\x01\x50" + P.compose_request(bytes([opcode]) + args)
            )
            return P.build_tx_frame(payload, seq, key, salt, nonce)

        def notify(self, opcode, args, **kwargs):
            frame = self.frame(opcode, args, **kwargs)
            self.notify_callback(None, bytearray(frame))
            return frame

    owner = LumalouClient(
        device,
        expected_device_fingerprint=parse_factory_device_fingerprint(
            token, keys=factory_keys
        ),
        client_factory=Transport,
        on_response=envelopes.append,
        on_state=states.append,
        disconnected_callback=disconnected,
    )
    return SimpleNamespace(
        client=owner,
        device=device,
        factory_token=token,
        fingerprint=parse_factory_device_fingerprint(token, keys=factory_keys),
        make_factory_token=make_factory_token,
        transports=transports,
        factory=Transport,
        envelopes=envelopes,
        states=states,
        disconnected=disconnected,
    )


async def connect(rig):
    await rig.client.connect()
    transport = rig.transports[-1]
    transport.keys = (rig.client._key, rig.client._nonce, rig.client._salt)
    return transport


async def test_device_fingerprint_binding_and_session_lifetime(rig):
    client = LumalouClient(
        rig.device,
        client_factory=rig.factory,
        expected_device_fingerprint=rig.fingerprint,
    )
    assert client.device_fingerprint is None
    await client.connect()
    assert client.device_fingerprint == rig.fingerprint
    await client.disconnect()
    assert client.device_fingerprint is None


async def test_different_device_key_rejected_before_notify_and_writes(rig):
    client = LumalouClient(
        rig.device,
        client_factory=rig.factory,
        expected_device_fingerprint="0" * 64,
    )
    with pytest.raises(FactoryIdentityMismatchError, match="expected device"):
        await client.connect()
    transport = rig.transports[-1]
    assert not transport.writes
    assert transport.notify_callback is None
    assert transport.disconnect_count == 1
    assert client.device_fingerprint is None


async def test_reconnect_rechecks_device_key_even_with_same_item(rig, monkeypatch):
    client = LumalouClient(
        rig.device,
        client_factory=rig.factory,
        expected_device_fingerprint=rig.fingerprint,
    )
    await client.connect()
    await client.disconnect()
    _, different_key = module.crypto.generate_keypair()

    async def different_device(_self, characteristic):
        assert characteristic == module.FACTORY
        return rig.make_factory_token(public_key=different_key)

    monkeypatch.setattr(rig.factory, "read_gatt_char", different_device)
    with pytest.raises(FactoryIdentityMismatchError, match="expected device"):
        await client.connect()
    assert client.device_fingerprint is None
    assert not rig.transports[-1].writes
    assert rig.transports[-1].notify_callback is None


async def test_default_connection_exposes_only_device_fingerprint(rig):
    client = LumalouClient(rig.device, client_factory=rig.factory)
    await client.connect()
    assert client.device_fingerprint == rig.fingerprint
    await client.disconnect()


@pytest.mark.parametrize("fingerprint", ["", "a" * 63, "G" * 64, "A" * 64, 123])
async def test_invalid_expected_fingerprint_rejected_before_io(rig, fingerprint):
    with pytest.raises(ValueError, match="64 lowercase hex"):
        LumalouClient(rig.device, expected_device_fingerprint=fingerprint)
    assert not rig.transports


async def waiting_request(rig, transport, *, opcode=0x02, payload=None, timeout=1):
    written = asyncio.Event()

    async def on_write(_payload):
        written.set()

    transport.on_write = on_write
    task = asyncio.create_task(
        rig.client.request(payload or C.request("global_state"), opcode, timeout)
    )
    await asyncio.wait_for(written.wait(), 1)
    return task


async def test_connect_device_factory_handshake_and_disconnect(rig):
    transport = await connect(rig)
    assert rig.client.connected and rig.client._seq == 2
    assert [write[0] for write in transport.writes] == [module.SESSION, module.TX]
    assert len(transport.writes[0][1]) == 37
    await rig.client.disconnect()
    assert not rig.client.connected and rig.client._client is None
    assert rig.client._key is None and rig.client._seq == 1
    assert transport.disconnect_count == 1
    rig.disconnected.assert_called_once_with(rig.client)


async def test_valid_signed_factory_identity_connects_without_expected_pin(rig):
    """Standalone clients still authenticate FACTORY when no key pin is given."""
    client = LumalouClient(rig.device, client_factory=rig.factory)

    await client.connect()

    transport = rig.transports[0]
    assert [write[0] for write in transport.writes] == [module.SESSION, module.TX]
    await client.disconnect()


async def test_invalid_factory_signature_writes_no_session_or_tx(
    rig, monkeypatch, caplog
):
    """Signature verification remains mandatory without an expected key pin."""
    tampered = bytearray(rig.factory_token)
    tampered[124] ^= 0x01

    async def read_tampered(_client, characteristic):
        assert characteristic == module.FACTORY
        return bytes(tampered)

    monkeypatch.setattr(rig.factory, "read_gatt_char", read_tampered)
    client = LumalouClient(rig.device, client_factory=rig.factory)
    with pytest.raises(FactoryIdentityError):
        await client.connect()

    transport = rig.transports[0]
    assert transport.notify_callback is None
    assert transport.writes == []
    assert transport.disconnect_count == 1
    assert client._client is None and not client.connected
    assert client._key is None and client._nonce is None and client._salt is None
    assert not client._cleanup_tasks
    assert "SYNTHETIC-SERIAL" not in caplog.text


async def test_reconnect_reauthenticates_expected_device_before_writes(
    rig, monkeypatch, caplog
):
    """Every new transport validates the signed device before SESSION/TX writes."""
    first_transport = await connect(rig)
    await rig.client.disconnect()

    async def read_different_signed_item(_client, characteristic):
        assert characteristic == module.FACTORY
        _, public_key = module.crypto.generate_keypair()
        return rig.make_factory_token(public_key=public_key)

    monkeypatch.setattr(rig.factory, "read_gatt_char", read_different_signed_item)
    with pytest.raises(FactoryIdentityMismatchError) as error:
        await rig.client.connect()

    second_transport = rig.transports[-1]
    assert second_transport is not first_transport
    assert second_transport.notify_callback is None
    assert second_transport.writes == []
    assert second_transport.disconnect_count == 1
    assert rig.client._client is None and not rig.client.connected
    assert rig.client._key is None and rig.client._nonce is None
    assert rig.client._salt is None and not rig.client._cleanup_tasks
    assert rig.fingerprint not in str(error.value)
    assert "SYNTHETIC-SERIAL" not in caplog.text


async def test_exact_response_envelope_and_detached_state(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    transport.notify(0x18, b"\x05")
    assert not task.done()  # Valid wrong opcode is observable, never a match.
    before = module.time.monotonic()
    transport.notify(0x02, bytes(13))
    response = await task
    assert response.opcode == 2 and response.args == bytes(13)
    assert (
        response.generation == rig.client.generation and response.received_at >= before
    )
    assert response.decode()["currentVolume"] == 0
    snapshot = rig.client.state
    snapshot["currentVolume"] = 9
    rig.states[-1]["currentVolume"] = 8
    assert rig.client.state["currentVolume"] == 0
    assert rig.client._waiter is None
    await rig.client.disconnect()


async def test_unsolicited_updates_and_identical_duplicate_is_ignored(rig):
    transport = await connect(rig)
    frame = transport.notify(0x02, bytes(13))
    transport.notify_callback(None, bytearray(frame))
    assert len(rig.states) == len(rig.envelopes) == 1
    transport.notify(0x02, bytes.fromhex("00000700000000000000000000"))
    assert rig.client.state["currentVolume"] == 7
    await rig.client.disconnect()


async def test_repeated_opcode_requires_clean_session_even_after_success(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    transport.notify(2, bytes(13))
    await task
    with pytest.raises(FreshSessionRequiredError):
        await rig.client.request_state()
    old_generation = rig.client.generation
    replacement = await connect(rig)
    assert rig.client.generation != old_generation
    assert rig.client.state is None and rig.client._seq == 2
    task = await waiting_request(rig, replacement)
    transport.notify(2, bytes(13))  # Old callback carries the retired generation.
    assert not task.done()
    replacement.notify(2, bytes(13))
    assert (await task).generation == rig.client.generation
    await rig.client.disconnect()


async def test_timeout_invalidates_and_late_response_cannot_complete_reconnect(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport, timeout=0.01)
    with pytest.raises(RequestTimeoutError):
        await task
    assert not rig.client.connected and rig.client.state is None
    assert rig.client._waiter is None and transport.disconnect_count == 1
    replacement = await connect(rig)
    task = await waiting_request(rig, replacement)
    transport.notify(2, bytes(13))
    assert not task.done()
    replacement.notify(2, bytes(13))
    await task
    await rig.client.disconnect()


async def test_unexpected_disconnect_fails_waiter_resets_state_and_session(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    old_generation = rig.client.generation
    transport.lose_connection()
    assert not rig.client.connected and rig.client.generation != old_generation
    with pytest.raises(DisconnectedError):
        await task
    assert rig.client._waiter is None and not rig.client._cleanup_tasks
    rig.disconnected.assert_called_once()
    replacement = await connect(rig)
    assert replacement is not transport and rig.client._seq == 2
    assert replacement.keys != transport.keys
    await rig.client.disconnect()


async def test_cancel_request_disconnects_and_never_replays(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not rig.client.connected and rig.client._waiter is None
    assert transport.disconnect_count == 1
    assert len(transport.writes) == 3  # session, ENABLE_RX, one query


@pytest.mark.parametrize("args", [b"", bytes(12), bytes(14)])
async def test_malformed_global_response_fails_without_state(rig, args):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    transport.notify(2, args)
    with pytest.raises(MalformedResponseError):
        await task
    assert not rig.client.connected and not rig.states and rig.client.state is None


@pytest.mark.parametrize("kind", ["header", "body", "declared", "fe", "truncated"])
async def test_invalid_frames_invalidate_pending_session(rig, kind):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    frame = bytearray(transport.frame(2, bytes(13)))
    if kind == "header":
        frame[7] ^= 1
    elif kind == "body":
        frame[-1] ^= 1
    elif kind == "declared":
        frame[6] += 1
        frame[7] = P.crc8(frame[:7])
    elif kind == "fe":
        frame = transport.frame(2, b"", plaintext=bytes.fromhex("0150fe0218051e"))
    else:
        frame = frame[:-1]
    transport.notify_callback(None, bytearray(frame))
    with pytest.raises(MalformedResponseError):
        await task
    assert not rig.client.connected and rig.client._waiter is None


async def test_transport_notification_ignored_while_waiting(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    transport.notify(2, b"", plaintext=bytes.fromhex("015002001e001c"))
    assert not task.done() and rig.client.connected
    transport.notify(2, bytes(13))
    await task
    await rig.client.disconnect()


async def test_unknown_opcode_is_explicit_unsupported_error(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    transport.notify(0xEE, b"\x00")
    with pytest.raises(UnsupportedResponseError):
        await task
    assert not rig.client.connected


@pytest.mark.parametrize(
    ("name", "opcode", "args"),
    [
        ("r2r_times", 0x22, bytes(14)),
        ("sleepy_times", 0x23, b"\xff" * 14),
        ("r2r_alarms", 0x27, bytes.fromhex("99999990")),
        ("routine_task_status", 0x94, bytes(7)),
    ],
)
async def test_named_requests_preserve_raw_payloads(rig, name, opcode, args):
    transport = await connect(rig)

    async def reply(_payload):
        transport.notify(opcode, args)

    transport.on_write = reply
    envelope = await rig.client.request_named(name)
    assert envelope.opcode == opcode and envelope.args == args
    if name in ("music_playlist", "clock_settings"):
        with pytest.raises(UnsupportedResponseError):
            envelope.decode()  # No invented layout; raw evidence remains available.
    else:
        assert envelope.decode() is not None
    await rig.client.disconnect()


@pytest.mark.parametrize("vector", READ_REQUESTS, ids=lambda v: v["name"])
async def test_every_named_request_sends_exact_query_and_matches_response(rig, vector):
    transport = await connect(rig)
    opcode = int(vector["response"], 16)
    # Known structured replies must pass strict decoding; all others remain raw.
    sizes = {
        0x02: 13,
        0x13: 4,
        0x19: 12,
        0x22: 14,
        0x23: 14,
        0x27: 4,
        0x94: 7,
        0x99: 2,
    }
    args = {
        0x19: bytes(range(1, 13)),
        0x99: bytes.fromhex("0121"),
    }.get(opcode, bytes(sizes[opcode]) if opcode in sizes else b"\x12\x34\xff")

    async def reply(frame):
        key, nonce, salt = transport.keys
        # Reverse RX's salt/nonce order when inspecting the outgoing TX frame.
        decoded = P.decrypt_rx_frame(frame, key, salt, nonce)
        assert decoded["crc_ok"]
        assert decoded["plaintext"] == P.encode_command(
            bytes.fromhex(vector["request"])
        )
        transport.notify(opcode, args)

    transport.on_write = reply
    envelope = await rig.client.request_named(vector["name"])
    assert envelope.opcode == opcode and envelope.args == args
    if opcode == 0x19:
        assert envelope.decode().slots == tuple(range(1, 13))
    elif opcode == 0x99:
        assert envelope.decode().brightness == 2
    assert envelope.generation == rig.client.generation
    writes = len(transport.writes)
    with pytest.raises(FreshSessionRequiredError):
        await rig.client.request_named(vector["name"])
    assert len(transport.writes) == writes
    await rig.client.disconnect()


@pytest.mark.parametrize(
    "args",
    [
        b"",
        bytes(3),
        bytes(5),
        b"\x24\x00\x00\x00",
        b"\x00\x60\x00\x00",
        b"\x00\x00\x60\x00",
        b"\x00\x00\x00\x07",
        b"\x1a\x00\x00\x00",
        b"\xff" * 4,
    ],
)
async def test_malformed_current_date_retires_session(rig, args):
    transport = await connect(rig)
    task = await waiting_request(
        rig, transport, opcode=0x13, payload=C.request("current_date")
    )
    transport.notify(0x13, args)
    with pytest.raises(MalformedResponseError):
        await task
    assert not rig.client.connected
    assert not rig.envelopes
    assert rig.client.state is None


async def test_current_date_unsolicited_transition_is_transient_observation(rig):
    transport = await connect(rig)
    transport.notify(0x13, bytes.fromhex("23590003"))
    transport.notify(0x13, bytes.fromhex("00000004"))
    assert [response.decode().weekday for response in rig.envelopes] == [3, 4]
    assert [response.decode().hour for response in rig.envelopes] == [23, 0]
    assert rig.client.state is None  # Clock readings do not replace GLOBAL_STATE.
    assert not rig.states
    writes = len(transport.writes)
    with pytest.raises(FreshSessionRequiredError):
        await rig.client.request_named("current_date")
    assert len(transport.writes) == writes
    await rig.client.disconnect()


@pytest.mark.parametrize(("day", "opcode"), [("friday", 0x90), ("saturday", 0x91)])
async def test_daily_routine_request_exact_response_ids(rig, day, opcode):
    transport = await connect(rig)

    async def reply(_payload):
        transport.notify(opcode, bytes(14))

    transport.on_write = reply
    envelope = await rig.client.request_day_routine(day)
    assert envelope.opcode == opcode
    assert envelope.decode().time.hour == 0
    await rig.client.disconnect()


async def test_requests_are_serialized_and_second_type_cannot_steal_first(rig):
    transport = await connect(rig)
    first = await waiting_request(rig, transport)
    second = asyncio.create_task(rig.client.request_named("r2r_times"))
    await asyncio.sleep(0)
    assert len(transport.writes) == 3
    transport.notify(2, bytes(13))
    await first
    # Wait until the serialized second query has reached the transport.
    while len(transport.writes) < 4:
        await asyncio.sleep(0)
    transport.notify(2, bytes(13))  # Unsolicited duplicate of the first type.
    assert not second.done()
    transport.notify(0x22, bytes(14))
    assert (await second).opcode == 0x22
    await rig.client.disconnect()


@pytest.mark.parametrize(
    "stage", ["connect", "read_gatt_char", "start_notify", "write_gatt_char"]
)
async def test_failed_handshake_always_closes_transport(rig, monkeypatch, stage):
    async def fail(*_args, **_kwargs):
        raise OSError("synthetic transport failure")

    monkeypatch.setattr(rig.factory, stage, fail)
    with pytest.raises(OSError):
        await rig.client.connect()
    assert rig.transports[0].disconnect_count == 1
    assert rig.client._client is None and not rig.client.connected
    assert rig.client._key is None and not rig.client._cleanup_tasks


async def test_cancel_connect_closes_partially_open_transport(rig, monkeypatch):
    started = asyncio.Event()

    async def hanging_connect(self):
        self.is_connected = True
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(rig.factory, "connect", hanging_connect)
    task = asyncio.create_task(rig.client.connect())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rig.transports[0].disconnect_count == 1 and not rig.client.connected
    assert not rig.client._cleanup_tasks


async def test_explicit_disconnect_interrupts_request(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    await rig.client.disconnect()
    with pytest.raises(DisconnectedError):
        await task
    assert rig.client._waiter is None


async def test_failed_send_invalidates_without_retry(rig):
    transport = await connect(rig)

    async def fail(_payload):
        raise OSError("ambiguous write")

    transport.on_write = fail
    with pytest.raises(OSError):
        await rig.client.send(C.play_audio(1))
    assert not rig.client.connected and transport.disconnect_count == 1
    assert len(transport.writes) == 3


async def test_repeated_cancel_waits_for_disconnect_and_preserves_cancellation(rig):
    transport = await connect(rig)
    original_disconnect = transport.disconnect
    closing, release = asyncio.Event(), asyncio.Event()

    async def delayed_disconnect():
        closing.set()
        await release.wait()
        await original_disconnect()

    transport.disconnect = delayed_disconnect
    task = await waiting_request(rig, transport)
    task.cancel()
    await closing.wait()
    for _ in range(3):
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.disconnect_count == 1 and not rig.client._cleanup_tasks


async def test_cancel_connect_not_masked_by_failed_cleanup(rig, monkeypatch):
    started = asyncio.Event()

    async def hanging_connect(self):
        started.set()
        await asyncio.Event().wait()

    async def failed_disconnect(self):
        self.disconnect_count += 1
        raise OSError("cleanup failure")

    monkeypatch.setattr(rig.factory, "connect", hanging_connect)
    monkeypatch.setattr(rig.factory, "disconnect", failed_disconnect)
    task = asyncio.create_task(rig.client.connect())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not rig.client.connected and not rig.client._cleanup_tasks


async def test_failed_write_consumes_waiter_exception(rig):
    transport = await connect(rig)
    loop = asyncio.get_running_loop()
    errors = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: errors.append(context))

    async def fail(_payload):
        raise OSError("synthetic write failure")

    transport.on_write = fail
    try:
        with pytest.raises(OSError):
            await rig.client.request_state()
        await asyncio.sleep(0)
        assert rig.client._waiter is None and not errors
    finally:
        loop.set_exception_handler(previous_handler)


async def test_repeated_cancel_during_explicit_disconnect(rig):
    transport = await connect(rig)
    closing, release = asyncio.Event(), asyncio.Event()

    async def delayed_disconnect():
        closing.set()
        await release.wait()

    transport.disconnect = delayed_disconnect
    task = asyncio.create_task(rig.client.disconnect())
    await closing.wait()
    for _ in range(3):
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not rig.client._cleanup_tasks


async def test_connect_timeout_closes_transport(rig, monkeypatch):
    async def hang(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(rig.factory, "connect", hang)
    with pytest.raises(asyncio.TimeoutError):
        await rig.client.connect(timeout=0.001)
    assert rig.transports[0].disconnect_count == 1 and not rig.client.connected


async def test_malformed_factory_token_never_reaches_session_write(rig, monkeypatch):
    async def short_token(self, _characteristic):
        return bytes(61)

    monkeypatch.setattr(rig.factory, "read_gatt_char", short_token)
    with pytest.raises(FactoryIdentityError):
        await rig.client.connect()
    assert not rig.transports[0].writes and rig.transports[0].disconnect_count == 1


async def test_no_session_and_unsupported_request_fail_before_io(rig):
    with pytest.raises(DisconnectedError):
        await rig.client.request_state()
    with pytest.raises(DisconnectedError):
        await rig.client.send(C.set_volume(1))
    with pytest.raises(UnsupportedResponseError):
        await rig.client.request(b"\x53", 0xEE)
    with pytest.raises(UnsupportedResponseError):
        await rig.client.request_named("unknown")
    assert not rig.transports


async def test_callback_failure_isolated_from_matching_response(rig):
    transport = await connect(rig)
    rig.client._on_response = Mock(side_effect=ValueError("consumer failure"))
    task = await waiting_request(rig, transport)
    transport.notify(2, bytes(13))
    assert (await task).opcode == 2
    await rig.client.disconnect()


async def test_callback_invalidation_cannot_publish_response_to_waiter(rig):
    transport = await connect(rig)
    rig.client._on_state = lambda _state: transport.lose_connection()
    task = await waiting_request(rig, transport)
    transport.notify(2, bytes(13))
    with pytest.raises(DisconnectedError):
        await task
    assert not rig.envelopes and not rig.client.connected


async def test_explicit_disconnect_reports_cleanup_failure(rig):
    transport = await connect(rig)

    async def fail():
        raise OSError("cannot disconnect")

    transport.disconnect = fail
    with pytest.raises(DisconnectedError, match="cleanup failed"):
        await rig.client.disconnect()
    assert not rig.client.connected and not rig.client._cleanup_tasks


async def test_bounded_rx_history_requires_fresh_session(rig):
    transport = await connect(rig)
    rig.client._seen_sequences = set(range(4096))
    task = await waiting_request(rig, transport)
    transport.notify(2, bytes(13), sequence=4096)
    with pytest.raises(FreshSessionRequiredError):
        await task
    assert not rig.client.connected


async def test_tx_sequence_never_wraps_or_reuses_ctr_nonce(rig):
    transport = await connect(rig)
    rig.client._seq = 0x100000000
    with pytest.raises(FreshSessionRequiredError):
        await rig.client.send(C.set_volume(1))
    assert len(transport.writes) == 2 and not rig.client.connected


async def test_malformed_typed_weekly_payload_retires_session(rig):
    transport = await connect(rig)
    task = await waiting_request(
        rig, transport, opcode=0x22, payload=C.request("r2r_times")
    )
    transport.notify(0x22, b"\xff\x00" + bytes(12))
    with pytest.raises(MalformedResponseError):
        await task
    assert not rig.client.connected


@pytest.mark.parametrize("prefix", [b"", b"\x01\x10", b"\x01\xff", b"\x02\x50"])
async def test_invalid_route_never_completes_request_or_publishes_state(rig, prefix):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    plaintext = prefix + P.compose_request(b"\x02" + bytes(13))
    transport.notify(2, bytes(13), plaintext=plaintext)
    with pytest.raises(MalformedResponseError):
        await task
    assert not rig.states and not rig.envelopes and not rig.client.connected


@pytest.mark.parametrize(
    ("opcode", "args", "name"),
    [
        (0x02, bytes(13), "global_state"),
        (0x22, bytes(14), "r2r_times"),
        (0x99, b"\x00\x00", "clock_settings"),
    ],
)
async def test_unsolicited_opcode_blocks_request_before_any_write(
    rig, opcode, args, name
):
    transport = await connect(rig)
    transport.notify(opcode, args, sequence=10)
    writes = len(transport.writes)

    async def delayed_duplicate(_payload):
        # Same opcode and contents, but a new sequence: not an RX replay ID.
        transport.notify(opcode, args, sequence=11)

    transport.on_write = delayed_duplicate
    try:
        with pytest.raises(FreshSessionRequiredError):
            await rig.client.request_named(name)
        assert len(transport.writes) == writes
        assert rig.client._waiter is None
    finally:
        await rig.client.disconnect()


async def test_unsolicited_opcode_guard_resets_only_after_clean_reconnect(rig):
    old = await connect(rig)
    old.notify(2, bytes(13))
    try:
        with pytest.raises(FreshSessionRequiredError):
            await rig.client.request_state(timeout=0.001)
    finally:
        await rig.client.disconnect()
    replacement = await connect(rig)
    task = await waiting_request(rig, replacement)
    old.notify(2, bytes(13), sequence=20)
    assert not task.done()
    replacement.notify(2, bytes(13))
    assert (await task).generation == rig.client.generation
    await rig.client.disconnect()


async def test_wrong_opcode_observed_during_other_request_cannot_be_queried_later(rig):
    transport = await connect(rig)
    task = await waiting_request(rig, transport)
    transport.notify(0x22, bytes(14))
    transport.notify(2, bytes(13))
    await task
    writes = len(transport.writes)
    try:
        with pytest.raises(FreshSessionRequiredError):
            await rig.client.request_named("r2r_times", timeout=0.001)
        assert len(transport.writes) == writes
    finally:
        await rig.client.disconnect()


async def test_unsolicited_between_request_guard_and_exchange_cannot_satisfy_it(
    rig, monkeypatch
):
    transport = await connect(rig)
    original_wait_for = asyncio.wait_for
    injected = False

    async def inject_before_exchange(awaitable, timeout):
        nonlocal injected
        if (
            getattr(getattr(awaitable, "cr_code", None), "co_name", None) == "exchange"
            and not injected
        ):
            injected = True
            transport.notify(2, bytes(13))
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(module.asyncio, "wait_for", inject_before_exchange)
    writes = len(transport.writes)
    try:
        with pytest.raises(FreshSessionRequiredError):
            await rig.client.request_state()
        assert injected and len(transport.writes) == writes
        assert rig.client._waiter is None
    finally:
        await rig.client.disconnect()


async def test_unsolicited_during_handshake_also_consumes_opcode_eligibility(
    rig, monkeypatch
):
    original_write = rig.factory.write_gatt_char

    async def notify_during_enable_rx(self, characteristic, payload, *, response):
        await original_write(self, characteristic, payload, response=response)
        if characteristic == module.TX:
            self.notify(2, bytes(13))

    monkeypatch.setattr(rig.factory, "write_gatt_char", notify_during_enable_rx)
    transport = await connect(rig)
    try:
        assert rig.client.state is not None and rig.client.connected
        with pytest.raises(FreshSessionRequiredError):
            await rig.client.request_state()
        assert len(transport.writes) == 2  # Handshake and ENABLE_RX only.
    finally:
        await rig.client.disconnect()
