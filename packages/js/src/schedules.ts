/** Strict, lossless schedule codecs; hardware restoration safety is unverified. */
import { DAY_ROUTINE } from "./generated.js";
import { integer, payload } from "./profile.js";

export const DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"] as const;
export type Day = typeof DAYS[number];
export const DAY_ROUTINE_RESPONSES: Record<Day, number> = {
  sunday: 0x2b, monday: 0x2c, tuesday: 0x2d, wednesday: 0x2e,
  thursday: 0x2f, friday: 0x90, saturday: 0x91,
};
export interface ClockTime { readonly hour: number; readonly minute: number }
export interface WeeklyTimes { readonly days: readonly (ClockTime | null)[] }
export interface WeeklyAlarms { readonly days: readonly number[]; readonly sound: number }
export interface RoutineTask { readonly step: number; readonly task: number }
export interface DailyRoutine { readonly time: ClockTime | null; readonly slots: readonly (RoutineTask | null)[] }
export interface RoutineTaskStatus { readonly currentStep: number; readonly taskStates: readonly number[] }

function entries(value: readonly unknown[], length: number): void {
  if (!Array.isArray(value) || value.length !== length) throw new Error(`expected ${length} entries`);
}

function encodeTime(value: ClockTime | null): number[] {
  if (value === null) return [255, 255];
  const hour = integer(value.hour, 0, 23, "hour"), minute = integer(value.minute, 0, 59, "minute");
  return [Math.floor(hour / 10) << 4 | hour % 10, Math.floor(minute / 10) << 4 | minute % 10];
}

function decodeTime(data: Uint8Array): ClockTime | null {
  if (data[0] === 255 && data[1] === 255) return null;
  for (const byte of data) if ((byte >> 4) > 9 || (byte & 15) > 9) throw new Error("invalid BCD time");
  const value = { hour: (data[0] >> 4) * 10 + (data[0] & 15), minute: (data[1] >> 4) * 10 + (data[1] & 15) };
  encodeTime(value);
  return value;
}

export function encodeWeeklyTimes(value: WeeklyTimes): Uint8Array {
  entries(value.days, 7);
  return Uint8Array.from(Array.from(value.days).flatMap(encodeTime));
}

export function decodeWeeklyTimes(data: Uint8Array): WeeklyTimes {
  payload(data, 14);
  return { days: Array.from({ length: 7 }, (_, index) => decodeTime(data.slice(index * 2, index * 2 + 2))) };
}

export function encodeWeeklyAlarms(value: WeeklyAlarms): Uint8Array {
  entries(value.days, 7);
  const values = [...Array.from(value.days, v => integer(v, 0, 10, "alarm")), integer(value.sound, 0, 15, "sound nibble")];
  return Uint8Array.from({ length: 4 }, (_, i) => values[i * 2] << 4 | values[i * 2 + 1]);
}

export function decodeWeeklyAlarms(data: Uint8Array): WeeklyAlarms {
  payload(data, 4);
  const values = Array.from(data).flatMap(b => [b >> 4, b & 15]);
  const value = { days: values.slice(0, 7), sound: values[7] };
  encodeWeeklyAlarms(value);
  return value;
}

export function routineFromSteps(time: ClockTime | null, steps: readonly (readonly number[])[]): DailyRoutine {
  const slots: (RoutineTask | null)[] = [];
  for (const [index, tasks] of steps.entries()) {
    if (tasks.length === 0) throw new Error("routine step must not be empty");
    for (const task of tasks) {
      if (slots.length === 12) throw new Error("routine holds at most twelve tasks");
      slots.push({ step: index + 1, task });
    }
  }
  while (slots.length < 12) slots.push(null);
  const value = { time, slots };
  encodeDailyRoutine(value);
  return value;
}

export function encodeDailyRoutine(value: DailyRoutine): Uint8Array {
  entries(value.slots, 12);
  return Uint8Array.from([...encodeTime(value.time), ...Array.from(value.slots, slot =>
    slot === null ? 0 : integer(slot.step, 1, 12, "step") << 4 | integer(slot.task, 0, 11, "task"))]);
}

export function decodeDailyRoutine(data: Uint8Array): DailyRoutine {
  payload(data, 14);
  const value = { time: decodeTime(data.slice(0, 2)), slots: Array.from(data.slice(2), byte =>
    byte === 0 ? null : { step: byte >> 4, task: byte & 15 }) };
  encodeDailyRoutine(value);
  return value;
}

/** Runtime-only. Task-state enum meanings and current-step sentinels are unknown. */
export function decodeRoutineTaskStatus(data: Uint8Array): RoutineTaskStatus {
  payload(data, 7);
  return { currentStep: data[0], taskStates: Array.from(data.slice(1)).flatMap(b => [b >> 4, b & 15]) };
}

export function encodeRoutineTaskStatus(value: RoutineTaskStatus): Uint8Array {
  entries(value.taskStates, 12);
  const values = Array.from(value.taskStates, v => integer(v, 0, 15, "task state nibble"));
  return Uint8Array.of(integer(value.currentStep, 0, 255, "current step byte"), ...Array.from({ length: 6 }, (_, i) => values[i * 2] << 4 | values[i * 2 + 1]));
}

function dayOpcode(operation: "SET" | "REQUEST", day: Day): number {
  if (!DAYS.includes(day)) throw new Error("unknown routine day");
  return DAY_ROUTINE[operation][day];
}
export const setDayRoutine = (day: Day, routine: DailyRoutine) => Uint8Array.of(dayOpcode("SET", day), ...encodeDailyRoutine(routine));
export const requestDayRoutine = (day: Day) => Uint8Array.of(dayOpcode("REQUEST", day));
export const setR2RTimes = (week: WeeklyTimes) => Uint8Array.of(0x46, ...encodeWeeklyTimes(week));
export const setSleepyTimes = (week: WeeklyTimes) => Uint8Array.of(0x48, ...encodeWeeklyTimes(week));
export const setR2RAlarms = (alarms: WeeklyAlarms) => Uint8Array.of(0x4a, ...encodeWeeklyAlarms(alarms));

export function parseScheduleResponse(opcode: number, args: Uint8Array): WeeklyTimes | WeeklyAlarms | DailyRoutine | RoutineTaskStatus {
  if (opcode === 0x22 || opcode === 0x23) return decodeWeeklyTimes(args);
  if (opcode === 0x27) return decodeWeeklyAlarms(args);
  if (Object.values(DAY_ROUTINE_RESPONSES).includes(opcode)) return decodeDailyRoutine(args);
  if (opcode === 0x94) return decodeRoutineTaskStatus(args);
  throw new Error("unsupported schedule response");
}
