import raw from '../data/city.json';
import { E, FILM, P, lib, type Pt } from '../film';
import { MONO, ROUTE_INK, clamp, drawMipped, sprite, text } from './g';

// Карта Москвы тушью по настоящим данным: МКАД, Москва-река, магистрали (OpenStreetMap) и 10 трамвайных трасс
// с остановками из артефактов сервиса. Мир - метры от центра (37.62, 55.755), y на север. Камера { x, y, z }:
// z пикселей экрана на метр. Издалека карта берётся из растра, собранного один раз; ближе рисуется вектором.

interface RawCity {
  trams: { r: number; d: number; p: number[] }[];
  stops: { id: string; n: string; x: number; y: number; r: number[]; h: number[] }[];
  roads: number[][];
  mkad: number[][];
  river: number[][];
}

export interface Cam {
  x: number;
  y: number;
  z: number;
}

interface Line {
  pts: Pt[];
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface Route extends Line {
  route: number;
  direction: number;
  cum: number[];
  length: number;
}

export interface Stop {
  id: string;
  name: string;
  x: number;
  y: number;
  routes: number[];
  hours: number[];
}

const city = raw as unknown as RawCity;

function toLine(flat: number[]): Line {
  const pts: Pt[] = [];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (let i = 0; i + 1 < flat.length; i += 2) {
    const x = flat[i]!;
    const y = flat[i + 1]!;
    pts.push([x, y]);
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return { pts, minX, minY, maxX, maxY };
}

export const ROUTES: Route[] = city.trams.map((t) => {
  const l = toLine(t.p);
  const cum = [0];
  for (let i = 1; i < l.pts.length; i++) {
    cum.push(cum[i - 1]! + Math.hypot(l.pts[i]![0] - l.pts[i - 1]![0], l.pts[i]![1] - l.pts[i - 1]![1]));
  }
  return { ...l, route: t.r, direction: t.d, cum, length: cum[cum.length - 1] ?? 0 };
});
export const STOPS: Stop[] = city.stops.map((s) => ({ id: s.id, name: s.n, x: s.x, y: s.y, routes: s.r, hours: s.h }));
const ROADS = city.roads.map(([kind, ...p]) => ({ kind: kind ?? 1, ...toLine(p) }));
const RIVER = city.river.map(toLine);

/** МКАД одним кольцом: выпуклая оболочка точек кольцевой, её хватает для рисунка. */
const MKAD: Pt[] = (() => {
  const pts = city.mkad.flatMap((f) => toLine(f).pts).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: Pt, a: Pt, b: Pt) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const half = (list: Pt[]) => list.reduce<Pt[]>((h, p) => {
    while (h.length >= 2 && cross(h[h.length - 2]!, h[h.length - 1]!, p) <= 0) h.pop();
    h.push(p);
    return h;
  }, []);
  const lower = half(pts);
  const upper = half([...pts].reverse());
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
})();

export function stopNamed(name: string): Stop {
  const s = STOPS.find((x) => x.name === name);
  if (!s) throw new Error(`нет остановки «${name}»`);
  return s;
}

export function routeBox(route: number): { x: number; y: number; w: number; h: number } {
  const own = ROUTES.filter((r) => r.route === route);
  const minX = Math.min(...own.map((r) => r.minX));
  const maxX = Math.max(...own.map((r) => r.maxX));
  const minY = Math.min(...own.map((r) => r.minY));
  const maxY = Math.max(...own.map((r) => r.maxY));
  return { x: (minX + maxX) / 2, y: (minY + maxY) / 2, w: maxX - minX, h: maxY - minY };
}

export const NETWORK = (() => {
  const minX = Math.min(...ROUTES.map((r) => r.minX));
  const maxX = Math.max(...ROUTES.map((r) => r.maxX));
  const minY = Math.min(...ROUTES.map((r) => r.minY));
  const maxY = Math.max(...ROUTES.map((r) => r.maxY));
  return { x: (minX + maxX) / 2, y: (minY + maxY) / 2, w: maxX - minX, h: maxY - minY };
})();

// ---------------------------------------------------------------------------
// Камера
// ---------------------------------------------------------------------------

export function toScreen(cam: Cam, x: number, y: number): Pt {
  return [960 + (x - cam.x) * cam.z, 540 - (y - cam.y) * cam.z];
}

/** Перелёт: масштаб по логарифму, центр по ширине кадра, чтобы цель не уплывала (как в LCT_2026). */
export function camLerp(a: Cam, b: Cam, q: number): Cam {
  if (q <= 0) return a;
  if (q >= 1) return b;
  const la = Math.log(a.z);
  const lb = Math.log(b.z);
  const z = Math.exp(lib.lerp(la, lb, q));
  let w = q;
  if (Math.abs(lb - la) > 1e-4) w = (1 / z - 1 / a.z) / (1 / b.z - 1 / a.z);
  return { x: lib.lerp(a.x, b.x, w), y: lib.lerp(a.y, b.y, w), z };
}

/** Камера по ключам [t, cam]: между ключами плавный перелёт. */
export function camPath(keys: [number, Cam][], t: number): Cam {
  if (t <= keys[0]![0]) return keys[0]![1];
  for (let i = 0; i + 1 < keys.length; i++) {
    const [t0, c0] = keys[i]!;
    const [t1, c1] = keys[i + 1]!;
    if (t <= t1) return camLerp(c0, c1, E.inOutCubic((t - t0) / (t1 - t0)));
  }
  return keys[keys.length - 1]![1];
}

/** Камера, в кадре которой прямоугольник мира помещается в область экрана. */
export function fitCam(box: { x: number; y: number; w: number; h: number }, screen: { x: number; y: number; w: number; h: number }): Cam {
  const z = Math.min(screen.w / box.w, screen.h / box.h);
  return { x: box.x - (screen.x + screen.w / 2 - 960) / z, y: box.y + (screen.y + screen.h / 2 - 540) / z, z };
}

// ---------------------------------------------------------------------------
// Растр для видов издалека
// ---------------------------------------------------------------------------

const REGION = (() => {
  const xs = MKAD.map((p) => p[0]);
  const ys = MKAD.map((p) => p[1]);
  const pad = 4000;
  return { x0: Math.min(...xs) - pad, x1: Math.max(...xs) + pad, y0: Math.min(...ys) - pad, y1: Math.max(...ys) + pad };
})();
const RASTER_W = 3000;
const RASTER_Z = RASTER_W / (REGION.x1 - REGION.x0);
/** Ближе этого растр мягкий: дальше рисуем вектором, в полосе между ними - растворяем. */
const VECTOR_FROM = RASTER_Z * 0.95;
const VECTOR_FULL = RASTER_Z * 1.35;

export interface Palette {
  paper: string;
  city: string;
  ink: string;
  road: string;
  water: string;
  flow: string;
}

export const DAY: Palette = { paper: '#EDE0C4', city: '#E0CFAD', ink: P.ink!, road: '#5B4331', water: '#9CC6CF', flow: '#FBF6EA' };
export const DUSK: Palette = { paper: '#2B2745', city: '#24203B', ink: '#E9E1F5', road: '#B9AED8', water: '#3E5B7A', flow: '#9CC2EA' };

const rasters = new Map<Palette, HTMLCanvasElement>();

function rasterCam(): Cam {
  return { x: (REGION.x0 + REGION.x1) / 2, y: (REGION.y0 + REGION.y1) / 2, z: RASTER_Z };
}

/** Собрать растр карты: вызывается при загрузке, чтобы первый кадр не ждал. */
export function buildRaster(pal: Palette): HTMLCanvasElement {
  const known = rasters.get(pal);
  if (known) return known;
  const h = Math.round((REGION.y1 - REGION.y0) * RASTER_Z);
  const c = FILM.makeCanvas(RASTER_W, h);
  const g = c.getContext('2d')!;
  const cam = rasterCam();
  const pt = (x: number, y: number): Pt => [RASTER_W / 2 + (x - cam.x) * cam.z, h / 2 - (y - cam.y) * cam.z];
  const saved = FILM.frameT;
  FILM.frameT = 0.001;
  drawBase(g, (x, y) => pt(x, y), cam.z, pal, true);
  FILM.frameT = saved;
  rasters.set(pal, c);
  return c;
}

/** Застройка внутри МКАД, дороги, река, кольцо МКАД. pt - перевод метров в пиксели холста g. */
function drawBase(g: CanvasRenderingContext2D, pt: (x: number, y: number) => Pt, z: number, pal: Palette, full: boolean,
  view?: { x0: number; y0: number; x1: number; y1: number }): void {
  const inView = (l: Line) => !view || (l.maxX > view.x0 && l.minX < view.x1 && l.maxY > view.y0 && l.minY < view.y1);
  g.save();
  g.lineCap = 'round';
  g.lineJoin = 'round';
  const ring = MKAD.map(([x, y]) => pt(x, y));
  g.fillStyle = pal.city;
  g.beginPath();
  lib.tracePath(g, ring, true);
  g.fill();
  // второстепенные и главные улицы: тонкая тушь, главные темнее
  for (const kind of [1, 0]) {
    g.beginPath();
    for (const r of ROADS) {
      if (r.kind !== kind || !inView(r)) continue;
      r.pts.forEach(([x, y], i) => {
        const [sx, sy] = pt(x, y);
        if (i) g.lineTo(sx, sy);
        else g.moveTo(sx, sy);
      });
    }
    g.strokeStyle = lib.rgba(pal.road, kind === 0 ? 0.42 : 0.2);
    g.lineWidth = kind === 0 ? Math.max(1.1, 32 * z) : Math.max(0.7, 18 * z);
    g.stroke();
  }
  // река: берега тушью и вода поверх
  const rw = Math.max(5, 200 * z);
  for (const [color, w] of [[pal.ink, rw + 3], [pal.water, rw]] as const) {
    g.beginPath();
    for (const r of RIVER) {
      if (!inView(r)) continue;
      r.pts.forEach(([x, y], i) => {
        const [sx, sy] = pt(x, y);
        if (i) g.lineTo(sx, sy);
        else g.moveTo(sx, sy);
      });
    }
    g.strokeStyle = color;
    g.globalAlpha = color === pal.ink ? 0.55 : 1;
    g.lineWidth = w;
    g.stroke();
  }
  g.globalAlpha = 1;
  g.restore();
  if (full) lib.inkPath(g, ring, { closed: true, width: 4.4, color: pal.ink, seed: 1, wobble: 1, double: true, boil: false });
}

// ---------------------------------------------------------------------------
// Кадр карты
// ---------------------------------------------------------------------------

export interface MapOpts {
  t: number;
  pal?: Palette;
  /** Прорисовка сети на титуле: 0 - пусто, 1 - всё на месте. */
  reveal?: number;
  /** Маршрут в фокусе: остальные бледнее. */
  focus?: number | null;
  focusAmount?: number;
  /** Час, по которому остановки получают кружки посадок; null - без кружков. */
  hour?: number | null;
  /** Кружки посадок только у остановок маршрута в фокусе. */
  focusStops?: boolean;
  /** Пурпурная подсветка перегруженных маршрутов, доля 0..1 на маршрут. */
  hot?: Record<number, number>;
  trams?: boolean;
  labels?: boolean;
  glow?: number;
}

function screenRuns(sp: Pt[], margin: number): Pt[][] {
  const runs: Pt[][] = [];
  let cur: Pt[] = [];
  const inView = (p: Pt) => p[0] > -margin && p[0] < 1920 + margin && p[1] > -margin && p[1] < 1080 + margin;
  for (let i = 0; i < sp.length; i++) {
    const p = sp[i]!;
    const prev = sp[i - 1];
    if (inView(p) || (prev && inView(prev))) {
      if (!cur.length && prev) cur.push(prev);
      cur.push(p);
    } else if (cur.length) {
      cur.push(p);
      runs.push(cur);
      cur = [];
    }
  }
  if (cur.length > 1) runs.push(cur);
  return runs;
}

function viewBox(cam: Cam, margin = 200) {
  const hw = (960 + margin) / cam.z;
  const hh = (540 + margin) / cam.z;
  return { x0: cam.x - hw, x1: cam.x + hw, y0: cam.y - hh, y1: cam.y + hh };
}

function pointAt(r: Route, s: number): { x: number; y: number; a: number } {
  let lo = 0;
  let hi = r.cum.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (r.cum[mid]! < s) lo = mid;
    else hi = mid;
  }
  const f = (s - r.cum[lo]!) / (r.cum[hi]! - r.cum[lo]! || 1);
  const [x0, y0] = r.pts[lo]!;
  const [x1, y1] = r.pts[hi]!;
  return { x: x0 + (x1 - x0) * f, y: y0 + (y1 - y0) * f, a: Math.atan2(-(y1 - y0), x1 - x0) };
}

