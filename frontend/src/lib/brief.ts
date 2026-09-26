import type { CalendarDay, Factors, NetworkLoad, RouteStop, ScenarioEvent } from '../api/types';
import { bottlenecks, intervalAdvice, type Bottleneck } from './dispatch';
import { fmt1, fmtCompact, fmtPct, fmtTemp } from './format';
import { dayLabel, isoDate } from './time';
import { SNOW_CM_TO_MM } from './weatherGrid';

// Утренняя сводка смены: день, погода, пики сети, где тесно и какие события. Считается из прогноза,
// расписания и погоды без запросов к модели; текст копируется в рабочий чат одной кнопкой.

/** Погода центра за день: осадки дождём в мм, снегом в см, как отдаёт Open-Meteo. */
export interface DayWeatherSeries {
  temp: (number | null)[];
  rain: (number | null)[];
  snow: (number | null)[];
}

export interface Brief {
  title: string;
  dayKind: string;
  source: string;
  weather: string | null;
  total: number;
  peakHour: number;
  peak: number;
  /** Разница с тем же днём недели неделей раньше, проценты; null - сравнить не с чем. */
  vsWeek: number | null;
  top: { route: number; total: number; share: number }[];
  crowded: Bottleneck[];
  events: string[];
  text: string;
}

export interface BriefInput {
  day: number;
  calendar: CalendarDay | undefined;
  load: NetworkLoad;
  weekAgo: NetworkLoad | undefined;
  factors: Factors | undefined;
  weather: DayWeatherSeries | null;
  routes: number[];
  limit: number;
  scenarioEvents: ScenarioEvent[];
  stops?: Map<number, RouteStop[]>;
  /** Сбои из новостей в этот день, уже одной строкой. */
  news?: string[];
}

const SOURCE: Record<string, string> = { fact: 'факт', forecast: 'прогноз', outlook: 'оценка' };
const KIND: Record<string, string> = { workday: 'рабочий день', saturday: 'суббота', sunday: 'воскресенье', holiday: 'праздник' };
/** Осадки меньше 0,1 мм в час не считаются. */
const WET_MM = 0.1;

function sum(values: number[] | undefined): number {
  return values ? values.reduce((a, b) => a + b, 0) : 0;
}

function networkHours(load: NetworkLoad, routes: number[]): number[] {
  return Array.from({ length: 24 }, (_, h) => routes.reduce((a, r) => a + (load.routes.get(r)?.[h] ?? 0), 0));
}

/** «−2…+1°, снег 9-14 ч, 3,2 мм» или «+5…+9°, без осадков». */
export function weatherLine(w: DayWeatherSeries | null): string | null {
  if (!w) return null;
  const temps = w.temp.filter((v): v is number => v != null);
  if (temps.length === 0) return null;
  const snowMm = w.snow.map((v) => (v ?? 0) * SNOW_CM_TO_MM);
  const wet = w.rain.map((r, h) => (r ?? 0) + (snowMm[h] ?? 0));
  const total = sum(wet);
  const range = `${fmtTemp(Math.min(...temps))}…${fmtTemp(Math.max(...temps))}`;
  if (total < WET_MM) return `${range}, без осадков`;
  const hours = wet.flatMap((v, h) => (v >= WET_MM ? [h] : []));
  const snowy = sum(snowMm) > sum(w.rain.map((v) => v ?? 0));
  return `${range}, ${snowy ? 'снег' : 'дождь'} ${hours[0]}-${(hours[hours.length - 1] ?? 0) + 1} ч, ${fmt1(total)} мм`;
}

/** События сети из factors.json, которые действуют в этот день. */
export function dayEvents(factors: Factors | undefined, date: string, dayOff: boolean): string[] {
  return (factors?.events ?? []).filter((e) => {
    const active = e.end ? e.start <= date && date <= e.end : e.start === date;
    const days = e.days === 'all' || (e.days === 'weekends' && dayOff) || (e.days === 'workdays' && !dayOff);
    return active && days && e.type !== 'data_anomaly';
  }).map((e) => (e.routes === 'all' ? e.description : `${e.routes.replaceAll(';', ', ')}: ${e.description}`));
}

function scenarioLines(events: ScenarioEvent[], date: string): string[] {
  return events.filter((e) => e.from <= date && date <= e.to).map((e) => `сценарий: ${e.label || 'событие'}, `
    + `${e.route ? `маршрут ${e.route}` : 'все маршруты'}${e.hours ? `, ${e.hours} ч` : ''}, ×${e.multiplier}`);
}

export function buildBrief(input: BriefInput): Brief {
  const { day, calendar, load, weekAgo, routes, limit } = input;
  const date = isoDate(day);
  const hours = networkHours(load, routes);
  const total = sum(hours);
  const peak = Math.max(...hours);
  const peakHour = hours.indexOf(peak);
  const before = weekAgo ? sum(networkHours(weekAgo, routes)) : 0;
  const vsWeek = before > 0 ? (100 * (total - before)) / before : null;
  const top = routes.map((route) => ({ route, total: sum(load.routes.get(route)) }))
    .sort((a, b) => b.total - a.total).slice(0, 3)
    .map((r) => ({ ...r, share: total > 0 ? r.total / total : 0 }));
  const crowded = bottlenecks([{ day, load, dayOff: calendar?.dayOff ?? false }], input.factors, routes, limit, input.stops);
  const events = [...dayEvents(input.factors, date, calendar?.dayOff ?? false), ...scenarioLines(input.scenarioEvents, date),
    ...(input.news ?? [])];
  const brief = {
    title: dayLabel(day),
    dayKind: calendar?.holiday ?? KIND[calendar?.dayType ?? 'workday'] ?? 'рабочий день',
    source: SOURCE[load.source] ?? 'прогноз',
    weather: weatherLine(input.weather),
    total, peak, peakHour, vsWeek, top, crowded, events,
  };
  return { ...brief, text: briefText(brief, limit) };
}

function briefText(b: Omit<Brief, 'text'>, limit: number): string {
  const lines = [
    `Сводка смены «Час пик»: ${b.title} (${b.dayKind}), ${b.source}`,
    b.weather ? `Погода в центре: ${b.weather}` : null,
    `Сеть: ${fmtCompact(b.total)} посадок, пик ${b.peakHour}:00-${b.peakHour + 1}:00 (${fmtCompact(b.peak)})`
      + (b.vsWeek != null ? `, к тому же дню неделей раньше ${fmtPct(b.vsWeek)}` : ''),
    `Больше всего посадок: ${b.top.map((r) => `№${r.route} - ${fmtCompact(r.total)}`).join(', ')}`,
    b.crowded.length
      ? `Тесно (больше ${limit} посадок на рейс):\n${b.crowded.slice(0, 5).map((c) => `- №${c.route}, ${c.from}-${c.to} ч: `
        + `до ${Math.round(c.peak)} на рейс, ${intervalAdvice(c)}`
        + (c.stop ? `, больше всего входят на «${c.stop}»` : '')).join('\n')}`
      : `Тесных часов нет: на рейс везде меньше ${limit} посадок`,
    b.events.length ? `События:\n${b.events.map((e) => `- ${e}`).join('\n')}` : null,
  ];
  return lines.filter(Boolean).join('\n');
}
