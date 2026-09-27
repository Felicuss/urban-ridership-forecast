import factsJson from '../data/facts.json';
import { E, P, lib } from '../film';
import {
  C, MONO, ROUTE_INK, card, chapter, compass, fmt, fmt1, kicker, para, seg, text, width,
} from './g';
import {
  DAY, DUSK, NETWORK, ROUTES, STOPS, cachedMap, camPath, drawMap, fitCam, toScreen, type Cam,
} from './map';
import { agentScreen, mapScreen, newsScreen, routeScreen, shiftScreen } from './product';
import { DUSK_STREET, PAPER_STREET, street } from './street';
import { stopScene } from './stop';
import type { Transition } from './transitions';

// Десять слайдов презентации «Час пик». Слайд рисует кадр только из своего времени t и после dur держит
// финальную позу; вагоны, река и «кипение» линий живут дальше. Числа - из data/facts.json (slide_facts.py).

export type Mode = 'paper' | 'blue' | 'dusk';

export interface Slide {
  id: string;
  label: string;
  mode: Mode;
  dur: number;
  tr: Transition;
  draw(ctx: CanvasRenderingContext2D, t: number): void;
}

interface Facts {
  totalBoardings: number;
  route17: { boardings: number; headway: number; perTrip: number };
  week: { spans: number; routes: number; top: { route: number; start: number; end: number; peak: number; hw: number; need: number }[] };
  overloadedHours: number;
  overloadedPct: number;
  vehicleHours: number;
  extraVehicleHours: number;
  extraPct: number;
  overloadedByRoute: Record<string, number>;
  incident: { minutes: number; lost: number; alpha: number; tryOn: string };
}
const F = factsJson as unknown as Facts;
const CAPACITY = 185;

// ---------------------------------------------------------------------------
// Камеры: конец одного слайда совпадает с началом следующего
// ---------------------------------------------------------------------------

const MAP_RIGHT = { x: 860, y: 60, w: 980, h: 700 };
const CITY: Cam = fitCam(NETWORK, MAP_RIGHT);
const CITY_END: Cam = { ...CITY, z: CITY.z * 1.05 };
const VALUE: Cam = fitCam(NETWORK, { x: 800, y: 150, w: 1060, h: 880 });
const FINAL: Cam = { ...fitCam(NETWORK, { x: 760, y: 60, w: 1100, h: 960 }), z: CITY.z * 0.8 };

function leftShade(ctx: CanvasRenderingContext2D, color: string, to = 900, alpha = 0.94): void {
  const g = ctx.createLinearGradient(0, 0, to, 0);
  g.addColorStop(0, lib.rgba(color, alpha));
  g.addColorStop(0.55, lib.rgba(color, alpha * 0.8));
  g.addColorStop(1, lib.rgba(color, 0));
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, to, 1080);
}

// ---------------------------------------------------------------------------
// 1. Титул
// ---------------------------------------------------------------------------

const title: Slide = {
  id: 'title', label: 'Час пик', mode: 'paper', dur: 11, tr: { kind: 'cut', dur: 0 },
  draw(ctx, t) {
    const cam = camPath([[0, CITY], [11, CITY_END]], t);
    const reveal = seg(t, 0.1, 3.4, 'inOutCubic');
    if (reveal < 1) drawMap(ctx, cam, { t, reveal });
    else cachedMap(ctx, 'title', CITY, cam, { t }, 1.06);
    leftShade(ctx, DAY.paper, 860);
    // под картой улица: лист светлеет к земле, по путям идёт «Витязь-М»
    const fade = ctx.createLinearGradient(0, 690, 0, 820);
    fade.addColorStop(0, lib.rgba(DAY.paper, 0));
    fade.addColorStop(1, lib.rgba(DAY.paper, 1));
    ctx.fillStyle = fade;
    ctx.fillRect(0, 690, 1920, 390);
    street(ctx, 1004, t, { pal: PAPER_STREET, scene: 'classic', seed: 1, k: 0.82, speed: 120, alpha: seg(t, 1.2, 1.5, 'linear') });
    compass(ctx, 1790, 120, 34, P.ink!, t);
    const x = 110;
    kicker(ctx, 'ХАКАТОН МОСКОВСКОГО ТРАНСПОРТА 2026', x, 190, { color: P.inkSoft, p: seg(t, 0.5, 0.8, 'linear') });
    text(ctx, 'Час пик', x - 8, 350, { size: 176, weight: 200, color: P.ink, p: seg(t, 0.7, 1.3, 'linear'), tracking: 2 });
    lib.ticks(ctx, x, 392, { length: 600 * seg(t, 1.1, 1.0), n: 30, len: 9, major: 5, majorLen: 20, color: P.ink, alpha: 0.5, width: 1.5 });
    para(ctx, 'Прогноз посадок в трамваи Москвы на каждый час, маршрут и остановку', x, 466,
      { size: 36, weight: 400, maxW: 740, lh: 48, color: P.ink, p: seg(t, 1.6, 1.5, 'linear') });
    para(ctx, 'Для диспетчера: где и когда вагоны переполнены, сколько их добавить и что будет при сбое.', x, 586,
      { size: 26, weight: 400, maxW: 700, lh: 36, color: P.inkSoft, p: seg(t, 2.6, 1.8, 'linear') });
    const stats: [string, string][] = [['10', 'маршрутов'], [fmt(STOPS.length), 'остановок'], ['0,90741', 'точность прогноза']];
    stats.forEach(([v, l], i) => {
      const q = seg(t, 3.6 + i * 0.3, 0.6);
      text(ctx, v, x + i * 230, 724, { size: 54, weight: 700, family: MONO, color: i === 2 ? P.annMagenta : P.ink, p: q, tracking: -1 });
      text(ctx, l, x + i * 230, 758, { size: 21, weight: 500, color: P.inkSoft, alpha: q });
    });
  },
};

