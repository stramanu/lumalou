# lumalou (Python)

Local BLE control for the Fisher-Price Lumalou. Pure Python (async, [bleak](https://github.com/hbldh/bleak)).

```bash
pip install lumalou
```

## Library

```python
import asyncio
from lumalou import LumalouClient, Color

async def main():
    devices = await LumalouClient.scan()
    async with LumalouClient(devices[0]["address"]) as luma:
        await luma.light_color(Color.RAINBOW)
        await luma.play(0)            # guided sleep playlist
        await luma.volume(5)
        print(await luma.request_state())

asyncio.run(main())
```

`request_state()` returns a fresh `GLOBAL_STATE` snapshot (on a timeout it falls back to the
last one seen in the session, as in 0.2.0). For other blocks use `request_named()` or
`request_day_routine()`, which return a `ResponseEnvelope`; `.decode()` gives typed values.

### Default vs strict

`LumalouClient(address)` is tolerant, like 0.2.0: any response type can be read again in the
same session (polling works), unexpected frames are ignored, and a FACTORY token that does not
verify only logs a warning. `LumalouClient(address, strict=True)` turns each of those into a
hard error: one fresh answer per response type per session, every frame accounted for,
authenticated device identity required. Passing `expected_device_fingerprint=...` always
requires authentication, in either mode.

Both were exercised on a real gld09 (2026-11-03): the FACTORY signature verifies with the
known manufacturing key, all 26 named reads and 7 day routines answer, repeated reads work in
the default mode and are refused in strict mode. See the
[client contract](../../docs/client-contract.md) and
[schedule codec reference](../../docs/schedule-codecs.md).

## CLI

```bash
lumalou scan
lumalou light --color blue --brightness 7
lumalou sound --source ocean --volume 5
lumalou soother                 # --off to stop
lumalou time                    # sync clock
lumalou state                   # read a fresh GLOBAL_STATE snapshot
lumalou send 3c05               # raw app_data (opcode + args)
```

Add `-a <address>` to target a device; otherwise it auto-scans.

Requires Python 3.10+, a Bluetooth LE adapter, and radio range of the device.

## Development

```bash
pip install -e ".[dev]"
pytest        # runs the shared golden vectors (spec/vectors.json)
```

MIT.