export function drawMap(ctx: CanvasRenderingContext2D, cam: Cam, o: MapOpts): void {
  const pal = o.pal ?? DAY;
  const t = o.t;
  const rv = o.reveal ?? 1;
  ctx.fillStyle = pal.paper;
  ctx.fillRect(0, 0, 1920, 1080);
  grid(ctx, cam, pal);
  // растр издалека, вектор вблизи, между ними растворение
  const va = clamp((cam.z - VECTOR_FROM) / (VECTOR_FULL - VECTOR_FROM));
  if (va < 1) {
    const c = buildRaster(pal);
    const [sx, sy] = toScreen(cam, REGION.x0, REGION.y1);
    ctx.save();
    ctx.globalAlpha *= (1 - va) * clamp(rv * 3);
    ctx.drawImage(c, sx, sy, (REGION.x1 - REGION.x0) * cam.z, (REGION.y1 - REGION.y0) * cam.z);
    ctx.restore();
  }
  if (va > 0) {
    ctx.save();
    ctx.globalAlpha *= va;
    drawBase(ctx, (x, y) => toScreen(cam, x, y), cam.z, pal, false, viewBox(cam));
    const ring = MKAD.map(([x, y]) => toScreen(cam, x, y));
    for (const run of screenRuns([...ring, ring[0]!], 80)) {
      lib.inkPath(ctx, run, { width: 4.4, color: pal.ink, seed: 1, wobble: 0.5, taper: [4, 6], boilAmp: 0.3, step: 6 });
    }
    ctx.restore();
  }
  riverFlow(ctx, cam, pal, t, rv);
  routes(ctx, cam, o, pal);
  if (o.trams !== false && rv >= 1) trams(ctx, cam, o, pal, t);
  stops(ctx, cam, o, pal);
  if (o.labels !== false) labels(ctx, cam, pal, rv);
}

