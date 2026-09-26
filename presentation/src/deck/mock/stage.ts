import { E, P, lib, type Pt } from '../../film';
import { clamp, kicker, seg, sprite } from '../g';
import { drawApp, initialState, type UiState } from './app';

// Сценарий макета: курсор летит к кнопке, нажимает, интерфейс меняется; камера наезжает на нужную часть экрана.
// Всё считается из времени слайда, поэтому перемотка и повтор дают тот же кадр.

export interface Act {
  t: number;
  /** Куда навести курсор к моменту t. */
  at?: Pt;
  click?: boolean;
  /** Протянуть курсор от at до drag за dur секунд с нажатой кнопкой. */
  drag?: Pt;
  dur?: number;
  apply?: (s: UiState, q: number) => void;
}

/** Кадр камеры на макете: x, y, ширина в координатах экрана сервиса; высота по 16:9. */
export type View = [number, number, number];
export const FULL: View = [0, 0, 1920];

const MOVE = 1.1;
const PRESS = 0.12;

export function runScript(acts: Act[], t: number): { s: UiState; cursor: Pt; press: number; ripple: { at: Pt; age: number } | null } {
  const s = initialState();
  let cursor: Pt = [980, 560];
  let ready = 0;
  let press = 0;
  let ripple: { at: Pt; age: number } | null = null;
  for (const a of acts) {
    if (a.at) {
      const depart = Math.max(ready, a.t - MOVE);
      if (t < a.t) {
        if (t > depart) {
          const q = E.inOutCubic((t - depart) / (a.t - depart));
          cursor = [lib.lerp(cursor[0], a.at[0], q), lib.lerp(cursor[1], a.at[1], q)];
        }
        return { s, cursor, press, ripple };
      }
      cursor = a.at;
      ready = a.t;
      if (a.click) {
        const age = t - a.t;
        if (age < 0.6) ripple = { at: a.at, age };
        press = age < PRESS ? 1 - age / PRESS : 0;
      }
      if (a.drag) {
        const q = E.inOutCubic(clamp((t - a.t - PRESS) / (a.dur ?? 1)));
        cursor = [lib.lerp(a.at[0], a.drag[0], q), lib.lerp(a.at[1], a.drag[1], q)];
        press = q < 1 ? 1 : 0;
        a.apply?.(s, q);
        ready = a.t + PRESS + (a.dur ?? 1);
        if (t < ready) return { s, cursor, press, ripple };
        continue;
      }
    } else if (t < a.t) {
      return { s, cursor, press, ripple };
    }
    const start = a.t + (a.click ? PRESS : 0);
    if (t >= start) a.apply?.(s, a.dur ? E.inOutCubic(clamp((t - start) / a.dur)) : 1);
    ready = Math.max(ready, start + (a.dur ?? 0) * 0.6);
  }
  return { s, cursor, press, ripple };
}

function lerpView(a: View, b: View, q: number): View {
  const w = Math.exp(lib.lerp(Math.log(a[2]), Math.log(b[2]), q));
  const k = Math.abs(b[2] - a[2]) > 1e-3 ? (1 / w - 1 / a[2]) / (1 / b[2] - 1 / a[2]) : q;
  const ca = [a[0] + a[2] / 2, a[1] + (a[2] * 9) / 32];
  const cb = [b[0] + b[2] / 2, b[1] + (b[2] * 9) / 32];
  return [lib.lerp(ca[0]!, cb[0]!, k) - w / 2, lib.lerp(ca[1]!, cb[1]!, k) - (w * 9) / 32, w];
}

/** Камера по ключам [t, кадр]: перелёт 1,6 с к каждому новому кадру. */
export function viewAt(keys: [number, View][], t: number): View {
  let v = keys[0]![1];
  for (let i = 1; i < keys.length; i++) {
    const [t1, b] = keys[i]!;
    if (t < t1) break;
    v = lerpView(keys[i - 1]![1], b, E.inOutCubic(clamp((t - t1) / 1.6)));
  }
  return v;
}

