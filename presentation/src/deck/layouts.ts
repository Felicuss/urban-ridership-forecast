import { E, P, lib } from '../film';
import { MONO, bullet, chapter, clamp, kicker, lines, para, seg, sprite, text } from './g';
import type { Scene } from './landmarks';
import { drawStage, type Act, type Frame, type View } from './mock/stage';
import { BLUE_STREET, DUSK_STREET, PAPER_STREET, street } from './street';
import type { Mode, Slide } from './slides';
import type { Transition } from './transitions';

// Раскладки слайдов с макетом сервиса. Чтобы пять слайдов подряд не были одинаковыми, у каждого своя сетка,
// фон и место Москвы внизу: экран справа и пункты слева, экран слева, субтитры под экраном на рассвете,
// газетные вырезки ночью, чат на синьке.

export type Layout = 'right' | 'left' | 'subtitles' | 'clippings' | 'chat';
type Bg = 'paper' | 'dawn' | 'night' | 'blue';

export interface Point {
  t: number;
  text: string;
}

export interface ProductOpts {
  id: string;
  label: string;
  num: string;
  title: string;
  dur: number;
  tr: Transition;
  points: Point[];
  acts: Act[];
  views: [number, View][];
  layout: Layout;
  bg: Bg;
  scene: Scene;
  seed: number;
}

const FRAMES: Record<Layout, Frame> = {
  right: { x: 610, y: 190, w: 1250 },
  left: { x: 60, y: 185, w: 1170 },
  subtitles: { x: 385, y: 192, w: 1150 },
  clippings: { x: 660, y: 214, w: 1190 },
  chat: { x: 60, y: 190, w: 1180 },
};
const STREET_K: Record<Layout, number> = { right: 0.62, left: 0.62, subtitles: 0.74, clippings: 0.62, chat: 0.62 };
const MODE: Record<Bg, Mode> = { paper: 'paper', dawn: 'paper', night: 'dusk', blue: 'blue' };
/** Наклон экрана на слайде с вырезками, радианы. */
const TILT = -0.018;

export function productSlide(o: ProductOpts): Slide {
  const frame = FRAMES[o.layout];
  const dark = o.bg === 'night' || o.bg === 'blue';
  return {
    id: o.id, label: o.label, mode: MODE[o.bg], dur: o.dur, tr: o.tr,
    draw(ctx, t) {
      background(ctx, o.bg);
      const pal = o.bg === 'night' ? DUSK_STREET : o.bg === 'blue' ? BLUE_STREET : PAPER_STREET;
      street(ctx, 1004, t, { pal, scene: o.scene, seed: o.seed, k: STREET_K[o.layout], lit: o.bg === 'night', speed: o.seed % 2 ? 95 : -95 });
      chapter(ctx, t, o.num, o.title, { blue: dark });
      if (o.layout === 'clippings') tilted(ctx, frame, () => drawStage(ctx, t, o.acts, o.views, frame, { blue: dark }));
      else drawStage(ctx, t, o.acts, o.views, frame, { blue: dark });
      const active = o.points.reduce((a, p, i) => (t >= p.t ? i : a), -1);
      if (o.layout === 'subtitles') subtitles(ctx, t, o.points, active);
      else if (o.layout === 'clippings') clippings(ctx, t, o.points, active);
      else if (o.layout === 'chat') chat(ctx, t, o.points, active);
      else list(ctx, t, o.points, active, o.layout === 'right' ? 56 : 1290, o.layout === 'right' ? 530 : 580, dark);
    },
  };
}

function background(ctx: CanvasRenderingContext2D, bg: Bg): void {
  if (bg === 'blue') {
    lib.blueprint(ctx, { w: 1920, h: 1080, center: [1240, 560] });
    return;
  }
  if (bg === 'night') {
    sprite(ctx, 'night-sky', 0, 0, 1920, 1080, nightSky);
    return;
  }
  lib.paper(ctx, { w: 1920, h: 1080, vignette: 0.25 });
  if (bg === 'dawn') sprite(ctx, 'dawn-sky', 0, 0, 1920, 1080, dawnSky);
}

