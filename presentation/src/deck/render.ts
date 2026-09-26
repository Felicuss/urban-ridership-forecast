import { FILM, P } from '../film';
import { MONO, clamp, text } from './g';
import { SLIDES, type Mode } from './slides';
import { composite } from './transitions';

// Кадр показа: слайд или переход между двумя слайдами и линейка внизу, как в LCT_2026. Время берётся из кадра
// Remotion, поэтому перемотка и повтор дают ту же картинку.

export const FPS = 60;
/** После анимации слайд держит финальную позу, а вагоны и река живут ещё столько секунд. */
export const HOLD = 600;

export const SEGMENTS = SLIDES.reduce<{ start: number; end: number }[]>((acc, s) => {
  const start = acc.length ? acc[acc.length - 1]!.end + 1 : 0;
  return [...acc, { start, end: start + Math.round((s.dur + HOLD) * FPS) - 1 }];
}, []);
export const TOTAL = SEGMENTS[SEGMENTS.length - 1]!.end + 1;

export function locate(frame: number): { index: number; t: number } {
  const index = Math.max(0, SEGMENTS.findIndex((s) => frame <= s.end));
  return { index, t: (frame - SEGMENTS[index]!.start) / FPS };
}

const BG: Record<Mode, string> = { paper: '#EDE0C4', blue: '#0B1230', dusk: '#2B2745' };

let layerA: HTMLCanvasElement | null = null;
let layerB: HTMLCanvasElement | null = null;

function layers(w: number, h: number): [HTMLCanvasElement, HTMLCanvasElement] {
  if (!layerA || layerA.width !== w || layerA.height !== h) {
    layerA = FILM.makeCanvas(w, h);
    layerB = FILM.makeCanvas(w, h);
  }
  return [layerA, layerB!];
}

function reset(c: CanvasRenderingContext2D): void {
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.globalAlpha = 1;
  c.globalCompositeOperation = 'source-over';
  c.setLineDash([]);
  c.shadowBlur = 0;
  c.imageSmoothingEnabled = true;
  c.imageSmoothingQuality = 'low';
}

export function drawSlide(c: CanvasRenderingContext2D, i: number, t: number): void {
  const s = SLIDES[i]!;
  reset(c);
  c.fillStyle = BG[s.mode];
  c.fillRect(0, 0, c.canvas.width, c.canvas.height);
  c.setTransform(FILM.S, 0, 0, FILM.S, 0, 0);
  c.save();
  try {
    s.draw(c, t);
  } finally {
    c.restore();
  }
  reset(c);
}

export interface Nav {
  from: number | null;
  fromT: number;
  dir: number;
}

export function renderFrame(canvas: HTMLCanvasElement, frame: number, nav: Nav): void {
  const ctx = canvas.getContext('2d', { alpha: false });
  if (!ctx) return;
  FILM.S = canvas.width / 1920;
  FILM.frameT = frame / FPS;
  const { index, t } = locate(frame);
  const slide = SLIDES[index]!;
  const tr = nav.dir < 0 ? { kind: 'push' as const, dur: 0.7 } : slide.tr;
  if (nav.from != null && nav.from !== index && t < tr.dur) {
    const [A, B] = layers(canvas.width, canvas.height);
    drawSlide(A.getContext('2d', { alpha: false })!, nav.from, nav.fromT + t);
    drawSlide(B.getContext('2d', { alpha: false })!, index, t);
    reset(ctx);
    composite(ctx, tr, A, B, clamp(t / tr.dur), nav.dir, SLIDES[nav.from]!.mode !== 'paper');
  } else {
    drawSlide(ctx, index, t);
  }
  hud(ctx, index, t, frame / FPS);
}

/** Линейка внизу: деление на слайд, пурпурный прогресс текущего, номер и подсказка по клавишам. */
function hud(ctx: CanvasRenderingContext2D, index: number, t: number, clock: number): void {
  reset(ctx);
  ctx.setTransform(FILM.S, 0, 0, FILM.S, 0, 0);
  const mode = SLIDES[index]!.mode;
  const col = mode === 'paper' ? P.inkSoft! : P.lavender!;
  const n = SLIDES.length;
  const x0 = 60;
  const x1 = 1860;
  const y = 1054;
  const seg = (x1 - x0) / n;
  ctx.save();
  ctx.strokeStyle = col;
  ctx.globalAlpha = 0.35;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x0, y);
  ctx.lineTo(x1, y);
  for (let k = 0; k <= n; k++) {
    ctx.moveTo(x0 + k * seg, y - 10);
    ctx.lineTo(x0 + k * seg, y);
  }
  ctx.stroke();
  ctx.globalAlpha = 0.95;
  ctx.strokeStyle = mode === 'paper' ? P.annMagenta! : P.magenta!;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(x0 + index * seg, y);
  ctx.lineTo(x0 + (index + clamp(t / SLIDES[index]!.dur)) * seg, y);
  ctx.stroke();
  ctx.restore();
  text(ctx, `${String(index + 1).padStart(2, '0')} / ${String(n).padStart(2, '0')}`, x1, y - 14,
    { size: 19, weight: 500, family: MONO, color: col, alpha: 0.7, align: 'right', tracking: 2 });
  const done = t > SLIDES[index]!.dur && index < n - 1;
  if (done) {
    const blink = 0.45 + 0.35 * Math.sin(clock * 3);
    text(ctx, 'дальше →', x1 - 130, y - 14, { size: 19, weight: 600, family: MONO, color: col, alpha: blink, align: 'right' });
  }
  const hint = 1 - clamp((clock - 6) / 1.5);
  if (hint > 0) {
    text(ctx, '← → листать   F полный экран', 960, y - 14, { size: 19, weight: 400, color: col, alpha: 0.6 * hint, align: 'center', tracking: 1 });
  }
}
