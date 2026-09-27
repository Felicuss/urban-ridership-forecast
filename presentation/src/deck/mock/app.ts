import { E } from '../../film';
import { NETWORK, STOPS, UI_ROUTE, camLerp, drawUiMap, fitRect, routeBox, uiPoint, type Cam, type Rect } from '../map';
import { plural } from '../g';
import { M, ROUTE_HOURS } from './data';
import {
  U, badge, bandChart, button, card, fmt, fmtK, hourBars, kpi, rr, slider, sparkline, t, tc, tw, type Band, type Ctx,
} from './ui';

// Макет экрана «Час пик» 1920 × 1080: те же блоки, что в сервисе, и состояние, которое меняет сценарий слайда
// (клик по маршруту, вкладка, ползунок, помощник). Рисуется векторно из состояния, без снимков.

export type Tab = 'forecast' | 'shift' | 'scenario' | 'factors' | 'model';

export interface UiState {
  dateLabel: string;
  minute: number;
  route: number | null;
  /** Выбор маршрута на карте: 0 - вся сеть, 1 - камера на маршруте. */
  routeQ: number;
  stopsQ: number;
  tab: Tab;
  horizon: 'day' | 'year';
  compare: number;
  limit: number;
  scroll: number;
  exportQ: number;
  bell: number;
  copied: boolean;
  alertQ: number;
  fleetHw: number | null;
  boardQ: number;
  scenario: number;
  newsHover: number | null;
  triedQ: number;
  agentQ: number;
  question: number;
  steps: number;
  answer: number;
  hover: { x: number; y: number; title: string; sub: string; q: number } | null;
  /** Кнопка, которую сейчас подсвечивает курсор, по имени. */
  hot: string | null;
}

export function initialState(): UiState {
  return {
    dateLabel: M.dateLabel, minute: 8 * 60 + 10, route: null, routeQ: 0, stopsQ: 0, tab: 'forecast', horizon: 'day', compare: 0,
    limit: 185, scroll: 0, exportQ: 0, bell: 0, copied: false, alertQ: 0, fleetHw: null, boardQ: 0, scenario: 0,
    newsHover: null, triedQ: 0, agentQ: 0, question: 0, steps: 0, answer: 0, hover: null, hot: null,
  };
}

// ---------------------------------------------------------------------------
// Геометрия экрана: по ней сценарии наводят курсор
// ---------------------------------------------------------------------------

export const L = {
  routeRow: (i: number) => ({ x: 20, y: 192 + i * 52.6, w: 270, h: 50 }),
  networkRow: { x: 20, y: 140, w: 270, h: 46 },
  stopsButton: { x: 30, y: 971, w: 250, h: 32 },
  tabs: (i: number) => ({ x: 1516 + i * 78, y: 72, w: 76, h: 30 }),
  horizon: (i: number) => ({ x: 1528 + i * 70, y: 170, w: 64, h: 26 }),
  compareWeek: { x: 1633, y: 628, w: 112, h: 30 },
  limitSlider: { x: 1534, y: 876, w: 352 },
  exportButton: { x: 1770, y: 12, w: 96, h: 32 },
  board: { x: 1730, y: 12, w: 30, h: 32 },
  bell: { x: 1692, y: 12, w: 30, h: 32 },
  pill: { x: 1496, y: 12, w: 186, h: 32 },
  timeline: { x: 323, y: 1001, w: 396 },
};

export const MAP_TOP = 66;
export const MAP_BOTTOM = 895;

export function mapRect(s: UiState): Rect {
  const x = 310 + 300 * E.inOutCubic(s.stopsQ);
  return { x, y: MAP_TOP, w: 1500 - x, h: MAP_BOTTOM - MAP_TOP };
}

export function mapCam(s: UiState): Cam {
  const rect = mapRect(s);
  const net = fitRect(NETWORK, rect, 0.9);
  const r17 = fitRect(routeBox(17), rect, 0.82);
  return camLerp(net, r17, E.inOutCubic(s.routeQ));
}

/** Точка остановки на экране: для курсора и подсказок. */
export function stopPoint(s: UiState, name: string, route = 17): [number, number] {
  const stop = STOPS.filter((x) => x.name === name && x.routes.includes(route))
    .sort((a, b) => (b.hours[8] ?? 0) - (a.hours[8] ?? 0))[0] ?? STOPS[0]!;
  return uiPoint(mapRect(s), mapCam(s), stop.x, stop.y);
}

// ---------------------------------------------------------------------------
// Экран целиком
// ---------------------------------------------------------------------------

