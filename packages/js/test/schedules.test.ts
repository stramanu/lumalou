import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as S from "../src/schedules.js";

const V = JSON.parse(readFileSync(new URL("../../../spec/schedule-vectors.json", import.meta.url), "utf8"));
const bytes = (s: string) => Uint8Array.from(Buffer.from(s, "hex"));
const hex = (data: Uint8Array) => Buffer.from(data).toString("hex");
const time = (t: [number, number] | null) => t === null ? null : { hour: t[0], minute: t[1] };

test("shared literal schedule vectors and all seven day identities", () => {
  for (const v of V.weeklyTimes) {
    const value = { days: v.days.map(time) };
    assert.deepEqual(S.decodeWeeklyTimes(bytes(v.args)), value);
    assert.equal(hex(S.encodeWeeklyTimes(value)), v.args);
    assert.equal(hex(S.setR2RTimes(value)), "46" + v.args);
    assert.equal(hex(S.setSleepyTimes(value)), "48" + v.args);
  }
  for (const v of V.alarms) {
    const value = { days: v.days, sound: v.sound };
    assert.deepEqual(S.decodeWeeklyAlarms(bytes(v.args)), value);
    assert.equal(hex(S.encodeWeeklyAlarms(value)), v.args);
    assert.equal(hex(S.setR2RAlarms(value)), "4a" + v.args);
  }
  for (const v of V.routines) {
    const value = { time: time(v.time), slots: v.slots.map((s: [number, number] | null) => s === null ? null : { step: s[0], task: s[1] }) };
    assert.deepEqual(S.decodeDailyRoutine(bytes(v.args)), value);
    assert.equal(hex(S.encodeDailyRoutine(value)), v.args);
    for (const d of V.dayOpcodes) {
      assert.equal(S.DAY_ROUTINE_RESPONSES[d.day as S.Day], d.response);
      assert.deepEqual(S.requestDayRoutine(d.day), Uint8Array.of(d.request));
      assert.deepEqual(S.setDayRoutine(d.day, value), Uint8Array.of(d.set, ...bytes(v.args)));
      assert.deepEqual(S.parseScheduleResponse(d.response, bytes(v.args)), value);
    }
  }
  for (const v of V.taskStatus) {
    const value = { currentStep: v.currentStep, taskStates: v.taskStates };
    assert.deepEqual(S.decodeRoutineTaskStatus(bytes(v.args)), value);
    assert.equal(hex(S.encodeRoutineTaskStatus(value)), v.args);
  }
});

test("all BCD byte pairs: only valid clock times or FF FF", () => {
  let valid = 0;
  for (let hour = 0; hour < 256; hour++) for (let minute = 0; minute < 256; minute++) {
    const raw = new Uint8Array(14); raw[0] = hour; raw[1] = minute;
    const good = hour === 255 && minute === 255 || (hour >> 4) <= 2 && (hour & 15) <= 9 && (hour >> 4) * 10 + (hour & 15) <= 23 && (minute >> 4) <= 5 && (minute & 15) <= 9;
    if (good) { assert.deepEqual(S.encodeWeeklyTimes(S.decodeWeeklyTimes(raw)), raw); valid++; }
    else assert.throws(() => S.decodeWeeklyTimes(raw));
  }
  assert.equal(valid, 1441);
});

test("every task slot byte preserves order and padding or explicitly rejects unknown encodings", () => {
  for (let slot = 0; slot < 12; slot++) for (let byte = 0; byte < 256; byte++) {
    const raw = new Uint8Array(14); raw[slot + 2] = byte;
    const good = byte === 0 || (byte >> 4) >= 1 && (byte >> 4) <= 12 && (byte & 15) <= 11;
    if (good) assert.deepEqual(S.encodeDailyRoutine(S.decodeDailyRoutine(raw)), raw);
    else assert.throws(() => S.decodeDailyRoutine(raw));
  }
});

test("all alarm nibbles and runtime status byte positions", () => {
  for (let position = 0; position < 8; position++) for (let nibble = 0; nibble < 16; nibble++) {
    const raw = new Uint8Array(4); raw[Math.floor(position / 2)] = nibble << (position % 2 ? 0 : 4);
    if (position === 7 || nibble <= 10) assert.deepEqual(S.encodeWeeklyAlarms(S.decodeWeeklyAlarms(raw)), raw);
    else assert.throws(() => S.decodeWeeklyAlarms(raw));
  }
  for (let position = 0; position < 7; position++) for (let byte = 0; byte < 256; byte++) {
    const raw = new Uint8Array(7); raw[position] = byte;
    assert.deepEqual(S.encodeRoutineTaskStatus(S.decodeRoutineTaskStatus(raw)), raw);
  }
});

test("malformed lengths, unknown days, empty/overflow steps and sparse arrays fail", () => {
  const codecs: [((b: Uint8Array) => unknown), number][] = [[S.decodeWeeklyTimes, 14], [S.decodeDailyRoutine, 14], [S.decodeWeeklyAlarms, 4], [S.decodeRoutineTaskStatus, 7]];
  for (const [decode, length] of codecs) for (let actual = 0; actual < 256; actual++) if (actual !== length) assert.throws(() => decode(new Uint8Array(actual)));
  for (const day of ["Sunday", "mondayy", "__proto__", "", 0]) assert.throws(() => S.requestDayRoutine(day as S.Day));
  assert.throws(() => S.parseScheduleResponse(0x19, new Uint8Array(12)));
  assert.throws(() => S.routineFromSteps(null, [[]]));
  assert.throws(() => S.routineFromSteps(null, [new Array(13).fill(1)]));
  assert.throws(() => S.routineFromSteps(null, [new Array(1)]));
  assert.throws(() => S.encodeWeeklyTimes({ days: new Array(7) }));
  assert.throws(() => S.encodeWeeklyAlarms({ days: new Array(7), sound: 0 }));
  assert.throws(() => S.encodeDailyRoutine({ time: null, slots: new Array(12) }));
  assert.throws(() => S.encodeRoutineTaskStatus({ currentStep: 0, taskStates: new Array(12) }));
  const exact = S.routineFromSteps(null, [[0, 11], [3]]);
  assert.equal(hex(S.encodeDailyRoutine(exact)), "ffff101b23000000000000000000");
});
