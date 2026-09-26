import { lib, type Pt } from '../film';
import { SANS, sprite } from './g';
import type { StreetPal } from './street';

// Трёхсекционный «Витязь-М» сбоку в окраске московских вагонов с автономным ходом. Рисунок кэшируется в растр.

export interface TramOpts {
  pal: StreetPal;
  /** 1 - едет влево носом вперёд, -1 - вправо. */
  dir: number;
  lit?: boolean;
  route?: string;
  /** Двери: 0 - закрыты, 1 - открыты. */
  doors?: number;
  /** Заполнение салона: 1 - все места, больше 1 - люди стоят плотнее. */
  fill?: number;
}

/** Места дверей по длине вагона, метры от носа: по две на секцию. */
export const DOORS = [2.2, 8, 13.7, 19.5, 25, 30.8];

/**
 * Окраска московских вагонов с автономным ходом (30649-30651): белая крыша, сплошная чёрная полоса остекления
 * с белой волной сверху, крупная надпись на стёклах, синий низ с выступами над тележками, красный пантограф.
 */
const LIVERY = {
  white: '#F5F6F8',
  glass: '#191B20',
  blue: '#2F6ED4',
  roof: '#DCDFE4',
  red: '#D23A2F',
  number: '#2B2D33',
  seam: 'rgba(150,156,166,0.9)',
  inside: '#B7A68A',
};
const LIVERY_DUSK = { ...LIVERY, white: '#DCD8E6', blue: '#2A5FB8', roof: '#B9B5C8', inside: '#D8B070' };
const SLOGAN = 'Это автономный трамвай.';
const BATTERY = 'Может ехать на батарее.';

// Высоты по корпусу, метры над рельсом со знаком минус: синий низ, белый пояс, полоса стёкол, белая крыша.
const Y_FLOOR = -0.6;
const Y_BLUE = -0.95;
const Y_GLASS = -1.4;
const Y_GLASS_TOP = -3.05;
const Y_ROOF = -3.5;
const BOGIES = [3, 16.9, 31];
const CARS: [number, number][] = [[0, 11.2], [11.5, 22.5], [22.8, 34]];
/** Центр надписи по длине вагона, метры от носа: на средней секции, как на фото вагона сбоку. */
const SLOGAN_AT = 17.2;

/**
 * «Витязь-М» сбоку: три секции, двери, окна, тележки, пантограф. x - нос, y - уровень рельса, s - пикселей в метре.
 * Рисунок кэшируется в растр на каждый вид: двери и заполнение салона округляются до десятых.
 */
export function tram(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, o: TramOpts): void {
  const doors = Math.round((o.doors ?? 0) * 10) / 10;
  const fill = Math.round((o.fill ?? 0) * 10) / 10;
  const key = `tram|${s}|${o.dir}|${o.pal.ink}|${o.lit ?? false}|${o.route ?? ''}|${doors}|${fill}`;
  const len = 34.6 * s;
  const left = o.dir > 0 ? -0.3 * s : -len;
  sprite(ctx, key, x + left, y - 5.8 * s, len + 0.6 * s, 6.3 * s, (g) => drawTram(g, x, y, s, { ...o, doors, fill }));
}

type Tp = (pts: Pt[]) => Pt[];

function carShape(a: number, b: number, i: number): Pt[] {
  if (i === 0) return [[0.35, Y_FLOOR], [0.08, Y_BLUE], [0.05, Y_GLASS], [0.3, -2.3], [0.75, Y_GLASS_TOP], [1.3, -3.42], [1.9, Y_ROOF], [b, Y_ROOF], [b, Y_FLOOR]];
  if (i === 2) return [[a, Y_FLOOR], [a, Y_ROOF], [b - 0.9, Y_ROOF], [b - 0.3, -3.3], [b, -2.8], [b + 0.05, Y_GLASS], [b - 0.1, -0.8], [b - 0.4, Y_FLOOR]];
  return [[a, Y_FLOOR], [a, Y_ROOF], [b, Y_ROOF], [b, Y_FLOOR]];
}

function fillPoly(ctx: CanvasRenderingContext2D, pts: Pt[], color: string): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  lib.tracePath(ctx, pts, true);
  ctx.fill();
}

