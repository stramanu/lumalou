# lumalou

[![CI](https://github.com/stramanu/lumalou/actions/workflows/ci.yml/badge.svg)](https://github.com/stramanu/lumalou/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/lumalou?label=pypi)](https://pypi.org/project/lumalou/)
[![npm](https://img.shields.io/npm/v/lumalou?label=npm)](https://www.npmjs.com/package/lumalou)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Local BLE control for the Fisher-Price Lumalou** — a reverse-engineered, multi-language
implementation of the *Lumalou Better Bedtime Routine System* (product code `gld09`)
protocol, after the official *Fisher-Price Smart Connect* app was discontinued.

No cloud, no backend: the encrypted handshake and every command run locally over Bluetooth LE.

> 🌥️ **Live web app** (Chrome/Edge, or iOS via Bluefy): <https://lumalou.emanuelestrazzullo.dev>

## Why a monorepo

The protocol is one thing, implemented for several ecosystems. The tricky, security-relevant
parts (the crypto handshake and framing) are **frozen and identical** across languages,
guaranteed by a shared, language-agnostic contract:

- **`spec/protocol.json`** — the single source of truth for opcodes and enums. Language modules
  are **generated** from it (`tools/codegen.py`), so they can never drift.
- **`spec/vectors.json`** — golden test vectors (input → expected output). **Every** binding runs
  the same vectors, so all languages are provably byte-for-byte identical.

Add a new language later (Rust, Go, Swift…) and the same vectors verify it.

## Packages

| Package | Language | Install |
|---|---|---|
| [`packages/python`](packages/python) | Python (async, `bleak`) | `pip install lumalou` |
| [`packages/js`](packages/js) | TypeScript / JavaScript (isomorphic core) | `npm install lumalou` |

Python ships a full client + CLI. The JS package ships the isomorphic protocol core plus an
optional browser client (`import { LumalouBrowserClient } from "lumalou/browser"`) using Web
Bluetooth. The [live web app](https://lumalou.emanuelestrazzullo.dev) is built on it.

## What it controls

Light (10 colours incl. rainbow, brightness, timers) · audio (guided sleep playlist, sound
effects, 12-track custom playlist, volume, timers) · nap and weekly sleep/wake schedules ·
routines · clock · live state readback.

## How it works

The Lumalou speaks Mattel's **MPID** protocol over a custom GATT service (`4cea0001-…`):

- **Handshake** — the device sends a signed token; the client performs an ephemeral **ECDH
  P-256** exchange and derives the session key via a 100-round AES-128-CTR stretch. No server.
- **Framing** — commands are wrapped `FE-frame → SSI0 → MPID` and encrypted with **AES-128-CTR**
  (CRC-8 integrity). Responses are decrypted and decoded symmetrically.

Full write-up: [`docs/protocol.md`](docs/protocol.md).

## Development

```bash
python tools/codegen.py        # regenerate language modules from spec/protocol.json
python tools/gen_vectors.py    # regenerate golden vectors

# Python
cd packages/python && pip install -e ".[dev]" && pytest

# JS/TS
cd packages/js && npm install && npm test && npm run build
```

CI runs both test suites and fails if the generated modules or vectors are out of date.

## Safety

The libraries **never** touch the firmware-update (DFU) service `00001530-…` and never send
OTA opcodes — a wrong write there would brick the device.

## Disclaimer

Personal reverse-engineering project for **interoperability** (EU Directive 2009/24/EC, art. 6)
after the official app's shutdown. Not affiliated with or endorsed by Mattel / Fisher-Price.
"Fisher-Price" and "Lumalou" are trademarks of their respective owners. Use at your own risk.

## License

MIT — see [LICENSE](LICENSE).