function grid(ctx: CanvasRenderingContext2D, cam: Cam, pal: Palette): void {
  const step = cam.z > 0.1 ? 1000 : 2000;
  const v = viewBox(cam, 0);
  ctx.save();
  ctx.strokeStyle = lib.rgba(pal === DAY ? P.inkFaint! : '#8C83B8', 0.16);
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = Math.floor(v.x0 / step) * step; x < v.x1; x += step) {
    const [sx] = toScreen(cam, x, 0);
    ctx.moveTo(sx, 0);
    ctx.lineTo(sx, 1080);
  }
  for (let y = Math.floor(v.y0 / step) * step; y < v.y1; y += step) {
    const [, sy] = toScreen(cam, 0, y);
    ctx.moveTo(0, sy);
    ctx.lineTo(1920, sy);
  }
  ctx.stroke();
  ctx.restore();
}

function riverFlow(ctx: CanvasRenderingContext2D, cam: Cam, pal: Palette, t: number, rv: number): void {
  if (rv < 0.2) return;
  const rw = Math.max(5, 200 * cam.z);
  const v = viewBox(cam);
  ctx.save();
  ctx.lineCap = 'round';
  ctx.beginPath();
  for (const r of RIVER) {
    if (r.maxX < v.x0 || r.minX > v.x1 || r.maxY < v.y0 || r.minY > v.y1) continue;
    r.pts.forEach(([x, y], i) => {
      const [sx, sy] = toScreen(cam, x, y);
      if (i) ctx.lineTo(sx, sy);
      else ctx.moveTo(sx, sy);
    });
  }
  ctx.strokeStyle = lib.rgba(pal.flow, 0.75 * clamp(rv * 2));
  ctx.lineWidth = Math.max(1.2, rw * 0.14);
  ctx.setLineDash([rw * 1.4 + 4, rw * 1.8 + 6]);
  ctx.lineDashOffset = -t * 30;
  ctx.stroke();
  ctx.restore();
}