/** Раннее утро: розовый свет сверху и низкое солнце справа. */
function dawnSky(g: CanvasRenderingContext2D): void {
  const sky = g.createLinearGradient(0, 0, 0, 760);
  sky.addColorStop(0, 'rgba(255,168,128,0.30)');
  sky.addColorStop(1, 'rgba(255,200,150,0)');
  g.fillStyle = sky;
  g.fillRect(0, 0, 1920, 1080);
  const glow = g.createRadialGradient(1745, 150, 10, 1745, 150, 230);
  glow.addColorStop(0, 'rgba(255,190,110,0.55)');
  glow.addColorStop(1, 'rgba(255,190,110,0)');
  g.fillStyle = glow;
  g.fillRect(1400, 0, 520, 480);
  g.fillStyle = 'rgba(244,150,86,0.75)';
  g.beginPath();
  g.arc(1745, 150, 46, 0, Math.PI * 2);
  g.fill();
}

/** Ночь: тёмное небо, звёзды и луна. */
function nightSky(g: CanvasRenderingContext2D): void {
  const sky = g.createLinearGradient(0, 0, 0, 1080);
  sky.addColorStop(0, '#161428');
  sky.addColorStop(1, '#2E2A4A');
  g.fillStyle = sky;
  g.fillRect(0, 0, 1920, 1080);
  const r = lib.rng('night-stars');
  for (let i = 0; i < 140; i++) {
    g.fillStyle = `rgba(233,225,245,${r.range(0.25, 0.8).toFixed(2)})`;
    g.beginPath();
    g.arc(r.range(0, 1920), r.range(0, 820), r.range(0.6, 1.8), 0, Math.PI * 2);
    g.fill();
  }
  g.fillStyle = 'rgba(255,236,200,0.9)';
  g.beginPath();
  g.arc(1620, 104, 30, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = '#18162B';
  g.beginPath();
  g.arc(1634, 96, 27, 0, Math.PI * 2);
  g.fill();
}

/** Экран, приколотый к листу под небольшим углом, с полосками скотча сверху. */
function tilted(ctx: CanvasRenderingContext2D, f: Frame, draw: () => void): void {
  const h = (f.w * 9) / 16;
  const cx = f.x + f.w / 2;
  const cy = f.y + h / 2;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(TILT);
  ctx.translate(-cx, -cy);
  draw();
  for (const [x, rot] of [[f.x + 70, -0.5], [f.x + f.w - 70, 0.45]] as const) {
    ctx.save();
    ctx.translate(x, f.y - 2);
    ctx.rotate(rot);
    ctx.fillStyle = 'rgba(236,222,184,0.78)';
    ctx.fillRect(-58, -15, 116, 30);
    ctx.restore();
  }
  ctx.restore();
}

/** Классический список пунктов: номер в кружке, активный пункт пурпурный. */
function list(ctx: CanvasRenderingContext2D, t: number, points: Point[], active: number, x: number, w: number, dark: boolean): void {
  let y = 250;
  points.forEach((p, i) => {
    const h = bullet(ctx, t, p.t - 0.3, x, y, p.text, { n: i + 1, active: active === i, maxW: w, blue: dark, size: 27 });
    y += Math.max(h, 36) + 28;
  });
}

/** Субтитры под экраном: один пункт крупно, номер и счётчик пунктов. */
function subtitles(ctx: CanvasRenderingContext2D, t: number, points: Point[], active: number): void {
  if (active < 0) return;
  const p = points[active]!;
  const q = seg(t, points[0]!.t - 0.3, 0.5);
  const x = 250;
  const y = 866;
  const w = 1420;
  const h = 104;
  ctx.save();
  ctx.globalAlpha *= q;
  ctx.fillStyle = 'rgba(0,0,0,0.16)';
  ctx.fillRect(x + 10, y + 10, w, h);
  sprite(ctx, 'subtitle-card', x - 8, y - 8, w + 16, h + 16, (g) => {
    g.fillStyle = lib.rgba(P.paper!, 0.97);
    g.fillRect(x, y, w, h);
    lib.inkPath(g, lib.rectPts(x, y, w, h, 40), { closed: true, width: 2.4, color: P.ink, seed: 71, wobble: 0.6, boil: false });
  });
  ctx.fillStyle = P.annMagenta!;
  ctx.beginPath();
  ctx.arc(x + 56, y + h / 2, 24, 0, Math.PI * 2);
  ctx.fill();
  text(ctx, String(active + 1), x + 56, y + h / 2 + 8, { size: 24, weight: 700, family: MONO, color: '#fff', align: 'center' });
  kicker(ctx, `${active + 1} / ${points.length}`, x + w - 30, y + 34, { size: 17, color: P.inkSoft, align: 'right' });
  const size = 28;
  const n = lines(ctx, p.text, { size, weight: 500, maxW: 1180 }).length;
  const ty = y + h / 2 + 10 - ((n - 1) * 36) / 2;
  para(ctx, p.text, x + 104, ty, { size, weight: 500, maxW: 1180, lh: 36, color: P.ink, p: seg(t, p.t - 0.25, 0.8, 'linear') });
  ctx.restore();
}

/** Пункты как вырезки из газеты: светлые карточки со скотчем, каждая под своим углом. */
function clippings(ctx: CanvasRenderingContext2D, t: number, points: Point[], active: number): void {
  const x = 52;
  const w = 540;
  let y = 206;
  points.forEach((p, i) => {
    const size = 24;
    const ls = lines(ctx, p.text, { size, weight: 500, maxW: w - 60 });
    const h = 36 + ls.length * 32;
    const q = seg(t, p.t - 0.3, 0.6);
    if (q > 0) {
      const e = E.outCubic(q);
      const cx = x + w / 2;
      const cy = y + h / 2;
      ctx.save();
      ctx.globalAlpha *= clamp(q * 1.6);
      ctx.translate(cx, cy + (1 - e) * -18);
      ctx.rotate(i % 2 ? 0.014 : -0.011);
      ctx.scale(lib.lerp(1.06, 1, e), lib.lerp(1.06, 1, e));
      ctx.translate(-cx, -cy);
      ctx.fillStyle = 'rgba(0,0,0,0.3)';
      ctx.fillRect(x + 7, y + 9, w, h);
      ctx.fillStyle = '#F2EAD7';
      ctx.fillRect(x, y, w, h);
      ctx.fillStyle = active === i ? P.annMagenta! : lib.rgba(P.ink!, 0.25);
      ctx.fillRect(x, y, 7, h);
      ctx.fillStyle = 'rgba(236,222,184,0.85)';
      ctx.fillRect(cx - 44, y - 12, 88, 24);
      para(ctx, p.text, x + 30, y + 36, { size, weight: active === i ? 600 : 500, maxW: w - 60, lh: 32, color: P.ink,
        p: seg(t, p.t - 0.2, 0.9, 'linear') });
      ctx.restore();
    }
    y += h + 24;
  });
}

/** Пункты как сообщения помощника: пузыри с хвостиком, свежий подсвечен. */
function chat(ctx: CanvasRenderingContext2D, t: number, points: Point[], active: number): void {
  const x = 1296;
  const w = 570;
  let y = 236;
  const head = seg(t, points[0]!.t - 0.6, 0.5);
  if (head > 0) kicker(ctx, 'ЧАТ С ПОМОЩНИКОМ', x, y - 14, { size: 18, color: P.lavender, alpha: 0.8 * head });
  y += 12;
  points.forEach((p, i) => {
    const size = 24;
    const ls = lines(ctx, p.text, { size, weight: 500, maxW: w - 56 });
    const h = 34 + ls.length * 32;
    const q = seg(t, p.t - 0.3, 0.55);
    if (q > 0) {
      const e = E.outBack(q);
      ctx.save();
      ctx.globalAlpha *= clamp(q * 1.8);
      ctx.translate(x, y + h);
      ctx.scale(lib.lerp(0.85, 1, e), lib.lerp(0.85, 1, e));
      ctx.translate(-x, -(y + h));
      ctx.beginPath();
      ctx.roundRect(x, y, w, h, 20);
      ctx.moveTo(x + 18, y + h - 2);
      ctx.lineTo(x - 12, y + h + 14);
      ctx.lineTo(x + 40, y + h - 2);
      ctx.fillStyle = lib.rgba(P.navyLight!, 0.95);
      ctx.fill();
      ctx.strokeStyle = active === i ? P.magenta! : lib.rgba(P.lavender!, 0.6);
      ctx.lineWidth = active === i ? 2.6 : 1.6;
      ctx.stroke();
      para(ctx, p.text, x + 28, y + 36, { size, weight: 500, maxW: w - 56, lh: 32, color: active === i ? P.lineWhite : P.lavender,
        p: seg(t, p.t - 0.2, 0.9, 'linear') });
      ctx.restore();
    }
    y += h + 30;
  });
}