export interface Frame {
  x: number;
  y: number;
  w: number;
}

/** Курсор-стрелка постоянного размера и кольцо клика. */
function cursorShape(ctx: CanvasRenderingContext2D, x: number, y: number, press: number): void {
  const k = 1.25 * (1 - 0.12 * press);
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(k, k);
  ctx.shadowColor = 'rgba(0,0,0,0.5)';
  ctx.shadowBlur = 6;
  ctx.shadowOffsetY = 2;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(0, 22);
  ctx.lineTo(5.5, 17);
  ctx.lineTo(9.5, 26);
  ctx.lineTo(13, 24.4);
  ctx.lineTo(9, 15.6);
  ctx.lineTo(16, 15.6);
  ctx.closePath();
  ctx.fillStyle = '#fff';
  ctx.fill();
  ctx.shadowColor = 'transparent';
  ctx.strokeStyle = '#111';
  ctx.lineWidth = 1.4;
  ctx.stroke();
  ctx.restore();
}

/**
 * Макет интерфейса в рамке на листе: сценарий, камера, курсор. Сам экран рисуется векторно в масштабе камеры.
 */
export function drawStage(ctx: CanvasRenderingContext2D, t: number, acts: Act[], views: [number, View][], f: Frame,
  o: { caption?: string; blue?: boolean; t0?: number } = {}): UiState {
  const h = (f.w * 9) / 16;
  const appear = seg(t, o.t0 ?? 0.2, 0.8);
  const { s, cursor, press, ripple } = runScript(acts, t);
  if (appear <= 0) return s;
  const v = viewAt(views, t);
  const k = f.w / v[2];
  ctx.save();
  ctx.globalAlpha *= clamp(appear * 1.5);
  ctx.translate(0, (1 - appear) * 40);
  ctx.fillStyle = lib.rgba(o.blue ? '#000' : P.ink!, 0.22);
  ctx.fillRect(f.x + 12, f.y + 14, f.w, h);
  ctx.save();
  ctx.beginPath();
  ctx.rect(f.x, f.y, f.w, h);
  ctx.clip();
  ctx.translate(f.x, f.y);
  ctx.scale(k, k);
  ctx.translate(-v[0], -v[1]);
  drawApp(ctx, s, t);
  if (ripple) {
    const r = 6 + 34 * E.outCubic(ripple.age / 0.6);
    ctx.strokeStyle = `rgba(255,255,255,${0.85 * (1 - ripple.age / 0.6)})`;
    ctx.lineWidth = 2.5 / k;
    ctx.beginPath();
    ctx.arc(ripple.at[0], ripple.at[1], r / Math.sqrt(k), 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
  const cx = f.x + (cursor[0] - v[0]) * k;
  const cy = f.y + (cursor[1] - v[1]) * k;
  if (cx > f.x - 10 && cx < f.x + f.w && cy > f.y - 10 && cy < f.y + h) {
    ctx.save();
    ctx.beginPath();
    ctx.rect(f.x, f.y, f.w, h);
    ctx.clip();
    cursorShape(ctx, cx, cy, press);
    ctx.restore();
  }
  sprite(ctx, `frame|${f.x}|${f.y}|${f.w}|${o.blue ?? false}`, f.x - 10, f.y - 10, f.w + 20, h + 20, (g) => {
    lib.inkPath(g, lib.rectPts(f.x, f.y, f.w, h, 40), { closed: true, width: 3, color: o.blue ? P.lavender : P.ink, seed: 21, wobble: 0.8, boil: false });
  });
  if (o.caption) kicker(ctx, o.caption, f.x, f.y + h + 40, { size: 18, color: o.blue ? P.lavender : P.inkSoft, alpha: 0.75 });
  ctx.restore();
  return s;
}
