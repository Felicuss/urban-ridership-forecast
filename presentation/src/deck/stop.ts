import { E, P, lib } from '../film';
import { MONO, card, chapter, clamp, fmt, kicker, mark, para, seg, sprite, text } from './g';
import { drawMap, fitCam, onScreen, routeBox, stopNamed } from './map';
import { M } from './mock/data';
import { drawPerson, randomLook, type Look } from './people';
import type { Slide } from './slides';
import { PAPER_STREET, backdrop } from './street';
import { DOORS, tram } from './tram';

// Слайд «Задача»: утро пятницы на остановке «ВДНХ (северная)» маршрута 17. Люди ждут, приезжает «Витязь-М»,
// двери открываются, пассажиры входят, в окнах становится тесно. Счётчик показывает, сколько людей входит
// в вагон за рейс по прогнозу, и перебирает вместимость 185.

const RAIL = 850;
const S = 30;
const STOP_X = 620;
const CAPACITY = 185;
const STOP_NAME = 'ВДНХ (северная)';

// поток за рейс в сторону Медведково в 8:00: посадки остановок делятся на рейсы этого часа
const stops = M.route17.stops;
const stopIndex = Math.max(0, stops.findIndex((s) => s.name === STOP_NAME));
const perTrip = M.route17.perTrip[8] ?? 312;
const dirTotal = stops.reduce((a, s) => a + s.value, 0);
const BEFORE = Math.round((stops.slice(0, stopIndex).reduce((a, s) => a + s.value, 0) / dirTotal) * perTrip);
const HERE = Math.round(((stops[stopIndex]?.value ?? 0) / dirTotal) * perTrip);

// времена сцены, секунды
const ARRIVE: [number, number] = [2.4, 6.2];
const OPEN: [number, number] = [6.4, 7.0];
const BOARD_FROM = 7.1;
const CLOSE: [number, number] = [13.0, 13.6];
const LEAVE: [number, number] = [13.9, 17.6];

interface Person {
  x: number;
  feet: number;
  look: Look;
  /** Куда смотрит, пока ждёт. */
  face: number;
  door: number;
  start: number;
  walk: number;
  appear: number;
}

const doorX = (i: number) => STOP_X + (DOORS[i]! + 0.65) * S;

const PEOPLE: Person[] = (() => {
  const r = lib.rng('stop-people');
  const raw = Array.from({ length: HERE }, () => {
    const x = r.range(150, 1780);
    let door = 0;
    for (let d = 1; d < DOORS.length; d++) if (Math.abs(doorX(d) - x) < Math.abs(doorX(door) - x)) door = d;
    return { x, feet: r.range(922, 970), look: randomLook(r), face: r() < 0.5 ? -1 : 1, door, start: 0, walk: 0, appear: 0.3 + r.range(0, 2.2) };
  });
  // у каждой двери своя очередь: ближние входят первыми
  for (let d = 0; d < DOORS.length; d++) {
    raw.filter((p) => p.door === d).sort((a, b) => Math.abs(a.x - doorX(d)) - Math.abs(b.x - doorX(d))).forEach((p, k) => {
      p.walk = Math.min(Math.abs(p.x - doorX(d)) / 190, 2.4);
      p.start = BOARD_FROM + k * 0.55 + d * 0.06 + Math.max(0, 0.9 - p.walk) * 0.3;
    });
  }
  return raw.sort((a, b) => a.feet - b.feet);
})();

/** Сколько человек вошло к моменту t: для счётчика и голов в окнах. */
function boarded(t: number): number {
  return PEOPLE.filter((p) => t >= p.start + p.walk + 0.35).length;
}

function shelter(ctx: CanvasRenderingContext2D): void {
  const x = 170;
  const y = 936;
  const ink = { width: 2, color: P.ink, wobble: 0.4, smooth: false, taper: [3, 4] as [number, number] };
  lib.inkPath(ctx, [[x, y - 150], [x + 270, y - 150], [x + 270, y - 136], [x, y - 136]], { ...ink, closed: true, fill: '#C38F2E' });
  for (const px of [x + 8, x + 258]) lib.inkLine(ctx, px, y - 136, px, y, { ...ink, width: 2.4 });
  ctx.fillStyle = lib.rgba('#9CC6CF', 0.35);
  ctx.fillRect(x + 14, y - 132, 240, 96);
  lib.inkPath(ctx, [[x + 14, y - 132], [x + 254, y - 132], [x + 254, y - 36], [x + 14, y - 36]], { ...ink, closed: true, width: 1.4 });
  lib.inkLine(ctx, x + 40, y - 30, x + 230, y - 30, { ...ink, width: 3 });
  // знак остановки с номером маршрута
  lib.inkLine(ctx, x - 40, y, x - 40, y - 190, { ...ink, width: 2.4 });
  lib.inkPath(ctx, [[x - 78, y - 230], [x - 2, y - 230], [x - 2, y - 176], [x - 78, y - 176]], { ...ink, closed: true, fill: P.white });
  text(ctx, 'Т', x - 40, y - 206, { size: 18, weight: 700, color: '#C2413B', align: 'center' });
  text(ctx, '17', x - 40, y - 184, { size: 18, weight: 700, family: MONO, color: P.ink, align: 'center' });
  kicker(ctx, 'ВДНХ (СЕВЕРНАЯ)', x + 135, y - 160, { size: 15, color: P.ink, align: 'center', alpha: 1 });
}

