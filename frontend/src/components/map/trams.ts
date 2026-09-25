import type { Factors, NetworkGeoJson, NetworkLoad } from '../../api/types';
import { buildPath, pointAt, type LngLat, type Path } from '../../lib/geo';
import { MINUTES_PER_DAY } from '../../lib/time';

// Вагоны на линиях. Интервал в каждом часе - из расписания transport.mos.ru (будни или выходные),
// время рейса - длина линии при средней эксплуатационной скорости. Положение вагона вычисляется
// из времени, а не накапливается, поэтому перемотка и ускорение дают ту же картину, что и живое время.

/** Средняя эксплуатационная скорость трамвая Москвы, м/мин (17 км/ч). */
export const SPEED_M_PER_MIN = 17_000 / 60;

export interface Line {
  route: number;
  direction: number;
  path: Path;
}

export function buildLines(network: NetworkGeoJson): Line[] {
  return network.features
    .filter((f) => f.properties.kind === 'path' && f.geometry.type === 'LineString')
    .map((f) => ({ route: Number(f.properties.route), direction: Number(f.properties.direction),
      path: buildPath(f.geometry.coordinates as LngLat[]) }));
}

export function headway(factors: Factors | undefined, route: number, dayOff: boolean, hour: number): number | null {
  const entry = factors?.schedule.routes[String(route)];
  const table = dayOff ? (entry?.weekend ?? entry?.weekday) : entry?.weekday;
  const h = table?.headway_min[hour];
  return h == null || h <= 0 ? null : h;
}

export interface TramState {
  at: LngLat;
  bearing: number;
  route: number;
}

/**
 * Вагоны на момент minute (минуты от начала горизонта). Маршрут без посадок в этот час
 * (ночь, маршрут 5 до запуска, выходные 7 и 50 до 15.11) вагонов не показывает.
 */
export function tramsAt(lines: Line[], minute: number, factors: Factors | undefined, dayOff: boolean,
  load: NetworkLoad | undefined): TramState[] {
  const hour = Math.floor((minute % MINUTES_PER_DAY) / 60);
  const out: TramState[] = [];
  for (const line of lines) {
    const h = headway(factors, line.route, dayOff, hour);
    const hourLoad = load?.routes.get(line.route)?.[load.hours.indexOf(hour)] ?? 0;
    if (h == null || hourLoad <= 0) continue;
    const trip = line.path.length / SPEED_M_PER_MIN;
    const offset = line.direction === 1 ? h / 2 : 0;
    const first = Math.floor((minute - offset - trip) / h) + 1;
    const last = Math.floor((minute - offset) / h);
    for (let j = first; j <= last; j++) {
      const progress = (minute - offset - j * h) / trip;
      const { at, bearing } = pointAt(line.path, progress * line.path.length);
      out.push({ at, bearing, route: line.route });
    }
  }
  return out;
}

export function tramCollection(trams: TramState[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: trams.map((t) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: t.at },
      properties: { route: t.route, bearing: t.bearing } })),
  };
}