function drawTram(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, o: TramOpts): void {
  const d = o.dir;
  const tp: Tp = (pts) => pts.map(([mx, my]) => [x + d * mx * s, y + my * s]);
  const L = o.lit ? LIVERY_DUSK : LIVERY;
  const ink = { width: 1.8, color: o.pal.ink, wobble: 0.35, taper: [3, 4] as [number, number], smooth: false };
  const open = o.doors ?? 0;
  // тележки
  for (const cx of BOGIES) {
    for (const wx of [-0.6, 0.6]) lib.inkCircle(ctx, x + d * (cx + wx) * s, y - 0.32 * s, 0.34 * s, { ...ink, smooth: true, fill: o.pal.ink, seed: Math.round(cx * 10 + wx * 10) });
    lib.inkPath(ctx, tp([[cx - 1.2, -0.4], [cx - 1.2, -0.7], [cx + 1.2, -0.7], [cx + 1.2, -0.4]]), { ...ink, closed: true, fill: L.roof, seed: Math.round(cx) });
  }
  // гармошки между секциями
  for (const [a, b] of [[11.2, 11.5], [22.5, 22.8]] as const) fillPoly(ctx, tp([[a, -0.8], [a, -3.3], [b, -3.3], [b, -0.8]]), '#2A2C31');
  CARS.forEach(([a, b], i) => {
    const body = tp(carShape(a, b, i));
    ctx.save();
    ctx.beginPath();
    lib.tracePath(ctx, body, true);
    ctx.clip();
    fillPoly(ctx, tp([[a - 1, Y_FLOOR + 0.1], [a - 1, Y_ROOF - 0.1], [b + 1, Y_ROOF - 0.1], [b + 1, Y_FLOOR + 0.1]]), L.white);
    fillPoly(ctx, tp([[a - 1, Y_FLOOR + 0.1], [a - 1, Y_BLUE], [b + 1, Y_BLUE], [b + 1, Y_FLOOR + 0.1]]), L.blue);
    for (const cx of BOGIES.filter((c) => c > a && c < b)) blueHump(ctx, tp, cx, L.blue);
    // стёкла одной полосой; у кабины лобовое стекло поднимается к крыше
    const glass: Pt[] = i === 0
      ? [[-1, Y_GLASS], [b + 1, Y_GLASS], [b + 1, Y_GLASS_TOP], [2.3, Y_GLASS_TOP], [1.5, -3.32], [0.8, -3.3], [-1, -1.9]]
      : [[a - 1, Y_GLASS], [b + 1, Y_GLASS], [b + 1, Y_GLASS_TOP], [a - 1, Y_GLASS_TOP]];
    fillPoly(ctx, tp(glass), L.glass);
    windows(ctx, tp, a, b, i, o, s);
    if (i === 0) cabPillar(ctx, tp, L.white, s);
    ornament(ctx, tp, i === 0 ? 2.25 : a, i === 2 ? b - 0.9 : b, s);
    doorSeams(ctx, tp, a, b, open, L, s);
    ctx.restore();
    lib.inkPath(ctx, body, { ...ink, closed: true, seed: 40 + i, width: 2.2 });
    // оборудование на крыше
    lib.inkPath(ctx, tp([[a + 2, Y_ROOF], [a + 2, -3.8], [b - 2, -3.8], [b - 2, Y_ROOF]]), { ...ink, closed: true, width: 1.4, fill: L.roof, seed: 70 + i });
  });
  decals(ctx, x, y, s, d, open, L);
  routeSign(ctx, tp, o.route, s, d);
  // фара
  const [hx, hy] = tp([[0.35, -1.12]])[0]!;
  if (o.lit) lib.glowDot(ctx, hx, hy, 0.18 * s, { color: '#FFE3A3', rays: 0, glow: 7, intensity: 0.9, seed: 5 });
  else {
    ctx.fillStyle = '#FFF3DC';
    ctx.beginPath();
    ctx.arc(hx, hy, 0.14 * s, 0, Math.PI * 2);
    ctx.fill();
  }
  // пантограф на средней секции, красный, как на вагоне
  lib.inkPath(ctx, tp([[16.2, -3.8], [17.4, -4.7], [16.4, -5.5], [18.2, -5.5]]), { ...ink, color: L.red, width: 2, seed: 91, smooth: false });
}

/** Синий обтекатель над тележкой: низ поднимается в белый пояс. */
function blueHump(ctx: CanvasRenderingContext2D, tp: Tp, cx: number, color: string): void {
  const top = Y_BLUE - 0.14;
  fillPoly(ctx, tp([[cx - 1.9, Y_BLUE + 0.01], [cx - 1.6, top], [cx + 1.6, top], [cx + 1.9, Y_BLUE + 0.01]]), color);
}

/** Белая стойка между лобовым стеклом и боковыми окнами кабины. */
function cabPillar(ctx: CanvasRenderingContext2D, tp: Tp, color: string, s: number): void {
  const [[x0, y0], [cx, cy], [x1, y1]] = tp([[2.25, Y_GLASS_TOP - 0.05], [1.75, -2.4], [1.95, Y_GLASS]]) as [Pt, Pt, Pt];
  ctx.strokeStyle = color;
  ctx.lineWidth = Math.max(1, 0.09 * s);
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.quadraticCurveTo(cx, cy, x1, y1);
  ctx.stroke();
}

