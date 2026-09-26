import type { Factors, NetworkGeoJson, NetworkLoad } from '../../api/types';
import { buildPath, pointAt, type LngLat, type Path } from '../../lib/geo';
import { MINUTES_PER_DAY } from '../../lib/time';
import { SPEED_KMH, headway } from '../../lib/dispatch';

// Вагоны на линиях. Интервал в каждом часе - из расписания transport.mos.ru (будни или выходные),
// время рейса - длина линии при средней эксплуатационной скорости. Положение вагона вычисляется
// из времени, а не накапливается, поэтому перемотка и ускорение дают ту же картину, что и живое время.

/** Средняя эксплуатационная скорость трамвая Москвы, м/мин (17 км/ч). */
export const SPEED_M_PER_MIN = (SPEED_KMH * 1000) / 60;

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

// Объёмные вагоны для крупного плана: три секции «Витязя-М» (34 м) слоями fill-extrusion - кузов в цвете
// маршрута, полоса окон (тёмная днём, светится после заката), светлая крыша, как полоса на плоском значке,
// и тёмная маска спереди.
// На общем плане вагон держит TRAM_SCREEN_PX пикселей длины, как плоский значок, и утолщён, чтобы читаться над
// линией. Когда настоящий вагон на экране становится длиннее, модель растёт вместе с картой, утолщение сходит
// на нет, и видно окна с простенками, скошенную кабину, гармошки между секциями, тележки и токоприёмник.
// До zoom 14 модель упрощённая (юбка, кузов, окна, крыша), чтобы сотня вагонов на общем плане не тормозила.

const M_LAT = 110_540;
const M_LON = 111_320 * Math.cos((55.75 * Math.PI) / 180);
const CAR = 11.1;
const GAP = 0.6;
const HALF_WIDTH = 2.1;
const NOSE = 2.2;
const WINDOWS_DAY = '#29303b';
const WINDOWS_NIGHT = '#ffc93d';
const ROOF = '#eef1f5';
const LAYERS: { b: number; h: number; c?: string }[] = [
  { b: 0.25, h: 2.0 },
  { b: 2.0, h: 2.85, c: WINDOWS_DAY },
  { b: 2.85, h: 3.35 },
  { b: 3.35, h: 3.6, c: ROOF },
];

type Ring = [number, number][];

/** Четырёхугольник вдоль хода вагона: от from до to метров, полуширина half у начала и halfTo у конца. */
function rect(at: LngLat, bearing: number, from: number, to: number, half: number, halfTo = half): Ring {
  const t = (bearing * Math.PI) / 180;
  const f = [Math.sin(t), Math.cos(t)];
  const r = [Math.cos(t), -Math.sin(t)];
  const corner = (a: number, s: number): [number, number] => [
    at[0] + (f[0]! * a + r[0]! * s) / M_LON,
    at[1] + (f[1]! * a + r[1]! * s) / M_LAT,
  ];
  const ring = [corner(from, -half), corner(to, -halfTo), corner(to, halfTo), corner(from, half)];
  return [...ring, ring[0]!];
}

/** Длина вагона на экране в пикселях: одна и та же у плоского значка и у объёмной модели на любом зуме. */
export const TRAM_SCREEN_PX = 32;
/** Метров в пикселе на zoom 0 на широте Москвы: MapLibre считает мир из тайлов по 512 пикселей. */
const M_PER_PX_Z0 = (40_075_016.7 / 512) * Math.cos((55.75 * Math.PI) / 180);
const TRAM_LENGTH_M = 3 * CAR + 2 * GAP;

/** Во сколько раз увеличить вагон на этом приближении, чтобы он читался на карте; меньше настоящего не бывает. */
export function tramScale(zoom: number): number {
  return Math.max(1, (TRAM_SCREEN_PX * M_PER_PX_Z0) / 2 ** zoom / TRAM_LENGTH_M);
}

/** Упрощённая модель для общего плана: вагон шире и выше, чтобы выделялся над линией маршрута. */
const LITE_LAYERS: { b: number; h: number; c?: string }[] = [
  { b: 0.25, h: 2.0 },
  { b: 2.0, h: 2.9, c: WINDOWS_DAY },
  { b: 2.9, h: 3.6, c: ROOF },
];
/**
 * Вагон шире и выше настоящего: по ширине он совпадает с плоским значком (14 из 44 пикселей длины) и шире
 * линии маршрута, поэтому не сливается с ней.
 */
