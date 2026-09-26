import { create } from 'zustand';
import type { CoefficientValue, Horizon, Scenario, ScenarioEvent } from '../api/types';
import { HORIZON_START, MINUTES_PER_DAY, TIMELINE_MINUTES, clampMinute, dayOf, nowOnTimeline } from '../lib/time';

// Состояние интерфейса. Время - минуты от 01.11.2025 00:00, из него карта берёт дату и час,
// трамваи - своё положение на линии. Флаги слоёв и настроек переживают перезагрузку страницы.

export type RightTab = 'forecast' | 'shift' | 'scenario' | 'factors' | 'model';

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
  satellite: boolean;
}

export const FLAG_LABELS: Record<keyof Flags, { label: string; hint: string }> = {
  heat: { label: 'Тепловая карта', hint: 'Посадки на остановках в выбранный час' },
  lines: { label: 'Загрузка линий', hint: 'Толщина линии - посадки маршрута в выбранный час' },
  stops: { label: 'Остановки', hint: 'Точки остановок, размер - посадки в час' },
  trams: { label: 'Трамваи', hint: 'Вагоны на линиях с интервалом по расписанию transport.mos.ru' },
  metro: { label: 'Метро', hint: 'Линии и станции метро из OpenStreetMap' },
  buildings: { label: 'Объёмные дома', hint: 'Высоты зданий из OpenStreetMap при приближении' },
  weather: { label: 'Погода', hint: 'Осадки там, где они идут, и температура по районам, Open-Meteo' },
  daylight: { label: 'Свет по времени суток', hint: 'Карта темнеет ночью и светлеет днём по высоте солнца' },
  labels: { label: 'Подписи', hint: 'Названия остановок на карте' },
  satellite: { label: 'Спутник', hint: 'Снимки Esri World Imagery вместо схемы города' },
  motion: { label: 'Анимации', hint: 'Плавные переходы интерфейса' },
  intro: { label: 'Заставка', hint: 'Трамвай при загрузке, потом он уезжает за край экрана' },
};

const DEFAULT_FLAGS: Flags = {
  intro: true, motion: true, heat: true, stops: true, lines: true, metro: false, buildings: true, trams: true,
  weather: true, daylight: true, labels: true, satellite: false,
};

const FLAGS_KEY = 'tram-ui.flags.v1';
const HIDDEN_KEY = 'tram-ui.hidden-routes.v2';
/** №5 запущен только 16.12.2025, команда от него отказалась: по умолчанию скрыт, включается в фильтре маршрутов. */
const DEFAULT_HIDDEN = [5];
const ALERTS_KEY = 'tram-ui.alerts.v1';

/** Подписка на оповещение: маршрут или его участок и порог посадок на рейс на следующий день. */
export interface AlertRule {
  id: string;
  route: number;
  segment: (Segment & { label: string }) | null;
  limit: number;
}

function loadAlerts(): AlertRule[] {
  try {
    const raw = localStorage.getItem(ALERTS_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed)
      ? parsed.filter((a): a is AlertRule => typeof a === 'object' && a != null && Number.isInteger((a as AlertRule).route)
        && typeof (a as AlertRule).limit === 'number')
      : [];
  } catch {
    return [];
  }
}

function saveAlerts(alerts: AlertRule[]): void {
  try {
    localStorage.setItem(ALERTS_KEY, JSON.stringify(alerts));
  } catch {
    // приватный режим браузера: подписки живут до перезагрузки
  }
}

function loadHidden(): number[] {
  try {
    const raw = localStorage.getItem(HIDDEN_KEY);
    if (raw == null) return DEFAULT_HIDDEN;
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((r): r is number => Number.isInteger(r)) : DEFAULT_HIDDEN;
  } catch {
    return DEFAULT_HIDDEN;
  }
}

function saveHidden(hidden: number[]): void {
  try {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify(hidden));
  } catch {
    // приватный режим браузера: фильтр живёт до перезагрузки
  }
}

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

/** Не больше 20 событий в сценарии: столько принимает сервис. */
export const MAX_EVENTS = 20;

/** Вид карты: сверху или в перспективе; объёмные дома включаются отдельно. */
export type ViewMode = 'top' | 'perspective';

/** Участок маршрута: направление и первая и последняя остановки по ходу движения. */
export interface Segment {
  direction: number;
  from: string;
  to: string;
}

