# Lumalou MPID protocol

Reverse-engineered from the official app and validated bit-exact against the device's native
library and the physical hardware. Machine-readable form: [`spec/protocol.json`](../spec/protocol.json).
For *how* this was worked out (the process, tools, and dead ends), see [`reversing.md`](reversing.md).

## Advertising

The connectable BLE advertisement uses Bluetooth company identifier `0x03B6`
(950). Its manufacturer payload is `MB | format version | connection flags |
firmware ASCII`; the company identifier is not included in these bytes. The
format byte is currently treated as opaque. An independent GLD09 controller
maps bit 7 to connected, bit 6 to pairing and zero flags to idle; its published
live observation confirms the idle value and firmware `0.3.7`, not every flag
combination:
[`kvdb/gld09-control`](https://github.com/kvdb/gld09-control/blob/7f157405e7b047e49eeb41e80bda01dee49ce15a/lumalou_mpid.py#L377-L404).
The Python package preserves the format byte and rejects malformed firmware
fields instead of silently replacing invalid bytes. Its 32-byte firmware limit
and character allowlist are defensive parser policy, not measured device limits.

## GATT

Custom service `4cea0001-c678-4202-b5d3-712dbb5e5b14`:

| Role | UUID | Direction | Purpose |
|---|---|---|---|
| tx | `4cea0002` | app → device (write) | encrypted command frames |
| rx | `4cea0003` | device → app (notify) | encrypted state / responses |
| factory | `4cea0004` | device → app (read) | signed MFG token (session bootstrap) |
| session | `4cea0005` | app → device (write) | app public key + salt |

⛔ A second service `00001530-1212-efde-1523-785feabcd123` is the Nordic DFU (firmware update)
service. **Never write to it** — a wrong write bricks the device.

## Handshake (local, no server)

The Python `parse_factory_device_fingerprint` helper validates an exact 192-byte
FACTORY token and its manufacturing signature, validates the signed P-256 device
key, and returns SHA-256 of its compressed 33-byte encoding. It never decodes
or returns a serial suffix. The 64-character lowercase hex fingerprint remains
stable across salt/signature changes and is a private per-key identifier, not
a product-model claim or proof of live key possession.

Verification uses ECDSA P-256/SHA-256. The source for
the public verification key and field offsets is the independent MIT-licensed
[`kvdb/gld09-control` project](https://github.com/kvdb/gld09-control/tree/6e3aff894b0065b760ba44f43a36c7e9988cead9),
with attribution in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).
The final four-byte salt is outside the signed region. This helper is pure and
the client authenticates the device fingerprint on every connection. A token with an invalid signature
or malformed signed key is rejected before notification,
key derivation, or any SESSION/TX write. Callers such as Home Assistant can
pass `expected_device_fingerprint` to bind the session to one signed device key;
a mismatch aborts and releases the transport. No model code or serial suffix
is decoded or exposed by the identity API.

1. Read and authenticate the MFG token from **factory**. It contains the
   device's compressed P-256 public key at bytes `[25:58]` and a 4-byte salt
   in the last 4 bytes.
2. If the caller supplied an expected device fingerprint, require an exact
   match with the authenticated key hash.
3. Generate an ephemeral P-256 keypair. Compute
   `shared = ECDH(app_priv, device_pub)` (X coord, 32 B).
4. Derive the session key by stretching: 100 rounds of AES-128-CTR over `shared`, each round using
   `key = shared[:16]` and IV `00 00 00 00 00 00 00 <counter> 00 "mattel" 00`. The first 16 bytes
   of the result are the AES-128 data-channel key.
5. Write `app_pubkey_compressed(33) || app_nonce(4)` to **session**. The device performs the same
   ECDH and derives the same key.

## Data frames

A command is built in three layers, then encrypted:

```
app command:  [opcode] + args                              (FPLumaModel)
FE-frame:     0xFE | len | app_command | XOR(len ^ bytes)
SSI0 wrap:    0x01 0x10 | FE-frame                          (routes BLE -> toy-IC)
MPID frame:   0x7E | seq(4) | len+1(2) | crc8 | AES-128-CTR(SSI0-wrap + crc8)
```

- **AES-128-CTR** with the session key; IV `seq || appNonce || deviceSalt || 0` for app→device,
  and `seq || deviceSalt || appNonce || 0` for device→app.
- **CRC-8** (polynomial 0x07) protects the header (plaintext) and the body (encrypted with it).

To receive data responses, first send the transport command `ENABLE_RX` (`01 50 01`). A response
arrives as `SSI0 | FE-frame | [response_opcode] + data`.

The exact plaintext transport events `00 7f 01 XX 00 00 00 00 00`
(XX = `03`, `06`, `07`, `12`) and `01 10 XX 00` (XX = `04`, `05`, `10`)
are target-observed session/request
acknowledgements. The Python client ignores only these fixed events without
interpreting them as application responses; no other `00 7f` payload is
accepted. Application responses still require the `01 50` route and a valid FE
frame.

## Commands

Full opcode and enum tables are in [`spec/protocol.json`](../spec/protocol.json). Highlights:
`SET_LIGHT_COLOR (0x3C)`, `SET_LED_BRIGHTNESS (0x3A)`, `PLAY_AUDIO (0x3F)`, `SET_VOLUME (0x37)`,
`SET_GLOBAL_ON (0x03)`, `START_NAP_TIME (0x4D)`, `SET_CURRENT_DATE (0x30)`,
`REQUEST_GLOBAL_STATE (0x53)` (runtime summary).

`GLOBAL_STATE` (response `0x02`) is a 26-nibble runtime summary covering selected
mode, light, audio, timer, clock, and routine fields. It is not a complete
configuration snapshot: it omits the custom playlist, weekly times and alarms,
and all seven daily routine payloads. See the decoders in each package.