export function drawApp(ctx: Ctx, s: UiState, time: number): void {
  if (s.boardQ >= 1) {
    board(ctx, s, time);
    return;
  }
  ctx.fillStyle = U.bg;
  ctx.fillRect(0, 0, 1920, 1080);
  const glow = ctx.createRadialGradient(960, -40, 0, 960, -40, 900);
  glow.addColorStop(0, 'rgba(122,162,247,0.08)');
  glow.addColorStop(1, 'rgba(122,162,247,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, 1920, 400);
  topBar(ctx, s);
  left(ctx, s);
  if (s.stopsQ > 0) stopsPanel(ctx, s);
  map(ctx, s, time);
  timeline(ctx, s);
  right(ctx, s);
  if (s.hover && s.hover.q > 0) tooltip(ctx, s.hover);
  if (s.agentQ > 0) agent(ctx, s);
  if (s.exportQ > 0) exportSheet(ctx, s);
  if (s.boardQ > 0) board(ctx, s, time);
}

function clock(minute: number): string {
  const m = Math.floor(minute) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function topBar(ctx: Ctx, s: UiState): void {
  rr(ctx, 16, 14, 28, 28, 8, '#18181b');
  rr(ctx, 23, 22, 14, 14, 3, '#f4f4f5');
  rr(ctx, 21, 34, 18, 4, 1, U.accent);
  t(ctx, 'Час пик', 54, 26, { size: 16, weight: 700 });
  t(ctx, 'посадки в трамваи Москвы по часам', 54, 42, { size: 11, color: U.muted });
  t(ctx, '‹', 276, 33, { size: 20, color: U.text2, align: 'center' });
  rr(ctx, 296, 12, 212, 32, 10, U.surface, U.line);
  t(ctx, s.dateLabel, 332, 33, { size: 13.5, weight: 500 });
  rr(ctx, 312, 21, 12, 13, 2, undefined, U.text2, 1.4);
  t(ctx, '›', 526, 33, { size: 20, color: U.text2, align: 'center' });
  rr(ctx, 546, 17, 60, 22, 11, undefined, 'rgba(122,162,247,0.45)');
  t(ctx, 'прогноз', 576, 32, { size: 11, weight: 500, color: U.accent, align: 'center' });
  t(ctx, clock(s.minute), 622, 37, { size: 24, weight: 600, mono: true });
  ctx.beginPath();
  ctx.arc(714, 28, 15, 0, Math.PI * 2);
  ctx.fillStyle = '#f4f4f5';
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(709, 21);
  ctx.lineTo(721, 28);
  ctx.lineTo(709, 35);
  ctx.fillStyle = U.bg;
  ctx.fill();
  rr(ctx, 740, 12, 64, 32, 9, U.surface, U.line);
  t(ctx, '×60 ▾', 772, 33, { size: 12, mono: true, align: 'center' });
  rr(ctx, 814, 12, 76, 32, 16, undefined, U.line);
  t(ctx, '● Сейчас', 852, 33, { size: 12.5, color: U.text2, align: 'center' });
  t(ctx, '☁ +5°  облачно', 916, 33, { size: 13, color: U.text2 });
  // справа: помощник, сценарий, колокольчик, табло, выгрузка, настройки
  const pillX = s.scenario > 0 ? 1366 : 1496;
  rr(ctx, pillX, 12, 186, 32, 16, '#000', U.lineStrong);
  const orb = ctx.createRadialGradient(pillX + 17, 25, 0, pillX + 20, 28, 8);
  orb.addColorStop(0, '#c9d6ff');
  orb.addColorStop(0.6, '#7aa2f7');
  orb.addColorStop(1, '#3b4a7a');
  ctx.fillStyle = orb;
  ctx.beginPath();
  ctx.arc(pillX + 20, 28, 7, 0, Math.PI * 2);
  ctx.fill();
  t(ctx, 'Спросить «Час пик»', pillX + 34, 33, { size: 12.5, color: U.text2 });
  rr(ctx, pillX + 160, 20, 16, 16, 4, undefined, U.lineStrong);
  t(ctx, '/', pillX + 168, 32, { size: 10, mono: true, color: U.muted, align: 'center' });
  if (s.scenario > 0) {
    rr(ctx, 1562, 12, 120, 32, 10, 'rgba(224,175,104,0.12)', 'rgba(224,175,104,0.45)');
    t(ctx, `Сценарий: ${s.scenario}  ↺`, 1622, 33, { size: 12.5, weight: 600, color: U.warn, align: 'center' });
  }
  if (s.bell > 0) rr(ctx, 1692, 12, 30, 30, 9, 'rgba(239,65,54,0.16)');
  bellIcon(ctx, 1707, 27, s.bell > 0 ? '#ffb3ad' : U.text2);
  if (s.bell > 0) {
    ctx.beginPath();
    ctx.arc(1718, 14, 8, 0, Math.PI * 2);
    ctx.fillStyle = U.red;
    ctx.fill();
    t(ctx, String(s.bell), 1718, 18, { size: 10, weight: 700, color: '#fff', align: 'center' });
  }
  rr(ctx, 1736, 20, 18, 13, 2, undefined, U.text2, 1.4);
  ctx.fillStyle = U.text2;
  ctx.fillRect(1742, 34, 6, 3);
  rr(ctx, 1770, 12, 96, 32, 10, undefined, U.line);
  t(ctx, '⤓ Выгрузка', 1818, 33, { size: 12.5, color: U.text2, align: 'center' });
  t(ctx, '⚙', 1891, 34, { size: 17, color: U.text2, align: 'center' });
}

function bellIcon(ctx: Ctx, x: number, y: number, color: string): void {
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x - 6, y + 4);
  ctx.lineTo(x - 6, y - 1);
  ctx.arc(x, y - 1, 6, Math.PI, 0);
  ctx.lineTo(x + 6, y + 4);
  ctx.lineTo(x + 8, y + 6);
  ctx.lineTo(x - 8, y + 6);
  ctx.closePath();
  ctx.stroke();
}

// ---------------------------------------------------------------------------
// Слева: маршруты
// ---------------------------------------------------------------------------

function left(ctx: Ctx, s: UiState): void {
  card(ctx, 10, 66, 290, 1004);
  rr(ctx, 22, 78, 266, 30, 8, U.bg, U.line);
  t(ctx, 'Остановка или номер маршрута', 34, 98, { size: 12.5, color: U.muted });
  t(ctx, 'Маршруты', 26, 128, { size: 13, weight: 600 });
  const hour = s.minute / 60;
  const netHours = Array.from({ length: 24 }, (_, h) => M.routes.reduce((a, r) => a + (r.hours[h] ?? 0), 0));
  const nr = L.networkRow;
  rr(ctx, nr.x, nr.y, nr.w, nr.h, 11, s.route == null ? U.surface3 : undefined);
  if (s.route == null) rr(ctx, nr.x, nr.y, 3, nr.h, 1.5, U.text);
  rr(ctx, 26, 150, 32, 26, 8, 'rgba(233,238,245,0.08)');
  t(ctx, 'все', 42, 167, { size: 11, weight: 600, color: U.text2, align: 'center' });
  t(ctx, 'Вся сеть', 68, 158, { size: 13, weight: 600 });
  tc(ctx, `${fmt(M.brief.total)} посадок за сутки, прогноз`, 68, 175, 130, { size: 10.5, color: U.muted });
  sparkline(ctx, netHours, 206, 148, 78, 28, '#e9eef5', hour);
  const max = Math.max(...M.routes.map((r) => r.total));
  M.routes.forEach((r, i) => {
    const row = L.routeRow(i);
    const color = UI_ROUTE[r.route]!;
    const on = s.route === r.route;
    if (on || s.hot === `route${r.route}`) {
      rr(ctx, row.x, row.y, row.w, row.h, 11, on ? U.surface3 : U.surface2);
      if (on) rr(ctx, row.x, row.y, 3, row.h, 1.5, color);
    }
    badge(ctx, 26, row.y + 12, String(r.route), color, { w: 32 });
    t(ctx, r.total > 0 ? fmtK(r.total) : 'нет рейсов', 68, row.y + 20, { size: 13, weight: 600, mono: true });
    tc(ctx, r.title, 68, row.y + 36, 128, { size: 10.5, color: U.muted });
    rr(ctx, 68, row.y + 42, 128, 2, 1, 'rgba(160,190,230,0.08)');
    rr(ctx, 68, row.y + 42, (128 * r.total) / max, 2, 1, color);
    sparkline(ctx, r.hours, 206, row.y + 10, 78, 28, color, hour);
  });
  if (s.route != null) routeCard(ctx, s);
}

function routeCard(ctx: Ctx, s: UiState): void {
  const color = UI_ROUTE[17]!;
  const y = 828;
  rr(ctx, 20, y, 270, 232, 12, `${color}14`, `${color}4d`);
  const hw = M.route17.headway8;
  const stats: [string, string][] = [['Интервал сейчас', `${hw} мин`], ['Рейсов в час', String(Math.round(60 / hw))],
    ['Посадок на рейс', fmt(M.route17.perTrip[8] ?? 0)]];
  stats.forEach(([l, v], i) => {
    t(ctx, l, 30 + i * 88, y + 22, { size: 10, color: U.muted });
    t(ctx, v, 30 + i * 88, y + 48, { size: 16, weight: 600, mono: true });
  });
  button(ctx, 30, y + 64, 122, 58, '', {});
  button(ctx, 158, y + 64, 122, 58, '', {});
  t(ctx, 'Пустить трамвай', 91, y + 90, { size: 12, align: 'center' });
  tc(ctx, `до «${M.route17.ends[0]}»`, 42, y + 108, 104, { size: 10.5, color: U.muted });
  t(ctx, 'Пустить трамвай', 219, y + 90, { size: 12, align: 'center' });
  tc(ctx, `до «${M.route17.ends[1]}»`, 170, y + 108, 104, { size: 10.5, color: U.muted });
  const b = L.stopsButton;
  rr(ctx, b.x, b.y, b.w, b.h, 9, s.stopsQ > 0.5 ? `${color}1f` : U.surface2, s.stopsQ > 0.5 || s.hot === 'stops' ? color : U.lineStrong);
  t(ctx, 'Остановки и участок', b.x + 12, b.y + 21, { size: 12.5 });
  t(ctx, `${M.route17.stops.length}  ›`, b.x + b.w - 12, b.y + 21, { size: 11, mono: true, color: U.muted, align: 'right' });
  t(ctx, 'Расписание на transport.mos.ru ↗', 30, y + 212, { size: 12, color: U.accent });
}

function stopsPanel(ctx: Ctx, s: UiState): void {
  const q = E.outCubic(s.stopsQ);
  ctx.save();
  ctx.globalAlpha *= q;
  ctx.translate(-16 * (1 - q), 0);
  const x = 310;
  const color = UI_ROUTE[17]!;
  rr(ctx, x, 66, 290, 1004, 14, U.surface, `${color}47`);
  badge(ctx, x + 12, 78, '17', color, { w: 30, h: 24 });
  t(ctx, 'Остановки', x + 52, 95, { size: 13, weight: 600 });
  t(ctx, String(M.route17.stops.length), x + 128, 95, { size: 11, mono: true, color: U.muted });
  rr(ctx, x + 10, 110, 131, 26, 8, U.surface3, U.lineStrong);
  tc(ctx, `до «${M.route17.ends[0]}»`, x + 20, 128, 115, { size: 11.5 });
  rr(ctx, x + 147, 110, 131, 26, 8, undefined, U.line);
  tc(ctx, `до «${M.route17.ends[1]}»`, x + 157, 128, 115, { size: 11.5, color: U.muted });
  t(ctx, 'Посадки в 8:00-9:00', x + 14, 158, { size: 11, color: U.muted });
  const stops = M.route17.stops;
  const max = Math.max(...stops.map((st) => st.value), 1);
  stops.forEach((st, i) => {
    const y = 180 + i * 24.8;
    t(ctx, String(st.seq), x + 30, y, { size: 10, mono: true, color: U.muted, align: 'right' });
    tc(ctx, st.name, x + 40, y, 140, { size: 12, color: U.text2 });
    rr(ctx, x + 190, y - 6, 40, 4, 2, U.surface3);
    rr(ctx, x + 190, y - 6, (40 * st.value) / max, 4, 2, color);
    t(ctx, fmt(st.value), x + 276, y, { size: 11, mono: true, align: 'right' });
  });
  t(ctx, 'Участок маршрута', x + 14, 945, { size: 12, color: U.text2 });
  rr(ctx, x + 40, 958, 236, 28, 8, U.bg, U.lineStrong);
  t(ctx, `1. ${stops[0]!.name}`, x + 50, 977, { size: 12 });
  rr(ctx, x + 40, 994, 236, 28, 8, U.bg, U.lineStrong);
  t(ctx, `${stops.length}. ${stops[stops.length - 1]!.name}`, x + 50, 1013, { size: 12 });
  rr(ctx, x + 14, 1030, 262, 30, 8, `${color}24`, `${color}73`);
  t(ctx, 'Прогноз участка', x + 145, 1050, { size: 12.5, align: 'center' });
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Карта и нижняя шкала
// ---------------------------------------------------------------------------

function map(ctx: Ctx, s: UiState, time: number): void {
  const rect = mapRect(s);
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(rect.x, rect.y, rect.w, rect.h, 14);
  ctx.clip();
  drawUiMap(ctx, rect, mapCam(s), { t: time, hour: s.minute / 60, focus: s.route, focusAmount: E.inOutCubic(s.routeQ), routeHours: ROUTE_HOURS });
  // слои карты сверху
  const chips = ['Теплокарта', 'Линии', 'Остановки', 'Трамваи', 'Метро', '3D-дома', 'Погода', 'Спутник', 'Маршруты 10/10'];
  const on = [true, true, true, true, false, true, true, false, false];
  rr(ctx, rect.x + 12, rect.y + 12, 782, 32, 10, 'rgba(12,13,16,0.86)');
  let cx = rect.x + 18;
  chips.forEach((c, i) => {
    const w = tw(ctx, c, { size: 12 }) + 26;
    if (on[i]) rr(ctx, cx, rect.y + 16, w, 24, 7, U.surface3);
    t(ctx, `• ${c}`, cx + 8, rect.y + 32, { size: 12, color: on[i] ? U.text : U.muted });
    cx += w + 4;
  });
  // легенда
  const lx = rect.x + 12;
  const ly = rect.y + rect.h - 130;
  rr(ctx, lx, ly, 250, 110, 12, 'rgba(12,13,16,0.9)', U.line);
  const hour = Math.floor(s.minute / 60);
  t(ctx, `Посадки в ${hour}:00-${hour + 1}:00, прогноз`, lx + 12, ly + 22, { size: 11.5 });
  const g = ctx.createLinearGradient(lx + 12, 0, lx + 238, 0);
  ['#4a5e8c', '#6f8fc9', '#8fb8a8', '#d9b36c', '#e0876a', '#d8666f'].forEach((c, i) => g.addColorStop(i / 5, c));
  ctx.fillStyle = g;
  ctx.fillRect(lx + 12, ly + 32, 226, 5);
  t(ctx, 'мало', lx + 12, ly + 50, { size: 9.5, color: U.muted });
  t(ctx, 'много', lx + 238, ly + 50, { size: 9.5, color: U.muted, align: 'right' });
  t(ctx, 'Толщина линии - посадки маршрута в этот', lx + 12, ly + 72, { size: 10.5, color: U.muted });
  t(ctx, 'час. Вагоны идут с интервалом по расписанию.', lx + 12, ly + 88, { size: 10.5, color: U.muted });
  // вид карты
  const vx = rect.x + rect.w - 244;
  const vy = rect.y + rect.h - 48;
  rr(ctx, vx, vy, 232, 32, 10, 'rgba(12,13,16,0.9)');
  rr(ctx, vx + 66, vy + 4, 92, 24, 7, U.surface3);
  t(ctx, 'Сверху', vx + 34, vy + 21, { size: 11.5, color: U.muted, align: 'center' });
  t(ctx, 'Перспектива', vx + 112, vy + 21, { size: 11.5, align: 'center' });
  t(ctx, 'На север', vx + 196, vy + 21, { size: 11.5, color: U.muted, align: 'center' });
  ctx.restore();
}

function tooltip(ctx: Ctx, h: NonNullable<UiState['hover']>): void {
  ctx.save();
  ctx.globalAlpha *= h.q;
  const w = Math.max(tw(ctx, h.title, { size: 13, weight: 600 }), tw(ctx, h.sub, { size: 12 })) + 28;
  const x = h.x + 18;
  const y = h.y - 70;
  rr(ctx, x, y, w, 56, 10, 'rgba(16,17,21,0.96)', U.lineStrong);
  t(ctx, h.title, x + 14, y + 23, { size: 13, weight: 600 });
  t(ctx, h.sub, x + 14, y + 42, { size: 12, color: U.text2 });
  ctx.restore();
}

const MONTHS_SHORT = ['ноя', 'дек', 'янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт'];

function timeline(ctx: Ctx, s: UiState): void {
  const x = mapRect(s).x;
  const w = 1500 - x;
  card(ctx, x, 905, w, 165);
  const isRoute = s.route != null && s.routeQ > 0.5;
  const values = isRoute ? M.route17.day.map((p) => p.p50) : M.network.day.map((p) => p.p50);
  const color = isRoute ? UI_ROUTE[17]! : '#e9eef5';
  t(ctx, 'Сутки по часам:', x + 12, 928, { size: 12, color: U.text2 });
  t(ctx, isRoute ? 'Маршрут 17' : 'Вся сеть', x + 110, 928, { size: 12, weight: 600 });
  t(ctx, `${fmt(values.reduce((a, b) => a + b, 0))} за сутки`, x + 408, 928, { size: 12, mono: true, color: U.text2, align: 'right' });
  const cw = Math.min(396, w * 0.36);
  sparkline(ctx, values, x + 12, 940, cw, 62, color);
  // ползунок времени суток
  const hq = (s.minute % 1440) / 1440;
  ctx.beginPath();
  ctx.arc(x + 12 + cw * hq, 1001, 7, 0, Math.PI * 2);
  ctx.fillStyle = U.bg;
  ctx.fill();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2.2;
  ctx.stroke();
  [0, 3, 6, 9, 12, 15, 18, 21, 24].forEach((h) => t(ctx, String(h), x + 12 + (cw * h) / 24, 1022, { size: 10, mono: true, color: U.muted, align: 'center' }));
  for (let k = 0; k < 8; k++) {
    const h = k * 3 + 1;
    t(ctx, `☁ ${M.weather.temp[h]! > 0 ? '+' : ''}${Math.round(M.weather.temp[h]!)}°`, x + 12 + (cw * (k * 3 + 1.5)) / 24, 1042,
      { size: 10.5, color: U.text2, align: 'center' });
  }
  // матрица 61 день × 24 часа
  const mx = x + cw + 30;
  const mw = w - cw - 42;
  t(ctx, 'Посадки по дням и часам', mx, 928, { size: 12, color: U.text2 });
  const days = M.network.matrix.length;
  const max = Math.max(...M.network.matrix.flat());
  const cellW = mw / days;
  const cellH = 90 / 24;
  const ramp = ['#26305a', '#3b5a9a', '#5f8fb9', '#9bbf9a', '#d9b36c', '#e0876a', '#d8666f'];
  M.network.matrix.forEach((row, d) => row.forEach((v, h) => {
    const k = Math.min(Math.floor(Math.sqrt(v / max) * ramp.length), ramp.length - 1);
    ctx.fillStyle = ramp[k]!;
    ctx.fillRect(mx + d * cellW, 940 + h * cellH, cellW - 0.6, cellH - 0.4);
  }));
  const di = 13;
  rr(ctx, mx + di * cellW - 1, 939, cellW + 2, 92, 2, undefined, '#fff', 1.4);
  t(ctx, 'Ноябрь 2025', mx, 1048, { size: 10.5, color: U.muted });
  t(ctx, 'Декабрь 2025', mx + 30 * cellW, 1048, { size: 10.5, color: U.muted });
}

// ---------------------------------------------------------------------------
// Справа: вкладки
// ---------------------------------------------------------------------------

const TABS: [Tab, string][] = [['forecast', 'Прогноз'], ['shift', 'Смена'], ['scenario', 'Сценарий'], ['factors', 'Факторы'], ['model', 'Точность']];

function right(ctx: Ctx, s: UiState): void {
  card(ctx, 1510, 66, 400, 1004);
  TABS.forEach(([id, label], i) => {
    const b = L.tabs(i);
    if (s.tab === id) rr(ctx, b.x, b.y, b.w, b.h, 9, U.surface3);
    else if (s.hot === `tab-${id}`) rr(ctx, b.x, b.y, b.w, b.h, 9, U.surface2);
    t(ctx, label, b.x + b.w / 2, b.y + 20, { size: 12.5, weight: 500, color: s.tab === id ? U.text : U.muted, align: 'center' });
    if (id === 'scenario' && s.scenario > 0) {
      ctx.beginPath();
      ctx.arc(b.x + b.w - 6, b.y + 4, 7, 0, Math.PI * 2);
      ctx.fillStyle = U.warn;
      ctx.fill();
      t(ctx, String(s.scenario), b.x + b.w - 6, b.y + 7.5, { size: 9, weight: 700, color: '#1a1204', align: 'center' });
    }
  });
  ctx.fillStyle = U.line;
  ctx.fillRect(1511, 108, 398, 1);
  ctx.save();
  ctx.beginPath();
  ctx.rect(1511, 109, 398, 960);
  ctx.clip();
  ctx.translate(0, -s.scroll);
  if (s.tab === 'forecast') forecast(ctx, s);
  if (s.tab === 'shift') shift(ctx, s);
  if (s.tab === 'scenario') scenario(ctx, s);
  ctx.restore();
}

function sum(p: Band[], k: keyof Band): number {
  return p.reduce((a, b) => a + b[k], 0);
}

function fmtRange(lo: number, hi: number): string {
  if (hi >= 1e6) return `${(lo / 1e6).toFixed(1).replace('.', ',')}-${(hi / 1e6).toFixed(1).replace('.', ',')} млн`;
  return hi >= 10000 ? `${Math.round(lo / 1000)}-${Math.round(hi / 1000)} тыс.` : `${fmt(lo)}-${fmt(hi)}`;
}

function forecast(ctx: Ctx, s: UiState): void {
  const isRoute = s.route != null && s.routeQ > 0.5;
  const color = isRoute ? UI_ROUTE[17]! : '#e9eef5';
  const scenarioOn = s.triedQ > 0 && isRoute;
  rr(ctx, 1522, 120, 10, 36, 5, color);
  t(ctx, isRoute ? 'Маршрут 17' : 'Вся сеть', 1542, 137, { size: 16, weight: 700 });
  const nameW = tw(ctx, isRoute ? 'Маршрут 17' : 'Вся сеть', { size: 16, weight: 700 });
  rr(ctx, 1550 + nameW, 124, 60, 18, 9, undefined, 'rgba(122,162,247,0.45)');
  t(ctx, 'прогноз', 1580 + nameW, 137, { size: 10.5, color: U.accent, align: 'center' });
  t(ctx, isRoute ? M.routes.find((r) => r.route === 17)!.title : '10 трамвайных маршрутов', 1542, 154, { size: 11.5, color: U.muted });
  rr(ctx, 1522, 166, 378, 32, 10, U.bg, U.line);
  ['Сутки', 'Месяц', 'Год'].forEach((h, i) => {
    const b = L.horizon(i);
    const on = (s.horizon === 'day' && i === 0) || (s.horizon === 'year' && i === 2);
    if (on) rr(ctx, b.x, b.y, b.w, b.h, 8, U.surface3);
    t(ctx, h, b.x + b.w / 2, b.y + 18, { size: 12.5, color: on ? U.text : U.text2, align: 'center' });
  });
  const year = s.horizon === 'year' && !isRoute;
  const pts: Band[] = year ? M.network.year : isRoute ? (scenarioOn ? M.news.scenario.route17.map((p) => ({ p10: p.p50 * 0.83, p50: p.p50, p90: p.p50 * 1.23 })) : M.route17.day) : M.network.day;
  const hour = Math.floor(s.minute / 60);
  const peak = pts.reduce((a, p, i) => (p.p50 > pts[a]!.p50 ? i : a), 0);
  const cur = pts[year ? 0 : hour]!;
  const tot = { p10: sum(pts, 'p10'), p50: sum(pts, 'p50'), p90: sum(pts, 'p90') };
  kpi(ctx, 1522, 208, 184, 76, year ? 'Посадок за 12 месяцев' : 'Посадок за сутки', fmtK(tot.p50), `коридор ${fmtRange(tot.p10, tot.p90)}`);
  kpi(ctx, 1714, 208, 186, 76, year ? 'Пиковый месяц' : 'Пиковый час', fmtK(pts[peak]!.p50),
    year ? `${MONTHS_SHORT[peak]} ${peak < 2 ? 2025 : 2026}` : `${String(peak).padStart(2, '0')}:00-${peak + 1}:00`, U.accent);
  kpi(ctx, 1522, 292, 184, 76, year ? 'Ноябрь 2025' : 'В выбранный час', year ? fmtK(cur.p50) : fmt(cur.p50), `коридор ${fmtRange(cur.p10, cur.p90)}`);
  if (scenarioOn) {
    const d = (100 * (M.news.scenario.total - M.news.scenario.baseline)) / M.news.scenario.baseline;
    kpi(ctx, 1714, 292, 186, 76, 'Сценарий к базе', `${d.toFixed(2).replace('.', ',')} %`, 'сеть за ноябрь-декабрь', U.red);
  } else {
    kpi(ctx, 1714, 292, 186, 76, 'Разброс прогноза', `±${Math.round((50 * (tot.p90 - tot.p10)) / tot.p50)} %`, 'половина коридора');
  }
  card(ctx, 1522, 380, 378, 236, U.surface);
  t(ctx, year ? 'Посадки по месяцам' : 'Посадки по часам', 1536, 404, { size: 12, weight: 600, color: U.text2 });
  const labels = year ? MONTHS_SHORT : pts.map((_, i) => (i % 5 === 0 ? String(i).padStart(2, '0') : ''));
  bandChart(ctx, 1530, 414, 362, 196, pts, color, {
    cursor: year ? 0 : s.minute / 60, labels,
    compare: s.compare > 0 && isRoute ? M.route17.compare.map((p) => p.p50) : undefined, compareAlpha: s.compare,
    base: scenarioOn ? M.news.scenario.route17.map((p) => p.base) : undefined,
  });
  if (year) return;
  t(ctx, 'Сравнить с', 1522, 648, { size: 11.5, color: U.muted });
  button(ctx, 1590, 630, 38, 26, 'нет', { active: s.compare === 0, size: 11.5 });
  button(ctx, L.compareWeek.x, 630, 112, 26, 'неделей раньше', { active: s.compare > 0, size: 11.5 });
  rr(ctx, 1752, 630, 110, 26, 8, U.bg, U.lineStrong);
  t(ctx, s.compare > 0 ? '07.11.2025' : 'дд.мм.гггг', 1764, 648, { size: 11.5, mono: true, color: s.compare > 0 ? U.text : U.muted });
  if (s.compare > 0 && isRoute) {
    ctx.save();
    ctx.globalAlpha *= s.compare;
    rr(ctx, 1522, 666, 14, 3, 1.5, U.compare);
    const cmp = sum(M.route17.compare, 'p50');
    t(ctx, `7.11, пт: ${fmtK(cmp)}, выбранный период +${(((tot.p50 - cmp) / cmp) * 100).toFixed(1).replace('.', ',')} % к нему`, 1542, 672, { size: 11.5, color: U.text2 });
    ctx.restore();
  }
  if (isRoute) perTrip(ctx, s);
}

function advice(limit: number): { from: number; to: number; now: number; need: number }[] {
  const out: { from: number; to: number; now: number; need: number }[] = [];
  M.route17.perTrip.forEach((pt, h) => {
    const b = M.route17.day[h]!.p50;
    const hw = pt > 0 ? Math.round(120 / (b / pt)) : 0;
    if (!hw || b <= 0) return;
    const need = Math.floor(120 / Math.ceil(b / limit));
    if (need >= hw) return;
    const last = out[out.length - 1];
    if (last && last.to === h) {
      last.to = h + 1;
      last.now = Math.min(last.now, hw);
      last.need = Math.min(last.need, need);
    } else out.push({ from: h, to: h + 1, now: hw, need });
  });
  return out;
}

function perTrip(ctx: Ctx, s: UiState): void {
  const y = 690;
  card(ctx, 1522, y, 378, 330, U.surface);
  t(ctx, 'Посадок на рейс', 1536, y + 24, { size: 12, weight: 600, color: U.text2 });
  hourBars(ctx, 1536, y + 40, 350, 84, M.route17.perTrip, s.limit, Math.floor(s.minute / 60));
  t(ctx, 'Больше всего на рейс в 8:00, около 312 посадок.', 1536, y + 160, { size: 11.5, color: U.muted });
  t(ctx, 'Порог посадок на рейс', 1536, y + 186, { size: 12.5 });
  t(ctx, String(Math.round(s.limit)), 1886, y + 186, { size: 12.5, weight: 600, mono: true, align: 'right' });
  slider(ctx, L.limitSlider.x, y + 204, L.limitSlider.w, (s.limit - 100) / 200);
  const list = advice(Math.round(s.limit));
  let ly = y + 234;
  if (list.length === 0) {
    t(ctx, `Во все часы меньше ${Math.round(s.limit)} посадок на рейс.`, 1546, ly + 4, { size: 12, color: U.text2 });
  }
  list.slice(0, 3).forEach((a) => {
    rr(ctx, 1536, ly - 12, 2, 36, 1, U.red);
    t(ctx, `${a.from}-${a.to} ч:`, 1546, ly + 2, { size: 12, weight: 700 });
    t(ctx, ` интервал ${a.need} мин вместо ${a.now}, чтобы на рейс`, 1546 + tw(ctx, `${a.from}-${a.to} ч:`, { size: 12, weight: 700 }), ly + 2, { size: 12, color: U.text2 });
    t(ctx, `приходилось не больше ${Math.round(s.limit)} посадок`, 1546, ly + 18, { size: 12, color: U.text2 });
    ly += 44;
  });
}

function shift(ctx: Ctx, s: UiState): void {
  ['Сводка', 'Оповещения', 'Узкие места', 'Выпуск'].forEach((c, i) => {
    const x = [1522, 1588, 1706, 1804][i]!;
    const w = [60, 112, 92, 64][i]!;
    rr(ctx, x, 118, w, 26, 13, undefined, U.line);
    t(ctx, c, x + w / 2, 135, { size: 11.5, color: U.text2, align: 'center' });
    if (i === 1 && s.bell > 0) {
      ctx.beginPath();
      ctx.arc(x + w - 12, 131, 7, 0, Math.PI * 2);
      ctx.fillStyle = U.red;
      ctx.fill();
      t(ctx, '1', x + w - 12, 135, { size: 9.5, weight: 700, color: '#fff', align: 'center' });
    }
  });
  // сводка смены
  let y = 160;
  card(ctx, 1522, y, 378, 500, U.surface);
  t(ctx, 'Сводка смены: 14 ноября 2025, пятница', 1536, y + 24, { size: 12.5, weight: 600, color: U.text2 });
  t(ctx, `рабочий день, прогноз. Погода: ${M.weather.line}`, 1536, y + 46, { size: 11.5, color: U.text2 });
  kpi(ctx, 1536, y + 60, 114, 72, 'Посадок', `${Math.round(M.brief.total / 1000)} тыс.`, 'за сутки');
  kpi(ctx, 1656, y + 60, 114, 72, 'Пиковый час', `${M.brief.peakHour}:00`, fmtK(M.brief.peak), U.accent);
  kpi(ctx, 1776, y + 60, 112, 72, 'К неделе назад', `+${String(M.brief.vsWeek).replace('.', ',')} %`, 'к 7.11', U.ok);
  let x = 1536;
  t(ctx, 'Больше всего посадок:', x, y + 156, { size: 11.5 });
  x += tw(ctx, 'Больше всего посадок: ', { size: 11.5 });
  M.brief.top.forEach((r, i) => {
    const s1 = `№${r.route}`;
    t(ctx, s1, x, y + 156, { size: 11.5, weight: 700, color: UI_ROUTE[r.route] });
    x += tw(ctx, s1, { size: 11.5, weight: 700 }) + 4;
    const s2 = `${fmtK(r.total)}${i < 2 ? ',' : ''}`;
    t(ctx, s2, x, y + 156, { size: 11.5 });
    x += tw(ctx, s2, { size: 11.5 }) + 6;
  });
  t(ctx, 'Тесно: больше 185 посадок на рейс', 1536, y + 180, { size: 11, color: U.muted });
  M.brief.crowded.forEach((c, i) => {
    const ry = y + 194 + i * 46;
    badge(ctx, 1540, ry + 4, String(c.route), UI_ROUTE[c.route]!, { w: 30, h: 24, size: 12 });
    t(ctx, `${c.start}-${c.end} ч, до `, 1580, ry + 14, { size: 12 });
    t(ctx, `${c.peak}`, 1580 + tw(ctx, `${c.start}-${c.end} ч, до `, { size: 12 }), ry + 14, { size: 12, weight: 700 });
    t(ctx, `на рейс`, 1580 + tw(ctx, `${c.start}-${c.end} ч, до ${c.peak} `, { size: 12 }) + 4, ry + 14, { size: 12 });
    t(ctx, `интервал ${c.hw} → ${c.need} мин`, 1580, ry + 31, { size: 11, color: U.muted });
  });
  t(ctx, 'События дня', 1536, y + 390, { size: 11, color: U.muted });
  t(ctx, `•  ${M.brief.events[0] ?? ''}`, 1540, y + 410, { size: 11.5, color: U.text2 });
  button(ctx, 1536, y + 432, 170, 32, s.copied ? 'Скопировано' : 'Скопировать для чата', { primary: true, size: 12.5 });
  button(ctx, 1714, y + 432, 170, 32, 'Сводка от помощника', { size: 12.5 });
  // оповещения
  y = 676;
  card(ctx, 1522, y, 378, s.alertQ > 0 ? 230 : 170, U.surface);
  t(ctx, 'Оповещения на завтра, 15 ноября, суббота', 1536, y + 24, { size: 12.5, weight: 600, color: U.text2 });
  if (s.alertQ > 0) {
    ctx.save();
    ctx.globalAlpha *= s.alertQ;
    t(ctx, 'Сработало 1 из 1', 1536, y + 48, { size: 12, color: U.text2 });
    rr(ctx, 1536, y + 58, 350, 50, 9, 'rgba(229,115,125,0.1)');
    rr(ctx, 1536, y + 58, 3, 50, 1.5, U.red);
    badge(ctx, 1548, y + 70, '17', UI_ROUTE[17]!, { w: 30, h: 24, size: 12 });
    t(ctx, 'весь маршрут, порог 185', 1588, y + 78, { size: 12 });
    const sp = M.alert.spans.map((x2) => `${x2.start}-${x2.end} ч до ${x2.peak}`).join(', ');
    t(ctx, `${sp} на рейс`, 1588, y + 96, { size: 11, color: U.muted });
    ctx.restore();
  } else {
    t(ctx, 'Подписок нет. Выберите маршрут и порог ниже.', 1536, y + 48, { size: 12, color: U.text2 });
  }
  const fy = y + (s.alertQ > 0 ? 128 : 66);
  t(ctx, 'Маршрут', 1536, fy + 6, { size: 10.5, color: U.muted });
  t(ctx, 'Порог на рейс', 1618, fy + 6, { size: 10.5, color: U.muted });
  rr(ctx, 1536, fy + 14, 70, 30, 8, U.bg, U.lineStrong);
  t(ctx, '№17 ▾', 1548, fy + 34, { size: 12.5 });
  rr(ctx, 1618, fy + 14, 90, 30, 8, U.bg, U.lineStrong);
  t(ctx, '185', 1630, fy + 34, { size: 12.5 });
  button(ctx, 1720, fy + 14, 104, 30, 'Подписаться', { primary: true, size: 12.5 });
  // узкие места
  y = s.alertQ > 0 ? 922 : 862;
  card(ctx, 1522, y, 378, 420, U.surface);
  t(ctx, 'Узкие места на 7 дней', 1536, y + 24, { size: 12.5, weight: 600, color: U.text2 });
  t(ctx, `${M.week.count} ${plural(M.week.count, ['отрезок', 'отрезка', 'отрезков'])} на ${M.week.routes} маршрутах`, 1536, y + 48, { size: 12, color: U.text2 });
  M.week.top.slice(0, 5).forEach((w, i) => {
    const ry = y + 62 + i * 60;
    badge(ctx, 1540, ry + 8, String(w.route), UI_ROUTE[w.route]!, { w: 30, h: 24, size: 12 });
    t(ctx, `${w.label}, ${w.start}-${w.end} ч: до ${w.peak} на рейс`, 1580, ry + 16, { size: 12, weight: 600 });
    t(ctx, `интервал ${w.hw} → ${w.need} мин; больше всего входят`, 1580, ry + 33, { size: 11, color: U.muted });
    t(ctx, `на «${w.stop}»`, 1580, ry + 48, { size: 11, color: U.muted });
  });
  // калькулятор выпуска
  y += 436;
  card(ctx, 1522, y, 378, 300, U.surface);
  t(ctx, 'Калькулятор выпуска', 1536, y + 24, { size: 12.5, weight: 600, color: U.text2 });
  t(ctx, 'Маршрут', 1536, y + 48, { size: 10.5, color: U.muted });
  t(ctx, 'Часы', 1618, y + 48, { size: 10.5, color: U.muted });
  rr(ctx, 1536, y + 56, 70, 30, 8, U.bg, U.lineStrong);
  t(ctx, '№17 ▾', 1548, y + 76, { size: 12.5 });
  rr(ctx, 1618, y + 56, 56, 30, 8, U.bg, U.lineStrong);
  t(ctx, '7', 1630, y + 76, { size: 12.5 });
  rr(ctx, 1680, y + 56, 56, 30, 8, U.bg, U.lineStrong);
  t(ctx, '10', 1692, y + 76, { size: 12.5 });
  const hw = s.fleetHw ?? M.fleet.scheduleHeadway;
  const hwr = Math.round(hw);
  t(ctx, 'Интервал, мин', 1536, y + 112, { size: 12.5 });
  if (s.fleetHw == null) t(ctx, 'как по расписанию', 1630, y + 112, { size: 10.5, color: U.muted });
  t(ctx, String(hwr), 1886, y + 112, { size: 12.5, weight: 600, mono: true, align: 'right' });
  slider(ctx, 1536, y + 130, 350, (hw - 3) / 17);
  const f = M.fleet.byHeadway[String(hwr)] ?? M.fleet.byHeadway['6']!;
  const custom = s.fleetHw != null;
  kpi(ctx, 1536, y + 148, 170, 72, 'Вагонов на линии', String(custom ? f.vehicles : M.fleet.scheduleVehicles), `по расписанию ${M.fleet.scheduleVehicles}`,
    custom && f.vehicles > M.fleet.scheduleVehicles ? U.red : undefined);
  kpi(ctx, 1714, y + 148, 172, 72, 'Посадок на рейс', String(custom ? f.perTrip : 312), 'по расписанию 312', custom && f.perTrip < 312 ? U.ok : undefined);
  kpi(ctx, 1536, y + 226, 170, 64, 'Вагоно-часов', String(custom ? f.vehicleHours : M.fleet.scheduleVehicleHours),
    `по расписанию ${M.fleet.scheduleVehicleHours}, 7-10 ч`);
  kpi(ctx, 1714, y + 226, 172, 64, 'Оборот', `${M.fleet.cycle} мин`, `${Math.round(60 / hwr)} рейсов в час`);
}

function scenario(ctx: Ctx, s: UiState): void {
  const tried = E.outCubic(s.triedQ);
  let y = 126;
  t(ctx, '«Что если»: добавьте перекрытие, мероприятие или сбой', 1522, y, { size: 12, color: U.muted });
  t(ctx, 'из новостей. Прогноз ноября-декабря пересчитается сразу.', 1522, y + 17, { size: 12, color: U.muted });
  y += 36;
  if (tried > 0) {
    const sc = M.news.scenario;
    const h = 170 * tried;
    ctx.save();
    ctx.beginPath();
    ctx.rect(1520, y, 382, h);
    ctx.clip();
    card(ctx, 1522, y, 378, 164, U.surface);
    t(ctx, 'Итог сценария по сети', 1536, y + 24, { size: 12.5, weight: 600, color: U.text2 });
    const d = (100 * (sc.total - sc.baseline)) / sc.baseline;
    kpi(ctx, 1536, y + 36, 170, 72, 'За горизонт', `${d.toFixed(2).replace('.', ',')} %`, `−${fmt(sc.baseline - sc.total)} посадок`, U.red);
    kpi(ctx, 1714, y + 36, 172, 72, 'Самый затронутый день', fmt(Math.abs(Math.min(...sc.deltas))), '19.12, пятница');
    const max = Math.max(...sc.deltas.map(Math.abs), 1);
    const bw = 350 / sc.deltas.length;
    sc.deltas.forEach((v, i) => {
      const bh = Math.max((Math.abs(v) / max) * 36, v !== 0 ? 4 : 1);
      ctx.fillStyle = v < 0 ? U.red : U.surface3;
      ctx.fillRect(1536 + i * bw, y + 154 - bh, bw - 1, bh);
    });
    ctx.restore();
    y += h + 10;
  }
  t(ctx, 'СОБЫТИЯ: ПЕРЕКРЫТИЯ, СТРОЙКИ, МЕРОПРИЯТИЯ', 1522, y + 14, { size: 10.5, weight: 600, color: U.muted, tracking: 0.8 });
  y += 26;
  if (tried > 0) {
    ctx.save();
    ctx.globalAlpha *= tried;
    for (let k = 0; k < 2; k++) {
      rr(ctx, 1522, y, 378, 44, 8, U.surface2);
      rr(ctx, 1522, y, 3, 44, 1.5, U.warn);
      t(ctx, `как сбой 16.12: технические причины: маршрут 17 ×${k ? '0,5' : '0,962'}`, 1534, y + 19, { size: 11.5, weight: 600 });
      t(ctx, k ? '19.12, 22:00-24:00' : '19.12, 21:00-22:00', 1534, y + 36, { size: 11, color: U.muted });
      y += 50;
    }
    ctx.restore();
  }
  ['Перекрытие маршрута 17 днём', 'Мероприятие: +30 % вечером', 'Снегопад: −15 % весь день'].forEach((p, i) => {
    const w = tw(ctx, p, { size: 11.5 }) + 20;
    const x = i === 2 ? 1522 : i === 0 ? 1522 : 1522 + tw(ctx, 'Перекрытие маршрута 17 днём', { size: 11.5 }) + 26;
    const yy = i === 2 ? y + 34 : y;
    button(ctx, x, yy, w, 28, p, { size: 11.5 });
  });
  y += 80;
  t(ctx, 'СБОИ ИЗ НОВОСТЕЙ ДЕПТРАНСА', 1522, y, { size: 10.5, weight: 600, color: U.muted, tracking: 0.8 });
  t(ctx, 'Канал проверен в 08:10: свежих сбоев на десяти маршрутах нет.', 1522, y + 20, { size: 11.5, color: U.text2 });
  t(ctx, '«Примерить» переносит такой же сбой на 19.12.', 1522, y + 37, { size: 11.5, color: U.text2 });
  y += 50;
  M.news.incidents.forEach((n, i) => {
    const hot = s.newsHover === i;
    rr(ctx, 1522, y, 378, 84, 8, hot ? U.surface3 : U.surface2);
    rr(ctx, 1522, y, 3, 84, 1.5, hot ? UI_ROUTE[n.routes[0]!]! : U.lineStrong);
    let x = 1534;
    n.routes.forEach((r) => {
      t(ctx, `№${r}`, x, y + 20, { size: 12, weight: 700, color: UI_ROUTE[r] });
      x += tw(ctx, `№${r}`, { size: 12, weight: 700 }) + 6;
    });
    const when = `${n.start.slice(8, 10)}.${n.start.slice(5, 7)}, ${n.start.slice(11, 16)}-${n.end.slice(11, 16)}, ${Math.round(n.minutes)} мин`;
    t(ctx, when, x, y + 20, { size: 12, weight: 600 });
    rr(ctx, 1818, y + 8, 74, 18, 6, undefined, U.lineStrong);
    t(ctx, 'в прогнозе', 1855, y + 21, { size: 10, color: U.muted, align: 'center' });
    tc(ctx, `${n.causeLabel}. ${n.location}`, 1534, y + 40, 356, { size: 11, color: U.muted });
    const tryHot = hot && s.hot === 'try';
    button(ctx, 1534, y + 50, 130, 26, 'Примерить на 19.12', { size: 11.5, active: tryHot });
    t(ctx, 'сообщение ↗', 1676, y + 68, { size: 11.5, color: U.accent });
    y += 92;
  });
  if (tried > 0.5) t(ctx, 'Добавлено 4 события: такой же сбой 19.12. Итог по сети - выше.', 1522, y + 10, { size: 11.5, color: U.text2 });
}

// ---------------------------------------------------------------------------
// Помощник, выгрузка, табло
// ---------------------------------------------------------------------------

const QUESTION = 'Покажи 17 маршрут 14 ноября в 8 утра';
const ANSWER = '14 ноября в 8:00 на маршруте 17 прогноз 5 349 посадок: около 312 на рейс при интервале 7 минут, это больше вместимости вагона. Показал маршрут на карте.';
const STEPS = ['Считаю прогноз', 'Показываю на экране'];

function wrap(ctx: Ctx, str: string, maxW: number, size: number): string[] {
  const out: string[] = [];
  let line = '';
  for (const w of str.split(' ')) {
    const test = line ? `${line} ${w}` : w;
    if (line && tw(ctx, test, { size }) > maxW) {
      out.push(line);
      line = w;
    } else line = test;
  }
  if (line) out.push(line);
  return out;
}

function agent(ctx: Ctx, s: UiState): void {
  const q = E.outBack(Math.min(s.agentQ, 1));
  const x = 1226;
  const y = 52;
  const w = 440;
  ctx.save();
  ctx.translate(x + w, y);
  ctx.scale(0.6 + 0.4 * q, 0.2 + 0.8 * q);
  ctx.translate(-(x + w), -y);
  ctx.globalAlpha *= Math.min(1, s.agentQ * 2);
  const h = 330;
  rr(ctx, x, y, w, h, 22, '#050507', U.lineStrong);
  t(ctx, 'Помощник диспетчера', x + 16, y + 28, { size: 13.5, weight: 700 });
  t(ctx, 'gpt-oss:120b, память Redis', x + 176, y + 28, { size: 11.5, color: U.muted });
  t(ctx, '↺   ✕', x + w - 16, y + 29, { size: 13, color: U.muted, align: 'right' });
  const qText = QUESTION.slice(0, Math.round(QUESTION.length * Math.min(s.question, 1)));
  if (s.question >= 1) {
    const qw = tw(ctx, QUESTION, { size: 13 }) + 22;
    rr(ctx, x + w - 16 - qw, y + 48, qw, 30, 14, U.surface3);
    t(ctx, QUESTION, x + w - 16 - qw + 11, y + 68, { size: 13 });
  } else {
    t(ctx, 'Спросите словами: агент посчитает, покажет на карте', x + 16, y + 64, { size: 12.5, color: U.muted });
    t(ctx, 'и откроет нужную панель.', x + 16, y + 81, { size: 12.5, color: U.muted });
    ['Покажи 17 маршрут 14 ноября в 8 утра', 'Где на этой неделе рейсы переполнены?', 'Что будет, если перекрыть 17 маршрут днём?'].forEach((e, i) => {
      rr(ctx, x + 16, y + 96 + i * 38, w - 32, 30, 10, undefined, i === 0 && s.hot === 'example' ? U.lineStrong : U.line);
      t(ctx, e, x + 28, y + 116 + i * 38, { size: 12.5, color: U.text2 });
    });
  }
  if (s.question >= 1) {
    let sx = x + 16;
    STEPS.forEach((st, i) => {
      const a = Math.min(Math.max(s.steps - i, 0), 1);
      if (a <= 0) return;
      const sw = tw(ctx, st, { size: 12 }) + 22;
      ctx.save();
      ctx.globalAlpha *= a;
      rr(ctx, sx, y + 92, sw, 26, 13, undefined, 'rgba(122,162,247,0.45)');
      t(ctx, st, sx + 11, y + 109, { size: 12, color: '#aac4ff' });
      ctx.restore();
      sx += sw + 8;
    });
    const shown = ANSWER.slice(0, Math.round(ANSWER.length * Math.min(s.answer, 1)));
    wrap(ctx, shown, w - 32, 13.5).forEach((line, i) => t(ctx, line, x + 16, y + 146 + i * 21, { size: 13.5 }));
  }
  ctx.fillStyle = U.line;
  ctx.fillRect(x, y + h - 64, w, 1);
  rr(ctx, x + 12, y + h - 50, 292, 38, 12, U.bg, U.lineStrong);
  const typing = s.question > 0 && s.question < 1;
  t(ctx, typing ? qText : 'Вопрос о посадках', x + 24, y + h - 26, { size: 13, color: typing ? U.text : U.muted });
  if (typing) rr(ctx, x + 26 + tw(ctx, qText, { size: 13 }), y + h - 40, 1.5, 18, 0, U.text);
  rr(ctx, x + 312, y + h - 50, 38, 38, 12, undefined, U.lineStrong);
  t(ctx, '🎙', x + 331, y + h - 25, { size: 14, color: U.text2, align: 'center' });
  button(ctx, x + 358, y + h - 50, 70, 38, 'Спросить', { primary: true, size: 12.5 });
  ctx.restore();
}

function exportSheet(ctx: Ctx, s: UiState): void {
  const q = E.outCubic(s.exportQ);
  ctx.save();
  ctx.fillStyle = `rgba(0,0,0,${0.35 * q})`;
  ctx.fillRect(0, 0, 1920, 1080);
  ctx.translate(360 * (1 - q), 0);
  const x = 1560;
  ctx.fillStyle = '#131418';
  ctx.fillRect(x, 0, 360, 1080);
  ctx.fillStyle = U.lineStrong;
  ctx.fillRect(x, 0, 1, 1080);
  t(ctx, 'Выгрузка прогноза', x + 20, 34, { size: 15, weight: 700 });
  t(ctx, '✕', x + 332, 34, { size: 14, color: U.muted, align: 'center' });
  t(ctx, 'ЧТО ВЫГРУЗИТЬ', x + 20, 70, { size: 10.5, weight: 600, color: U.muted, tracking: 0.8 });
  const opts: [string, string][] = [['Маршрут 17', 'выбранный маршрут'], ['Все маршруты', '10 маршрутов, как в сабмите'],
    ['Все остановки', '452 остановки, оценка по долям'], ['Вся сеть', 'сумма по 10 маршрутам']];
  opts.forEach(([a, b], i) => {
    const y = 84 + i * 60;
    rr(ctx, x + 20, y, 320, 52, 10, i === 0 ? U.surface2 : undefined, i === 0 ? U.lineStrong : U.line);
    ctx.beginPath();
    ctx.arc(x + 42, y + 20, 6, 0, Math.PI * 2);
    ctx.strokeStyle = U.text2;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    if (i === 0) {
      ctx.beginPath();
      ctx.arc(x + 42, y + 20, 3, 0, Math.PI * 2);
      ctx.fillStyle = U.text;
      ctx.fill();
    }
    t(ctx, a, x + 60, y + 24, { size: 13, weight: 600 });
    t(ctx, b, x + 60, y + 42, { size: 11, color: U.muted });
  });
  t(ctx, 'ПЕРИОД', x + 20, 342, { size: 10.5, weight: 600, color: U.muted, tracking: 0.8 });
  ['Сутки', 'Месяц', 'Ноябрь-декабрь', 'Год', 'Свой'].forEach((p, i) => {
    const xs = [20, 84, 150, 272, 320][i]!;
    const w = tw(ctx, p, { size: 12 }) + 22;
    if (i < 4) button(ctx, x + xs, 354, w, 28, p, { active: i === 2, size: 12 });
  });
  t(ctx, '2025-11-01 - 2025-12-31: прогноз, источник в столбце «источник».', x + 20, 404, { size: 11, color: U.muted });
  t(ctx, 'ШАГ', x + 20, 438, { size: 10.5, weight: 600, color: U.muted, tracking: 0.8 });
  ['По часам', 'По суткам', 'По месяцам'].forEach((p, i) => button(ctx, x + 20 + i * 104, 450, 98, 28, p, { active: i === 0, size: 12 }));
  rr(ctx, x + 20, 500, 320, 44, 10, U.surface2);
  t(ctx, 'Строк в файле', x + 34, 527, { size: 12.5, color: U.text2 });
  t(ctx, '1 464', x + 326, 528, { size: 18, weight: 700, mono: true, align: 'right' });
  button(ctx, x + 20, 556, 250, 36, '⤓ Скачать XLSX', { primary: true, size: 13 });
  button(ctx, x + 278, 556, 62, 36, 'CSV', { size: 13 });
  t(ctx, 'CSV в UTF-8 с разделителем «;», открывается в Excel.', x + 20, 614, { size: 11, color: U.muted });
  t(ctx, 'Маршруты по часам за ноябрь-декабрь совпадают', x + 20, 630, { size: 11, color: U.muted });
  t(ctx, 'с файлом сабмита.', x + 20, 646, { size: 11, color: U.muted });
  ctx.restore();
}

function board(ctx: Ctx, s: UiState, time: number): void {
  const q = E.outCubic(s.boardQ);
  ctx.save();
  ctx.globalAlpha *= q;
  ctx.fillStyle = '#050608';
  ctx.fillRect(0, 0, 1920, 1080);
  const g = ctx.createRadialGradient(960, -200, 0, 960, -200, 1200);
  g.addColorStop(0, '#151b2b');
  g.addColorStop(1, 'rgba(5,6,8,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 1920, 1080);
  t(ctx, 'Час пик', 48, 84, { size: 22, weight: 700 });
  t(ctx, 'табло', 140, 84, { size: 22, color: U.muted });
  t(ctx, clock(s.minute), 268, 100, { size: 72, weight: 700, mono: true });
  t(ctx, '14 ноября 2025, пятница', 490, 96, { size: 18, color: U.text2 });
  t(ctx, '+5°', 930, 90, { size: 32, weight: 600 });
  t(ctx, 'облачно', 1000, 90, { size: 18, color: U.text2 });
  t(ctx, 'вся сеть в этот час', 1780, 58, { size: 17, color: U.text2, align: 'right' });
  t(ctx, fmtK(M.network.day[8]!.p50), 1780, 102, { size: 34, weight: 700, mono: true, align: 'right' });
  const spot = M.board.find((b) => b.route === 17)!;
  const color = UI_ROUTE[17]!;
  rr(ctx, 48, 144, 1824, 650, 28, `${color}10`, `${color}59`);
  rr(ctx, 76, 172, 150, 150, 28, color);
  t(ctx, '17', 151, 280, { size: 96, weight: 800, mono: true, color: '#0b0d12', align: 'center' });
  t(ctx, M.routes.find((r) => r.route === 17)!.title, 254, 240, { size: 40, weight: 700 });
  t(ctx, '8:00-9:00 · прогноз посадок', 254, 280, { size: 20, color: U.text2 });
  const cells: [string, string, string, string?][] = [
    ['посадок в час', fmt(spot.now), ''],
    ['на один рейс', String(spot.perTrip), 'больше 185: вагон переполнен', U.red],
    ['интервал', `${spot.headway} мин`, 'по расписанию'],
    ['следующий час', fmt(spot.next), `▼ ${fmt(spot.now - spot.next)}`],
  ];
  cells.forEach(([l, v, sub, c], i) => {
    const x = 76 + i * 450;
    rr(ctx, x, 344, 426, 180, 20, 'rgba(255,255,255,0.02)', U.line);
    t(ctx, l, x + 22, 378, { size: 17, color: U.muted });
    t(ctx, v, x + 22, 470, { size: 84, weight: 700, mono: true, color: c ?? U.text });
    t(ctx, sub, x + 22, 506, { size: 16, color: i === 3 ? U.ok : U.text2 });
  });
  sparkline(ctx, M.route17.day.map((p) => p.p50), 76, 548, 1768, 170, color);
  ctx.strokeStyle = 'rgba(255,255,255,0.7)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(76 + (1768 * 8) / 23, 548);
  ctx.lineTo(76 + (1768 * 8) / 23, 718);
  ctx.stroke();
  t(ctx, `Больше всего входят: ${M.route17.stops.slice().sort((a, b) => b.value - a.value).slice(0, 3).map((x) => `${x.name} ${x.value}`).join(' · ')}`,
    76, 760, { size: 20, color: U.text2 });
  rr(ctx, 48, 814, 1824 * ((time * 0.12) % 1), 3, 1.5, U.text2);
  M.board.forEach((b, i) => {
    const x = 48 + i * 184;
    const on = b.route === 17;
    rr(ctx, x, 834, 172, 118, 16, U.surface, on ? UI_ROUTE[b.route] : U.line, on ? 2 : 1);
    t(ctx, String(b.route), x + 14, 868, { size: 24, weight: 800, mono: true, color: UI_ROUTE[b.route] });
    const v = b.perTrip;
    const col = v == null ? U.muted : v > 185 ? U.red : v > 148 ? U.warn : U.text;
    t(ctx, v == null ? '-' : String(v), x + 14, 914, { size: 34, weight: 700, mono: true, color: col });
    t(ctx, v == null ? 'не ходит' : 'на рейс', x + 14, 938, { size: 13, color: U.muted });
  });
  rr(ctx, 48, 972, 1824, 50, 14, 'rgba(239,65,54,0.07)', 'rgba(239,65,54,0.35)');
  const tick = `Завтра №17: ${M.alert.spans.map((x) => `${x.start}-${x.end} ч до ${x.peak} на рейс`).join(', ')}`;
  t(ctx, tick, 1880 - ((time * 90) % 2400), 1004, { size: 19 });
  ctx.restore();
}

/** Координаты маршрута 17 в списке и остальных целей: для сценариев. */
export const TARGET = {
  route17: () => { const r = L.routeRow(M.routes.findIndex((x) => x.route === 17)); return [r.x + 120, r.y + 25] as [number, number]; },
  stops: () => [L.stopsButton.x + 125, L.stopsButton.y + 16] as [number, number],
  tab: (id: Tab) => { const b = L.tabs(TABS.findIndex(([x]) => x === id)); return [b.x + b.w / 2, b.y + b.h / 2] as [number, number]; },
  horizon: (i: number) => { const b = L.horizon(i); return [b.x + b.w / 2, b.y + b.h / 2] as [number, number]; },
  compareWeek: () => [L.compareWeek.x + 56, 643] as [number, number],
  limit: (v: number) => [L.limitSlider.x + (L.limitSlider.w * (v - 100)) / 200, 894] as [number, number],
  export: () => [1818, 28] as [number, number],
  board: () => [1745, 28] as [number, number],
  pill: (scenario: boolean) => [scenario ? 1459 : 1589, 28] as [number, number],
  timeline: (minute: number) => [323 + (396 * minute) / 1440, 1001] as [number, number],
};