/** Салон за тонированным стеклом: вечером тёплый свет, в окнах головы пассажиров. */
function windows(ctx: CanvasRenderingContext2D, tp: Tp, a: number, b: number, i: number, o: TramOpts, s: number): void {
  const doors = DOORS.filter((dx) => dx > a && dx + 1.3 < b - 0.3);
  for (let wx = a + (i === 0 ? 2.5 : 0.4); wx + 1.1 < b - (i === 2 ? 0.8 : 0.3); wx += 1.5) {
    if (doors.some((dx) => wx + 1.1 > dx - 0.1 && wx < dx + 1.4)) continue;
    if (o.lit) fillPoly(ctx, tp([[wx, -1.55], [wx, -2.75], [wx + 1.15, -2.75], [wx + 1.15, -1.55]]), 'rgba(255,196,110,0.34)');
    heads(ctx, tp, wx, o.fill ?? 0, s, wx * 13 + i, o.lit ? 'rgba(30,24,18,0.85)' : 'rgba(168,176,190,0.5)');
  }
}

/** Белая «бегущая волна» по верху стёкол: гребень закручивается в завиток. Мелко - просто линия. */
function ornament(ctx: CanvasRenderingContext2D, tp: Tp, a: number, b: number, s: number): void {
  const h = 0.24;
  const yc = Y_GLASS_TOP + 0.2;
  ctx.save();
  ctx.strokeStyle = '#F2F3F5';
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(0.8, 0.035 * s);
  ctx.beginPath();
  const line = tp([[a + 0.1, yc + h / 2], [b - 0.1, yc + h / 2]]);
  ctx.moveTo(...line[0]!);
  ctx.lineTo(...line[1]!);
  if (h * s >= 5) {
    const p = h * 2.1;
    const R = 0.46 * h;
    for (let ux = a + 0.15; ux + p < b - 0.1; ux += p) {
      const cx = ux + 0.62 * p;
      const cy = yc - h / 2 + R;
      const [[x0, y0], [c1x, c1y], [c2x, c2y], [x1, y1]] = tp([[ux, yc + h / 2], [ux + 0.3 * p, yc + h / 2], [cx - R * 1.1, yc - h / 2], [cx, yc - h / 2]]) as [Pt, Pt, Pt, Pt];
      ctx.moveTo(x0, y0);
      ctx.bezierCurveTo(c1x, c1y, c2x, c2y, x1, y1);
      const turn: Pt[] = [];
      for (let k = 1; k <= 14; k++) {
        const q = k / 14;
        const ang = -Math.PI / 2 + q * Math.PI * 2.2;
        const r = R * (1 - 0.7 * q);
        turn.push([cx + Math.cos(ang) * r, cy + Math.sin(ang) * r]);
      }
      for (const [px, py] of tp(turn)) ctx.lineTo(px, py);
    }
  }
  ctx.stroke();
  ctx.restore();
}

/** Двери: тонкий контур створок; открытая дверь - светлый проём салона. */
function doorSeams(ctx: CanvasRenderingContext2D, tp: Tp, a: number, b: number, open: number, L: typeof LIVERY, s: number): void {
  const pw = 0.65 * (1 - 0.82 * open);
  for (const dx of DOORS.filter((v) => v > a && v + 1.3 < b - 0.3)) {
    if (open > 0) {
      fillPoly(ctx, tp([[dx + pw, Y_FLOOR - 0.05], [dx + pw, Y_GLASS_TOP + 0.02], [dx + 1.3 - pw, Y_GLASS_TOP + 0.02], [dx + 1.3 - pw, Y_FLOOR - 0.05]]), L.inside);
      const [[px, py0], [, py1]] = tp([[dx + 0.65, Y_FLOOR - 0.05], [dx + 0.65, Y_GLASS_TOP + 0.02]]) as [Pt, Pt];
      ctx.strokeStyle = lib.rgba('#E3B23C', Math.min(1, open * 1.5));
      ctx.lineWidth = Math.max(1, 0.07 * s);
      ctx.beginPath();
      ctx.moveTo(px, py0);
      ctx.lineTo(px, py1);
      ctx.stroke();
    }
    ctx.strokeStyle = L.seam;
    ctx.lineWidth = Math.max(0.7, 0.035 * s);
    ctx.beginPath();
    for (const [p0, p1] of [[dx, dx + pw], [dx + 1.3 - pw, dx + 1.3]] as const) {
      lib.tracePath(ctx, tp([[p0, Y_FLOOR - 0.05], [p0, Y_GLASS_TOP + 0.02], [p1, Y_GLASS_TOP + 0.02], [p1, Y_FLOOR - 0.05]]), true);
    }
    ctx.stroke();
  }
}

