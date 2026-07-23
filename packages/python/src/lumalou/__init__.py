"""
lumalou — local BLE control for the Fisher-Price Lumalou (gld09).

Reverse-engineered MPID protocol: ECDH P-256 handshake + AES-128-CTR, pure Python.

    import asyncio
    from lumalou import LumalouClient, Color

    async def main():
        devices = await LumalouClient.scan()
        async with LumalouClient(devices[0]["address"]) as luma:
            await luma.light_color(Color.RAINBOW)
            print(await luma.request_state())

    asyncio.run(main())
"""
from .client import LumalouClient
from ._generated import (Color, Audio, Song, LightDuration, PlaylistDuration,
                         NapDuration, Alarm, RoutineControl, ClockFormat,
                         OperationMode, Stage)
from .protocol import build_tx_frame, decrypt_rx_frame, encode_command, crc8

__version__ = "0.1.0"

__all__ = [
    "LumalouClient",
    "Color", "Audio", "Song", "LightDuration", "PlaylistDuration", "NapDuration",
    "Alarm", "RoutineControl", "ClockFormat", "OperationMode", "Stage",
    "build_tx_frame", "decrypt_rx_frame", "encode_command", "crc8",
]