function routeAlpha(o: MapOpts, route: number): number {
  const f = o.focus;
  return f == null || f === route ? 1 : 1 - 0.78 * (o.focusAmount ?? 1);
}

function routes(ctx: CanvasRenderingContext2D, cam: Cam, o: MapOpts, pal: Palette): void {
  const rv = o.reveal ?? 1;
  const base = clamp(1.8 + cam.z * 18, 2.4, 7);
  ROUTES.forEach((r, k) => {
    // трассы прорисовываются по очереди, как пером
    const q = clamp((rv - 0.25 - k * 0.022) / 0.45);
    if (q <= 0) return;
    const n = Math.max(2, Math.ceil(r.pts.length * q));
    const sp = r.pts.slice(0, n).map(([x, y]) => toScreen(cam, x, y));
    const alpha = routeAlpha(o, r.route);
    const focus = o.focus === r.route;
    const hot = o.hot?.[r.route] ?? 0;
    const color = pal === DAY ? ROUTE_INK[r.route]! : lib.mix(ROUTE_INK[r.route]!, '#ffffff', 0.35);
    for (const run of screenRuns(sp, 60)) {
      if (hot > 0) {
        lib.inkPath(ctx, run, { width: base + 10 * hot, color: P.annMagenta, alpha: 0.28 * alpha, seed: k + 300, wobble: 1.2, taper: [4, 8], boilAmp: 0.5, step: 7 });
      }
      lib.inkPath(ctx, run, { width: (focus ? base * 1.35 : base) * (r.direction ? 0.55 : 1), color, alpha: alpha * (r.direction ? 0.7 : 1),
        seed: k + 200, wobble: 0.6, taper: [4, 8], boilAmp: 0.45, step: 5 });
    }
  });
}

