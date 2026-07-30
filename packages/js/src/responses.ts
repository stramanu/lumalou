// Decode device responses. Values are raw integers (canonical, matches the spec).
import { RESPONSES } from "./generated.js";
import { hex } from "./crypto.js";

const nibbles = (data: Uint8Array): number[] => {
  const out: number[] = [];
  for (const b of data) out.push(b >> 4, b & 0x0f);
  return out;
};

export interface GlobalState {
  operationMode: number; activityState: number; musicStatus: number; currentSong: number;
  currentVolume: number; playlistDuration: number; lightStatus: number; lightBrightness: number;
  lightColor: number; napTimeStatus: number; napDuration: number; ready2RiseStatus: number;
  ready2RiseAlarmStatus: number; timePrescaler: number; currentStage: number; clockDisplay: number;
  clockBrightness: number; clockFormat: number; routineMusicStatus: number; taskRewardSfx: number;
  routineRewardSfx: number; lightDuration: number; routineVolume: number; routineModeStatus: number;
  alarmExecuting: number;
}

/** Decode the GLOBAL_STATE snapshot (response 0x02) into raw integer fields. */
export function parseGlobalState(args: Uint8Array): GlobalState {
  const n = nibbles(args);
  while (n.length < 26) n.push(0);
  return {
    operationMode: n[0], activityState: n[1], musicStatus: n[2],
    currentSong: (n[3] << 4) | n[4], currentVolume: n[5], playlistDuration: n[6],
    lightStatus: n[7], lightBrightness: n[8], lightColor: n[9],
    napTimeStatus: n[10], napDuration: n[11], ready2RiseStatus: n[12],
    ready2RiseAlarmStatus: n[13], timePrescaler: n[14], currentStage: n[15],
    clockDisplay: n[16], clockBrightness: n[17], clockFormat: n[18],
    routineMusicStatus: n[19], taskRewardSfx: n[20], routineRewardSfx: n[21],
    lightDuration: n[22], routineVolume: n[23], routineModeStatus: n[24],
    alarmExecuting: n[25],
  };
}

export const responseName = (opcode: number): string =>
  RESPONSES[opcode] ?? "0x" + opcode.toString(16);

/** Decode an MPID plaintext response: strip SSI header, then the FE-frame. */
export function parseResponsePayload(plaintext: Uint8Array): { ok: boolean; opcode?: number; args?: Uint8Array } {
  let d = plaintext;
  if (d.length >= 2 && (d[0] === 0x01 || d[0] === 0x02)) d = d.slice(2);
  const fe = d.indexOf(0xfe);
  if (fe >= 0 && d.length >= fe + 3) {
    d = d.slice(fe);
    const len = d[1];
    const body = d.slice(2, 2 + len);
    return { ok: true, opcode: body[0], args: body.slice(1) };
  }
  return { ok: false };
}

const unbcd = (b: number) => (b >> 4) * 10 + (b & 0x0f);

export function parseDayRoutine(args: Uint8Array) {
  if (args.length !== 14) throw new Error(`a day routine is 14 bytes, got ${args.length}`);
  const time = args[0] === 0xff && args[1] === 0xff ? null : [unbcd(args[0]), unbcd(args[1])];
  const bySteps = new Map<number, number[]>();
  for (const byte of args.slice(2)) {
    if (byte === 0) continue;                 // padding
    const step = byte >> 4;
    if (!bySteps.has(step)) bySteps.set(step, []);
    bySteps.get(step)!.push(byte & 0x0f);
  }
  const steps = [...bySteps.keys()].sort((a, b) => a - b).map((k) => bySteps.get(k)!);
  return { time, steps };
}

export function parseWeeklyTimes(args: Uint8Array) {
  if (args.length !== 14) throw new Error(`weekly times are 14 bytes, got ${args.length}`);
  const out: ([number, number] | null)[] = [];
  for (let i = 0; i < 14; i += 2) {
    const [h, m] = [args[i], args[i + 1]];
    out.push(h === 0xff && m === 0xff ? null : [unbcd(h), unbcd(m)]);
  }
  return out;
}

export function parseR2RAlarms(args: Uint8Array) {
  if (args.length !== 4) throw new Error(`alarm times are 4 bytes, got ${args.length}`);
  const n = nibbles(args);
  return { days: n.slice(0, 7), sfx: n[7] };
}

export function parseRoutineMusicStatus(args: Uint8Array) {
  if (args.length !== 2) throw new Error(`routine music status is 2 bytes, got ${args.length}`);
  return { music: args[0], taskRewards: args[1] >> 4, routineRewards: args[1] & 0x0f };
}

export function parseClockSettings(args: Uint8Array) {
  if (args.length !== 2) throw new Error(`clock settings are 2 bytes, got ${args.length}`);
  const n = nibbles(args);
  return { display: n[1], brightness: n[2], format: n[3] };
}

export function parseCurrentDate(args: Uint8Array) {
  if (args.length !== 4) throw new Error(`current date is 4 bytes, got ${args.length}`);
  return { hour: unbcd(args[0]), minute: unbcd(args[1]), second: unbcd(args[2]), weekday: args[3] };
}

/** Best-effort: the 7-byte layout is unconfirmed, so raw is always included. */
export function parseRoutineTaskStatus(args: Uint8Array) {
  const out: Record<string, unknown> = { raw: hex(args) };
  if (args.length === 7) {
    out.currentStep = args[0];
    out.taskStates = nibbles(args.slice(1));
  }
  return out;
}

const PARSERS: Record<number, (a: Uint8Array) => unknown> = {
  0x13: parseCurrentDate,
  0x22: parseWeeklyTimes,
  0x23: parseWeeklyTimes,
  0x27: parseR2RAlarms,
  0x93: parseRoutineMusicStatus,
  0x94: parseRoutineTaskStatus,
  0x99: parseClockSettings,
};
for (const op of [0x2b, 0x2c, 0x2d, 0x2e, 0x2f, 0x90, 0x91]) PARSERS[op] = parseDayRoutine;

/** Decode a response when its layout is known, else return the raw bytes. */
export function parseResponse(opcode: number, args: Uint8Array): unknown {
  const parser = PARSERS[opcode];
  return parser ? parser(args) : args;
}
