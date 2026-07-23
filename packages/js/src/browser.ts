// Optional browser BLE client (Web Bluetooth). Chrome/Edge, or iOS via Bluefy.
//   import { LumalouBrowserClient } from "lumalou/browser";
import * as X from "./crypto.js";
import { GATT } from "./generated.js";
import { parseGlobalState, parseResponsePayload, type GlobalState } from "./responses.js";
import { ENABLE_RX, request } from "./commands.js";

const SERVICE = GATT.service;
const { tx: TX, rx: RX, factory: FACTORY, session: SESSION } = GATT.characteristics;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export interface BrowserClientOptions {
  onState?: (state: GlobalState) => void;
  onStatus?: (status: string) => void;
  onLog?: (message: string) => void;
}

/** Web Bluetooth client. Requires a secure context (https/localhost) and Web Bluetooth support. */
export class LumalouBrowserClient {
  connected = false;
  private device?: BluetoothDevice;
  private tx?: BluetoothRemoteGATTCharacteristic;
  private session?: BluetoothRemoteGATTCharacteristic;
  private key!: Uint8Array;
  private nonce!: Uint8Array;
  private salt!: Uint8Array;
  private seq = 1;
  private queue: Promise<void> = Promise.resolve();
  private opts: BrowserClientOptions;

  constructor(opts: BrowserClientOptions = {}) {
    this.opts = opts;
  }

  static isSupported(): boolean {
    return typeof navigator !== "undefined" &&
      "bluetooth" in navigator &&
      typeof navigator.bluetooth?.requestDevice === "function" &&
      (typeof window === "undefined" || window.isSecureContext);
  }

  private log(m: string) { this.opts.onLog?.(m); }
  private status(s: string) { this.opts.onStatus?.(s); }

  async connect(): Promise<void> {
    if (!LumalouBrowserClient.isSupported()) throw new Error("Web Bluetooth not available (use Chrome/Edge, or Bluefy on iOS).");
    this.status("scanning");
    this.device = await navigator.bluetooth.requestDevice({ acceptAllDevices: true, optionalServices: [SERVICE] });
    this.device.addEventListener("gattserverdisconnected", () => { this.connected = false; this.status("disconnected"); });
    this.status("connecting");
    const server = await this.device.gatt!.connect();
    const svc = await server.getPrimaryService(SERVICE);
    this.tx = await svc.getCharacteristic(TX);
    this.session = await svc.getCharacteristic(SESSION);
    const rx = await svc.getCharacteristic(RX);
    const factory = await svc.getCharacteristic(FACTORY);
    await rx.startNotifications();
    rx.addEventListener("characteristicvaluechanged", (e) =>
      this.onRx(new Uint8Array((e.target as BluetoothRemoteGATTCharacteristic).value!.buffer)));

    this.status("handshake");
    const token = new Uint8Array((await factory.readValue()).buffer);
    this.salt = token.slice(token.length - 4);
    const devicePub = token.slice(25, 58);
    const eph = await X.makeEphemeral();
    this.nonce = eph.nonce;
    this.key = (await X.deriveSessionKey(eph.privKey, devicePub)).slice(0, 16);
    await this.session.writeValueWithResponse(X.concat(eph.pubComp, eph.nonce)); // 37 bytes
    await sleep(400);
    await this.write(ENABLE_RX);
    await sleep(300);
    this.connected = true;
    this.status("ready");
    await this.requestState();
  }

  async disconnect(): Promise<void> {
    this.connected = false;
    try { this.device?.gatt?.disconnect(); } catch { /* ignore */ }
  }

  private write(plaintext: Uint8Array): Promise<void> {
    this.queue = this.queue.then(async () => {
      if (!this.device?.gatt?.connected || !this.tx) return;
      const frame = await X.buildTxFrame(plaintext, this.seq++, this.key, this.nonce, this.salt);
      try { await this.tx.writeValueWithoutResponse(frame); } catch (e) { this.log(String(e)); }
      await sleep(160);
    });
    return this.queue;
  }

  /** Send a raw application command ([opcode] + args). */
  send(appData: Uint8Array): Promise<void> {
    return this.write(X.encodeCommand(appData));
  }

  async requestState(): Promise<void> {
    await this.send(request("global_state"));
  }

  private async onRx(frame: Uint8Array): Promise<void> {
    const res = await X.decryptRxFrame(frame, this.key, this.nonce, this.salt);
    if (!res || !res.crcOk) return;
    const r = parseResponsePayload(res.plaintext);
    if (r.ok && r.opcode === 0x02 && r.args) {
      this.opts.onState?.(parseGlobalState(r.args));
    }
  }
}
