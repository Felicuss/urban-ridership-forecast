import type { Factors, NetworkGeoJson, NetworkLoad, RouteStop } from '../api/types';

// Расчёты для диспетчера поверх прогноза: посадки на рейс, узкие места, выпуск вагонов. Интервалы - из
// расписания transport.mos.ru в factors.json, посадки - кадры прогноза по часам. Всё считается в браузере
// из уже загруженных данных, поэтому без лишних запросов к сервису.

/** Вместимость «Витязя-М» при 5 чел/м² по данным производителя (pk-ts.org): порог посадок на рейс. */
export const CAPACITY = 185;
/** Чаще, чем раз в 3 минуты в каждую сторону, трамваи на линию не выпустить. */
export const MIN_HEADWAY = 3;
/** Средняя эксплуатационная скорость трамвая, км/ч: та же, с которой по карте едут вагоны. */
export const SPEED_KMH = 17;

/** Интервал движения в час по расписанию, минуты; null - маршрут в этот час не ходит. */
export function headway(factors: Factors | undefined, route: number, dayOff: boolean, hour: number): number | null {
  const entry = factors?.schedule.routes[String(route)];
  const table = dayOff ? (entry?.weekend ?? entry?.weekday) : entry?.weekday;
  const h = table?.headway_min[hour];
  return h == null || h <= 0 ? null : h;
}

/** Рейсов в час в обе стороны при интервале hw минут. */
export function tripsPerHour(hw: number): number {
  return 2 * (60 / hw);
}

/** Посадок на рейс по 24 часам: посадки маршрута в час, делённые на рейсы в обе стороны. */
export function perTripDay(factors: Factors | undefined, route: number, dayOff: boolean,
  hours: number[] | undefined, share = 1, oneWay = false): number[] {
  return Array.from({ length: 24 }, (_, h) => {
    const hw = headway(factors, route, dayOff, h);
    if (!hw || !hours) return 0;
    const trips = oneWay ? 60 / hw : tripsPerHour(hw);
    return ((hours[h] ?? 0) * share) / trips;
  });
}

/** Самый редкий интервал, при котором на рейс в обе стороны приходится не больше limit посадок. */
export function neededHeadway(boardings: number, limit: number): number {
  return boardings > 0 ? Math.floor(120 / Math.ceil(boardings / limit)) : 60;
}

export interface HourSpan {
  from: number;
  to: number;
  peak: number;
  peakHour: number;
}

/** Часы выше порога, склеенные в отрезки «7-10 ч» с пиком внутри. */
export function spansAbove(values: number[], limit: number): HourSpan[] {
  const out: HourSpan[] = [];
  values.forEach((v, h) => {
    if (v <= limit) return;
    const last = out[out.length - 1];
    if (last && last.to === h) {
      out[out.length - 1] = { ...last, to: h + 1, ...(v > last.peak ? { peak: v, peakHour: h } : {}) };
    } else {
      out.push({ from: h, to: h + 1, peak: v, peakHour: h });
    }
  });
  return out;
}

export interface Bottleneck extends HourSpan {
  day: number;
  route: number;
  /** Интервал по расписанию в час пика и интервал, при котором поток уложится в порог. */
  headway: number;
  need: number;
  /** Остановка с наибольшими посадками маршрута в час пика: где копится поток. */
  stop: string | null;
}

/** Узкие места: маршрут, день и часы, где посадок на рейс больше порога, от самых острых. */
export function bottlenecks(days: { day: number; load: NetworkLoad; dayOff: boolean }[], factors: Factors | undefined,
  routes: number[], limit: number, routeStops?: Map<number, RouteStop[]>): Bottleneck[] {
  const out: Bottleneck[] = [];
  for (const { day, load, dayOff } of days) {
    for (const route of routes) {
      const hours = load.routes.get(route);
      for (const span of spansAbove(perTripDay(factors, route, dayOff, hours), limit)) {
        const hw = headway(factors, route, dayOff, span.peakHour) ?? 0;
        const stops = routeStops?.get(route) ?? [];
        const top = stops.reduce<{ name: string; v: number } | null>((best, s) => {
          const v = load.stops.get(s.stopId)?.[span.peakHour] ?? 0;
          return !best || v > best.v ? { name: s.name, v } : best;
        }, null);
        out.push({ ...span, day, route, headway: hw, need: neededHeadway(hours?.[span.peakHour] ?? 0, limit),
          stop: top?.name ?? null });
      }
    }
  }
  return out.sort((a, b) => b.peak - a.peak);
}

/** Длина трассы маршрута туда и обратно, метры, по линиям сети. */
export function routeLength(network: NetworkGeoJson | undefined, route: number): number {
  return (network?.features ?? [])
    .filter((f) => f.properties.kind === 'path' && f.properties.route === route)
    .reduce((a, f) => a + (f.properties.length_m ?? 0), 0);
}

export interface Fleet {
  /** Оборот: рейс туда и обратно с отстоем на обеих конечных, минуты. */
  cycle: number;
  vehicles: number;
  tripsPerHour: number;
}

/** Сколько вагонов держит интервал: оборот, делённый на интервал, с округлением вверх. */
export function fleet(lengthM: number, speedKmh: number, layoverMin: number, hw: number): Fleet {
  const cycle = (lengthM / 1000 / speedKmh) * 60 + 2 * layoverMin;
  return { cycle, vehicles: hw > 0 ? Math.ceil(cycle / hw) : 0, tripsPerHour: hw > 0 ? 60 / hw : 0 };
}

/** Доля посадок маршрута на участке: сумма долей его остановок в одном направлении. */
export function segmentShare(stops: RouteStop[] | undefined, direction: number, from: string, to: string): number {
  const own = (stops ?? []).filter((s) => s.direction === direction).sort((a, b) => a.seq - b.seq);
  const i = own.findIndex((s) => s.stopId === from);
  const j = own.findIndex((s) => s.stopId === to);
  if (i < 0 || j < 0) return 0;
  return own.slice(Math.min(i, j), Math.max(i, j) + 1).reduce((a, s) => a + s.share, 0);
}

/** Совет по интервалу для узкого места одной фразой. */
export function intervalAdvice(b: Pick<Bottleneck, 'headway' | 'need'>): string {
  if (b.need >= b.headway) return `интервала ${b.headway} мин хватает`;
  return b.need >= MIN_HEADWAY
    ? `интервал ${b.headway} → ${b.need} мин`
    : `даже интервал ${MIN_HEADWAY} мин не хватит: нужен вагон вместительнее или параллельный маршрут`;
}