/** Стартовое время: прогнозная неделя 10-16 ноября 2025 с текущим временем суток и днём недели. */
function startMinute(): number {
  const now = nowOnTimeline();
  const dow = (new Date().getDay() + 6) % 7;
  return (dayOf(HORIZON_START) + 9 + dow) * MINUTES_PER_DAY + (now % MINUTES_PER_DAY);
}
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
  /** Когда «Сейчас» выключился из-за ручного выбора времени: по нему показывается плашка. */
  nowNotice: number | null;
  route: number | null;
  stop: string | null;
  segment: Segment | null;
  /** Панель остановок выбранного маршрута справа от списка маршрутов. */
  stopsOpen: boolean;
  setStopsOpen: (open: boolean) => void;
  /** Маршрут по станциям и дням поверх карты. */
  matrixOpen: boolean;
  setMatrixOpen: (open: boolean) => void;
  horizon: Horizon;
  tab: RightTab;
  scenario: Scenario;
  flags: Flags;
  /** Маршруты, скрытые на карте фильтром. */
  hiddenRoutes: number[];
  toggleRoute: (route: number) => void;
  setHiddenRoutes: (routes: number[]) => void;
  settingsOpen: boolean;
  /** Тур по разделам: сам открывается при первом входе, потом по кнопке «?» в верхней строке. */
  tourOpen: boolean;
  setTourOpen: (open: boolean) => void;
  alerts: AlertRule[];
  addAlert: (rule: Omit<AlertRule, 'id'>) => void;
  removeAlert: (id: string) => void;
  /** Режим табло на большой экран диспетчерской. */
  boardOpen: boolean;
  setBoardOpen: (open: boolean) => void;
  /** День шкалы, с которым сравнивается прогноз; null - без сравнения. */
  compareDay: number | null;
  setCompareDay: (day: number | null) => void;
  viewMode: ViewMode;
  setViewMode: (v: ViewMode) => void;
  /** Карта повёрнута: только тогда видна кнопка «На север». */
  rotated: boolean;
  setRotated: (rotated: boolean) => void;
  /** Ручной выбор минуты: выключает режим «Сейчас». */
  setMinute: (m: number) => void;
  /** Ход часов симуляции: режим «Сейчас» не трогает. */
  tick: (m: number) => void;
  dismissNowNotice: () => void;
  setDay: (day: number) => void;
  setHour: (hour: number) => void;
  togglePlay: () => void;
  setSpeed: (s: Speed) => void;
  setFollowNow: (on: boolean) => void;
  selectRoute: (route: number | null) => void;
  selectStop: (stop: string | null) => void;
  setSegment: (segment: Segment | null) => void;
  setHorizon: (h: Horizon) => void;
  setTab: (t: RightTab) => void;
  setCoefficient: (key: string, value: CoefficientValue | undefined) => void;
  addEvent: (e: ScenarioEvent) => void;
  removeEvent: (index: number) => void;
  resetScenario: () => void;
  setFlag: (key: keyof Flags, value: boolean) => void;
  setSettingsOpen: (open: boolean) => void;
}

const wrapMinute = (m: number) => ((m % TIMELINE_MINUTES) + TIMELINE_MINUTES) % TIMELINE_MINUTES;

export const useStore = create<State>((set, get) => {
  // любой ручной выбор времени выключает «Сейчас», и интерфейс об этом говорит
  const manual = (patch: Partial<State>): Partial<State> =>
    get().followNow ? { ...patch, followNow: false, nowNotice: Date.now() } : patch;
  return {
    ride: null,
    rideProgress: null,
    startRide: (route, direction, speed = 40) => set({
      ride: { route, direction, speed, startedAt: performance.now(), hour: Math.floor((get().minute % 1440) / 60) },
      rideProgress: { passed: 0, boarded: 0, stopName: '', finished: false },
      route,
    }),
    stopRide: () => set({ ride: null, rideProgress: null }),
    setRideProgress: (rideProgress) => set({ rideProgress }),
    minute: startMinute(),
    playing: false,
    speed: 60,
    followNow: false,
    nowNotice: null,
    route: null,
    stop: null,
    segment: null,
    stopsOpen: false,
    setStopsOpen: (stopsOpen) => set({ stopsOpen }),
    matrixOpen: false,
    setMatrixOpen: (matrixOpen) => set({ matrixOpen }),
    horizon: 'day',
    tab: 'forecast',
    scenario: { coefficients: {}, events: [] },
    flags: loadFlags(),
    hiddenRoutes: loadHidden(),
    toggleRoute: (route) => {
      const hidden = get().hiddenRoutes;
      const next = hidden.includes(route) ? hidden.filter((r) => r !== route) : [...hidden, route];
      saveHidden(next);
      set({ hiddenRoutes: next });
    },
    setHiddenRoutes: (routes) => {
      saveHidden(routes);
      set({ hiddenRoutes: routes });
    },
    settingsOpen: false,
    tourOpen: false,
    setTourOpen: (tourOpen) => set({ tourOpen }),
    alerts: loadAlerts(),
    addAlert: (rule) => {
      const next = [...get().alerts, { ...rule, id: `${Date.now().toString(36)}-${rule.route}` }];
      saveAlerts(next);
      set({ alerts: next });
    },
    removeAlert: (id) => {
      const next = get().alerts.filter((a) => a.id !== id);
      saveAlerts(next);
      set({ alerts: next });
    },
    boardOpen: false,
    setBoardOpen: (boardOpen) => set({ boardOpen }),
    compareDay: null,
    setCompareDay: (compareDay) => set({ compareDay }),
    viewMode: 'perspective',
    setViewMode: (viewMode) => set({ viewMode }),
    rotated: false,
    setRotated: (rotated) => set({ rotated }),
    setMinute: (m) => set(manual({ minute: wrapMinute(m) })),
    tick: (m) => set({ minute: wrapMinute(m) }),
    dismissNowNotice: () => set({ nowNotice: null }),
    setDay: (day) => set(manual({ minute: clampMinute(day * MINUTES_PER_DAY + (get().minute % MINUTES_PER_DAY)) })),
    setHour: (hour) => set(manual({
      minute: clampMinute(Math.floor(get().minute / MINUTES_PER_DAY) * MINUTES_PER_DAY + hour * 60),
    })),
    togglePlay: () => set(manual({ playing: !get().playing })),
    setSpeed: (speed) => set(manual({ speed })),
    setFollowNow: (on) => set(on ? { followNow: true, playing: false, speed: 1, minute: nowOnTimeline(), nowNotice: null }
      : { followNow: false }),
    selectRoute: (route) => set(route == null ? { route, stop: null, segment: null, stopsOpen: false, matrixOpen: false }
      : { route, stop: null, segment: null }),
    selectStop: (stop) => set({ stop, segment: null }),
    setSegment: (segment) => set({ segment, stop: null }),
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
  };
});

export function isDefaultScenario(s: Scenario): boolean {
  return Object.keys(s.coefficients).length === 0 && s.events.length === 0;
}
