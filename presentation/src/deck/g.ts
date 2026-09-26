import { E, FILM, P, lib, type EaseName, type Pt } from '../film';

// Текст, карточки и заголовки в стиле презентации LCT_2026: тонкий гротеск, моноширинные подписи с
// разрядкой, линейка с делениями под заголовком. Всё - чистые функции времени слайда t.

export const SANS = '"Onest", "Segoe UI Variable Display", system-ui, sans-serif';
export const MONO = '"JetBrains Mono", ui-monospace, Consolas, monospace';

/** Цвета поверх палитры движка: сети на синьке, графит интерфейса, цвета маршрутов на бумаге. */
export const C = {
  power: '#FF3D98',
  water: '#6FB7FF',
  gas: '#F2C94C',
  heat: '#FF8A5B',
  sewer: '#9CE6C6',
  telecom: '#C8C1EF',
  graphite: '#1D1F22',
  screen: '#0E1014',
};

/** Маршруты на бумаге: те же оттенки, что в сервисе, только темнее, чтобы читались на кремовом листе. */
export const ROUTE_INK: Record<number, string> = {
  1: '#3B6FB6', 5: '#C2415B', 7: '#C98A1B', 11: '#2E8C7E', 12: '#7A4FB0',
  17: '#D8742B', 25: '#2F8FB8', 26: '#6C8F2F', 28: '#C0588C', 50: '#5A6378',
};

const sprites = new Map<string, HTMLCanvasElement>();

export const clamp = (v: number, lo = 0, hi = 1) => (v < lo ? lo : v > hi ? hi : v);

/** Доля появления с t0 за dur секунд. */
export const seg = (t: number, t0: number, dur: number, e: EaseName = 'outExpo') => lib.seg(t, t0, t0 + dur, e);

export interface TextOpts {
  size?: number;
  weight?: number;
  color?: string;
  alpha?: number;
  align?: 'left' | 'center' | 'right';
  family?: string;
  tracking?: number;
  baseline?: CanvasTextBaseline;
  /** Доля проявления: буквы всплывают по очереди слева направо. */
  p?: number | null;
  rise?: number;
  maxW?: number;
  lh?: number;
}

const measureCache = new Map<string, number>();
export function font(o: TextOpts): string {
  return `${o.weight ?? 300} ${o.size ?? 42}px ${o.family ?? SANS}`;
}

function measure(ctx: CanvasRenderingContext2D, str: string, f: string, tracking: number): number {
  const key = `${f}|${tracking}|${str}`;
  let v = measureCache.get(key);
  if (v == null) {
    ctx.save();
    ctx.font = f;
    ctx.letterSpacing = `${tracking}px`;
    v = ctx.measureText(str).width;
    ctx.restore();
    if (measureCache.size > 6000) measureCache.clear();
    measureCache.set(key, v);
  }
  return v;
}

export function width(ctx: CanvasRenderingContext2D, str: string, o: TextOpts): number {
  return measure(ctx, str, font(o), o.tracking ?? 0);
}

const wrapCache = new Map<string, string[]>();
export function lines(ctx: CanvasRenderingContext2D, str: string, o: TextOpts): string[] {
  const f = font(o);
  const tr = o.tracking ?? 0;
  const maxW = o.maxW ?? 800;
  const key = `${f}|${maxW}|${str}`;
  const known = wrapCache.get(key);
  if (known) return known;
  const out: string[] = [];
  for (const para of str.split('\n')) {
    let line = '';
    for (const w of para.split(' ')) {
      const test = line ? `${line} ${w}` : w;
      if (line && measure(ctx, test, f, tr) > maxW) {
        out.push(line);
        line = w;
      } else line = test;
    }
    out.push(line);
  }
  wrapCache.set(key, out);
  return out;
}

