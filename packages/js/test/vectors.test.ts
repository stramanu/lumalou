// Golden-vector conformance: the JS/TS binding must match spec/vectors.json.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import {
  crc8, fromHex, hex, deriveSessionKey, encodeCommand, buildTxFrame, decryptRxFrame,
} from "../src/crypto.js";
import { parseGlobalState, parseResponsePayload } from "../src/responses.js";

const here = dirname(fileURLToPath(import.meta.url));
const V = JSON.parse(readFileSync(resolve(here, "../../../spec/vectors.json"), "utf8"));

test("crc8", () => {
  for (const v of V.crc8) assert.equal(crc8(fromHex(v.data), v.init), v.expected);
});

test("sessionKey (ECDH + stretch)", async () => {
  for (const v of V.sessionKey) {
    const priv = await crypto.subtle.importKey("jwk", v.jwk, { name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
    const key = await deriveSessionKey(priv, fromHex(v.devicePubCompressed));
    assert.equal(hex(key), v.expected);
  }
});

test("encodeCommand", () => {
  for (const v of V.encodeCommand) assert.equal(hex(encodeCommand(fromHex(v.appData))), v.expected);
});

test("txFrame", async () => {
  for (const v of V.txFrame) {
    const f = await buildTxFrame(fromHex(v.plaintext), v.seq, fromHex(v.key), fromHex(v.nonce), fromHex(v.salt));
    assert.equal(hex(f), v.expected);
  }
});

test("rxDecrypt", async () => {
  for (const v of V.rxDecrypt) {
    const r = await decryptRxFrame(fromHex(v.frame), fromHex(v.key), fromHex(v.nonce), fromHex(v.salt));
    assert.ok(r);
    assert.equal(hex(r!.plaintext), v.expectedPlaintext);
    assert.equal(r!.crcOk, v.expectedCrcOk);
  }
});

test("globalState", () => {
  for (const v of V.globalState) {
    assert.deepEqual(parseGlobalState(fromHex(v.args)), v.expected);
  }
});

test("responseFrame", () => {
  for (const v of V.responseFrame) {
    const r = parseResponsePayload(fromHex(v.plaintext));
    assert.ok(r.ok);
    assert.equal(r.opcode, v.expectedOpcode);
    assert.equal(hex(r.args!), v.expectedArgs);
  }
});