// ---------------------------------------------------------------------------
// 3. Прогноз: данные и точность
// ---------------------------------------------------------------------------

const SOURCES: [string, string][] = [
  ['62,4 млн поездок, январь-октябрь 2025', C.water],
  ['погода по часам, Open-Meteo', C.telecom],
  ['праздники и рабочие субботы', C.sewer],
  ['интервалы по расписанию transport.mos.ru', C.gas],
  ['поездки на трамвае по месяцам, data.mos.ru', C.heat],
  ['сбои из канала Дептранса', C.power],
  ['трассы и остановки, OpenStreetMap', P.lineWhite!],
];
const NODE: [number, number] = [1120, 590];

const model: Slide = {
  id: 'model', label: 'Прогноз', mode: 'blue', dur: 14, tr: { kind: 'lens', dur: 1.4, x: 1380, y: 600 },
  draw(ctx, t) {
    lib.blueprint(ctx, { w: 1920, h: 1080, center: [1120, 590] });
    chapter(ctx, t, '02 · ПРОГНОЗ', 'Модель учится на 62,4 млн поездок и внешних данных', { blue: true });
    SOURCES.forEach(([label, color], i) => {
      const y = 280 + i * 92;
      const t0 = 0.8 + i * 0.28;
      const q = seg(t, t0, 0.5);
      if (q <= 0) return;
      text(ctx, label, 90, y + 8, { size: 27, weight: 400, color: P.lineWhite, p: q });
      // линия данных от подписи к узлу модели, по ней бегут точки
      const x0 = 640;
      const pts: [number, number][] = [];
      for (let k = 0; k <= 30; k++) {
        const u = k / 30;
        const e = E.inOutSine(u);
        pts.push([lib.lerp(x0, NODE[0], u), lib.lerp(y, NODE[1], e)]);
      }
      const drawn = seg(t, t0 + 0.2, 1.0, 'inOutCubic');
      const n = Math.max(2, Math.round(pts.length * drawn));
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = 10;
      lib.inkPath(ctx, pts.slice(0, n), { width: 2.4, color, seed: 40 + i, wobble: 0, taper: [2, 2], boilAmp: 0.2 });
      ctx.restore();
      if (drawn >= 1) {
        for (let k = 0; k < 3; k++) {
          const u = (t * 0.35 + k / 3 + i * 0.13) % 1;
          const j = Math.min(pts.length - 1, Math.floor(u * (pts.length - 1)));
          const [px, py] = pts[j]!;
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(px, py, 3.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    });
    const nq = seg(t, 2.8, 0.8);
    if (nq > 0) {
      lib.glowDot(ctx, NODE[0], NODE[1], 16 * nq, { color: P.glow, rays: 8, intensity: nq, seed: 3 });
      text(ctx, 'прогноз v11', NODE[0], NODE[1] + 64, { size: 22, weight: 600, family: MONO, color: P.lavender, align: 'center', alpha: nq });
      lib.inkLine(ctx, NODE[0] + 30, NODE[1], lib.lerp(NODE[0] + 30, 1250, seg(t, 3.0, 0.6)), NODE[1], { width: 3, color: P.lineWhite, seed: 60, wobble: 0 });
    }
    const cx = 1250;
    const cy = 330;
    card(ctx, cx, cy, 600, 520, { p: seg(t, 3.4, 0.6), blue: true });
    if (t < 3.5) return;
    kicker(ctx, 'ТОЧНОСТЬ НА ПРОВЕРКЕ ОРГАНИЗАТОРОВ', cx + 40, cy + 64, { color: P.lavender, size: 19, p: seg(t, 3.6, 0.6, 'linear') });
    const sc = lib.lerp(0.469, 0.90741, seg(t, 3.8, 1.8, 'outCubic'));
    text(ctx, sc.toFixed(5).replace('.', ','), cx + 36, cy + 190, { size: 108, weight: 700, family: MONO, color: P.lineWhite, tracking: -2, alpha: seg(t, 3.7, 0.4) });
    const bars: [string, number, string][] = [['Час пик', 0.90741, P.magenta!], ['базовое решение организаторов', 0.469, P.lavender!]];
    bars.forEach(([l, v, c], i) => {
      const q = seg(t, 4.4 + i * 0.3, 1.0, 'inOutCubic');
      const by = cy + 250 + i * 76;
      ctx.fillStyle = lib.rgba(c, i ? 0.45 : 0.95);
      ctx.fillRect(cx + 40, by, 520 * v * q, 14);
      text(ctx, `${l}: ${v.toFixed(i ? 3 : 5).replace('.', ',')}`, cx + 40, by + 44, { size: 22, weight: 500, color: P.lineWhite, alpha: q });
    });
    para(ctx, 'Финальная модель v11 на проверке организаторов. Факт попадает в коридор прогноза 8 раз из 10.',
      cx + 40, cy + 430, { size: 23, weight: 400, maxW: 530, lh: 32, color: P.lavender, p: seg(t, 5.4, 1.4, 'linear') });
  },
};

// ---------------------------------------------------------------------------
// 9. Польза
// ---------------------------------------------------------------------------

const maxOver = Math.max(...Object.values(F.overloadedByRoute));
const HOT: Record<number, number> = Object.fromEntries(Object.entries(F.overloadedByRoute).map(([r, v]) => [Number(r), v / maxOver]));
const totalHours = Math.round(F.overloadedHours / (F.overloadedPct / 100));

const value: Slide = {
  id: 'value', label: 'Польза', mode: 'paper', dur: 15, tr: { kind: 'tram', dur: 2.6 },
  draw(ctx, t) {
    const cam = camPath([[0, { ...VALUE, z: VALUE.z * 0.92 }], [12, VALUE]], t);
    const hot = seg(t, 1.0, 1.6, 'inOutSine');
    const hotMap = Object.fromEntries(Object.entries(HOT).map(([r, v]) => [Number(r), v * hot]));
    if (hot < 1) drawMap(ctx, cam, { t, hot: hotMap });
    else cachedMap(ctx, 'value', { ...VALUE, z: VALUE.z * 0.92 }, cam, { t, hot: hotMap }, 1.09);
    leftShade(ctx, DAY.paper, 900, 0.9);
    chapter(ctx, t, '08 · ПОЛЬЗА', 'Вагоны туда и тогда, где их не хватает');
    // подписи самых перегруженных маршрутов у их трасс
    Object.entries(F.overloadedByRoute).slice(0, 5).forEach(([route, hours], i) => {
      const r = ROUTES.find((x) => x.route === Number(route) && x.direction === 0);
      if (!r) return;
      const [x, y] = r.pts[Math.floor(r.pts.length * 0.62)]!;
      const [sx, sy] = toScreen(cam, x, y);
      const q = seg(t, 2.0 + i * 0.3, 0.5);
      if (q <= 0) return;
      const label = `№${route} · ${hours} ч`;
      const w = width(ctx, label, { size: 20, weight: 700, family: MONO });
      ctx.save();
      ctx.globalAlpha *= q;
      ctx.fillStyle = ROUTE_INK[Number(route)]!;
      ctx.fillRect(sx + 12, sy - 34, w + 16, 30);
      ctx.restore();
      text(ctx, label, sx + 20, sy - 12, { size: 20, weight: 700, family: MONO, color: '#fff', alpha: q });
    });
    const items: [string, string, string][] = [
      [`${fmt1(F.overloadedPct)} %`, `часов работы маршрутов в ноябре-декабре идут с переполненными вагонами: ${fmt(F.overloadedHours)} из ${fmt(totalHours)}`, P.annMagenta!],
      [`+${fmt1(F.extraPct)} %`, `вагоно-часов хватит, чтобы в вагон входило не больше ${CAPACITY} человек, если добавлять их точечно по прогнозу`, '#2E7D4F'],
      ['7 дней', 'узкие места видны за неделю: есть время перестроить наряд до часа пик', P.ink!],
    ];
    items.forEach(([big, small, color], i) => {
      const y = 250 + i * 240;
      const q = seg(t, 1.4 + i * 0.9, 0.6);
      card(ctx, 60, y, 700, 206, { p: q, seed: 30 + i });
      if (q <= 0) return;
      text(ctx, big, 96, y + 94, { size: 72, weight: 700, family: MONO, color, tracking: -2, p: q });
      para(ctx, small, 96, y + 142, { size: 23, weight: 400, maxW: 630, lh: 30, color: P.ink, p: seg(t, 1.7 + i * 0.9, 1.2, 'linear') });
    });
    text(ctx, 'Часы с переполненными вагонами по маршрутам, ноябрь-декабрь 2025', 1860, 1010,
      { size: 19, weight: 500, color: P.inkSoft, align: 'right', alpha: seg(t, 3, 0.6) });
  },
};

// ---------------------------------------------------------------------------
// 10. Как устроено и как запустить
// ---------------------------------------------------------------------------

const finale: Slide = {
  id: 'final', label: 'Запуск', mode: 'dusk', dur: 15, tr: { kind: 'fade', dur: 1.6 },
  draw(ctx, t) {
    const cam = camPath([[0, FINAL], [15, { ...FINAL, z: FINAL.z * 1.06 }]], t);
    const glow = seg(t, 1.0, 3.0, 'linear');
    if (glow < 1) drawMap(ctx, cam, { t, pal: DUSK, glow });
    else cachedMap(ctx, 'final', FINAL, cam, { t, pal: DUSK, glow }, 1.07);
    leftShade(ctx, DUSK.paper, 1250, 0.95);
    // вечерняя улица: окна и вагон светятся
    const fade = ctx.createLinearGradient(0, 700, 0, 830);
    fade.addColorStop(0, lib.rgba(DUSK.paper, 0));
    fade.addColorStop(1, lib.rgba(DUSK.paper, 1));
    ctx.fillStyle = fade;
    ctx.fillRect(0, 700, 1920, 380);
    street(ctx, 1004, t, { pal: DUSK_STREET, scene: 'panorama', seed: 4, k: 0.82, lit: true, speed: -110, alpha: seg(t, 0.8, 1.6, 'linear') });
    const x = 110;
    const bone = '#EDE6F6';
    const lav = '#C8C1EF';
    text(ctx, 'Час пик', x - 6, 196, { size: 124, weight: 200, color: bone, p: seg(t, 0.4, 1.2, 'linear') });
    lib.ticks(ctx, x, 230, { length: 460 * seg(t, 0.8, 1.0), n: 23, len: 9, major: 5, majorLen: 20, color: bone, alpha: 0.6, width: 1.5 });
    para(ctx, 'Прогноз на каждый час, маршрут и остановку, инструменты смены и помощник в одном сервисе.', x, 296,
      { size: 30, weight: 400, maxW: 760, lh: 42, color: bone, p: seg(t, 1.2, 1.4, 'linear') });
    kicker(ctx, 'КАК УСТРОЕНО', x, 410, { color: lav, p: seg(t, 2.4, 0.5, 'linear') });
    [
      'Модель на Python считается заранее, сервис сверяет её файлы по sha256',
      'Java 25 и Spring WebFlux: 4 000 запросов в секунду, p95 меньше 1 мс на 2 vCPU',
      'React 19 и MapLibre: карта, смена, сценарии, табло, помощник',
      'Тесты: 73 на Java, 25 на Python, 11 в интерфейсе, 6 у MCP-сервера',
    ].forEach((line, i) => text(ctx, `·  ${line}`, x, 454 + i * 40, { size: 25, weight: 400, color: bone, p: seg(t, 2.6 + i * 0.35, 0.8, 'linear') }));
    const cq = seg(t, 4.4, 0.6);
    if (cq > 0) {
      ctx.save();
      ctx.globalAlpha *= cq;
      ctx.fillStyle = lib.rgba('#1B1830', 0.92);
      ctx.fillRect(x - 4, 608, 560, 58);
      ctx.strokeStyle = lib.rgba(lav, 0.6);
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x - 4, 608, 560, 58);
      ctx.restore();
      text(ctx, 'docker compose up -d --build', x + 20, 646, { size: 28, weight: 600, family: MONO, color: bone, p: cq });
    }
    text(ctx, 'интерфейс http://localhost:8080 · API /swagger-ui.html', x, 700, { size: 20, weight: 500, family: MONO, color: lav, p: seg(t, 5.0, 0.8, 'linear') });
    text(ctx, 'github.com/Mojarung/hakaton_moskovskogo_transporta_2026', x, 736, { size: 21, weight: 600, family: MONO, color: lav, p: seg(t, 5.6, 1.0, 'linear') });
  },
};

export const SLIDES: Slide[] = [title, stopScene, model, mapScreen, routeScreen, shiftScreen, newsScreen, agentScreen, value, finale];
