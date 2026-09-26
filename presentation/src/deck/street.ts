import { FILM, P, lib, type Pt } from '../film';
import { skyline, type Scene, type Shape } from './landmarks';
import { tram } from './tram';

// Улица Москвы тушью: панорама места (landmarks.ts), пятиэтажки, пути с контактной сетью и «Витязь-М» (tram.ts).
// Панорама рисуется один раз в растр, вагон и провода живые.

export interface StreetPal {
  ink: string;
  fill: string;
  fill2: string;
  window: string;
  lit: string;
  /** Ночью и на синем листе цветные фасады и купола приглушаются к этому цвету. */
  shade: string;
  shadeK: number;
}

export const PAPER_STREET: StreetPal = {
  ink: P.ink!, fill: '#E2D1B0', fill2: '#D8C3A0', window: '#B89C74', lit: '#F1BF4A', shade: '#E2D1B0', shadeK: 0,
};
export const DUSK_STREET: StreetPal = {
  ink: '#E9E1F5', fill: '#3A3358', fill2: '#332D4E', window: '#4A4270', lit: '#FFD27A', shade: '#3A3358', shadeK: 0.55,
};
export const BLUE_STREET: StreetPal = {
  ink: '#C8C1EF', fill: 'rgba(24,35,77,0.9)', fill2: 'rgba(24,35,77,0.75)', window: '#3A4A86', lit: '#FFF3DC', shade: '#18234D', shadeK: 0.62,
};

const skyCache = new Map<string, HTMLCanvasElement>();

/**
 * Панорама места в растр над линией земли, k - масштаб силуэтов. Строится один раз на место, палитру и масштаб экрана.
 */
function skylineRaster(pal: StreetPal, scene: Scene, seed: number, k: number, lit: boolean): HTMLCanvasElement {
  const key = `${pal.ink}|${scene}|${seed}|${k}|${lit}|${FILM.S.toFixed(3)}`;
  const known = skyCache.get(key);
  if (known) return known;
  const H = Math.ceil(380 * k);
  const c = FILM.makeCanvas(Math.round(1920 * FILM.S), Math.round(H * FILM.S));
  const g = c.getContext('2d')!;
  g.scale(FILM.S, FILM.S);
  const tp = (pts: Shape): Pt[] => pts.map(([x, y]) => [x, H + y * k]);
  const sky = skyline(scene, seed);
  const saved = FILM.frameT;
  FILM.frameT = 0.001;
  const ink = { closed: true, smooth: false, color: pal.ink, wobble: 0.5, taper: [3, 5] as [number, number] };
  for (const shape of sky.back) lib.inkPath(g, tp(shape), { ...ink, width: 1.6, fill: pal.fill2, seed: shape.length * 7 + seed });
  sky.colored.forEach((c, i) => {
    lib.inkPath(g, tp(c.shape), { ...ink, smooth: c.smooth ?? false, width: 1.5, fill: lib.mix(c.color, pal.shade, pal.shadeK), seed: 300 + i });
  });
  g.strokeStyle = lib.rgba(pal.ink, 0.5);
  g.lineWidth = 0.9;
  g.beginPath();
  for (const [a, b] of sky.lattice) {
    const [pa, pb] = tp([a, b]);
    g.moveTo(pa![0], pa![1]);
    g.lineTo(pb![0], pb![1]);
  }
  g.stroke();
  for (const shape of sky.front) lib.inkPath(g, tp(shape), { ...ink, width: 1.5, fill: pal.fill, seed: Math.round(shape[0]![0]), wobble: 0.4 });
  for (const [x, y] of tp(sky.windows)) {
    g.fillStyle = lit && (x * 7 + y * 3) % 5 > 1.4 ? pal.lit : lib.rgba(pal.window, 0.8);
    g.fillRect(x - 2.5 * k, y - 3 * k, 5 * k, 5 * k);
  }
  for (const shape of sky.trees) lib.inkPath(g, tp(shape), { closed: true, width: 1.4, color: pal.ink, fill: lit ? '#3F4D46' : '#A9BC8C', seed: Math.round(shape[0]![0]), wobble: 1 });
  for (const [x, y] of tp(sky.stars)) {
    g.fillStyle = '#C2413B';
    g.beginPath();
    for (let i = 0; i < 10; i++) {
      const a = -Math.PI / 2 + (i * Math.PI) / 5;
      const rr = (i % 2 ? 2.4 : 6) * k;
      if (i) g.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
      else g.moveTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
    }
    g.closePath();
    g.fill();
  }
  FILM.frameT = saved;
  skyCache.set(key, c);
  return c;
}