const WIDTH_BOOST = 2.4;
const HEIGHT_BOOST = 1.8;

/** Утолщение по масштабу: полное, пока вагон увеличен втрое и больше, и никакого в настоящем размере. */
function boost(max: number, scale: number): number {
  return 1 + (max - 1) * Math.min(1, Math.max(0, (scale - 1) / 2));
}

const BELLOWS = '#23272e';
const UNDER = '#15181d';
const PANTOGRAPH = '#3a404a';
/** Простенок между окнами и шаг окон вдоль кузова, м. */
const PILLAR = 0.35;
const PANE_STEP = 2.3;

export function tramBodies(trams: { at: LngLat; bearing: number; color: string }[], scale = 1,
  night = false, lite = false): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  const up = scale * boost(HEIGHT_BOOST, scale);
  const push = (ring: Ring, b: number, h: number, c: string) => features.push({ type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [ring] }, properties: { b: b * up, h: h * up, c } });
  const car = CAR * scale;
  const gap = GAP * scale;
  const half = HALF_WIDTH * scale * boost(WIDTH_BOOST, scale);
  const nose = NOSE * scale;
  const pillar = PILLAR * scale;
  for (const tram of trams) {
    const front = (3 * car + 2 * gap) / 2;
    for (let i = 0; i < 3; i++) {
      const to = front - i * (car + gap);
      const from = to - car;
      const bodyTo = i === 0 ? to - nose : to;
      if (lite) {
        for (const layer of LITE_LAYERS) {
          const color = layer.c === WINDOWS_DAY && night ? WINDOWS_NIGHT : layer.c ?? tram.color;
          push(rect(tram.at, tram.bearing, from, to, half), layer.b, layer.h, color);
        }
        continue;
      }
      const at = tram.at;
      const dir = tram.bearing;
      const windows = night ? WINDOWS_NIGHT : WINDOWS_DAY;
      // тележки под кузовом и гармошка к следующей секции
      push(rect(at, dir, from + 1.2 * scale, to - 1.2 * scale, half * 0.78), 0, 0.3, UNDER);
      if (i < 2) push(rect(at, dir, from - gap, from, half * 0.86), 0.45, 3.2, BELLOWS);
      // юбка и кузов; у головной секции кабина сужается к носу
      push(rect(at, dir, from, bodyTo, half), LAYERS[0]!.b, LAYERS[0]!.h, tram.color);
      if (i === 0) push(rect(at, dir, bodyTo, to, half, half * 0.72), LAYERS[0]!.b, LAYERS[0]!.h, tram.color);
      // полоса окон: стёкла с простенками в цвет кузова
      const panes = Math.max(1, Math.round((bodyTo - from) / (PANE_STEP * scale)));
      const pane = (bodyTo - from - (panes + 1) * pillar) / panes;
      for (let k = 0; k <= panes; k++) {
        const x = from + k * (pane + pillar);
        push(rect(at, dir, x, x + pillar, half), LAYERS[1]!.b, LAYERS[1]!.h, tram.color);
        if (k < panes) push(rect(at, dir, x + pillar, x + pillar + pane, half), LAYERS[1]!.b, LAYERS[1]!.h, windows);
      }
      push(rect(at, dir, from, bodyTo, half), LAYERS[2]!.b, LAYERS[2]!.h, tram.color);
      push(rect(at, dir, from, i === 0 ? to - nose * 0.45 : to, half * 0.92, i === 0 ? half * 0.8 : half * 0.92),
        LAYERS[3]!.b, LAYERS[3]!.h, ROOF);
      // кабина: тёмное лобовое стекло сужается к носу, токоприёмник на средней секции
      if (i === 0) push(rect(at, dir, bodyTo, to - 0.3 * scale, half - 0.15 * scale, (half - 0.15 * scale) * 0.74), 1.05, 3.3, '#14181f');
      if (i === 1) {
        const mid = (from + to) / 2;
        push(rect(at, dir, mid - 1.3 * scale, mid + 1.3 * scale, half * 0.34), 3.6, 3.95, PANTOGRAPH);
      }
    }
  }
  return { type: 'FeatureCollection', features };
}
