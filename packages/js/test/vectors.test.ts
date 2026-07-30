// Golden-vector conformance: the JS/TS binding must match spec/vectors.json.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import {
  crc8, fromHex, hex, deriveSessionKey, encodeCommand, buildTxFrame, decryptRxFrame,
} from "../src/crypto.js";
import { parseGlobalState, parseResponsePayload, parseDayRoutine, parseWeeklyTimes,
  parseClockSettings, parseCurrentDate } from "../src/responses.js";
import { setDayRoutine, requestDayRoutine, setR2RTimes, setR2RAlarms, setRoutineMusicStatus, request,
  setLightColor, setBrightness, setGlobalState } from "../src/commands.js";

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

test("dayRoutine vectors", () => {
  for (const v of V.dayRoutine) {
    const time: [number, number] | null = v.time === null ? null : [v.time[0], v.time[1]];
    const out = setDayRoutine(v.day, time, v.steps);
    assert.equal(hex(out.slice(1)), v.expected);
    const parsed = parseDayRoutine(fromHex(v.expected));
    assert.deepEqual(parsed.steps, v.steps);
    assert.deepEqual(parsed.time, time);
  }
});

test("weeklyTimes vectors", () => {
  for (const v of V.weeklyTimes) {
    const times = v.times.map((t: number[] | null) => (t === null ? null : [t[0], t[1]]));
    assert.equal(hex(setR2RTimes(times).slice(1)), v.expected);
    assert.deepEqual(parseWeeklyTimes(fromHex(v.expected)), times);
  }
});

test("r2rAlarms vectors", () => {
  for (const v of V.r2rAlarms) {
    assert.equal(hex(setR2RAlarms(v.days, v.sfx).slice(1)), v.expected);
  }
});

test("routineMusicStatus vectors", () => {
  for (const v of V.routineMusicStatus) {
    const out = setRoutineMusicStatus(v.music, v.taskRewards, v.routineRewards);
    assert.equal(hex(out.slice(1)), v.expected);
  }
});

test("clockSettings vectors", () => {
  for (const v of V.clockSettings) {
    assert.deepEqual(parseClockSettings(fromHex(v.args)), v.expected);
  }
});

test("currentDate vectors", () => {
  for (const v of V.currentDate) {
    assert.deepEqual(parseCurrentDate(fromHex(v.args)), v.expected);
  }
});

test("every request name resolves to a one-byte payload", () => {
  const names = [
    // keep in sync with REQUESTS in packages/python/src/lumalou/commands.py
    "global_state", "current_date", "toyic_fw_version", "led_brightness", "light_color",
    "light_duration", "volume", "routine_volume", "song_playing", "music_playlist",
    "playlist_duration", "operation_mode", "activity_state", "current_stage",
    "clock_settings", "transmission_mode", "routine_mode_status", "routine_task_status",
    "routine_music_status", "r2r_status", "r2r_times", "sleepy_times",
    "r2r_alarm_status", "r2r_alarms", "nap_current_status", "time_prescaler",
  ];
  for (const n of names) {
    const out = request(n);
    assert.equal(out.length, 1, `${n} did not resolve`);
    assert.ok(out[0] > 0, `${n} resolved to opcode 0`);
  }
  assert.equal(names.length, 26);
});

test("day routine rejects the inputs Python rejects", () => {
  assert.throws(() => setDayRoutine("sunday", [7, 0], [[1], [], [3]]), /empty/i);
  assert.throws(
    () => setDayRoutine("sunday", [7, 0], [[1], ...Array.from({ length: 14 }, () => []), [3]]),
    /empty/i,
  );
  assert.throws(() => setDayRoutine("funday" as never, null, [[1]]), /funday/);
  assert.throws(() => requestDayRoutine("funday" as never), /funday/);
  assert.throws(() => setDayRoutine("sunday", [7, 0], Array.from({ length: 13 }, () => [1])), /12/);
  assert.throws(() => setR2RTimes([[7, 0]] as never), /7/);
  // the legitimate boundary still works
  assert.doesNotThrow(() => setDayRoutine("sunday", [7, 0], Array.from({ length: 12 }, () => [1])));
});

test("request rejects an unknown name", () => {
  assert.throws(() => request("bogus_name"), /bogus_name/);
});

test("out-of-range arguments are rejected", () => {
  assert.throws(() => setR2RAlarms([16, 0, 0, 0, 0, 0, 0], 0), /alarm must be 0-10/);
  assert.throws(() => setDayRoutine("sunday", [24, 0], [[1]]), /hour must be 0-23/);
  assert.throws(() => setDayRoutine("sunday", [7, 0], [[12]]), /task id must be 0-11/);
  assert.doesNotThrow(() => setR2RAlarms([9, 9, 9, 9, 9, 9, 9], 0));
});

test("boundary values are still accepted (parity with Python)", () => {
  assert.doesNotThrow(() => setLightColor(9));
  assert.doesNotThrow(() => setBrightness(0));
  assert.doesNotThrow(() => setDayRoutine("sunday", [23, 59], [[11]]));
  // the 0x0f "leave unchanged" sentinel sits outside every field's own range
  // and must still be accepted when no fields are given
  assert.equal(hex(setGlobalState()), "01ffffffff");
});

test("non-integer arguments are rejected", () => {
  for (const bad of [9.5, -0.5, NaN, Infinity]) {
    assert.throws(() => setBrightness(bad as number));
  }
  assert.doesNotThrow(() => setBrightness(9));
});