/** Рельсы со шпалами и контактный провод с опорами. */
function track(ctx: CanvasRenderingContext2D, x0: number, x1: number, y: number, s: number, pal: StreetPal, wireH: number): void {
  ctx.save();
  ctx.strokeStyle = pal.ink;
  ctx.lineWidth = 2.4;
  ctx.beginPath();
  ctx.moveTo(x0, y);
  ctx.lineTo(x1, y);
  ctx.stroke();
  ctx.strokeStyle = lib.rgba(pal.ink, 0.6);
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(x0, y + 5);
  ctx.lineTo(x1, y + 5);
  ctx.stroke();
  ctx.strokeStyle = lib.rgba(pal.ink, 0.55);
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  for (let x = x0; x < x1; x += 0.9 * s) {
    ctx.moveTo(x, y + 2);
    ctx.lineTo(x - 3, y + 9);
  }
  ctx.stroke();
  // опоры и провод с провисом
  const span = 26 * s;
  ctx.strokeStyle = lib.rgba(pal.ink, 0.75);
  ctx.lineWidth = 1.1;
  ctx.beginPath();
  for (let x = x0 - (x0 % span); x < x1 + span; x += span) {
    ctx.moveTo(x, y);
    ctx.lineTo(x, y - wireH - 0.8 * s);
    ctx.moveTo(x, y - wireH - 0.6 * s);
    ctx.lineTo(x + 1.2 * s, y - wireH - 0.2 * s);
    ctx.moveTo(x, y - wireH);
    ctx.quadraticCurveTo(x + span / 2, y - wireH + 0.35 * s, x + span, y - wireH);
  }
  ctx.stroke();
  ctx.restore();
}

export interface StreetOpts {
  pal: StreetPal;
  scene: Scene;
  seed: number;
  /** Масштаб силуэтов и вагона. */
  k: number;
  lit?: boolean;
  /** Скорость вагона, пикселей в секунду; знак - направление. */
  speed?: number;
  x0?: number;
  x1?: number;
  alpha?: number;
}

/**
 * Полоса улицы: панорама, пути, провод и вагон, который едет по кругу. y - уровень рельса.
 */
export function street(ctx: CanvasRenderingContext2D, y: number, t: number, o: StreetOpts): void {
  const x0 = o.x0 ?? 0;
  const x1 = o.x1 ?? 1920;
  const s = 13 * o.k;
  ctx.save();
  ctx.globalAlpha *= o.alpha ?? 1;
  ctx.beginPath();
  ctx.rect(x0, y - 420, x1 - x0, 460);
  ctx.clip();
  const sky = skylineRaster(o.pal, o.scene, o.seed, o.k, o.lit ?? false);
  const H = sky.height / FILM.S;
  ctx.drawImage(sky, 0, y - H - 4, 1920, H);
  track(ctx, x0, x1, y, s, o.pal, 5.7 * s);
  const speed = o.speed ?? 110;
  const len = 34 * s;
  const span = x1 - x0 + len + 200;
  const dir = speed > 0 ? -1 : 1;
  const pos = ((Math.abs(speed) * t) % span);
  const nose = dir < 0 ? x0 - 100 + pos : x1 + 100 - pos;
  tram(ctx, nose, y - 1, s, { pal: o.pal, dir, lit: o.lit, route: '17' });
  ctx.restore();
}

/** Панорама и пути без вагона: для сцены на остановке, где вагоном управляет сцена. */
export function backdrop(ctx: CanvasRenderingContext2D, y: number, pal: StreetPal, scene: Scene, k: number, s: number): void {
  const sky = skylineRaster(pal, scene, 6, k, false);
  const H = sky.height / FILM.S;
  ctx.drawImage(sky, 0, y - H - 4, 1920, H);
  track(ctx, 0, 1920, y, s, pal, 5.7 * s);
}
