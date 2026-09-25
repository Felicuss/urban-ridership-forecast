// Геометрия для движения трамвая: путь с накопленной длиной, точка на пути по расстоянию,
// проекция остановки на путь. Метры на плоскости около Москвы, для анимации этой точности хватает.

export type LngLat = [number, number];

const M_PER_DEG_LAT = 110_540;
const M_PER_DEG_LON = 111_320 * Math.cos((55.75 * Math.PI) / 180);

export interface Path {
  coords: LngLat[];
  cum: Float64Array;
  length: number;
}

export function segmentMeters(a: LngLat, b: LngLat): number {
  return Math.hypot((b[0] - a[0]) * M_PER_DEG_LON, (b[1] - a[1]) * M_PER_DEG_LAT);
}

export function buildPath(coords: LngLat[]): Path {
  const cum = new Float64Array(coords.length);
  for (let i = 1; i < coords.length; i++) {
    cum[i] = (cum[i - 1] ?? 0) + segmentMeters(coords[i - 1]!, coords[i]!);
  }
  return { coords, cum, length: cum[coords.length - 1] ?? 0 };
}

/** Точка и курс (градусы от севера) на расстоянии d метров от начала пути. */
export function pointAt(path: Path, d: number): { at: LngLat; bearing: number } {
  const { coords, cum } = path;
  const dist = Math.min(Math.max(d, 0), path.length);
  let lo = 0;
  let hi = coords.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if ((cum[mid] ?? 0) <= dist) lo = mid;
    else hi = mid;
  }
  const a = coords[lo]!;
  const b = coords[hi]!;
  const span = (cum[hi] ?? 0) - (cum[lo] ?? 0);
  const t = span > 0 ? (dist - (cum[lo] ?? 0)) / span : 0;
  const at: LngLat = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  const bearing = (Math.atan2((b[0] - a[0]) * M_PER_DEG_LON, (b[1] - a[1]) * M_PER_DEG_LAT) * 180) / Math.PI;
  return { at, bearing };
}

/** Расстояние вдоль пути до ближайшей к точке позиции на пути. */
export function projectOnPath(path: Path, p: LngLat): number {
  let best = Infinity;
  let bestD = 0;
  const { coords, cum } = path;
  for (let i = 0; i < coords.length - 1; i++) {
    const a = coords[i]!;
    const b = coords[i + 1]!;
    const ax = (p[0] - a[0]) * M_PER_DEG_LON;
    const ay = (p[1] - a[1]) * M_PER_DEG_LAT;
    const bx = (b[0] - a[0]) * M_PER_DEG_LON;
    const by = (b[1] - a[1]) * M_PER_DEG_LAT;
    const len2 = bx * bx + by * by;
    const t = len2 > 0 ? Math.min(Math.max((ax * bx + ay * by) / len2, 0), 1) : 0;
    const dx = ax - bx * t;
    const dy = ay - by * t;
    const dist2 = dx * dx + dy * dy;
    if (dist2 < best) {
      best = dist2;
      bestD = (cum[i] ?? 0) + Math.sqrt(len2) * t;
    }
  }
  return bestD;
}
