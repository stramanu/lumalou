// AUTO-GENERATED from spec/protocol.json by tools/codegen.py. Do not edit.

export const GATT = {
  "service": "4cea0001-c678-4202-b5d3-712dbb5e5b14",
  "characteristics": {
    "tx": "4cea0002-c678-4202-b5d3-712dbb5e5b14",
    "rx": "4cea0003-c678-4202-b5d3-712dbb5e5b14",
    "factory": "4cea0004-c678-4202-b5d3-712dbb5e5b14",
    "session": "4cea0005-c678-4202-b5d3-712dbb5e5b14"
  },
  "blacklist": {
    "dfuService": "00001530-1212-efde-1523-785feabcd123",
    "note": "Nordic DFU / firmware update service. Never write to it."
  }
} as const;

export const COMMANDS = {
  "SET_GLOBAL_STATE": 1,
  "SET_GLOBAL_ON": 3,
  "SET_CURRENT_DATE": 48,
  "REQUEST_CURRENT_DATE": 49,
  "SEND_PAIRING_COMPLETE": 52,
  "REQUEST_TOYIC_FW_VERSION": 53,
  "SET_VOLUME": 55,
  "TURN_OFF_AUDIO": 56,
  "REQUEST_VOLUME": 57,
  "SET_LED_BRIGHTNESS": 58,
  "REQUEST_LED_BRIGHTNESS": 59,
  "SET_LIGHT_COLOR": 60,
  "REQUEST_LIGHT_COLOR": 61,
  "TURN_OFF_CLOUD_BACKLIGHT": 62,
  "PLAY_AUDIO": 63,
  "SET_MUSIC_PLAYLIST": 64,
  "REQUEST_MUSIC_PLAYLIST": 65,
  "SET_PLAYLIST_DURATION": 66,
  "REQUEST_PLAYLIST_DURATION": 67,
  "SET_R2R_STATUS": 68,
  "REQUEST_R2R_STATUS": 69,
  "SET_R2R_TIMES": 70,
  "REQUEST_R2R_TIMES": 71,
  "SET_SLEEPY_TIMES": 72,
  "REQUEST_SLEEPY_TIMES": 73,
  "SET_R2R_ALARMS": 74,
  "REQUEST_R2R_ALARM_STATUS": 75,
  "REQUEST_R2R_ALARMS": 76,
  "START_NAP_TIME": 77,
  "REQUEST_CURRENT_NAP_TIME_STATUS": 78,
  "SET_NAP_TIME_ALARM": 79,
  "REQUEST_NAP_TIME_ALARM_STATUS": 80,
  "REQUEST_NAP_TIME_ALARM": 81,
  "SET_TIME_PRESCALER": 82,
  "REQUEST_GLOBAL_STATE": 83,
  "REQUEST_SONG_PLAYING": 85,
  "SET_ROUTINE_MODE_STATUS": 88,
  "REQUEST_ROUTINE_MODE_STATUS": 89,
  "SET_ROUTINE_TASK_STATUS": 104,
  "SET_ROUTINE_MUSIC_STATUS": 105,
  "REQUEST_ROUTINE_MUSIC_STATUS": 106,
  "ROUTINE_CONTROL_COMMAND": 107,
  "SET_SOOTHER_MODE_LIGHT_DURATION": 108,
  "REQUEST_SOOTHER_MODE_LIGHT_DURATION": 109,
  "REQUEST_OPERATION_MODE": 114,
  "REQUEST_TIME_PRESCALER": 115,
  "REQUEST_ACTIVITY_STATE": 116,
  "REQUEST_CURRENT_STAGE": 117,
  "REQUEST_TRANSMISSION_MODE": 118,
  "SET_ROUTINE_MODE_VOLUME": 119,
  "REQUEST_ROUTINE_MODE_VOLUME": 120,
  "SET_CLOCK_SETTINGS": 121,
  "REQUEST_CLOCK_SETTINGS": 122,
  "START_ROUTINE_MODE": 123
} as const;
export const DAY_ROUTINE = {
  "SET": {
    "sunday": 90,
    "monday": 92,
    "tuesday": 94,
    "wednesday": 96,
    "thursday": 98,
    "friday": 100,
    "saturday": 102
  },
  "REQUEST": {
    "sunday": 91,
    "monday": 93,
    "tuesday": 95,
    "wednesday": 97,
    "thursday": 99,
    "friday": 101,
    "saturday": 103
  }
} as const;
export const RESPONSES: Record<number, string> = { 2: "GLOBAL_STATE", 17: "OTA_COMPLETE", 18: "TOYIC_FW_VERSION", 19: "CURRENT_DATE", 20: "CURRENT_SONG", 21: "CURRENT_VOLUME", 22: "LIGHT_STATUS", 23: "LIGHT_BRIGHTNESS", 24: "LIGHT_COLOR", 25: "CURRENT_PLAYLIST", 26: "AUDIO_TIMER_DURATION", 27: "TIMER_ABOUT_TO_EXPIRE", 28: "NAP_TIME_STATUS", 29: "TRANSMISSION_MODE", 30: "OPERATION_MODE", 31: "ACTIVITY_STATE", 32: "CURRENT_STAGE", 33: "READY_TO_RISE_STATUS", 34: "READY_TO_RISE_TIMES", 35: "SLEEPY_TIME_TIMES", 36: "NAP_TIME_ALARM_STATUS", 37: "NAP_TIME_ALARM_TIME", 38: "READY_TO_RISE_ALARM_STATUS", 39: "READY_TO_RISE_ALARM_TIMES", 40: "TIME_PRESCALER", 43: "SUNDAY_ROUTINE", 44: "MONDAY_ROUTINE", 45: "TUESDAY_ROUTINE", 46: "WEDNESDAY_ROUTINE", 47: "THURSDAY_ROUTINE", 144: "FRIDAY_ROUTINE", 145: "SATURDAY_ROUTINE", 146: "ROUTINE_MODE_STATUS", 147: "ROUTINE_MUSIC_STATUS", 148: "ROUTINE_TASK_STATUS", 149: "LIGHT_DURATION", 152: "ROUTINE_VOLUME_LEVEL", 153: "CLOCK_SETTINGS" };

