"""Decode passive Lumalou manufacturer advertisements."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MANUFACTURER_ID = 0x03B6
MANUFACTURER_PREFIX = b"MB"
MAX_FIRMWARE_LENGTH = 32

ConnectionState = Literal["idle", "pairing", "connected", "unknown"]

_FIRMWARE_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,31}")


@dataclass(frozen=True, slots=True)
class LumalouAdvertisement:
    """Validated fields from one passive manufacturer payload."""

    format_version: int
    connection_state: ConnectionState
    firmware_version: str | None


def is_lumalou_advertisement(payload: object) -> bool:
    """Return whether a manufacturer payload carries the Lumalou prefix."""
    return isinstance(payload, bytes) and payload.startswith(MANUFACTURER_PREFIX)


def parse_advertisement(payload: bytes) -> LumalouAdvertisement:
    """Strictly decode ``MB | format | flags | firmware ASCII``.

    The Bluetooth company identifier is not part of ``payload``. Firmware may
    be absent and may have trailing NUL padding. The 32-byte limit
    and character allowlist are defensive API policy, not device capabilities.
    The format byte is preserved as opaque metadata because its version
    semantics are not yet documented by a published capture.
    """
    if not isinstance(payload, bytes):
        raise TypeError("advertisement payload must be bytes")
    if not payload.startswith(MANUFACTURER_PREFIX):
        raise ValueError("advertisement payload does not have the Lumalou prefix")
    if len(payload) < 4:
        raise ValueError("Lumalou advertisement must contain format and flags")

    format_version = payload[2]
    flags = payload[3]
    if flags & 0x80:
        connection_state: ConnectionState = "connected"
    elif flags & 0x40:
        connection_state = "pairing"
    elif flags == 0:
        connection_state = "idle"
    else:
        connection_state = "unknown"

    firmware_bytes = payload[4:]
    if len(firmware_bytes) > MAX_FIRMWARE_LENGTH:
        raise ValueError("firmware field is too long")

    firmware_version = None
    if firmware_bytes:
        unpadded = firmware_bytes.rstrip(b"\x00")
        if b"\x00" in unpadded:
            raise ValueError("firmware field contains embedded NUL")
        if unpadded:
            try:
                candidate = unpadded.decode("ascii")
            except UnicodeDecodeError as err:
                raise ValueError("firmware field must be ASCII") from err
            if _FIRMWARE_PATTERN.fullmatch(candidate) is None:
                raise ValueError("firmware field has invalid characters")
            firmware_version = candidate

    return LumalouAdvertisement(
        format_version=format_version,
        connection_state=connection_state,
        firmware_version=firmware_version,
    )