function platform(ctx: CanvasRenderingContext2D): void {
  ctx.fillStyle = '#E4D3B2';
  ctx.fillRect(0, RAIL + 10, 1920, 990 - RAIL - 10);
  // плитка платформы
  ctx.strokeStyle = lib.rgba(P.inkFaint!, 0.28);
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let y = RAIL + 44; y < 990; y += 34) {
    ctx.moveTo(0, y);
    ctx.lineTo(1920, y);
  }
  for (let x = 0; x < 1920; x += 60) {
    ctx.moveTo(x, RAIL + 30);
    ctx.lineTo(x - 18, 990);
  }
  ctx.stroke();
  lib.inkLine(ctx, 0, RAIL + 10, 1920, RAIL + 10, { width: 2.4, color: P.ink, seed: 31, wobble: 0.3, taper: [2, 2] });
  ctx.fillStyle = lib.rgba('#EAB530', 0.8);
  for (let x = 0; x < 1920; x += 26) ctx.fillRect(x, RAIL + 18, 18, 5);
  lib.inkLine(ctx, 0, 990, 1920, 990, { width: 2, color: P.ink, seed: 32, wobble: 0.3, taper: [2, 2] });
}

function counterCard(ctx: CanvasRenderingContext2D, t: number, count: number): void {
  const x = 60;
  const y = 196;
  card(ctx, x, y, 700, 446, { p: seg(t, 0.8, 0.6), seed: 5 });
  if (t < 0.9) return;
  kicker(ctx, 'МАРШРУТ 17 · ПЯТНИЦА 14 НОЯБРЯ · 8:00', x + 36, y + 56, { size: 20, color: P.inkSoft, p: seg(t, 1.0, 0.6, 'linear') });
  text(ctx, `${fmt(M.route17.day[8]!.p50)} посадок за час · интервал ${M.route17.headway8} мин`, x + 36, y + 98,
    { size: 25, weight: 500, color: P.ink, p: seg(t, 1.3, 0.8, 'linear') });
  const a = seg(t, 2.0, 0.6);
  text(ctx, fmt(count), x + 32, y + 212, { size: 104, weight: 700, family: MONO, color: count > CAPACITY ? P.annMagenta : P.ink, alpha: a, tracking: -2 });
  text(ctx, 'вошли в вагон', x + 280, y + 176, { size: 26, weight: 500, color: P.ink, alpha: a });
  text(ctx, 'за рейс, прогноз', x + 280, y + 208, { size: 26, weight: 500, color: P.inkSoft, alpha: a });
  // вместимость против потока
  const bx = x + 36;
  const by = y + 250;
  const bw = 628;
  const scale = bw / perTrip;
  ctx.save();
  ctx.globalAlpha *= a;
  const blue = Math.min(count, CAPACITY) * scale;
  ctx.fillStyle = lib.rgba(P.annBlue!, 0.85);
  ctx.fillRect(bx, by, blue, 28);
  if (count > CAPACITY) {
    ctx.fillStyle = lib.rgba(P.annMagenta!, 0.25);
    ctx.fillRect(bx + CAPACITY * scale, by, (count - CAPACITY) * scale, 28);
    ctx.save();
    ctx.beginPath();
    ctx.rect(bx + CAPACITY * scale, by, (count - CAPACITY) * scale, 28);
    ctx.clip();
    ctx.strokeStyle = P.annMagenta!;
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let hx = bx + CAPACITY * scale - 30; hx < bx + count * scale; hx += 9) {
      ctx.moveTo(hx, by + 28);
      ctx.lineTo(hx + 22, by);
    }
    ctx.stroke();
    ctx.restore();
  }
  lib.inkPath(ctx, lib.rectPts(bx, by, bw, 28, 30), { closed: true, width: 2, seed: 8, wobble: 0.5 });
  lib.inkLine(ctx, bx + CAPACITY * scale, by - 14, bx + CAPACITY * scale, by + 42, { width: 2.4, seed: 9 });
  ctx.restore();
  text(ctx, `вагон «Витязь-М» везёт ${CAPACITY} человек`, bx, by + 70, { size: 22, weight: 500, color: '#2F6FB0', alpha: a });
  if (count > CAPACITY) {
    text(ctx, `ещё ${fmt(count - CAPACITY)} не помещаются`, bx + CAPACITY * scale + 14, by - 14, { size: 22, weight: 600, color: P.annMagenta });
  }
  para(ctx, 'Это поток входящих: выходы в данных не видны. Но в час пик одного интервала 7 минут не хватает, и сервис это видит заранее.',
    x + 36, y + 372, { size: 21, weight: 400, maxW: 630, lh: 29, color: P.inkSoft, p: seg(t, LEAVE[1] - 0.4, 1.6, 'linear') });
}

