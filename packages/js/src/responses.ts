// Decode device responses. Values are raw integers (canonical, matches the spec).
import { RESPONSES } from "./generated.js";

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