/** Одна строка; при o.p < 1 буквы поднимаются и проявляются по очереди. Возвращает ширину. */
export function text(ctx: CanvasRenderingContext2D, str: string, x: number, y: number, o: TextOpts = {}): number {
  if (!str) return 0;
  const f = font(o);
  const tr = o.tracking ?? 0;
  const w = measure(ctx, str, f, tr);
  let x0 = x;
  if (o.align === 'center') x0 = x - w / 2;
  else if (o.align === 'right') x0 = x - w;
  ctx.save();
  ctx.font = f;
  ctx.fillStyle = o.color ?? P.ink!;
  ctx.textBaseline = o.baseline ?? 'alphabetic';
  ctx.letterSpacing = `${tr}px`;
  const alpha = o.alpha ?? 1;
  if (o.p == null || o.p >= 1) {
    ctx.globalAlpha *= alpha;
    ctx.fillText(str, x0, y);
  } else if (o.p > 0) {
    const spread = 0.55;
    let cx = x0;
    const base = ctx.globalAlpha;
    for (let i = 0; i < str.length; i++) {
      const ch = str[i]!;
      const cw = measure(ctx, ch, f, tr);
      const q = clamp((o.p - (i / str.length) * spread) / (1 - spread));
      if (q > 0) {
        const e = E.outCubic(q);
        ctx.globalAlpha = base * alpha * e;
        ctx.fillText(ch, cx, y + (1 - e) * (o.rise ?? 14));
      }
      cx += cw;
    }
  }
  ctx.restore();
  return w;
}

/** Абзац по ширине o.maxW; o.p проявляет его строками. Возвращает высоту. */
export function para(ctx: CanvasRenderingContext2D, str: string, x: number, y: number, o: TextOpts = {}): number {
  const ls = lines(ctx, str, o);
  const lh = o.lh ?? (o.size ?? 32) * 1.34;
  ls.forEach((line, i) => {
    const q = o.p == null ? 1 : clamp((o.p * (ls.length + 1.2) - i) / 1.2);
    if (q > 0) text(ctx, line, x, y + i * lh, { ...o, p: q >= 1 ? null : q, rise: 10 });
  });
  return ls.length * lh;
}

/** Мелкая моноширинная подпись с разрядкой. */
export function kicker(ctx: CanvasRenderingContext2D, str: string, x: number, y: number, o: TextOpts = {}): number {
  return text(ctx, str, x, y, { size: 22, weight: 600, family: MONO, tracking: 3, alpha: 0.8, ...o });
}

/** Карточка на бумаге (рамка тушью) или на синьке (двойная лавандовая рамка). */
export function card(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number,
  o: { p?: number; blue?: boolean; dark?: boolean; seed?: number; fill?: string } = {}): void {
  const q = o.p ?? 1;
  if (q <= 0) return;
  ctx.save();
  const e = E.outBack(clamp(q));
  ctx.translate(x + w / 2, y + h / 2);
  ctx.scale(lib.lerp(0.94, 1, e), lib.lerp(0.94, 1, e));
  ctx.globalAlpha *= clamp(q * 2);
  ctx.translate(-(x + w / 2), -(y + h / 2));
  if (o.blue) {
    ctx.fillStyle = lib.rgba(P.navyLight!, 0.94);
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = lib.rgba(P.lavender!, 0.7);
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);
    ctx.strokeStyle = lib.rgba(P.lavender!, 0.3);
    ctx.lineWidth = 1;
    ctx.strokeRect(x + 7, y + 7, w - 14, h - 14);
  } else if (q >= 1) {
    // карточка на месте: рамка тушью из растра, без пересчёта каждый кадр
    sprite(ctx, `card|${x}|${y}|${w}|${h}|${o.seed ?? 3}|${o.fill ?? ''}`, x - 6, y - 6, w + 12, h + 12, (g) => {
      g.fillStyle = lib.rgba(o.fill ?? P.white!, 0.96);
      g.fillRect(x, y, w, h);
      lib.inkPath(g, lib.rectPts(x, y, w, h, 30), { closed: true, width: 2.4, seed: o.seed ?? 3, wobble: 1.1, boil: false });
    });
  } else {
    ctx.fillStyle = lib.rgba(o.fill ?? P.white!, 0.96);
    ctx.fillRect(x, y, w, h);
    lib.inkPath(ctx, lib.rectPts(x, y, w, h, 30), { closed: true, width: 2.4, seed: o.seed ?? 3, wobble: 1.1 });
  }
  ctx.restore();
}

