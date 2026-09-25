import { test } from "node:test";
import assert from "node:assert/strict";
import { parseClockSettings, parseMusicPlaylist } from "../src/responses.js";

test("observed ordered playlist response retains all twelve slots", () => {
  assert.deepEqual(parseMusicPlaylist(Uint8Array.from({ length: 12 }, (_, i) => i + 1)), {
    slots: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
  });
  assert.deepEqual(parseMusicPlaylist(new Uint8Array(12)), { slots: Array(12).fill(0) });
});

test("playlist response rejects wrong length and unsupported IDs", () => {
  assert.throws(() => parseMusicPlaylist(new Uint8Array(11)));
  const invalid = new Uint8Array(12);
  invalid[4] = 13;
  assert.throws(() => parseMusicPlaylist(invalid));
});

test("observed clock response decodes display, brightness and format", () => {
  assert.deepEqual(parseClockSettings(Uint8Array.of(1, 0x21)), {
    displayOn: true,
    brightness: 2,
    format: 1,
  });
  assert.deepEqual(parseClockSettings(Uint8Array.of(0, 0)), {
    displayOn: false,
    brightness: 0,
    format: 0,
  });
});

test("clock response rejects wrong length and reserved values", () => {
  assert.throws(() => parseClockSettings(Uint8Array.of(1)));
  assert.throws(() => parseClockSettings(Uint8Array.of(2, 0x21)));
  assert.throws(() => parseClockSettings(Uint8Array.of(1, 0xa1)));
  assert.throws(() => parseClockSettings(Uint8Array.of(1, 0x2f)));
});
