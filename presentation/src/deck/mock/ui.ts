import { MONO, SANS, text, width, type TextOpts } from '../g';

// Элементы интерфейса «Час пик» для макета: тёмная тема сервиса, шрифты Onest и JetBrains Mono. Всё в
// координатах экрана сервиса 1920 × 1080, векторно: при наезде камеры текст остаётся чётким.

export const U = {
  bg: '#101115',
  surface: '#17181c',
  surface2: '#1e1f24',
  surface3: '#2a2b31',
  line: 'rgba(160,190,230,0.13)',
  lineStrong: 'rgba(160,190,230,0.24)',
  text: '#e9eef5',
  text2: '#b7bcc6',
  muted: '#7d8290',
  accent: '#7aa2f7',
  red: '#e5737d',
  warn: '#e0af68',
  ok: '#9ece6a',
  compare: '#f5c07a',
};

export type Ctx = CanvasRenderingContext2D;

export function rr(ctx: Ctx, x: number, y: number, w: number, h: number, r: number, fill?: string, stroke?: string, lw = 1): void {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lw;
    ctx.stroke();
  }
}

export function t(ctx: Ctx, str: string, x: number, y: number, o: TextOpts & { mono?: boolean } = {}): number {
  return text(ctx, str, x, y, { size: 13, weight: 400, color: U.text, ...o, family: o.mono ? MONO : SANS });
}

export function tw(ctx: Ctx, str: string, o: TextOpts & { mono?: boolean } = {}): number {
  return width(ctx, str, { size: 13, weight: 400, ...o, family: o.mono ? MONO : SANS });
}

/** Текст, который не вылезает за maxW: обрезается многоточием, как в интерфейсе. */
export function tc(ctx: Ctx, str: string, x: number, y: number, maxW: number, o: TextOpts & { mono?: boolean } = {}): void {
  let s = str;
  while (s.length > 1 && tw(ctx, s, o) > maxW) s = s.slice(0, -2);
  t(ctx, s === str ? s : `${s.trimEnd()}…`, x, y, o);
}

export function card(ctx: Ctx, x: number, y: number, w: number, h: number, fill = U.surface): void {
  rr(ctx, x, y, w, h, 14, fill, U.line);
}

export function button(ctx: Ctx, x: number, y: number, w: number, h: number, label: string,
  o: { primary?: boolean; active?: boolean; size?: number; align?: 'center' | 'left'; mono?: boolean } = {}): void {
  const fill = o.primary ? U.text : o.active ? U.surface3 : U.surface2;
  rr(ctx, x, y, w, h, 9, fill, o.primary ? undefined : o.active ? U.lineStrong : U.line);
  const size = o.size ?? 13;
  const color = o.primary ? U.bg : o.active ? U.text : U.text2;
  if (o.align === 'left') t(ctx, label, x + 12, y + h / 2 + size * 0.36, { size, weight: o.primary ? 600 : 500, color, mono: o.mono });
  else t(ctx, label, x + w / 2, y + h / 2 + size * 0.36, { size, weight: o.primary ? 600 : 500, color, align: 'center', mono: o.mono });
}

export function kpi(ctx: Ctx, x: number, y: number, w: number, h: number, label: string, value: string, sub: string,
  tone?: string): void {
  const g = ctx.createLinearGradient(0, y, 0, y + h);
  g.addColorStop(0, U.surface2);
  g.addColorStop(1, U.surface);
  rr(ctx, x, y, w, h, 12, undefined, U.line);
  ctx.fillStyle = g;
  ctx.fill();
  ctx.stroke();
  t(ctx, label, x + 12, y + 20, { size: 11, color: U.muted });
  t(ctx, value, x + 12, y + 46, { size: 19, weight: 600, mono: true, color: tone ?? U.text });
  tc(ctx, sub, x + 12, y + 64, w - 20, { size: 11, color: U.text2 });
}

