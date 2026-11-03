/** Source-backed SET layouts. These are NOT schemas for 0x19/0x93/0x99 replies. */
export function integer(value: number, low: number, high: number, name: string): number {
  if (!Number.isInteger(value) || value < low || value > high) throw new Error(`${name} must be an integer from ${low} to ${high}`);
  return value;
}

export function payload(data: Uint8Array, length: number): Uint8Array {
  if (!(data instanceof Uint8Array) || data.length !== length) throw new Error(`payload must be exactly ${length} bytes`);
  return data;
}

export interface MusicPlaylist { readonly slots: readonly number[] }
export interface ClockSettings { readonly displayOn: boolean; readonly brightness: number; readonly format: number }
/** Byte/nibble ranges only; music and rewards are not asserted to be booleans or song IDs. */
export interface RoutineMusicSettings { readonly music: number; readonly taskReward: number; readonly routineReward: number }

export function playlistFromSongs(songs: readonly number[]): MusicPlaylist {
  const slots: number[] = [];
  for (const song of songs) {
    integer(song, 0, 12, "playlist song");
    if (song) {
      if (slots.length === 12) throw new Error("playlist holds at most twelve songs");
      slots.push(song);
    }
  }
  return { slots: [...slots, ...Array(12 - slots.length).fill(0)] };
}

export function encodeMusicPlaylist(value: MusicPlaylist): Uint8Array {
  if (!Array.isArray(value.slots) || value.slots.length !== 12) throw new Error("playlist needs twelve slots");
  return Uint8Array.from(Array.from(value.slots, v => integer(v, 0, 12, "playlist song")));
}

export function decodeMusicPlaylistSet(data: Uint8Array): MusicPlaylist {
  const value = { slots: Array.from(payload(data, 12)) };
  encodeMusicPlaylist(value);
  return value;
}

export function encodeClockSettings(value: ClockSettings): Uint8Array {
  if (typeof value.displayOn !== "boolean") throw new Error("displayOn must be boolean");
  return Uint8Array.of(Number(value.displayOn), integer(value.brightness, 0, 9, "clock brightness") << 4 | integer(value.format, 0, 1, "clock format"));
}

export function decodeClockSettingsSet(data: Uint8Array): ClockSettings {
  payload(data, 2);
  if (data[0] !== 0 && data[0] !== 1) throw new Error("unsupported clock SET reserved bits or display value");
  const value = { displayOn: Boolean(data[0]), brightness: data[1] >> 4, format: data[1] & 15 };
  encodeClockSettings(value);
  return value;
}

export function encodeRoutineMusicSettings(value: RoutineMusicSettings): Uint8Array {
  return Uint8Array.of(integer(value.music, 0, 255, "routine music byte"), integer(value.taskReward, 0, 15, "task reward nibble") << 4 | integer(value.routineReward, 0, 15, "routine reward nibble"));
}

export function decodeRoutineMusicSettingsSet(data: Uint8Array): RoutineMusicSettings {
  payload(data, 2);
  return { music: data[0], taskReward: data[1] >> 4, routineReward: data[1] & 15 };
}

/** Caller supplies independently established length. No response schema is inferred. */
export class OpaqueBlock {
  readonly length: number;
  private readonly bytes: Uint8Array;
  constructor(data: Uint8Array, length: number) {
    this.length = integer(length, 0, 254, "payload length");
    this.bytes = Uint8Array.from(payload(data, length));
  }
  get data(): Uint8Array { return this.bytes.slice(); }
}
