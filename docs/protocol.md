# Lumalou MPID protocol

Reverse-engineered from the official app and validated bit-exact against the device's native
library and the physical hardware. Machine-readable form: [`spec/protocol.json`](../spec/protocol.json).

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

1. Read the MFG token from **factory**. It contains the device's compressed P-256 public key at
   bytes `[25:58]` and a 4-byte salt in the last 4 bytes.
2. Generate an ephemeral P-256 keypair. Compute `shared = ECDH(app_priv, device_pub)` (X coord, 32 B).
3. Derive the session key by stretching: 100 rounds of AES-128-CTR over `shared`, each round using
   `key = shared[:16]` and IV `00 00 00 00 00 00 00 <counter> 00 "mattel" 00`. The first 16 bytes
   of the result are the AES-128 data-channel key.
4. Write `app_pubkey_compressed(33) || app_nonce(4)` to **session**. The device performs the same
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

## Commands

Full opcode and enum tables are in [`spec/protocol.json`](../spec/protocol.json). Highlights:
`SET_LIGHT_COLOR (0x3C)`, `SET_LED_BRIGHTNESS (0x3A)`, `PLAY_AUDIO (0x3F)`, `SET_VOLUME (0x37)`,
`SET_GLOBAL_ON (0x03)`, `START_NAP_TIME (0x4D)`, `SET_CURRENT_DATE (0x30)`,
`REQUEST_GLOBAL_STATE (0x53)` (full snapshot).

`GLOBAL_STATE` (response `0x02`) is a 26-nibble snapshot of the whole device state
(mode, light, audio, timers, clock, routine). See the decoders in each package.
