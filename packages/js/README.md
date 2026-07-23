# lumalou (JavaScript / TypeScript)

Isomorphic protocol core for the Fisher-Price Lumalou — crypto handshake, framing, commands
and response decoding. Works in the browser (with Web Bluetooth) and in Node. Ships ESM, CJS
and type definitions.

```bash
npm install lumalou
```

## Usage

The package provides the protocol core; you supply the transport (Web Bluetooth in the browser,
noble in Node). Example of the handshake + a command frame in the browser:

```ts
import { makeEphemeral, deriveSessionKey, encodeCommand, buildTxFrame, setLightColor, Color } from "lumalou";

// after connecting to the GATT service and reading the FACTORY token:
const token = new Uint8Array(await factory.readValue().then((v) => v.buffer));
const devicePub = token.slice(25, 58);
const deviceSalt = token.slice(-4);

const { privKey, pubComp, nonce } = await makeEphemeral();
const key = (await deriveSessionKey(privKey, devicePub)).slice(0, 16);
await session.writeValueWithResponse(new Uint8Array([...pubComp, ...nonce])); // 37 bytes

let seq = 1;
const frame = await buildTxFrame(encodeCommand(setLightColor(Color.BLUE)), seq++, key, nonce, deviceSalt);
await tx.writeValueWithoutResponse(frame);
```

A full browser app using this core lives at <https://lumalou.emanuelestrazzullo.dev>.

## Development

```bash
npm install
npm test          # runs the shared golden vectors (spec/vectors.json)
npm run build     # ESM + CJS + .d.ts
npm run typecheck
```

MIT.