export function trams(ctx: CanvasRenderingContext2D, cam: Cam, o: MapOpts, pal: Palette, t: number): void {
  const len = clamp(34 * cam.z * 4, 9, 22);
  const w = len * 0.42;
  ROUTES.forEach((r) => {
    const alpha = routeAlpha(o, r.route);
    if (alpha < 0.3) return;
    const n = Math.max(2, Math.floor(r.length / 1800));
    const color = ROUTE_INK[r.route]!;
    for (let k = 0; k < n; k++) {
      const s = (t * 160 + (k * r.length) / n + r.route * 311 + r.direction * 811) % r.length;
      const p = pointAt(r, s);
      const [sx, sy] = toScreen(cam, p.x, p.y);
      if (sx < -30 || sx > 1950 || sy < -30 || sy > 1110) continue;
      ctx.save();
      ctx.translate(sx, sy);
      ctx.rotate(p.a);
      ctx.globalAlpha *= alpha;
      ctx.fillStyle = color;
      ctx.strokeStyle = pal.ink;
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.roundRect(-len / 2, -w / 2, len, w, w / 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = lib.rgba(P.white!, 0.85);
      ctx.fillRect(-len / 2 + w * 0.5, -w * 0.14, len - w, w * 0.28);
      ctx.restore();
    }
  });
}

function stops(ctx: CanvasRenderingContext2D, cam: Cam, o: MapOpts, pal: Palette): void {
  const rv = o.reveal ?? 1;
  if (rv < 0.7) return;
  const pop = E.outBack(clamp((rv - 0.7) / 0.3));
  const r0 = clamp(cam.z * 14, 1.8, 5);
  const maxHour = o.hour != null ? Math.max(...STOPS.map((s) => s.hours[o.hour!] ?? 0), 1) : 1;
  for (const s of STOPS) {
    const [sx, sy] = toScreen(cam, s.x, s.y);
    if (sx < -60 || sx > 1980 || sy < -60 || sy > 1140) continue;
    const focused = o.focus == null || s.routes.includes(o.focus);
    const a = focused ? 1 : 1 - 0.8 * (o.focusAmount ?? 1);
    if (a < 0.1) continue;
    ctx.save();
    ctx.globalAlpha *= a * pop;
    if (o.hour != null && (!o.focusStops || focused)) {
      const v = (s.hours[o.hour] ?? 0) / maxHour;
      const r = 3 + 26 * Math.sqrt(v) * clamp(cam.z * 8, 0.6, 1.4);
      ctx.fillStyle = lib.rgba(lib.mix('#E7B96A', P.annMagenta!, v), 0.55);
      ctx.beginPath();
      ctx.arc(sx, sy, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = lib.rgba(pal.ink, 0.7);
      ctx.lineWidth = 1.4;
      ctx.stroke();
    } else {
      ctx.fillStyle = pal === DAY ? P.white! : '#1E1B33';
      ctx.strokeStyle = pal.ink;
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.arc(sx, sy, r0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();
    if (o.glow && o.glow > 0) {
      lib.glowDot(ctx, sx, sy, r0 * 0.9, { color: '#FFE3A3', rays: 0, glow: 5, intensity: o.glow * 0.8, seed: s.x });
    }
  }
}

function labels(ctx: CanvasRenderingContext2D, cam: Cam, pal: Palette, rv: number): void {
  const a = clamp((rv - 0.4) * 2);
  if (a <= 0) return;
  const lab = (s: string, x: number, y: number) => {
    const [sx, sy] = toScreen(cam, x, y);
    text(ctx, s, sx, sy, { size: 16, weight: 600, family: MONO, color: pal.ink, alpha: 0.55 * a, tracking: 3 });
  };
  const top = MKAD.reduce((b, p) => (p[1] > b[1] ? p : b));
  lab('МКАД', top[0] + 2500, top[1] - 1200);
  lab('МОСКВА-РЕКА', 6200, -5200);
  // Кремль треугольником, как на карте LCT
  const k = [[-150, -90], [170, -80], [20, 170]].map(([x, y]) => toScreen(cam, x!, y!));
  lib.inkPath(ctx, k, { closed: true, width: 1.8, fill: pal === DAY ? '#C88C86' : '#C8C1EF', color: pal.ink, seed: 9, smooth: false, alpha: a });
  // масштабная линейка 5 км
  const L = 5000 * cam.z;
  if (L > 60 && L < 900) {
    lib.ticks(ctx, 1560, 980, { length: L, n: 5, len: 8, major: 5, majorLen: 14, color: pal.ink, alpha: 0.7 * a, width: 1.6 });
    text(ctx, '5 км', 1560 + L + 12, 986, { size: 17, weight: 600, family: MONO, color: pal.ink, alpha: 0.7 * a });
  }
}

/** Точка мира на экране с проверкой, что она в кадре. */
export function onScreen(cam: Cam, x: number, y: number): Pt | null {
  const p = toScreen(cam, x, y);
  return p[0] > -20 && p[0] < 1940 && p[1] > -20 && p[1] < 1100 ? p : null;
}


// ---------------------------------------------------------------------------
// Карта в макете интерфейса: тёмная схема как в сервисе, чистые линии без «туши»
// ---------------------------------------------------------------------------

/** Цвета маршрутов в интерфейсе сервиса (frontend/src/lib/routes.ts). */
export const UI_ROUTE: Record<number, string> = {
  1: '#7aa2f7', 5: '#f7768e', 7: '#e0af68', 11: '#73daca', 12: '#bb9af7',
  17: '#ff9e64', 25: '#7dcfff', 26: '#b9d98a', 28: '#f5a9c8', 50: '#a9b1d6',
};

const UI_RASTER_W = 4200;
let uiBase: HTMLCanvasElement | null = null;

/** Подложка тёмной карты: застройка, улицы, река, МКАД. Строится один раз. */
export function uiRaster(): HTMLCanvasElement {
  if (uiBase) return uiBase;
  const z = UI_RASTER_W / (REGION.x1 - REGION.x0);
  const h = Math.round((REGION.y1 - REGION.y0) * z);
  const c = FILM.makeCanvas(UI_RASTER_W, h);
  const g = c.getContext('2d')!;
  const pt = (x: number, y: number): Pt => [(x - REGION.x0) * z, (REGION.y1 - y) * z];
  g.fillStyle = '#1b1c21';
  g.fillRect(0, 0, UI_RASTER_W, h);
  g.lineCap = 'round';
  g.lineJoin = 'round';
  const ring = MKAD.map(([x, y]) => pt(x, y));
  g.fillStyle = '#202127';
  g.beginPath();
  lib.tracePath(g, ring, true);
  g.fill();
  const stroke = (lines: Line[], color: string, w: number) => {
    g.beginPath();
    for (const l of lines) {
      l.pts.forEach(([x, y], i) => {
        const [sx, sy] = pt(x, y);
        if (i) g.lineTo(sx, sy);
        else g.moveTo(sx, sy);
      });
    }
    g.strokeStyle = color;
    g.lineWidth = w;
    g.stroke();
  };
  stroke(ROADS.filter((r) => r.kind === 1), 'rgba(150,158,176,0.16)', 1.3);
  stroke(ROADS.filter((r) => r.kind === 0), 'rgba(214,170,110,0.2)', 2.6);
  stroke(RIVER, '#1d3350', Math.max(6, 170 * z));
  g.strokeStyle = 'rgba(160,170,190,0.28)';
  g.lineWidth = 3;
  g.beginPath();
  lib.tracePath(g, ring, true);
  g.stroke();
  uiBase = c;
  return c;
}

export interface UiMapOpts {
  t: number;
  hour: number;
  focus: number | null;
  focusAmount: number;
  /** Посадки маршрутов по часам: толщина линии. */
  routeHours: Record<number, number[]>;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Камера, при которой прямоугольник мира помещается в область rect с полями. */
export function fitRect(box: { x: number; y: number; w: number; h: number }, rect: Rect, pad = 0.86): Cam {
  return { x: box.x, y: box.y, z: Math.min(rect.w / box.w, rect.h / box.h) * pad };
}

const HEAT: [number, number, number][] = [[74, 94, 140], [111, 143, 201], [143, 184, 168], [217, 179, 108], [224, 135, 106], [216, 102, 111]];
function heat(v: number): string {
  const x = clamp(v) * (HEAT.length - 1);
  const i = Math.min(Math.floor(x), HEAT.length - 2);
  const f = x - i;
  const a = HEAT[i]!;
  const b = HEAT[i + 1]!;
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)},${Math.round(a[1] + (b[1] - a[1]) * f)},${Math.round(a[2] + (b[2] - a[2]) * f)})`;
}

function hourValue(values: number[], hour: number): number {
  const h = Math.min(Math.max(hour, 0), 23);
  const i = Math.floor(h);
  return (values[i] ?? 0) * (1 - (h - i)) + (values[Math.min(i + 1, 23)] ?? 0) * (h - i);
}

/** Тёмная карта сервиса в прямоугольнике rect: подложка, линии по посадкам, остановки теплом, вагоны. */
export function drawUiMap(ctx: CanvasRenderingContext2D, rect: Rect, cam: Cam, o: UiMapOpts): void {
  const base = uiRaster();
  const pt = (x: number, y: number): Pt => [rect.x + rect.w / 2 + (x - cam.x) * cam.z, rect.y + rect.h / 2 - (y - cam.y) * cam.z];
  ctx.save();
  ctx.beginPath();
  ctx.rect(rect.x, rect.y, rect.w, rect.h);
  ctx.clip();
  ctx.fillStyle = '#1b1c21';
  ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
  const [bx, by] = pt(REGION.x0, REGION.y1);
  drawMipped(ctx, base, bx, by, (REGION.x1 - REGION.x0) * cam.z, (REGION.y1 - REGION.y0) * cam.z);
  const maxRoute = Math.max(...Object.values(o.routeHours).map((h) => hourValue(h, o.hour)), 1);
  const alpha = (route: number) => (o.focus == null || o.focus === route ? 1 : 1 - 0.8 * o.focusAmount);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  const k = clamp(cam.z * 22, 0.8, 2.2);
  for (const r of ROUTES) {
    const load = hourValue(o.routeHours[r.route] ?? [], o.hour) / maxRoute;
    ctx.beginPath();
    r.pts.forEach(([x, y], i) => {
      const [sx, sy] = pt(x, y);
      if (i) ctx.lineTo(sx, sy);
      else ctx.moveTo(sx, sy);
    });
    const a = alpha(r.route) * (r.direction ? 0.7 : 1);
    ctx.globalAlpha = a * 0.25;
    ctx.strokeStyle = UI_ROUTE[r.route]!;
    ctx.lineWidth = (6 + 12 * load) * k;
    ctx.stroke();
    ctx.globalAlpha = a;
    ctx.lineWidth = (2 + 4 * load) * k;
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  // остановки: кружок теплом по посадкам в этот час
  const maxStop = Math.max(...STOPS.map((s) => hourValue(s.hours, o.hour)), 1);
  for (const s of STOPS) {
    const [sx, sy] = pt(s.x, s.y);
    if (sx < rect.x - 20 || sx > rect.x + rect.w + 20 || sy < rect.y - 20 || sy > rect.y + rect.h + 20) continue;
    const focused = o.focus == null || s.routes.includes(o.focus);
    const a = focused ? 1 : 1 - 0.85 * o.focusAmount;
    const v = hourValue(s.hours, o.hour) / maxStop;
    const r = (2.2 + 9 * Math.sqrt(v)) * k * 0.75;
    ctx.globalAlpha = a * 0.9;
    ctx.fillStyle = heat(Math.sqrt(v));
    ctx.beginPath();
    ctx.arc(sx, sy, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = 'rgba(10,10,14,0.85)';
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }
  // вагоны: прямоугольники с полосой окон, едут по трассе
  const len = 11 * k;
  const w = len * 0.4;
  for (const r of ROUTES) {
    const a = alpha(r.route);
    if (a < 0.3 || hourValue(o.routeHours[r.route] ?? [], o.hour) <= 0) continue;
    const n = Math.max(2, Math.floor(r.length / 1700));
    for (let i = 0; i < n; i++) {
      const s = (o.t * 120 + (i * r.length) / n + r.route * 311 + r.direction * 811) % r.length;
      const p = pointAt(r, s);
      const [sx, sy] = pt(p.x, p.y);
      if (sx < rect.x || sx > rect.x + rect.w || sy < rect.y || sy > rect.y + rect.h) continue;
      ctx.save();
      ctx.translate(sx, sy);
      ctx.rotate(p.a);
      ctx.globalAlpha = a;
      ctx.fillStyle = UI_ROUTE[r.route]!;
      ctx.beginPath();
      ctx.roundRect(-len / 2, -w / 2, len, w, w / 2);
      ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.fillRect(-len / 2 + w * 0.6, -w * 0.13, len - w * 1.2, w * 0.26);
      ctx.restore();
    }
  }
  ctx.restore();
}

/** Точка мира в пиксели прямоугольника карты. */
export function uiPoint(rect: Rect, cam: Cam, x: number, y: number): Pt {
  return [rect.x + rect.w / 2 + (x - cam.x) * cam.z, rect.y + rect.h / 2 - (y - cam.y) * cam.z];
}

/**
 * Карта из растра: неподвижный рисунок строится один раз для камеры base (самой дальней на слайде) с запасом
 * резкости res, а медленный дрейф камеры - это сдвиг и масштаб растра. Вагоны рисуются поверх вживую.
 */
export function cachedMap(ctx: CanvasRenderingContext2D, key: string, base: Cam, cam: Cam, o: MapOpts, res: number): void {
  const pal = o.pal ?? DAY;
  const k = cam.z / base.z;
  ctx.save();
  ctx.translate(960 + (base.x - cam.x) * cam.z, 540 - (base.y - cam.y) * cam.z);
  ctx.scale(k, k);
  ctx.translate(-960, -540);
  sprite(ctx, `map|${key}`, 0, 0, 1920, 1080, (g) => drawMap(g, base, { ...o, t: 0, trams: false }), res);
  ctx.restore();
  if (o.trams !== false) trams(ctx, cam, o, pal, o.t);
}