/** Заголовок главы в левом верхнем углу: номер моноширинным, строка тонким гротеском, линия тушью. */
export function chapter(ctx: CanvasRenderingContext2D, t: number, num: string, title: string, o: { blue?: boolean } = {}): void {
  const blue = o.blue ?? false;
  const a = seg(t, 0.25, 0.4, 'linear');
  const w = width(ctx, title, { size: 48, weight: 300 }) + 64;
  if (a > 0) {
    ctx.save();
    ctx.globalAlpha *= a;
    ctx.fillStyle = blue ? lib.rgba(P.navyLight!, 0.94) : lib.rgba(P.paper!, 0.95);
    ctx.fillRect(40, 26, w, 132);
    ctx.restore();
    if (a >= 1) {
      sprite(ctx, `chapter|${w}|${blue}`, 30, 148, w + 20, 20, (g) => lib.inkLine(g, 40, 158, 40 + w, 158, { width: 2.4, color: blue ? P.lavender : P.ink, seed: 12, boil: false }));
    } else {
      lib.inkLine(ctx, 40, 158, 40 + w * a, 158, { width: 2.4, color: blue ? P.lavender : P.ink, seed: 12, alpha: a });
    }
  }
  kicker(ctx, num, 72, 72, { color: blue ? P.lavender : P.inkSoft, p: seg(t, 0.25, 0.5, 'linear') });
  text(ctx, title, 68, 128, { size: 48, weight: 300, color: blue ? P.lineWhite : P.ink, p: seg(t, 0.35, 0.9, 'linear') });
}

/** Пункт списка: номер в кружке и абзац. Активный пункт ярче, пройденные спокойнее. */
export function bullet(ctx: CanvasRenderingContext2D, t: number, t0: number, x: number, y: number, str: string,
  o: { n: number; active: boolean; maxW: number; blue?: boolean; size?: number }): number {
  const q = seg(t, t0, 0.5);
  if (q <= 0) return 0;
  const ink = o.blue ? P.lineWhite! : P.ink!;
  const soft = o.blue ? P.lavender! : P.inkSoft!;
  const size = o.size ?? 28;
  ctx.save();
  ctx.globalAlpha *= clamp(q * 1.5);
  const cy = y - size * 0.36;
  ctx.fillStyle = o.active ? P.annMagenta! : lib.rgba(soft, 0.2);
  ctx.beginPath();
  ctx.arc(x + 16, cy, 16, 0, Math.PI * 2);
  ctx.fill();
  text(ctx, String(o.n), x + 16, cy + 6, { size: 17, weight: 700, family: MONO, align: 'center', color: o.active ? '#fff' : soft });
  ctx.restore();
  return para(ctx, str, x + 48, y, { size, weight: o.active ? 500 : 400, color: o.active ? ink : lib.mix(ink, soft, 0.35),
    maxW: o.maxW - 48, lh: size * 1.32, p: seg(t, t0 + 0.05, 0.9, 'linear') });
}

/** Компас-роза: круг, восемь лучей, пурпурная стрелка на север. */
export function compass(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, color: string, t: number): void {
  const q = seg(t, 0.4, 1.2);
  if (q <= 0) return;
  ctx.save();
  ctx.globalAlpha *= q;
  lib.inkCircle(ctx, x, y, r, { width: 1.6, color, seed: 91, wobble: 0.5 });
  for (let k = 0; k < 8; k++) {
    const a = (k / 8) * Math.PI * 2 + 0.12;
    const L = k % 2 ? r * 0.8 : r * 1.35;
    lib.inkLine(ctx, x - Math.cos(a) * L * 0.2, y - Math.sin(a) * L * 0.2, x + Math.cos(a) * L, y + Math.sin(a) * L,
      { width: 1.3, color, seed: 92 + k, wobble: 0.2 });
  }
  lib.inkLine(ctx, x, y, x + Math.sin(0.12) * r * 1.5, y - Math.cos(0.12) * r * 1.5, { width: 3, color: P.annMagenta, seed: 99, wobble: 0 });
  text(ctx, 'С', x + Math.sin(0.12) * r * 1.9, y - Math.cos(0.12) * r * 1.9, { size: 18, weight: 700, family: MONO, color, align: 'center' });
  ctx.restore();
}

