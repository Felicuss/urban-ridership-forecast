import { create } from 'zustand';
import type { CoefficientValue, Horizon, Scenario, ScenarioEvent } from '../api/types';
import { HORIZON_MINUTES, MINUTES_PER_DAY, clampMinute, nowInHorizon } from '../lib/time';

// Состояние интерфейса. Время - минуты от 01.11.2025 00:00, из него карта берёт дату и час,
// трамваи - своё положение на линии. Флаги слоёв и настроек переживают перезагрузку страницы.

export type RightTab = 'forecast' | 'scenario' | 'factors' | 'model';

export interface Flags {
  intro: boolean;
  motion: boolean;
  heat: boolean;
  stops: boolean;
  lines: boolean;
  metro: boolean;
  buildings: boolean;
  trams: boolean;
  weather: boolean;
  daylight: boolean;
  labels: boolean;
}

export const FLAG_LABELS: Record<keyof Flags, { label: string; hint: string }> = {
  heat: { label: 'Тепловая карта', hint: 'Посадки на остановках в выбранный час' },
  lines: { label: 'Загрузка линий', hint: 'Толщина линии - посадки маршрута в выбранный час' },
  stops: { label: 'Остановки', hint: 'Точки остановок, размер - посадки в час' },
  trams: { label: 'Трамваи', hint: 'Вагоны на линиях с интервалом по расписанию transport.mos.ru' },
  metro: { label: 'Метро', hint: 'Линии и станции метро из OpenStreetMap' },
  buildings: { label: 'Объёмные дома', hint: 'Высоты зданий из OpenStreetMap при приближении' },
  weather: { label: 'Погода', hint: 'Температура и осадки в выбранный час по данным Open-Meteo' },
  daylight: { label: 'Свет по времени суток', hint: 'Карта темнеет ночью и светлеет днём по высоте солнца' },
  labels: { label: 'Подписи', hint: 'Названия остановок на карте' },
  motion: { label: 'Анимации', hint: 'Плавные переходы интерфейса' },
  intro: { label: 'Заставка', hint: 'Трамвай при загрузке и облака над картой' },
};

const DEFAULT_FLAGS: Flags = {
  intro: true, motion: true, heat: true, stops: true, lines: true, metro: false, buildings: true, trams: true,
  weather: true, daylight: true, labels: true,
};

const FLAGS_KEY = 'tram-ui.flags.v1';

function loadFlags(): Flags {
  try {
    const raw = localStorage.getItem(FLAGS_KEY);
    return raw ? { ...DEFAULT_FLAGS, ...(JSON.parse(raw) as Partial<Flags>) } : DEFAULT_FLAGS;
  } catch {
    return DEFAULT_FLAGS;
  }
}

function saveFlags(flags: Flags): void {
  try {
    localStorage.setItem(FLAGS_KEY, JSON.stringify(flags));
  } catch {
    // приватный режим браузера: флаги живут до перезагрузки
  }
}

export const SPEEDS = [1, 60, 300, 900, 3600] as const;
export type Speed = (typeof SPEEDS)[number];

/** Поездка одного трамвая по маршруту: камера следует за ним, на остановках копятся посадки. */
export interface Ride {
  route: number;
  direction: number;
  startedAt: number;
  speed: number;
  hour: number;
}

export interface RideProgress {
  passed: number;
  boarded: number;
  stopName: string;
  finished: boolean;
}

interface State {
  ride: Ride | null;
  rideProgress: RideProgress | null;
  startRide: (route: number, direction: number, speed?: number) => void;
  stopRide: () => void;
  setRideProgress: (p: RideProgress) => void;
  minute: number;
  playing: boolean;
  speed: Speed;
  followNow: boolean;
  route: number | null;
  stop: string | null;
  horizon: Horizon;
  tab: RightTab;
  scenario: Scenario;
  flags: Flags;
  settingsOpen: boolean;
  setMinute: (m: number) => void;
  setDay: (day: number) => void;
  setHour: (hour: number) => void;
  togglePlay: () => void;
  setSpeed: (s: Speed) => void;
  setFollowNow: (on: boolean) => void;
  selectRoute: (route: number | null) => void;
  selectStop: (stop: string | null) => void;
  setHorizon: (h: Horizon) => void;
  setTab: (t: RightTab) => void;
  setCoefficient: (key: string, value: CoefficientValue | undefined) => void;
  addEvent: (e: ScenarioEvent) => void;
  removeEvent: (index: number) => void;
  resetScenario: () => void;
  setFlag: (key: keyof Flags, value: boolean) => void;
  setSettingsOpen: (open: boolean) => void;
}

export const useStore = create<State>((set, get) => ({
  ride: null,
  rideProgress: null,
  startRide: (route, direction, speed = 40) => set({
    ride: { route, direction, speed, startedAt: performance.now(), hour: Math.floor((get().minute % 1440) / 60) },
    rideProgress: { passed: 0, boarded: 0, stopName: '', finished: false },
    route,
  }),
  stopRide: () => set({ ride: null, rideProgress: null }),
  setRideProgress: (rideProgress) => set({ rideProgress }),
  minute: nowInHorizon(),
  playing: false,
  speed: 60,
  followNow: false,
  route: null,
  stop: null,
  horizon: 'day',
  tab: 'forecast',
  scenario: { coefficients: {}, events: [] },
  flags: loadFlags(),
  settingsOpen: false,
  setMinute: (m) => set({ minute: ((m % HORIZON_MINUTES) + HORIZON_MINUTES) % HORIZON_MINUTES }),
  setDay: (day) => set({ minute: clampMinute(day * MINUTES_PER_DAY + (get().minute % MINUTES_PER_DAY)),
    followNow: false }),
  setHour: (hour) => set({
    minute: clampMinute(Math.floor(get().minute / MINUTES_PER_DAY) * MINUTES_PER_DAY + hour * 60),
    followNow: false,
  }),
  togglePlay: () => set({ playing: !get().playing, followNow: false }),
  setSpeed: (speed) => set({ speed }),
  setFollowNow: (on) => set(on ? { followNow: true, playing: false, speed: 1, minute: nowInHorizon() }
    : { followNow: false }),
  selectRoute: (route) => set({ route, stop: null }),
  selectStop: (stop) => set({ stop }),
  setHorizon: (horizon) => set({ horizon }),
  setTab: (tab) => set({ tab }),
  setCoefficient: (key, value) => {
    const next = { ...get().scenario.coefficients };
    if (value === undefined) delete next[key];
    else next[key] = value;
    set({ scenario: { ...get().scenario, coefficients: next } });
  },
  addEvent: (e) => set({ scenario: { ...get().scenario, events: [...get().scenario.events, e] } }),
  removeEvent: (index) => set({
    scenario: { ...get().scenario, events: get().scenario.events.filter((_, i) => i !== index) },
  }),
  resetScenario: () => set({ scenario: { coefficients: {}, events: [] } }),
  setFlag: (key, value) => {
    const flags = { ...get().flags, [key]: value };
    saveFlags(flags);
    set({ flags });
  },
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
}));

export function isDefaultScenario(s: Scenario): boolean {
  return Object.keys(s.coefficients).length === 0 && s.events.length === 0;
}
