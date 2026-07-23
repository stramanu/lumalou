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

## CLI

```bash
lumalou scan
lumalou light --color blue --brightness 7
lumalou sound --source ocean --volume 5
lumalou soother                 # --off to stop
lumalou time                    # sync clock
lumalou state                   # read full state
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