export const Color = { WARM: 0, RED: 1, YELLOW: 2, ORANGE: 3, GREEN: 4, BLUE: 5, PURPLE: 6, NIGHT_LIGHT: 7, COOL: 8, RAINBOW: 9 } as const;
export type Color = (typeof Color)[keyof typeof Color];

export const Audio = { SLEEP_PLAYLIST: 0, CUSTOM_PLAYLIST: 1, PINK_NOISE: 2, OCEAN: 3, RAIN: 4, BROWN_NOISE: 5, NATURE: 6, HIGHWAY: 7 } as const;
export type Audio = (typeof Audio)[keyof typeof Audio];

export const Song = { NO_SONG: 0, SLEEP_BABY_SLEEP: 1, HOUR_GLASS: 2, FRERE_JACQUES: 3, HOW_LOVELY_THE_EVENING: 4, TARREGA_LAGRIMA: 5, WHATS_THE_MATTER_DEAR: 6, SUO_GAN: 7, WATER_COLOR_DREAMS: 8, DANCE_OF_THE_JELLYFISH: 9, INSIDE_THE_BUBBLE: 10, PAPER_KITES: 11, CRICKETS_IN_SPACE: 12, PINK_NOISE: 13, OCEAN: 14, RAIN: 15, BROWN_NOISE: 16, NATURE: 17, HIGHWAY: 18 } as const;
export type Song = (typeof Song)[keyof typeof Song];

export const LightDuration = { MIN_15: 0, MIN_30: 1, MIN_60: 2, MIN_90: 3, CONTINUOUS: 4, MIN_1: 5 } as const;
export type LightDuration = (typeof LightDuration)[keyof typeof LightDuration];

export const PlaylistDuration = { MIN_15: 0, MIN_30: 1, MIN_60: 2, MIN_90: 3, MIN_120: 4, CONTINUOUS: 5, MIN_1: 6 } as const;
export type PlaylistDuration = (typeof PlaylistDuration)[keyof typeof PlaylistDuration];

export const NapDuration = { INACTIVE: 0, MIN_15: 1, MIN_30: 2, MIN_45: 3, MIN_60: 4, MIN_75: 5, MIN_90: 6, MIN_105: 7, MIN_120: 8, MIN_150: 9, MIN_180: 10, MIN_1: 11 } as const;
export type NapDuration = (typeof NapDuration)[keyof typeof NapDuration];

export const Alarm = { ACTIVE: 0, AFTER_15: 1, AFTER_30: 2, AFTER_45: 3, AFTER_60: 4, AFTER_75: 5, AFTER_90: 6, AFTER_105: 7, AFTER_120: 8, INACTIVE: 9, AFTER_1: 10 } as const;
export type Alarm = (typeof Alarm)[keyof typeof Alarm];

export const RoutineControl = { COMPLETE_TASK: 0, PREV_TASK: 1, RESTART_SEQUENCE: 2, COMPLETE_SEQUENCE: 3, CANCEL: 4 } as const;
export type RoutineControl = (typeof RoutineControl)[keyof typeof RoutineControl];

export const OperationMode = { SOOTHER: 0, DAYTIME_AWAKE: 2, SLEEPY_TIME: 3, PAIRING: 4, FIRMWARE_UPDATE: 5, NAPTIME: 6, ROUTINE: 7 } as const;
export type OperationMode = (typeof OperationMode)[keyof typeof OperationMode];

export const Stage = { NONE: 0, READY: 1, SETTLE: 2, SLEEP: 3 } as const;
export type Stage = (typeof Stage)[keyof typeof Stage];

export const ClockFormat = { H12: 0, H24: 1 } as const;
export type ClockFormat = (typeof ClockFormat)[keyof typeof ClockFormat];

