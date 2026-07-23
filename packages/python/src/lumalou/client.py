"""Async BLE client (bleak): scan, handshake, send commands, read state."""
from __future__ import annotations

import asyncio
import datetime
from typing import Callable, Optional

from bleak import BleakClient, BleakScanner

from . import commands as C
from . import crypto
from . import protocol as P
from . import responses as R
from ._generated import GATT

SERVICE = GATT["service"]
TX = GATT["characteristics"]["tx"]
RX = GATT["characteristics"]["rx"]
FACTORY = GATT["characteristics"]["factory"]
SESSION = GATT["characteristics"]["session"]

WRITE_SPACING = 0.15  # seconds between writes (the device is sensitive to bursts)


class LumalouClient:
    """Async client. Use as an async context manager or via connect()/disconnect()."""

    def __init__(self, address: str, *, on_state: Optional[Callable[[dict], None]] = None):
        self.address = address
        self.connected = False
        self._on_state = on_state
        self._client: Optional[BleakClient] = None
        self._key = self._nonce = self._salt = None
        self._seq = 1
        self._lock = asyncio.Lock()
        self._state: Optional[dict] = None
        self._state_waiters: list[asyncio.Future] = []

    @staticmethod
    async def scan(timeout: float = 8.0) -> list[dict]:
        """Scan for BLE devices. The Lumalou advertises its AP number as its name."""
        found = await BleakScanner.discover(timeout=timeout, return_adv=True)
        out = [{
            "address": addr,
            "name": adv.local_name or dev.name,
            "rssi": adv.rssi,
            "manufacturer": {str(k): v.hex() for k, v in adv.manufacturer_data.items()},
        } for addr, (dev, adv) in found.items()]
        out.sort(key=lambda r: -(r["rssi"] or -999))
        return out

    async def connect(self):
        self._client = BleakClient(self.address)
        await self._client.connect()
        await self._client.start_notify(RX, self._on_rx)
        token = bytes(await self._client.read_gatt_char(FACTORY))
        device_pub = crypto.token_device_pubkey(token)
        self._salt = crypto.token_device_salt(token)
        priv, pub = crypto.generate_keypair()
        self._nonce = crypto.new_nonce()
        self._key = crypto.derive_session_key(priv, device_pub)[:16]
        await self._client.write_gatt_char(SESSION, pub + self._nonce, response=True)  # 37B
        await asyncio.sleep(0.4)
        await self._write(C.ENABLE_RX)  # let the toy-IC stream responses
        await asyncio.sleep(0.3)
        self.connected = True
        return self

    async def disconnect(self):
        self.connected = False
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *exc):
        await self.disconnect()

    async def _write(self, plaintext: bytes):
        async with self._lock:
            frame = P.build_tx_frame(plaintext, self._seq, self._key, self._nonce, self._salt)
            self._seq += 1
            await self._client.write_gatt_char(TX, frame, response=False)
            await asyncio.sleep(WRITE_SPACING)

    async def send(self, app_data: bytes):
        """Send a raw application command ([opcode] + args)."""
        await self._write(P.encode_command(app_data))

    def _on_rx(self, _sender, data: bytearray):
        res = P.decrypt_rx_frame(bytes(data), self._key, self._nonce, self._salt)
        if not res or not res["crc_ok"]:
            return
        r = P.parse_response_frame(res["plaintext"])
        if r.get("ok") and r.get("opcode") == 0x02:
            st = R.parse_global_state(r["args"])
            self._state = st
            for fut in self._state_waiters:
                if not fut.done():
                    fut.set_result(st)
            self._state_waiters.clear()
            if self._on_state:
                self._on_state(st)

    async def request_state(self, timeout: float = 3.0) -> Optional[dict]:
        """Query the full GLOBAL_STATE and return it decoded."""
        fut = asyncio.get_event_loop().create_future()
        self._state_waiters.append(fut)
        await self.send(C.request("global_state"))
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            return self._state

    @property
    def state(self) -> Optional[dict]:
        return self._state

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

    async def sync_time(self, when: Optional[datetime.datetime] = None):
        d = when or datetime.datetime.now()
        weekday = (d.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> device Sun=0..Sat=6
        await self.send(C.set_current_date(d.hour, d.minute, d.second, weekday))
