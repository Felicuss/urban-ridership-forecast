import { E, P, lib } from '../film';
import { clamp } from './g';
import { BLUE_STREET, DUSK_STREET, PAPER_STREET } from './street';
import { tram } from './tram';

// Переходы между слайдами из презентации LCT_2026: прошлый слайд A уходит, новый B приходит, p от 0 до 1.
// Оба уже нарисованы в своих холстах того же размера, что и экран.

export type TransitionKind = 'cut' | 'fade' | 'lens' | 'scan' | 'push' | 'zoom' | 'ink' | 'tram';

export interface Transition {
  kind: TransitionKind;
  dur: number;
  /** Точка линзы или наезда в координатах кадра 1920 × 1080. */
  x?: number;
  y?: number;
  angle?: number;
  ring?: string;
  seed?: number;
  axis?: 'x' | 'y';
}

export function composite(ctx: CanvasRenderingContext2D, tr: Transition, A: HTMLCanvasElement, B: HTMLCanvasElement, p: number,
  dir: number, fromBlue: boolean): void {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1;
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const S = w / 1920;
  const x = (tr.x ?? 960) * S;
  const y = (tr.y ?? 540) * S;
  switch (tr.kind) {
    case 'cut':
      ctx.drawImage(B, 0, 0);
      return;
    case 'fade': {
      ctx.drawImage(A, 0, 0);
      ctx.globalAlpha = E.inOutSine(p);
      ctx.drawImage(B, 0, 0);
      ctx.globalAlpha = 1;
      return;
    }
    case 'lens': {
      // B проявляется в растущем круге, по краю кольцо с делениями, как у линзы
      const e = E.inOutSine(p);
      const R = Math.hypot(Math.max(x, w - x), Math.max(y, h - y)) * 1.02;
      const r = Math.max(0.5, e * R);
      ctx.drawImage(A, 0, 0);
      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.clip();
      const k = 1.08 - 0.08 * e;
      ctx.translate(x, y);
      ctx.scale(k, k);
      ctx.translate(-x, -y);
      ctx.drawImage(B, 0, 0);
      ctx.restore();
      ringEdge(ctx, x, y, r, S, p, tr.ring ?? (fromBlue ? P.lavender! : P.ink!));
      return;
    }
    case 'scan': {
      // диагональная развёртка с двойной кромкой
      const e = E.inOutSine(p);
      const a = tr.angle ?? -0.52;
      const nx = -Math.sin(a);
      const ny = Math.cos(a);
      const L = (Math.abs(nx) * w + Math.abs(ny) * h) / 2 + 80 * S;
      const d = -L + 2 * L * e;
      const ux = Math.cos(a);
      const uy = Math.sin(a);
      const far = Math.hypot(w, h);
      const px0 = w / 2 + nx * d;
      const py0 = h / 2 + ny * d;
      ctx.drawImage(A, 0, 0);
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(px0 - ux * far, py0 - uy * far);
      ctx.lineTo(px0 + ux * far, py0 + uy * far);
      ctx.lineTo(px0 + ux * far - nx * far * 2, py0 + uy * far - ny * far * 2);
      ctx.lineTo(px0 - ux * far - nx * far * 2, py0 - uy * far - ny * far * 2);
      ctx.closePath();
      ctx.clip();
      ctx.drawImage(B, 0, 0);
      ctx.restore();
      ctx.save();
      ctx.strokeStyle = tr.ring ?? P.annYellow!;
      ctx.lineWidth = 3 * S;
      ctx.beginPath();
      ctx.moveTo(px0 - ux * far, py0 - uy * far);
      ctx.lineTo(px0 + ux * far, py0 + uy * far);
      ctx.stroke();
      ctx.globalAlpha = 0.45;
      ctx.lineWidth = 1.5 * S;
      ctx.beginPath();
      ctx.moveTo(px0 - ux * far + nx * 9 * S, py0 - uy * far + ny * 9 * S);
      ctx.lineTo(px0 + ux * far + nx * 9 * S, py0 + uy * far + ny * 9 * S);
      ctx.stroke();
      ctx.restore();
      return;
    }
    case 'push': {
      // лист едет: соседний приходит сбоку, как продолжение одного чертежа
      const e = E.inOutCubic(p);
      const sgn = dir < 0 ? -1 : 1;
      const vertical = tr.axis === 'y';
      const dx = vertical ? 0 : -sgn * w * e;
      const dy = vertical ? -sgn * h * e : 0;
      ctx.drawImage(A, dx, dy);
      ctx.drawImage(B, dx + (vertical ? 0 : sgn * w), dy + (vertical ? sgn * h : 0));
      ctx.save();
      ctx.globalAlpha = Math.sin(Math.PI * p) * 0.5;
      ctx.fillStyle = P.ink!;
      if (vertical) ctx.fillRect(0, dy + sgn * h - 2 * S, w, 4 * S);
      else ctx.fillRect(dx + (sgn > 0 ? w : 0) - 2 * S, 0, 4 * S, h);
      ctx.restore();
      return;
    }
    case 'zoom': {
      // наезд в точку: A растёт и тает, B собирается из той же точки
      const e = E.inOutCubic(p);
      const zA = 1 + 5 * E.inQuart(p);
      const zB = 0.55 + 0.45 * E.outCubic(p);
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(zB, zB);
      ctx.translate(-x, -y);
      ctx.drawImage(B, 0, 0);
      ctx.restore();
      ctx.save();
      ctx.globalAlpha = 1 - clamp((e - 0.25) / 0.6);
      ctx.translate(x, y);
      ctx.scale(zA, zA);
      ctx.translate(-x, -y);
      ctx.drawImage(A, 0, 0);
      ctx.restore();
      return;
    }
    case 'ink': {
      // B проступает кляксами, как тушь по бумаге
      const e = E.inOutCubic(p);
      ctx.drawImage(A, 0, 0);
      ctx.save();
      ctx.beginPath();
      const r = lib.rng(`ink${tr.seed ?? 1}`);
      for (let k = 0; k < 26; k++) {
        const bx = r() * w;
        const by = r() * h;
        const delay = r() * 0.45;
        const q = clamp((e - delay) / (1 - delay));
        const rad = E.outCubic(q) * Math.hypot(w, h) * (0.18 + r() * 0.22);
        if (rad <= 0) continue;
        ctx.moveTo(bx + rad, by);
        for (let j = 1; j <= 28; j++) {
          const aa = (j / 28) * Math.PI * 2;
          const wob = 1 + 0.12 * lib.noise1(j * 0.7 + k * 3.1, 5);
          ctx.lineTo(bx + Math.cos(aa) * rad * wob, by + Math.sin(aa) * rad * wob);
        }
        ctx.closePath();
      }
      ctx.clip();
      ctx.drawImage(B, 0, 0);
      ctx.restore();
      return;
    }
    case 'tram': {
      // «Витязь-М» проезжает через экран справа налево и увозит прошлый слайд: за хвостом вагона уже новый
      const e = E.inOutSine(p);
      const s = 46;
      const len = 34 * s;
      const rail = 1012;
      const nose = 1920 + 80 - (1920 + 160 + len) * e;
      const rear = nose + len;
      ctx.drawImage(A, 0, 0);
      ctx.save();
      ctx.beginPath();
      ctx.rect(Math.max(0, rear * S), 0, w, h);
      ctx.clip();
      ctx.drawImage(B, 0, 0);
      ctx.restore();
      ctx.save();
      ctx.setTransform(S, 0, 0, S, 0, 0);
      const pal = fromBlue ? BLUE_STREET : tr.ring === 'dusk' ? DUSK_STREET : PAPER_STREET;
      // кромка за хвостом: двойная линия тушью от провода до крыши
      ctx.strokeStyle = pal.ink;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(rear + 4, 0);
      ctx.lineTo(rear + 4, rail - 3.4 * s);
      ctx.stroke();
      ctx.globalAlpha = 0.45;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(rear + 14, 0);
      ctx.lineTo(rear + 14, rail - 3.4 * s);
      ctx.stroke();
      ctx.globalAlpha = 1;
      // провод и рельс на время проезда
      ctx.strokeStyle = lib.rgba(pal.ink, 0.8);
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(0, rail - 5.55 * s);
      ctx.lineTo(1920, rail - 5.55 * s);
      ctx.stroke();
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(0, rail + 2);
      ctx.lineTo(1920, rail + 2);
      ctx.stroke();
      tram(ctx, nose, rail, s, { pal, dir: 1, route: '17', lit: pal === DUSK_STREET });
      ctx.restore();
      return;
    }
    default:
      ctx.drawImage(B, 0, 0);
  }
}

function ringEdge(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, S: number, p: number, color: string): void {
  const fade = Math.sin(Math.PI * clamp(p));
  if (fade <= 0.01) return;
  ctx.save();
  ctx.globalAlpha = fade;
  ctx.strokeStyle = color;
  ctx.lineWidth = 3 * S;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = fade * 0.5;
  ctx.lineWidth = 1.5 * S;
  ctx.beginPath();
  ctx.arc(x, y, r + 12 * S, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = fade * 0.8;
  ctx.lineWidth = 2 * S;
  ctx.beginPath();
  for (let k = 0; k < 72; k++) {
    const a = (k / 72) * Math.PI * 2 + p * 1.4;
    const L = (k % 6 === 0 ? 22 : 10) * S;
    ctx.moveTo(x + Math.cos(a) * (r + 12 * S), y + Math.sin(a) * (r + 12 * S));
    ctx.lineTo(x + Math.cos(a) * (r + 12 * S + L), y + Math.sin(a) * (r + 12 * S + L));
  }
  ctx.stroke();
  ctx.restore();
}