/** Надписи на борту читаются слева направо в любую сторону движения; в открытых дверях их нет. */
function decals(ctx: CanvasRenderingContext2D, x: number, y: number, s: number, d: number, open: number, L: typeof LIVERY): void {
  const at = (m: number) => x + d * m * s;
  const cx = at(SLOGAN_AT);
  ctx.save();
  if (open > 0) {
    const pw = 0.65 * (1 - 0.82 * open);
    ctx.beginPath();
    ctx.rect(x - 40 * s, y - 6 * s, 80 * s, 7 * s);
    for (const dx of DOORS) {
      const x0 = at(dx + pw);
      const x1 = at(dx + 1.3 - pw);
      ctx.rect(Math.min(x0, x1), y - 4 * s, Math.abs(x1 - x0), 4 * s);
    }
    ctx.clip('evenodd');
  }
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.font = `500 100px ${SANS}`;
  const size = Math.min((100 * 12.8 * s) / ctx.measureText(SLOGAN).width, 0.94 * s);
  ctx.font = `500 ${size}px ${SANS}`;
  ctx.fillStyle = '#F7F8FA';
  ctx.fillText(SLOGAN, cx, y - 1.82 * s);
  const small = 0.3 * s;
  ctx.font = `500 ${small}px ${SANS}`;
  ctx.fillStyle = L.blue;
  const bw = ctx.measureText(BATTERY).width;
  const bx = cx - 0.3 * s;
  ctx.fillText(BATTERY, bx, y - 1.07 * s);
  ctx.font = `500 ${0.24 * s}px ${SANS}`;
  ctx.fillStyle = L.number;
  ctx.textAlign = 'right';
  ctx.fillText('30651', bx - bw / 2 - 0.9 * s, y - 1.08 * s);
  ctx.restore();
  // герб Москвы у кабины
  const gx = at(3.4);
  const gy = y - 1.16 * s;
  const gw = 0.2 * s;
  ctx.fillStyle = L.red;
  ctx.beginPath();
  ctx.moveTo(gx - gw / 2, gy - gw * 0.6);
  ctx.lineTo(gx + gw / 2, gy - gw * 0.6);
  ctx.lineTo(gx + gw / 2, gy + gw * 0.25);
  ctx.quadraticCurveTo(gx + gw / 2, gy + gw * 0.6, gx, gy + gw * 0.72);
  ctx.quadraticCurveTo(gx - gw / 2, gy + gw * 0.6, gx - gw / 2, gy + gw * 0.25);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = '#F5F6F8';
  ctx.beginPath();
  ctx.arc(gx, gy, gw * 0.18, 0, Math.PI * 2);
  ctx.fill();
}

/** Номер маршрута на табло над лобовым стеклом. */
function routeSign(ctx: CanvasRenderingContext2D, tp: Tp, route: string | undefined, s: number, d: number): void {
  if (!route) return;
  const [rx, ry] = tp([[1.0, -3.1]])[0]!;
  ctx.save();
  ctx.fillStyle = '#101114';
  ctx.fillRect(d > 0 ? rx : rx - 1.5 * s, ry - 0.2 * s, 1.5 * s, 0.4 * s);
  ctx.font = `700 ${0.34 * s}px "JetBrains Mono", monospace`;
  ctx.fillStyle = '#FFB547';
  ctx.textAlign = 'center';
  ctx.fillText(route, d > 0 ? rx + 0.75 * s : rx - 0.75 * s, ry + 0.13 * s);
  ctx.restore();
}

/** Головы пассажиров в окне: до двух внизу, при переполнении ещё ряд выше и теснее. */
function heads(ctx: CanvasRenderingContext2D, tp: Tp, wx: number, fill: number, s: number, seed: number, color: string): void {
  if (fill <= 0) return;
  const r = lib.rng(`h${Math.round(seed)}`);
  const slots: [number, number][] = [[0.3, -2.18], [0.82, -2.22], [0.55, -2.5], [0.12, -2.45], [0.98, -2.48]];
  const n = Math.min(slots.length, Math.floor(fill * 2.2 + r()));
  ctx.fillStyle = color;
  for (let k = 0; k < n; k++) {
    const [hx, hy] = slots[k]!;
    const [[px, py]] = tp([[wx + hx, hy]]) as [Pt];
    ctx.beginPath();
    ctx.arc(px, py, 0.16 * s, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(px, py + 0.34 * s, 0.24 * s, 0.2 * s, 0, Math.PI, 0);
    ctx.fill();
  }
}
