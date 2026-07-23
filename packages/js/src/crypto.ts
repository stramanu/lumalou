// MPID crypto and framing — isomorphic (Web Crypto). Validated against golden vectors.

export const hex = (u8: Uint8Array): string =>
  [...u8].map((b) => b.toString(16).padStart(2, "0")).join("");
export const fromHex = (s: string): Uint8Array =>
  new Uint8Array((s.match(/.{1,2}/g) ?? []).map((b) => parseInt(b, 16)));
export const concat = (...arrs: Uint8Array[]): Uint8Array => {
  const out = new Uint8Array(arrs.reduce((n, a) => n + a.length, 0));
  let o = 0;
  for (const a of arrs) { out.set(a, o); o += a.length; }
  return out;
};

// ---- CRC-8, polynomial 0x07 ----
const CRC8 = (() => {
  const t: number[] = [];
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = c & 0x80 ? ((c << 1) ^ 0x07) & 0xff : (c << 1) & 0xff;
    t.push(c);
  }
  return t;
})();
export function crc8(data: Uint8Array, init = 0xff): number {
  let c = init;
  for (const b of data) c = CRC8[(b ^ c) & 0xff];
  return c;
}

// ---- AES-128-CTR (128-bit big-endian counter) ----
async function aesCtr(key16: Uint8Array, iv16: Uint8Array, data: Uint8Array): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey("raw", key16, { name: "AES-CTR" }, false, ["encrypt"]);
  const buf = await crypto.subtle.encrypt({ name: "AES-CTR", counter: iv16, length: 128 }, key, data);
  return new Uint8Array(buf);
}

// ---- ECDH P-256 + "mattel" stretch ----
const P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffffn;
const A = P - 3n;
const B = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604bn;

function modpow(base: bigint, exp: bigint, mod: bigint): bigint {
  let r = 1n; base %= mod;
  while (exp > 0n) { if (exp & 1n) r = (r * base) % mod; exp >>= 1n; base = (base * base) % mod; }
  return r;
}
const bytesToBig = (u8: Uint8Array): bigint => { let x = 0n; for (const b of u8) x = (x << 8n) | BigInt(b); return x; };
const bigToBytes = (x: bigint, len: number): Uint8Array => {
  const out = new Uint8Array(len);
  for (let i = len - 1; i >= 0; i--) { out[i] = Number(x & 0xffn); x >>= 8n; }
  return out;
};

/** Decompress a compressed P-256 point (33 bytes) to uncompressed (65 bytes). */
export function decompressPoint(comp33: Uint8Array): Uint8Array {
  const x = bytesToBig(comp33.slice(1));
  const yy = ((((x * x) % P) * x) % P + (A * x) % P + B) % P;
  let y = modpow(yy, (P + 1n) / 4n, P);
  if ((y & 1n) !== BigInt(comp33[0] & 1)) y = P - y;
  return concat(new Uint8Array([0x04]), bigToBytes(x, 32), bigToBytes(y, 32));
}

export function compressPoint(unc65: Uint8Array): Uint8Array {
  return concat(new Uint8Array([0x02 | (unc65[64] & 1)]), unc65.slice(1, 33));
}

/** Derive the 32-byte session key from (our private key, device compressed pubkey). */
export async function deriveSessionKey(privKey: CryptoKey, devPubComp33: Uint8Array): Promise<Uint8Array> {
  const devUnc = decompressPoint(devPubComp33);
  const devKey = await crypto.subtle.importKey("raw", devUnc, { name: "ECDH", namedCurve: "P-256" }, false, []);
  let shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "ECDH", public: devKey }, privKey, 256));
  for (let c = 0; c < 100; c++) {
    const iv = new Uint8Array([0, 0, 0, 0, 0, 0, 0, c, 0, 0x6d, 0x61, 0x74, 0x74, 0x65, 0x6c, 0]);
    shared = await aesCtr(shared.slice(0, 16), iv, shared);
  }
  return shared;
}

/** Generate an ephemeral keypair; returns the private CryptoKey, compressed pubkey and nonce. */
export async function makeEphemeral(): Promise<{ privKey: CryptoKey; pubComp: Uint8Array; nonce: Uint8Array }> {
  const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
  const pubRaw = new Uint8Array(await crypto.subtle.exportKey("raw", kp.publicKey));
  return { privKey: kp.privateKey, pubComp: compressPoint(pubRaw), nonce: crypto.getRandomValues(new Uint8Array(4)) };
}

// ---- application framing ----
export function composeRequest(appData: Uint8Array): Uint8Array {
  let xor = appData.length & 0xff;
  for (const b of appData) xor ^= b;
  return concat(new Uint8Array([0xfe, appData.length & 0xff]), appData, new Uint8Array([xor & 0xff]));
}
export function ssi0Wrap(feFrame: Uint8Array, address = 0): Uint8Array {
  return concat(new Uint8Array([0x01, ((1 << 4) & 0xf0) | (address & 0x0f)]), feFrame);
}
export function encodeCommand(appData: Uint8Array): Uint8Array {
  return ssi0Wrap(composeRequest(appData));
}

// ---- MPID frame + AES-128-CTR ----
const be32 = (n: number) => new Uint8Array([(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff]);
const be16 = (n: number) => new Uint8Array([(n >>> 8) & 0xff, n & 0xff]);
const iv = (seq: number, a4: Uint8Array, b4: Uint8Array) => concat(be32(seq), a4, b4, new Uint8Array(4));

export async function buildTxFrame(
  plaintext: Uint8Array, seq: number, key16: Uint8Array, nonce4: Uint8Array, devSalt4: Uint8Array,
): Promise<Uint8Array> {
  const h0 = concat(new Uint8Array([0x7e]), be32(seq), be16(plaintext.length + 1));
  const header = concat(h0, new Uint8Array([crc8(h0)]));
  const body = concat(plaintext, new Uint8Array([crc8(plaintext)]));
  return concat(header, await aesCtr(key16, iv(seq, nonce4, devSalt4), body));
}

export async function decryptRxFrame(
  frame: Uint8Array, key16: Uint8Array, nonce4: Uint8Array, devSalt4: Uint8Array,
): Promise<{ seq: number; plaintext: Uint8Array; crcOk: boolean } | null> {
  if (frame.length < 9 || frame[0] !== 0x7e) return null;
  const seq = ((frame[1] << 24) | (frame[2] << 16) | (frame[3] << 8) | frame[4]) >>> 0;
  const dec = await aesCtr(key16, iv(seq, devSalt4, nonce4), frame.slice(8));
  const plaintext = dec.slice(0, -1);
  return { seq, plaintext, crcOk: crc8(plaintext) === dec[dec.length - 1] };
}