export function sparkline(ctx: Ctx, values: number[], x: number, y: number, w: number, h: number, color: string, hour?: number): void {
  const max = Math.max(...values, 1);
  const px = (i: number) => x + 1 + (i / (values.length - 1)) * (w - 2);
  const py = (v: number) => y + h - 2 - (v / max) * (h - 4);
  const g = ctx.createLinearGradient(0, y, 0, y + h);
  g.addColorStop(0, `${color}59`);
  g.addColorStop(1, `${color}00`);
  ctx.beginPath();
  values.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
  ctx.lineTo(px(values.length - 1), y + h);
  ctx.lineTo(px(0), y + h);
  ctx.closePath();
  ctx.fillStyle = g;
  ctx.fill();
  ctx.beginPath();
  values.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.4;
  ctx.stroke();
  if (hour != null) {
    const hi = Math.min(Math.max(Math.round(hour), 0), values.length - 1);
    ctx.beginPath();
    ctx.arc(px(hi), py(values[hi] ?? 0), 2.6, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.stroke();
  }
}

export interface Band {
  p10: number;
  p50: number;
  p90: number;
}

/** График с коридором, как uPlot в сервисе: коридор, линия прогноза, пунктир базы или сравнения, курсор. */
export function bandChart(ctx: Ctx, x: number, y: number, w: number, h: number, pts: Band[], color: string,
  o: { cursor?: number; labels?: string[]; compare?: number[]; compareAlpha?: number; base?: number[]; ticks?: number[] } = {}): void {
  const max = Math.max(...pts.map((p) => p.p90), ...(o.compare ?? []), ...(o.base ?? []), 1);
  const nice = Math.pow(10, Math.floor(Math.log10(max)));
  const top = Math.ceil(max / nice) * nice;
  const px = (i: number) => x + 44 + (i / (pts.length - 1)) * (w - 50);
  const py = (v: number) => y + h - 22 - (v / top) * (h - 30);
  ctx.save();
  ctx.strokeStyle = 'rgba(160,190,230,0.07)';
  ctx.lineWidth = 1;
  for (let k = 0; k <= 3; k++) {
    const v = (top / 3) * k;
    ctx.beginPath();
    ctx.moveTo(x + 44, py(v));
    ctx.lineTo(x + w - 6, py(v));
    ctx.stroke();
    const label = v >= 1e6 ? `${Math.round(v / 1e6)} млн` : v >= 1000 ? `${Math.round(v / 1000)} тыс` : String(Math.round(v));
    t(ctx, label, x + 38, py(v) + 4, { size: 10, mono: true, color: U.muted, align: 'right' });
  }
  (o.labels ?? []).forEach((l, i) => {
    if (!l) return;
    t(ctx, l, px(i), y + h - 4, { size: 10, mono: true, color: U.muted, align: 'center' });
  });
  ctx.beginPath();
  pts.forEach((p, i) => (i ? ctx.lineTo(px(i), py(p.p90)) : ctx.moveTo(px(i), py(p.p90))));
  for (let i = pts.length - 1; i >= 0; i--) ctx.lineTo(px(i), py(pts[i]!.p10));
  ctx.closePath();
  ctx.fillStyle = `${color}2e`;
  ctx.fill();
  const line = (vals: number[], stroke: string, lw: number, dash: number[] = [], alpha = 1) => {
    ctx.save();
    ctx.globalAlpha *= alpha;
    ctx.beginPath();
    vals.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lw;
    ctx.setLineDash(dash);
    ctx.stroke();
    ctx.restore();
  };
  if (o.base) line(o.base, 'rgba(233,238,245,0.6)', 1.6, [5, 4]);
  if (o.compare) line(o.compare, U.compare, 1.8, [2, 3], o.compareAlpha ?? 1);
  line(pts.map((p) => p.p50), color, 2.2);
  if (o.cursor != null) {
    const cx = px(o.cursor);
    ctx.strokeStyle = 'rgba(255,255,255,0.75)';
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(cx, y + 6);
    ctx.lineTo(cx, y + h - 22);
    ctx.stroke();
  }
  ctx.restore();
}

/** Столбики по часам с цветом по порогу, как «Посадок на рейс». */
export function hourBars(ctx: Ctx, x: number, y: number, w: number, h: number, values: number[], limit: number, hour: number): void {
  const max = Math.max(...values, limit, 1);
  const bw = w / values.length;
  values.forEach((v, i) => {
    const bh = Math.max((v / max) * h, v > 0 ? 3 : 0);
    const color = v > limit ? U.red : v > 0.8 * limit ? U.warn : U.accent;
    rr(ctx, x + i * bw + 1, y + h - bh, bw - 2, bh, 2, color);
    if (i === hour) rr(ctx, x + i * bw + 1, y + h - bh, bw - 2, bh, 2, undefined, '#fff', 1.2);
  });
  [0, 6, 12, 18, 23].forEach((hh) => t(ctx, String(hh), x + hh * bw + bw / 2, y + h + 14, { size: 10, mono: true, color: U.muted, align: 'center' }));
}

export function slider(ctx: Ctx, x: number, y: number, w: number, q: number): void {
  rr(ctx, x, y - 2, w, 4, 2, U.surface3);
  rr(ctx, x, y - 2, w * q, 4, 2, U.text2);
  ctx.beginPath();
  ctx.arc(x + w * q, y, 7, 0, Math.PI * 2);
  ctx.fillStyle = U.bg;
  ctx.fill();
  ctx.strokeStyle = U.text;
  ctx.lineWidth = 2;
  ctx.stroke();
}

export function badge(ctx: Ctx, x: number, y: number, label: string, color: string, o: { w?: number; h?: number; size?: number } = {}): void {
  const w = o.w ?? 34;
  const h = o.h ?? 26;
  rr(ctx, x, y, w, h, 8, `${color}2e`);
  t(ctx, label, x + w / 2, y + h / 2 + 4.5, { size: o.size ?? 13, weight: 700, mono: true, color, align: 'center' });
}

export const fmt = (v: number) => String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
export const fmtK = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1).replace('.', ',')} млн`
  : v >= 10000 ? `${(v / 1000).toFixed(1).replace('.', ',')} тыс.` : fmt(v));
