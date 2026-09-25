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

// Объёмные вагоны для крупного плана: три секции «Витязя-М» (34 м) слоями fill-extrusion - юбка в цвете
// маршрута, белый кузов, полоса окон (тёмная днём, светится после заката), крыша и тёмная маска спереди.
// На среднем приближении вагон увеличен до 2,2 раза, иначе он тоньше линии маршрута; с zoom 16,8 размер настоящий.

const M_LAT = 110_540;
const M_LON = 111_320 * Math.cos((55.75 * Math.PI) / 180);
const CAR = 11.1;
const GAP = 0.6;
const HALF_WIDTH = 2.1;
const NOSE = 2.2;
const WINDOWS_DAY = '#29303b';
const WINDOWS_NIGHT = '#f3d79b';
const LAYERS: { b: number; h: number; c?: string }[] = [
  { b: 0.25, h: 1.05 },
  { b: 1.05, h: 2.0, c: '#e8ebf0' },
  { b: 2.0, h: 2.85, c: WINDOWS_DAY },
  { b: 2.85, h: 3.35, c: '#e8ebf0' },
  { b: 3.35, h: 3.6, c: '#9aa3b2' },
];

type Ring = [number, number][];

function rect(at: LngLat, bearing: number, from: number, to: number, half: number): Ring {
  const t = (bearing * Math.PI) / 180;
  const f = [Math.sin(t), Math.cos(t)];
  const r = [Math.cos(t), -Math.sin(t)];
  const corner = (a: number, s: number): [number, number] => [
    at[0] + (f[0]! * a + r[0]! * s) / M_LON,
    at[1] + (f[1]! * a + r[1]! * s) / M_LAT,
  ];
  const ring = [corner(from, -half), corner(to, -half), corner(to, half), corner(from, half)];
  return [...ring, ring[0]!];
}

/** Во сколько раз увеличить вагон на этом приближении, чтобы он читался на карте. */
export function tramScale(zoom: number): number {
  return Math.min(Math.max(2 ** (16.8 - zoom), 1), 2.2);
}

export function tramBodies(trams: { at: LngLat; bearing: number; color: string }[], scale = 1,
  night = false): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  const push = (ring: Ring, b: number, h: number, c: string) => features.push({ type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [ring] }, properties: { b: b * scale, h: h * scale, c } });
  const car = CAR * scale;
  const gap = GAP * scale;
  const half = HALF_WIDTH * scale;
  const nose = NOSE * scale;
  for (const tram of trams) {
    const front = (3 * car + 2 * gap) / 2;
    for (let i = 0; i < 3; i++) {
      const to = front - i * (car + gap);
      const from = to - car;
      const bodyTo = i === 0 ? to - nose : to;
      for (const layer of LAYERS) {
        const upto = layer.b >= 1.05 && layer.b < 3.35 ? bodyTo : to;
        const color = layer.c === WINDOWS_DAY && night ? WINDOWS_NIGHT : layer.c ?? tram.color;
        push(rect(tram.at, tram.bearing, from, upto, half), layer.b, layer.h, color);
      }
      if (i === 0) push(rect(tram.at, tram.bearing, to - nose, to - 0.3 * scale, half - 0.15 * scale), 1.05, 3.3, '#14181f');
    }
  }
  return { type: 'FeatureCollection', features };
}
