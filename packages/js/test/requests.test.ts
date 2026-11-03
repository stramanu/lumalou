import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { request } from "../src/commands.js";
import { COMMANDS } from "../src/generated.js";

const vectors = JSON.parse(readFileSync(new URL("../../../spec/read-requests.json", import.meta.url), "utf8")).requests;

// exposed=false: real opcodes that never answered on a gld09; documented, not offered
const exposed = vectors.filter((v: { exposed?: boolean }) => v.exposed !== false);

test("all 28 source-backed read-only queries have exact command bytes", () => {
  assert.equal(vectors.length, 28);
  assert.equal(exposed.length, 26);
  assert.deepEqual(
    vectors.map((v: {command: string}) => v.command).sort(),
    Object.keys(COMMANDS).filter(name => name.startsWith("REQUEST_")).sort(),
  );
  for (const vector of exposed) {
    assert.deepEqual(request(vector.name), new Uint8Array([parseInt(vector.request, 16)]));
  }
});

test("unknown, inherited and unsafe query names never become opcode zero", () => {
  for (const name of ["", "unknown", "toString", "constructor", "__proto__", "SET_TIME_PRESCALER", "set_time_prescaler", "SEND_PAIRING_COMPLETE", "nap_alarm", "nap_alarm_status"]) {
    assert.throws(() => request(name), /unknown request name/);
  }
});
