"""Async BLE client (bleak): scan, handshake, send commands, read state."""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import commands as C
from . import crypto
from . import protocol as P
from . import responses as R
from ._generated import GATT, RESPONSES
from .factory import (
    InvalidFactoryTokenError,
    parse_factory_device_fingerprint,
)
from .schedules import DAY_ROUTINE_RESPONSES

SERVICE = GATT["service"]
TX = GATT["characteristics"]["tx"]
RX = GATT["characteristics"]["rx"]
FACTORY = GATT["characteristics"]["factory"]
SESSION = GATT["characteristics"]["session"]

WRITE_SPACING = 0.15  # seconds between writes (the device is sensitive to bursts)
DISCONNECT_TIMEOUT = 5.0
_LOGGER = logging.getLogger(__name__)


class LumalouError(Exception):
    """Base for explicit client failures (never a cached successful response)."""


class DisconnectedError(LumalouError):
    """The current session is no longer usable."""


class RequestTimeoutError(LumalouError, TimeoutError):
    """No matching response arrived before the deadline; session invalidated."""


class MalformedResponseError(LumalouError, ValueError):
    """A frame or a known typed payload failed validation."""


class FactoryIdentityError(LumalouError):
    """The device manufacturing identity could not be authenticated."""


class FactoryIdentityMismatchError(FactoryIdentityError):
    """The authenticated device does not match the caller's expected item."""


class UnsupportedResponseError(LumalouError, ValueError):
    """The opcode or typed payload layout is not supported."""


class FreshSessionRequiredError(LumalouError):
    """The same response type cannot safely be requested twice in one session."""


@dataclass(frozen=True)
class ResponseEnvelope:
    """A validated frame observed in one session, not proof of write causality."""

    opcode: int
    args: bytes
    generation: int
    received_at: float
    sequence: int

    def decode(self):
        """Decode only established layouts; raw unknown layouts stay explicit."""
        try:
            if self.opcode == 0x02:
                return R.parse_global_state(self.args)
            if self.opcode == 0x13:
                return R.parse_current_date(self.args)
            if self.opcode == 0x19:
                return R.parse_music_playlist(self.args)
            if self.opcode == 0x99:
                return R.parse_clock_settings(self.args)
            return R.parse_schedule_response(self.opcode, self.args)
        except ValueError as err:
            if self.opcode in _TYPED_RESPONSES:
                raise MalformedResponseError(str(err)) from err
            raise UnsupportedResponseError(
                "no typed decoder for this response"
            ) from err


_TYPED_RESPONSES = {
    0x02,
    0x13,
    0x19,
    0x22,
    0x23,
    0x27,
    0x94,
    0x99,
    *DAY_ROUTINE_RESPONSES.values(),
}
_REQUEST_RESPONSES = {
    "global_state": 0x02,
    "current_date": 0x13,
    "toyic_fw_version": 0x12,
    "led_brightness": 0x17,
    "light_color": 0x18,
    "light_duration": 0x95,
    "volume": 0x15,
    "routine_volume": 0x98,
    "song_playing": 0x14,
    "music_playlist": 0x19,
    "playlist_duration": 0x1A,
    "operation_mode": 0x1E,
    "activity_state": 0x1F,
    "current_stage": 0x20,
    "clock_settings": 0x99,
    "transmission_mode": 0x1D,
    "routine_mode_status": 0x92,
    "routine_music_status": 0x93,
    "r2r_status": 0x21,
    "r2r_times": 0x22,
    "sleepy_times": 0x23,
    "r2r_alarm_status": 0x26,
    "r2r_alarms": 0x27,
    "routine_task_status": 0x94,
    "nap_current_status": 0x1C,
    "nap_alarm_status": 0x24,
    "nap_alarm": 0x25,
    "time_prescaler": 0x28,
}


