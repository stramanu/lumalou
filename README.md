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
Bluetooth. A companion [web app](https://lumalou.emanuelestrazzullo.dev) implements the same
protocol as a live demo.

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

## Related devices (Fisher-Price Smart Connect)

The Smart Connect app controlled a whole family of Fisher-Price devices. It was removed from
**Google Play in March 2025** and the app's **backend services shut down in August 2025**, so
none of them can be controlled by the official app anymore. Only the app's online services are
gone — the devices themselves speak a **local** Bluetooth protocol, which is exactly why this
project can still control them.

They come in two protocol generations, which are technically distinct (different GATT
characteristics and crypto — the legacy line predates the magic-device line). This library
implements the **newer "magic device" generation** (the MPID handshake over the
`tx`/`rx`/`session`/`factory` characteristics) that the Lumalou uses. Across that generation the
transport — handshake and framing — is identical; only the per-device command set differs. The
**legacy generation** uses a different characteristic layout and crypto and is not supported yet.

Legend: ✅ confirmed on hardware · 🟡 same protocol, untested · ⚪ different (legacy) protocol.

| Device | Product code | Protocol | This library |
|---|---|---|---|
| **Lumalou** (Better Bedtime Routine System) | `gld09` | magic device (MPID) | ✅ confirmed |
| **Bunny** | `gmn58` | magic device (MPID) | 🟡 likely — shared handshake, different commands |
| **Whisper** | `ghp38` | magic device (MPID) | 🟡 likely — shared handshake, different commands |
| Swing · Cradle Swing · Revolve Swing · Glider | `cbv76` `dkd85` `flg83` `ffh99` `gdd39` | legacy | ⚪ not yet |
| Mobile · Mobile Baby · Mobile Baby 2 | `cdm85` `cmk04` `dfp73` | legacy | ⚪ not yet |
| Sleeper · Deluxe Sleeper · Bassinet | `cmp94` `dpv51` `dpv70` | legacy | ⚪ not yet |
| Lamp Soother · Seahorse | `dyw47` `fhc95` | legacy | ⚪ not yet |

**Why 🟡 is a strong bet:** the magic-device models share the same local ECDH handshake, and
the app ships each one's manufacturing public key hardcoded (Lumalou `gld09`, Bunny `gmn58`,
Whisper `ghp38`). Connecting should work the same way — only the command opcodes change.

**Have one of these** — especially a Bunny or Whisper, or any legacy device? Please
[open an issue](https://github.com/stramanu/lumalou/issues). A test or a Bluetooth (HCI snoop)
capture is the fastest way to extend support.

## FAQ

**Is the Fisher-Price Smart Connect app coming back?**
There's no official word. It was removed from Google Play in March 2025 and its backend
services shut down in August 2025. This project is an independent, community alternative.

**Do I need the Smart Connect app to use this?**
No. It talks to the device directly over Bluetooth — no app, no account, no cloud, nothing to
sign up for.

**Which devices work?**
Confirmed on the **Lumalou** (`gld09`). The other magic-device models (**Bunny**, **Whisper**)
almost certainly work at the transport level but are untested. Legacy devices use a different
protocol and aren't supported yet — see [Related devices](#related-devices-fisher-price-smart-connect).

**Is any of my data sent anywhere?**
No. The handshake and every command run locally on your device. There is no server.

**Does it work on iPhone?**
Yes, through the **Bluefy** browser (Safari and Chrome on iOS don't support Web Bluetooth).
On desktop, use Chrome or Edge.

**Is this affiliated with Mattel or Fisher-Price?**
No. It's an independent reverse-engineering project for interoperability. "Fisher-Price" and
"Lumalou" are trademarks of their respective owners.

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