/** Пурпурная пометка: кольцо вокруг точки и подпись моноширинным. */
export function mark(ctx: CanvasRenderingContext2D, t: number, t0: number, x: number, y: number, r: number,
  label?: string, o: { dx?: number; dy?: number; align?: 'left' | 'right' } = {}): void {
  const q = seg(t, t0, 0.5);
  if (q <= 0) return;
  const pts: Pt[] = lib.ellipsePts(x, y, r * (0.9 + 0.1 * q), r * (0.9 + 0.1 * q), 48);
  lib.inkPath(ctx, pts.slice(0, Math.max(2, Math.round(pts.length * q))), { width: 3, color: P.annMagenta, seed: Math.round(x + y), wobble: 1.4 });
  if (!label) return;
  const dx = o.dx ?? r + 18;
  const dy = o.dy ?? -r - 10;
  const lx = x + dx;
  const ly = y + dy;
  const lq = seg(t, t0 + 0.25, 0.5);
  if (lq <= 0) return;
  lib.inkPath(ctx, [[x + (dx > 0 ? r * 0.7 : -r * 0.7), y - r * 0.7], [lx, ly + 8]], { width: 2, color: P.annMagenta, seed: 7, wobble: 0.3, alpha: lq });
  const w = width(ctx, label, { size: 22, weight: 600, family: MONO });
  const align = o.align ?? (dx > 0 ? 'left' : 'right');
  const bx = align === 'left' ? lx - 6 : lx - w - 10;
  ctx.save();
  ctx.globalAlpha *= lq;
  ctx.fillStyle = P.annMagenta!;
  ctx.fillRect(bx, ly - 22, w + 16, 32);
  ctx.restore();
  text(ctx, label, bx + 8, ly, { size: 22, weight: 600, family: MONO, color: '#fff', p: lq });
}

export const fmt = (v: number) => String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
export const fmt1 = (v: number) => v.toFixed(1).replace('.', ',');

/**
 * Растр для неподвижного рисунка: строится один раз на ключ и масштаб экрана, потом только копируется.
 * Так «тушь», которая строит линию из сотен четырёхугольников, не пересчитывается каждый кадр.
 */
export function sprite(ctx: CanvasRenderingContext2D, key: string, x: number, y: number, w: number, h: number,
  draw: (g: CanvasRenderingContext2D) => void, res = 1): void {
  const k = `${key}|${FILM.S.toFixed(3)}|${res}`;
  let c = sprites.get(k);
  if (!c) {
    c = FILM.makeCanvas(Math.max(1, Math.ceil(w * FILM.S * res)), Math.max(1, Math.ceil(h * FILM.S * res)));
    const g = c.getContext('2d')!;
    g.scale(FILM.S * res, FILM.S * res);
    g.translate(-x, -y);
    const saved = FILM.frameT;
    FILM.frameT = 0.001;
    draw(g);
    FILM.frameT = saved;
    if (sprites.size > 400) sprites.clear();
    sprites.set(k, c);
  }
  ctx.drawImage(c, x, y, w, h);
}

const mipCache = new WeakMap<HTMLCanvasElement, HTMLCanvasElement[]>();

/**
 * Крупный растр, уменьшенный в несколько раз: берётся ближайшая копия не меньше нужного размера, уменьшенная
 * заранее вдвое, вчетверо и так далее. Сглаживание «high» на каждом кадре стоило десятки миллисекунд.
 */
export function drawMipped(ctx: CanvasRenderingContext2D, src: HTMLCanvasElement, x: number, y: number, w: number, h: number): void {
  let levels = mipCache.get(src);
  if (!levels) {
    levels = [src];
    for (let c = src; c.width > 480;) {
      const next = FILM.makeCanvas(Math.ceil(c.width / 2), Math.ceil(c.height / 2));
      const g = next.getContext('2d')!;
      g.imageSmoothingQuality = 'high';
      g.drawImage(c, 0, 0, next.width, next.height);
      levels.push(next);
      c = next;
    }
    mipCache.set(src, levels);
  }
  const need = Math.abs(w * ctx.getTransform().a);
  let pick = levels[0]!;
  for (const level of levels) if (level.width >= need) pick = level;
  ctx.drawImage(pick, x, y, w, h);
}

/** Форма слова для числа: 1 отрезок, 2 отрезка, 5 отрезков. */
export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(Math.round(n));
  if (a % 10 === 1 && a % 100 !== 11) return forms[0];
  if (a % 10 >= 2 && a % 10 <= 4 && (a % 100 < 12 || a % 100 > 14)) return forms[1];
  return forms[2];
}