class LumalouClient:
    """Async client. Use as an async context manager or via connect()/disconnect()."""

    def __init__(
        self,
        address: str | BLEDevice,
        *,
        on_state: Callable[[dict], None] | None = None,
        on_response: Callable[[ResponseEnvelope], None] | None = None,
        client_factory: Callable[..., BleakClient] | None = None,
        disconnected_callback: Callable[[LumalouClient], None] | None = None,
        expected_device_fingerprint: str | None = None,
    ):
        if expected_device_fingerprint is not None and (
            not isinstance(expected_device_fingerprint, str)
            or len(expected_device_fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in expected_device_fingerprint)
        ):
            raise ValueError(
                "expected device fingerprint must be 64 lowercase hex characters"
            )
        self._expected_device_fingerprint = expected_device_fingerprint
        self._device_fingerprint: str | None = None
        self.address = address
        self.connected = False
        self._on_state = on_state
        self._on_response = on_response
        self._client_factory = client_factory
        self._disconnected_callback = disconnected_callback
        self._client: BleakClient | None = None
        self._key = self._nonce = self._salt = None
        self._seq = 1
        self._lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._state: dict | None = None
        self._generation = 0
        self._session_active = False
        self._waiter: asyncio.Future | None = None
        self._expected_opcode: int | None = None
        self._requested_opcodes: set[int] = set()
        self._observed_opcodes: set[int] = set()
        self._seen_sequences: set[int] = set()
        self._cleanup_tasks: set[asyncio.Task] = set()
        self.last_error: LumalouError | None = None

    @staticmethod
    async def scan(timeout: float = 8.0) -> list[dict]:
        """Scan for BLE devices. The Lumalou advertises its AP number as its name."""
        found = await BleakScanner.discover(timeout=timeout, return_adv=True)
        out = [
            {
                "address": addr,
                "name": adv.local_name or dev.name,
                "rssi": adv.rssi,
                "manufacturer": {
                    str(k): v.hex() for k, v in adv.manufacturer_data.items()
                },
            }
            for addr, (dev, adv) in found.items()
        ]
        out.sort(key=lambda r: -(r["rssi"] or -999))
        return out

    @property
    def device_fingerprint(self) -> str | None:
        """Authenticated device-key fingerprint for the current session only."""
        return self._device_fingerprint if self.connected else None

    @property
    def generation(self) -> int:
        return self._generation

    @staticmethod
    def _callback(function, argument) -> None:
        if function is not None:
            try:
                function(argument)
            except Exception:
                _LOGGER.exception("Lumalou callback failed")

    async def _cleanup_transport(self, client) -> None:
        await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)

    def _invalidate(self, error: LumalouError) -> None:
        """Invalidate synchronously before scheduling any transport cleanup."""
        active = self._session_active
        self._session_active = False
        self.connected = False
        self.last_error = error
        self._device_fingerprint = None
        self._generation += 1
        self._state = None
        self._key = self._nonce = self._salt = None
        self._seq = 1
        self._requested_opcodes.clear()
        self._observed_opcodes.clear()
        self._seen_sequences.clear()
        waiter, self._waiter = self._waiter, None
        self._expected_opcode = None
        if waiter is not None and not waiter.done():
            waiter.set_exception(error)
        client, self._client = self._client, None
        if client is not None:
            task = asyncio.create_task(self._cleanup_transport(client))
            # Retrieve errors even if invalidation came from an unsolicited frame.
            task.add_done_callback(
                lambda completed: (
                    completed.exception() if not completed.cancelled() else None
                )
            )
            self._cleanup_tasks.add(task)
        if active:
            self._callback(self._disconnected_callback, self)

    async def _drain_cleanup(self) -> None:
        """Cancellation never abandons an already-started disconnect."""
        tasks = tuple(self._cleanup_tasks)
        if not tasks:
            return
        pending = asyncio.gather(*tasks, return_exceptions=True)
        cancelled = False
        try:
            while not pending.done():
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError:
                    cancelled = True
            results = pending.result()
        finally:
            self._cleanup_tasks.difference_update(task for task in tasks if task.done())
        if cancelled:
            raise asyncio.CancelledError
        if any(isinstance(result, BaseException) for result in results):
            raise DisconnectedError("BLE disconnect cleanup failed")

    async def _abort(self, error: LumalouError) -> None:
        self._invalidate(error)
        try:
            await self._drain_cleanup()
        except DisconnectedError:
            _LOGGER.warning("BLE cleanup failed after a session error")

    def _transport_disconnected(self, generation: int) -> None:
        if generation == self._generation and self._session_active:
            self._invalidate(DisconnectedError("BLE connection was lost"))

    def _require_session(self, generation: int, *, handshaking: bool = False) -> None:
        if (
            generation != self._generation
            or self._client is None
            or not self._session_active
            or (not handshaking and not self.connected)
        ):
            if generation != self._generation and self.last_error is not None:
                raise self.last_error
            raise DisconnectedError("no active Lumalou session")

    async def connect(self, timeout: float = 20.0):
        """Create a new transport/session; BLEDevice never triggers a scan.

        The factory receives (address_or_device, disconnected_callback=...).
        HA can supply its own connection adapter here without global patches.
        """
        async with self._lock, self._lifecycle_lock:
            await self.disconnect()
            self.last_error = None
            generation = self._generation
            self._session_active = True
            try:
                self._client = (self._client_factory or BleakClient)(
                    self.address,
                    disconnected_callback=lambda _client: self._transport_disconnected(
                        generation
                    ),
                )
                await asyncio.wait_for(self._handshake(generation), timeout)
                self._require_session(generation, handshaking=True)
                self.connected = True
            except BaseException as error:
                failure = (
                    error
                    if isinstance(error, LumalouError)
                    else DisconnectedError("BLE connection or handshake failed")
                )
                await self._abort(failure)
                raise
        return self

    async def _handshake(self, generation: int) -> None:
        client = self._client
        await client.connect()
        self._require_session(generation, handshaking=True)
        token = bytes(await client.read_gatt_char(FACTORY))
        self._require_session(generation, handshaking=True)
        try:
            fingerprint = parse_factory_device_fingerprint(token)
        except InvalidFactoryTokenError as error:
            raise FactoryIdentityError(
                "device factory identity could not be authenticated"
            ) from error
        if (
            self._expected_device_fingerprint is not None
            and fingerprint != self._expected_device_fingerprint
        ):
            raise FactoryIdentityMismatchError(
                "device factory identity does not match the expected device"
            )
        self._device_fingerprint = fingerprint
        device_pub = crypto.token_device_pubkey(token)
        self._salt = crypto.token_device_salt(token)
        priv, pub = crypto.generate_keypair()
        self._nonce = crypto.new_nonce()
        self._key = crypto.derive_session_key(priv, device_pub)[:16]
        await client.start_notify(
            RX, lambda sender, data: self._on_rx(generation, sender, data)
        )
        self._require_session(generation, handshaking=True)
        await client.write_gatt_char(SESSION, pub + self._nonce, response=True)
        await asyncio.sleep(0.4)
        self._require_session(generation, handshaking=True)
        await self._write(C.ENABLE_RX, generation, handshaking=True)
        await asyncio.sleep(0.3)

    async def disconnect(self):
        self._invalidate(DisconnectedError("Lumalou disconnected"))
        await self._drain_cleanup()

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *exc):
        await self.disconnect()

    async def _write(
        self, plaintext: bytes, generation: int, *, handshaking: bool = False
    ):
        self._require_session(generation, handshaking=handshaking)
        if self._seq > 0xFFFFFFFF:
            raise FreshSessionRequiredError("transmit sequence exhausted")
        frame = P.build_tx_frame(
            plaintext, self._seq, self._key, self._nonce, self._salt
        )
        self._seq += 1
        await self._client.write_gatt_char(TX, frame, response=False)
        await asyncio.sleep(WRITE_SPACING)
        self._require_session(generation, handshaking=handshaking)

    async def send(self, app_data: bytes, timeout: float = 10.0):
        """Send a raw application command ([opcode] + args)."""
        plaintext = P.encode_command(app_data)
        async with self._lock:
            try:
                await asyncio.wait_for(
                    self._write(plaintext, self._generation), timeout
                )
            except BaseException as error:
                failure = (
                    error
                    if isinstance(error, LumalouError)
                    else DisconnectedError(
                        "command failed; never automatically replayed"
                    )
                )
                await self._abort(failure)
                raise

    def _on_rx(self, generation: int, _sender, data: bytearray):
        if (
            generation != self._generation
            or not self._session_active
            or self._key is None
        ):
            return
        try:
            res = P.decrypt_rx_frame(bytes(data), self._key, self._nonce, self._salt)
            if not res or not res["crc_ok"]:
                raise MalformedResponseError("invalid MPID length or CRC")
            sequence = res["seq"]
            if sequence in self._seen_sequences:
                return
            if len(self._seen_sequences) >= 4096:
                raise FreshSessionRequiredError(
                    "receive sequence history limit reached"
                )
            self._seen_sequences.add(sequence)
            response = P.parse_response_frame(res["plaintext"])
            if not response["ok"]:
                if response["error"] == "unsupported_transport":
                    return
                raise MalformedResponseError(
                    "unsupported SSI route or invalid FE length/checksum"
                )
            if response["opcode"] not in RESPONSES:
                raise UnsupportedResponseError("unknown application response opcode")
            envelope = ResponseEnvelope(
                response["opcode"],
                response["args"],
                generation,
                time.monotonic(),
                sequence,
            )
            decoded = envelope.decode() if envelope.opcode in _TYPED_RESPONSES else None
        except LumalouError as error:
            self._invalidate(error)
            return
        except (TypeError, ValueError) as error:
            self._invalidate(MalformedResponseError(str(error)))
            return
        # Record all validated observations, not only requested responses.
        # A later same-type notification with a new RX sequence could be its
        # delayed duplicate. Retain this before invoking external callbacks.
        self._observed_opcodes.add(envelope.opcode)
        if envelope.opcode == 0x02:
            self._state = decoded
            self._callback(self._on_state, deepcopy(decoded))
        if generation != self._generation:
            return
        self._callback(self._on_response, envelope)
        # A callback can disconnect the client, so recheck generation afterwards.
        if (
            generation == self._generation
            and self._waiter is not None
            and not self._waiter.done()
            and envelope.opcode == self._expected_opcode
        ):
            self._waiter.set_result(envelope)

    async def request(
        self, app_data: bytes, expected_opcode: int, timeout: float = 3.0
    ) -> ResponseEnvelope:
        """Read an exact response type once per session, with no cache fallback.

        RX sequence is only a duplicate detector, not a request correlation ID.
        Any previously requested OR observed opcode requires a clean reconnect:
        a delayed duplicate with a new RX sequence is indistinguishable, even
        if the first observation was unsolicited or answered another request.
        """
        plaintext = P.encode_command(app_data)
        if type(expected_opcode) is not int or expected_opcode not in RESPONSES:
            raise UnsupportedResponseError("unsupported expected response opcode")
        async with self._lock:
            generation = self._generation
            self._require_session(generation)
            if (
                expected_opcode in self._requested_opcodes
                or expected_opcode in self._observed_opcodes
            ):
                raise FreshSessionRequiredError(
                    "reconnect before requesting a previously requested or observed response type"
                )
            self._requested_opcodes.add(expected_opcode)
            future = asyncio.get_running_loop().create_future()

            async def exchange():
                # wait_for schedules this coroutine. Unsolicited data can arrive
                # after the outer guard but before exchange starts. Never make
                # its future eligible for those pre-write notifications.
                self._require_session(generation)
                if expected_opcode in self._observed_opcodes:
                    raise FreshSessionRequiredError(
                        "response type observed before query write; reconnect required"
                    )
                self._waiter, self._expected_opcode = future, expected_opcode
                await self._write(plaintext, generation)
                return await future

            try:
                envelope = await asyncio.wait_for(exchange(), timeout)
                self._require_session(generation)
                return envelope
            except asyncio.TimeoutError as error:
                failure = RequestTimeoutError(
                    "Lumalou response timed out; reconnect required"
                )
                await self._abort(failure)
                raise failure from error
            except BaseException as error:
                failure = (
                    error
                    if isinstance(error, LumalouError)
                    else DisconnectedError("request interrupted")
                )
                await self._abort(failure)
                raise
            finally:
                if self._waiter is future:
                    self._waiter = None
                    self._expected_opcode = None
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()  # A failed write can leave an unawaited waiter.

    async def request_named(self, name: str, timeout: float = 3.0) -> ResponseEnvelope:
        if name not in _REQUEST_RESPONSES:
            raise UnsupportedResponseError("unsupported named request")
        return await self.request(C.request(name), _REQUEST_RESPONSES[name], timeout)

    async def request_day_routine(
        self, day: str, timeout: float = 3.0
    ) -> ResponseEnvelope:
        payload = C.request_day_routine(day)
        return await self.request(payload, DAY_ROUTINE_RESPONSES[day], timeout)

    async def request_state(self, timeout: float = 3.0) -> dict:
        return (await self.request_named("global_state", timeout)).decode()

    @property
    def state(self) -> dict | None:
        """Last observation in the live session; never used as a request result."""
        return deepcopy(self._state)

    # ---- high-level API ----
    async def light_color(self, color: int):
        await self.send(C.set_light_color(int(color)))

    async def brightness(self, level: int):
        await self.send(C.set_led_brightness(level))

    async def light_off(self):
        await self.send(C.turn_off_backlight())

    async def light_duration(self, duration: int):
        await self.send(C.set_light_duration(int(duration)))

    async def volume(self, level: int):
        await self.send(C.set_volume(level))

    async def play(self, source: int):
        await self.send(C.play_audio(int(source)))

    async def audio_off(self):
        await self.send(C.turn_off_audio())

    async def playlist(self, song_ids):
        await self.send(C.set_music_playlist(song_ids))

    async def nap(self, duration: int):
        await self.send(C.start_nap(int(duration)))

    async def soother(self, on: bool = True):
        await self.send(C.set_global_on(on))

    async def sync_time(self, when: datetime.datetime | None = None):
        d = when or datetime.datetime.now().astimezone()
        weekday = (d.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> device Sun=0..Sat=6
        await self.send(C.set_current_date(d.hour, d.minute, d.second, weekday))