function inset(ctx: CanvasRenderingContext2D, t: number): void {
  const r = { x: 1300, y: 40, w: 560, h: 380 };
  const q = seg(t, 1.2, 0.8);
  if (q <= 0) return;
  ctx.save();
  ctx.globalAlpha *= q;
  card(ctx, r.x - 12, r.y - 12, r.w + 24, r.h + 60, { seed: 44 });
  const cam = fitCam(routeBox(17), { x: r.x + 30, y: r.y + 30, w: r.w - 60, h: r.h - 60 });
  sprite(ctx, 'inset', r.x, r.y, r.w, r.h, (g) => {
    g.beginPath();
    g.rect(r.x, r.y, r.w, r.h);
    g.clip();
    drawMap(g, cam, { t: 0, focus: 17, focusAmount: 1, labels: false, trams: false });
  });
  const stop = stopNamed(STOP_NAME);
  const p = onScreen(cam, stop.x, stop.y);
  ctx.restore();
  if (p) mark(ctx, t, 1.8, p[0], p[1], 20, 'вы здесь', { dx: -40, dy: -46 });
  kicker(ctx, `МАРШРУТ 17 · ${M.routes.find((x) => x.route === 17)?.title.toUpperCase() ?? ''}`, r.x, r.y + r.h + 34,
    { size: 15, color: P.inkSoft, alpha: q });
}

export const stopScene: Slide = {
  id: 'stop', label: 'Остановка', mode: 'paper', dur: 20, tr: { kind: 'tram', dur: 2.6 },
  draw(ctx, t) {
    lib.paper(ctx, { w: 1920, h: 1080, vignette: 0.2 });
    backdrop(ctx, RAIL, PAPER_STREET, 'vdnh', 1.0, S);
    // вагон: приезжает, стоит с открытыми дверями, уезжает
    let nose = STOP_X;
    if (t < ARRIVE[1]) nose = lib.lerp(2150, STOP_X, E.outCubic(clamp((t - ARRIVE[0]) / (ARRIVE[1] - ARRIVE[0]))));
    if (t > LEAVE[0]) nose = lib.lerp(STOP_X, -1300, E.inCubic(clamp((t - LEAVE[0]) / (LEAVE[1] - LEAVE[0]))));
    const doors = t < CLOSE[0] ? seg(t, OPEN[0], OPEN[1] - OPEN[0], 'inOutCubic') : 1 - seg(t, CLOSE[0], CLOSE[1] - CLOSE[0], 'inOutCubic');
    const inside = boarded(t);
    const after = seg(t, LEAVE[0], LEAVE[1] - LEAVE[0] + 1, 'inOutSine');
    const count = t < ARRIVE[1] - 0.6 ? 0 : BEFORE + inside + (perTrip - BEFORE - HERE) * after;
    const shown = t < ARRIVE[1] - 0.6 ? 0 : count * seg(t, ARRIVE[1] - 0.6, 1.2, 'outCubic');
    tram(ctx, nose, RAIL - 1, S, { pal: PAPER_STREET, dir: 1, route: '17', doors, fill: shown / CAPACITY });
    sprite(ctx, 'ground', 0, 690, 1920, 310, (g) => {
      platform(g);
      shelter(g);
    });
    for (const p of PEOPLE) {
      const appear = seg(t, p.appear, 0.5);
      if (appear <= 0) continue;
      const target = STOP_X + (DOORS[p.door]! + 0.65) * S;
      const walkQ = clamp((t - p.start) / Math.max(p.walk, 0.2));
      const x = t < p.start ? p.x + Math.sin(t * 1.3 + p.x) * 1.5 : lib.lerp(p.x, target, E.inOutSine(walkQ));
      const walking = walkQ > 0 && walkQ < 1;
      const stride = walking ? Math.sin(t * 11 + p.x) : 0;
      const enter = clamp((t - p.start - p.walk) / 0.35);
      const face = t < p.start ? p.face : Math.sign(target - p.x) || p.face;
      drawPerson(ctx, p.look, x, p.feet - (enter * 30 + (p.feet - 930) * enter), face, stride, 1 - enter);
    }
    chapter(ctx, t, '01 · ЗАДАЧА', 'Людей больше, чем мест в вагоне');
    counterCard(ctx, t, Math.round(shown));
    inset(ctx, t);
  },
};
