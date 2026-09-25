import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as P from "../src/profile.js";
import * as C from "../src/commands.js";
import { parseGlobalState } from "../src/responses.js";

const V = JSON.parse(readFileSync(new URL("../../../spec/profile-vectors.json", import.meta.url), "utf8"));
const fromHex = (s: string) => Uint8Array.from(Buffer.from(s, "hex"));
const hex = (data: Uint8Array) => Buffer.from(data).toString("hex");

test("literal SET-only profile vectors", () => {
  for (const v of V.playlists) {
    assert.equal(hex(C.setMusicPlaylist({ slots: v.slots })), v.set);
    assert.deepEqual(P.decodeMusicPlaylistSet(fromHex(v.set).slice(1)), { slots: v.slots });
  }
  for (const v of V.clockSettings) {
    assert.equal(hex(C.setClockSettings(v.displayOn, v.brightness, v.format)), v.set);
    assert.deepEqual(P.decodeClockSettingsSet(fromHex(v.set).slice(1)), { displayOn: v.displayOn, brightness: v.brightness, format: v.format });
  }
  for (const v of V.routineMusicSettings) {
    assert.equal(hex(C.setRoutineMusicSettings(v)), v.set);
    assert.deepEqual(P.decodeRoutineMusicSettingsSet(fromHex(v.set).slice(1)), { music: v.music, taskReward: v.taskReward, routineReward: v.routineReward });
  }
});

test("all 65536 clock SET encodings: accept 40, preserve unsupported bytes explicitly", () => {
  let valid = 0;
  for (let first = 0; first < 256; first++) for (let second = 0; second < 256; second++) {
    const raw = Uint8Array.of(first, second);
    if (first <= 1 && (second >> 4) <= 9 && (second & 15) <= 1) {
      assert.deepEqual(P.encodeClockSettings(P.decodeClockSettingsSet(raw)), raw);
      valid++;
    } else {
      assert.throws(() => P.decodeClockSettingsSet(raw));
      assert.deepEqual(new P.OpaqueBlock(raw, 2).data, raw);
    }
  }
  assert.equal(valid, 40);
});

test("all 65536 music/reward SET encodings retain unknown semantics", () => {
  for (let music = 0; music < 256; music++) for (let rewards = 0; rewards < 256; rewards++) {
    const raw = Uint8Array.of(music, rewards);
    assert.deepEqual(P.encodeRoutineMusicSettings(P.decodeRoutineMusicSettingsSet(raw)), raw);
  }
});

test("every possible playlist byte in every slot", () => {
  for (let slot = 0; slot < 12; slot++) for (let song = 0; song < 256; song++) {
    const raw = new Uint8Array(12); raw[slot] = song;
    if (song <= 12) assert.deepEqual(P.encodeMusicPlaylist(P.decodeMusicPlaylistSet(raw)), raw);
    else {
      assert.throws(() => P.decodeMusicPlaylistSet(raw));
      assert.deepEqual(new P.OpaqueBlock(raw, 12).data, raw);
    }
  }
});

test("wrong lengths, input types, overflow and coercion never silently truncate or wrap", () => {
  const codecs: [((d: Uint8Array) => unknown), number][] = [
    [P.decodeMusicPlaylistSet, 12], [P.decodeClockSettingsSet, 2], [P.decodeRoutineMusicSettingsSet, 2], [parseGlobalState, 13],
  ];
  for (const [decode, length] of codecs) {
    for (let actual = 0; actual < 256; actual++) if (actual !== length) assert.throws(() => decode(new Uint8Array(actual)));
    for (const bad of [null, [], "00", new Array(length).fill(0)]) assert.throws(() => decode(bad as never));
  }
  assert.equal(hex(C.setMusicPlaylist([1, 0, 1])), "40010100000000000000000000");
  assert.throws(() => C.setMusicPlaylist(new Array(13).fill(1)));
  assert.throws(() => C.setMusicPlaylist(new Array(12))); // sparse values must not turn into zero
  assert.throws(() => C.setMusicPlaylist({ slots: new Array(12) }));
  for (const bad of [-1, 13, 1.5, "1", true, null]) assert.throws(() => C.setMusicPlaylist([bad as number]));
  for (const bad of [0, 1, null, "false"]) assert.throws(() => C.setClockSettings(bad as never, 0, 0));
  for (const bad of [-1, 10, 1.5, "1", true]) assert.throws(() => C.setClockSettings(true, bad as number, 0));
  for (const bad of [-1, 2, 1.5, "1", true]) assert.throws(() => C.setClockSettings(true, 0, bad as number));
  for (const bad of [-1, 256, 1.5, "1", true, null]) assert.throws(() => C.setRoutineMusicSettings({ music: bad as number, taskReward: 0, routineReward: 0 }));
  for (const bad of [-1, 16, 1.5, "1", true, null]) {
    assert.throws(() => C.setRoutineMusicSettings({ music: 0, taskReward: bad as number, routineReward: 0 }));
    assert.throws(() => C.setRoutineMusicSettings({ music: 0, taskReward: 0, routineReward: bad as number }));
  }
  const setters: [((n: number) => Uint8Array), number][] = [[C.setLightColor, 9], [C.setBrightness, 9], [C.setLightDuration, 5], [C.setVolume, 9], [C.setRoutineVolume, 255], [C.setPlaylistDuration, 6], [C.setNapAlarm, 10]];
  for (const [setter, max] of setters) {
    assert.equal(setter(0)[1], 0); assert.equal(setter(max)[1], max);
    for (const bad of [-1, max + 1, 1.5, "1", true, null]) assert.throws(() => setter(bad as number));
  }
  for (const [setter, opcode] of [[C.setR2RStatus, 0x44], [C.setRoutineStatus, 0x58]] as const) {
    assert.deepEqual(setter(false), Uint8Array.of(opcode, 0));
    assert.deepEqual(setter(true), Uint8Array.of(opcode, 1));
    for (const bad of [0, 1, null, "false", []]) assert.throws(() => setter(bad as never));
  }
});

test("opaque block owns exact bytes, rejects guessed or mismatched lengths", () => {
  for (let length = 0; length < 255; length++) {
    const raw = Uint8Array.from({ length }, (_, i) => i);
    const block = new P.OpaqueBlock(raw, length);
    assert.deepEqual(block.data, raw);
    raw.fill(255); assert.notDeepEqual(length ? block.data : Uint8Array.of(0), length ? raw : Uint8Array.of(1));
    const returned = block.data; returned.fill(255);
    assert.deepEqual(block.data, Uint8Array.from({ length }, (_, i) => i));
    assert.throws(() => new P.OpaqueBlock(raw, length + 1));
  }
  for (const length of [-1, 255, true, 2.0]) assert.throws(() => new P.OpaqueBlock(new Uint8Array(), length as number));
});
