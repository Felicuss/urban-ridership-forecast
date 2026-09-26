// Строгие типы, с которыми работает интерфейс. Схема OpenAPI помечает поля records необязательными,
// поэтому ответы нормализуются в queries.ts.

export type Level = 'route' | 'stop' | 'segment' | 'network';
export type Granularity = 'hour' | 'day' | 'month';
export type Horizon = 'day' | 'week' | 'month' | 'year';

export type Source = 'fact' | 'forecast' | 'outlook';

export interface CalendarDay {
  date: string;
  dayOfWeek: number;
  dayType: 'workday' | 'saturday' | 'sunday' | 'holiday';
  kind: string;
  dayOff: boolean;
  holiday: string | null;
  source: Source;
}

export interface Point {
  source: Source;
  period: string;
  p50: number;
  p10: number;
  p90: number;
  /** Посадки в самый загруженный час внутри точки за сутки или месяц; у почасовых точек нет. */
  peak?: number | null;
  /** Этот час: 2025-11-14T08:00. */
  peakAt?: string | null;
  baseline?: number;
  delta?: number;
  deltaPct?: number | null;
}

export interface Series {
  target: { level: string; id: string; name: string; estimate: boolean };
  granularity: Granularity;
  from: string;
  to: string;
  points: Point[];
  total: Point;
  notes: string[];
  scenario: boolean;
}

export interface Coefficient {
  key: string;
  label: string;
  group: string;
  type: 'number' | 'integer' | 'boolean' | 'date' | 'datetime';
  defaultValue: number | boolean | string;
  min: number | string | null;
  max: number | string | null;
  step: number | null;
  source: string;
}

export type CoefficientValue = number | boolean | string;

export interface ScenarioEvent {
  route?: number;
  from: string;
  to: string;
  hours?: string;
  multiplier: number;
  label?: string;
}

export interface Scenario {
  coefficients: Record<string, CoefficientValue>;
  events: ScenarioEvent[];
}

export interface Stop {
  id: string;
  name: string;
  lat: number;
  lon: number;
  source: string;
  routes: number[];
}

export interface RouteInfo {
  route: number;
  stops: number;
  forecastTotal: number;
  forecastPerDay: number;
}

export interface RouteStop {
  direction: number;
  seq: number;
  stopId: string;
  name: string;
  lat: number;
  lon: number;
  share: number;
}

export interface NetworkLoad {
  source: Source;
  date: string;
  hours: number[];
  routes: Map<number, number[]>;
  stops: Map<string, number[]>;
}

export interface Meta {
  modelVersion: string;
  gitCommit: string;
  generatedAt: string;
  forecastOrigin: string;
  horizonFrom: string;
  horizonTo: string;
  timelineFrom: string;
  timelineTo: string;
  routes: number[];
  leaderboardWapeScore: number;
  defaultSubmission: string;
  quality: BacktestQuality;
  applicability: string[];
}

export interface BacktestQuality {
  scheme: string;
  folds: Record<string, string>;
  wape_score: Record<Granularity, Record<string, number>>;
  interval_nominal: number;
  interval_coverage_leave_one_fold_out: Record<Granularity, number>;
  leaderboard_wape_score: number;
  year: {
    seasonal_index: Record<string, number>;
    corridor: number;
    index_check_city_tram: { months: number; mape_pct: number; mean_error_pct: number; max_abs_error_pct: number };
  };
  stops: { stops: number; osm_matched_to_reference: number; osm_stops: number };
}

export interface GapPeriod {
  route: number;
  from: string;
  to: string;
  days: number;
  day_kinds: string;
  fact: number;
  expected: number;
  restored: number;
  reason: string;
  type: string;
  source: string;
}

export interface Factors {
  calendar: { date: string; dow: number; day_type: string; day_off: boolean; holiday: string | null }[];
  weather: {
    dates: string[];
    source: string;
    temp: (number | null)[][];
    precip: (number | null)[][];
    snow: (number | null)[][];
    wind: (number | null)[][];
    code: (number | null)[][];
    cloud: (number | null)[][];
  };
  traffic: { source: string; months: string[]; score: number[]; pct: (number | null)[] };
  city_ridership: { source: string; months: string[]; per_day: number[] };
  schedule: {
    source: string;
    fetched_at: string;
    routes: Record<string, {
      title: string;
      page: string;
      weekday?: { headway_min: (number | null)[]; service_from: string; service_to: string };
      weekend?: { headway_min: (number | null)[]; service_from: string; service_to: string };
    }>;
  };
  history: { source: string; dates: string[]; routes: Record<string, number[]> };
  /** Пропуски факта 2025: период, причина со ссылкой и восстановленные по прошлым неделям посадки по часам. */
  gaps?: {
    rule: string;
    restore: string;
    periods: GapPeriod[];
    restored: Record<string, Record<string, number[]>>;
  };
  /** Проверки оборудования вне часов работы маршрутов: отброшены из факта. */
  equipment_checks?: {
    rule: string;
    window: string;
    cells: number;
    validations: number;
    share_pct: number;
    off_hours: Record<string, number[]>;
  };
  events: {
    start: string;
    end: string | null;
    routes: string;
    days: string;
    type: string;
    description: string;
    source: string;
    effect: string | null;
  }[];
}

export interface NetworkFeatureProps {
  kind: 'path' | 'track' | 'stop';
  route?: number;
  direction?: number;
  length_m?: number;
  stop_id?: string;
  name?: string;
  routes?: number[];
  source?: string;
}

export interface NetworkGeoJson {
  type: 'FeatureCollection';
  features: {
    type: 'Feature';
    geometry: { type: 'LineString' | 'MultiLineString' | 'Point'; coordinates: unknown };
    properties: NetworkFeatureProps;
  }[];
}
