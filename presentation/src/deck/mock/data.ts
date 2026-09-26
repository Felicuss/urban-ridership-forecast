import raw from '../../data/mock.json';
import type { Band } from './ui';

// Что сервис показывает в пятницу 14 ноября 2025: собирает scripts/mock_data.py из API и артефактов.

export interface Span {
  route: number;
  date: string;
  start: number;
  end: number;
  peak: number;
  hour: number;
  hw: number;
  need: number;
  hwMin: number;
  needMin: number;
  stop?: string;
  label?: string;
}

export interface Incident {
  id: string;
  routes: number[];
  start: string;
  end: string;
  minutes: number;
  causeLabel: string;
  location: string;
  inForecast: boolean;
}

export interface MockData {
  date: string;
  dateLabel: string;
  weather: { temp: number[]; precip: number[]; code: number[]; line: string };
  network: { day: Band[]; year: Band[]; matrix: number[][]; matrixFrom: string };
  routes: { route: number; title: string; total: number; hours: number[] }[];
  route17: { day: Band[]; compare: Band[]; perTrip: number[]; spans: Span[]; headway8: number;
    stops: { seq: number; name: string; value: number }[]; ends: [string, string] };
  brief: { total: number; peakHour: number; peak: number; vsWeek: number; top: { route: number; total: number }[];
    crowded: Span[]; events: string[] };
  alert: { date: string; spans: Span[] };
  week: { count: number; routes: number; top: Span[] };
  fleet: { cycle: number; lengthKm: number; byHeadway: Record<string, { vehicles: number; perTrip: number; vehicleHours: number }>;
    scheduleHeadway: number; scheduleVehicles: number; scheduleVehicleHours: number };
  news: { incidents: Incident[]; alpha: number; tryOn: string; incident: string;
    scenario: { events: unknown[]; total: number; baseline: number; deltas: number[]; route17: { p50: number; base: number }[] } };
  board: { route: number; now: number; next: number; headway: number | null; perTrip: number | null }[];
}

export const M = raw as unknown as MockData;
export const ROUTE_HOURS: Record<number, number[]> = Object.fromEntries(M.routes.map((r) => [r.route, r.hours]));
