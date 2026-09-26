import { TARGET, initialState, stopPoint, type UiState } from './mock/app';
import { M } from './mock/data';
import { FULL } from './mock/stage';
import { productSlide } from './layouts';

// Слайды с макетом интерфейса: курсор ходит по экрану сервиса и нажимает кнопки, пункт загорается, когда курсор
// делает то, о чём он говорит. Раскладка, фон и место Москвы внизу у каждого слайда свои (layouts.ts).

const hover = (x: number, y: number, title: string, sub: string) => (s: UiState, q: number) => { s.hover = { x, y, title, sub, q }; };

// ---------------------------------------------------------------------------
// 03. Экран диспетчера
// ---------------------------------------------------------------------------

const S0 = initialState();
const vdnh = stopPoint(S0, 'ВДНХ (северная)');
const vdnhValue = M.route17.stops.find((s) => s.name === 'ВДНХ (северная)')?.value ?? 0;
const matrixCell: [number, number] = [736 + 13 * (752 / 61) + 6, 940 + 8 * (90 / 24) + 2];

export const mapScreen = productSlide({
  id: 'map', label: 'Карта', num: '03 · ЭКРАН ДИСПЕТЧЕРА', title: 'Вся сеть на одной карте: любой день и час', dur: 30, seed: 3,
  layout: 'right', bg: 'paper', scene: 'city',
  tr: { kind: 'tram', dur: 2.6 },
  points: [
    { t: 2.4, text: 'Карта в выбранный час: цвет остановки - посадки, толщина линии - посадки маршрута, вагоны идут по расписанию' },
    { t: 8.0, text: 'Ползунок времени: посадки и вагоны меняются по часам, от утреннего пика к вечернему' },
    { t: 15.0, text: 'Прогноз сети, маршрута, остановки или участка на сутки, месяц или год с коридором' },
    { t: 21.5, text: 'Матрица «61 день × 24 часа» внизу: видны пики и выходные, клик переносит время' },
  ],
  views: [[0, FULL], [1.6, [310, 66, 1190]], [7.8, [300, 470, 1100]], [14.4, [1020, 110, 900]], [21.2, [300, 500, 1000]], [27, FULL]],
  acts: [
    { t: 3.6, at: vdnh, apply: hover(vdnh[0], vdnh[1], 'ВДНХ (северная)', `${vdnhValue} посадок в 8:00-9:00, прогноз`), dur: 0.3 },
    { t: 9.2, at: TARGET.timeline(490), drag: TARGET.timeline(18 * 60 + 10), dur: 3.8,
      apply: (s, q) => { s.hover = null; s.minute = 490 + (18 * 60 - 480) * q; } },
    { t: 16.2, at: TARGET.horizon(2), click: true, apply: (s) => { s.minute = 18 * 60 + 10; s.horizon = 'year'; } },
    { t: 22.6, at: matrixCell, apply: (s, q) => { s.minute = 18 * 60 + 10; s.horizon = 'year'; hover(matrixCell[0], matrixCell[1], 'пт 14.11, 8:00-9:00', `${M.network.day[8]!.p50.toLocaleString('ru-RU')} посадок по сети`)(s, q); }, dur: 0.3 },
    { t: 25.4, at: matrixCell, click: true, apply: (s) => { s.hover = null; s.minute = 8 * 60 + 10; s.horizon = 'day'; } },
  ],
});

// ---------------------------------------------------------------------------
// 04. Маршрут
// ---------------------------------------------------------------------------

const pickRoute = (s: UiState, q: number) => { s.route = 17; s.routeQ = q; };

export const routeScreen = productSlide({
  id: 'route', label: 'Маршрут', num: '04 · МАРШРУТ И ОСТАНОВКИ', title: 'Сколько входит в рейс и когда добавить вагоны', dur: 36, seed: 5,
  layout: 'left', bg: 'paper', scene: 'luzhniki',
  tr: { kind: 'zoom', dur: 1.3, x: 645, y: 514 },
  points: [
    { t: 2.4, text: 'Клик по маршруту: карта летит к трассе, справа прогноз маршрута на сутки' },
    { t: 8.4, text: 'Остановки маршрута с посадками за час и участок между двумя остановками' },
    { t: 14.2, text: 'Сравнение с другой датой: 7 ноября жёлтым пунктиром на том же графике' },
    { t: 19.6, text: 'Посадок на рейс по расписанию: в 8:00 около 312 при вместимости вагона 185' },
    { t: 24.8, text: 'Порог меняется ползунком, совет по интервалу пересчитывается сразу' },
    { t: 30.8, text: 'Выгрузка в CSV или XLSX: маршрут, остановки, участок или вся сеть' },
  ],
  views: [[0, FULL], [2.2, [0, 60, 1500]], [8.2, [0, 60, 1000]], [14.0, [1020, 110, 900]], [19.4, [1020, 540, 900]], [30.4, [1020, 0, 900]]],
  acts: [
    { t: 3.6, at: TARGET.route17(), click: true, dur: 1.6, apply: pickRoute },
    { t: 9.6, at: TARGET.stops(), click: true, dur: 0.9, apply: (s, q) => { pickRoute(s, 1); s.stopsQ = q; } },
    { t: 15.4, at: TARGET.compareWeek(), click: true, dur: 0.9, apply: (s, q) => { s.compare = q; } },
    { t: 20.6, at: [1536 + 8.5 * (350 / 24), 780], apply: () => undefined },
    { t: 26.0, at: TARGET.limit(185), drag: TARGET.limit(260), dur: 2.8, apply: (s, q) => { s.limit = 185 + 75 * q; } },
    { t: 31.8, at: TARGET.export(), click: true, dur: 0.7, apply: (s, q) => { s.exportQ = q; } },
  ],
});

// ---------------------------------------------------------------------------
// 05. Смена
// ---------------------------------------------------------------------------

const toShift = (s: UiState) => { s.tab = 'shift'; };
const scrollTo = (from: number, to: number) => (s: UiState, q: number) => { toShift(s); s.scroll = from + (to - from) * q; };

export const shiftScreen = productSlide({
  id: 'shift', label: 'Смена', num: '05 · ВКЛАДКА «СМЕНА»', title: 'Утро диспетчера: сводка, оповещения, узкие места', dur: 38, seed: 8,
  layout: 'subtitles', bg: 'dawn', scene: 'kremlin',
  tr: { kind: 'ink', dur: 1.4, seed: 3 },
  points: [
    { t: 2.4, text: 'Сводка смены: посадки, пиковый час, погода и тесные часы на одном экране' },
    { t: 7.6, text: 'Одна кнопка кладёт сводку в буфер обмена для рабочего чата' },
    { t: 12.2, text: 'Оповещения: подписка на маршрут или участок, колокольчик считает сработавшие на завтра' },
    { t: 18.6, text: `Узкие места на 7 дней: ${M.week.count} отрезок, острее всего №17 в 7-10 ч, до ${M.week.top[0]?.peak} на рейс` },
    { t: 24.0, text: 'Калькулятор выпуска: интервал 4 мин вместо 6 - это 23 вагона вместо 15 и 178 посадок на рейс' },
    { t: 31.4, text: 'Табло на большой экран диспетчерской: крупные числа, маршруты сменяются сами' },
  ],
  views: [[0, FULL], [2.2, [1020, 70, 900]], [7.4, [1020, 200, 900]], [12.0, [1020, 110, 900]], [30.6, FULL]],
  acts: [
    { t: 3.4, at: TARGET.tab('shift'), click: true, apply: toShift },
    { t: 8.8, at: [1621, 608], click: true, apply: (s) => { toShift(s); s.copied = true; } },
    { t: 12.4, dur: 1.4, apply: scrollTo(0, 520) },
    { t: 14.8, at: [1772, 771 - 520], click: true, dur: 0.7, apply: (s, q) => { scrollTo(0, 520)(s, 1); s.alertQ = q; s.bell = 1; } },
    { t: 18.8, dur: 1.6, apply: (s, q) => { scrollTo(520, 800)(s, q); s.alertQ = 1; s.bell = 1; } },
    { t: 24.2, dur: 1.6, apply: (s, q) => { scrollTo(800, 1248)(s, q); s.alertQ = 1; s.bell = 1; } },
    { t: 26.2, at: [1536 + (350 * 3) / 17, 1488 - 1248], drag: [1536 + (350 * 1) / 17, 1488 - 1248], dur: 2.4,
      apply: (s, q) => { scrollTo(800, 1248)(s, 1); s.alertQ = 1; s.bell = 1; s.fleetHw = 6 - 2 * q; } },
    { t: 32.6, at: TARGET.board(), click: true, dur: 1.0, apply: (s, q) => { scrollTo(800, 1248)(s, 1); s.alertQ = 1; s.bell = 1; s.fleetHw = 4; s.boardQ = q; } },
  ],
});

// ---------------------------------------------------------------------------
// 06. Сценарии и новости
// ---------------------------------------------------------------------------

const night = (s: UiState) => { s.dateLabel = '19 декабря 2025, пятница'; s.minute = 22 * 60 + 10; s.route = 17; s.routeQ = 1; };
const newsY = 162 + 26 + 80 + 50 + 3 * 92;

export const newsScreen = productSlide({
  id: 'news', label: 'Сценарии', num: '06 · СЦЕНАРИИ И НОВОСТИ', title: 'Сбой из новостей Дептранса сразу становится сценарием', dur: 32, seed: 11,
  layout: 'clippings', bg: 'night', scene: 'theatre',
  tr: { kind: 'scan', dur: 1.3, angle: 0.5, ring: '#E43D8C' },
  points: [
    { t: 2.4, text: 'Сервис сам читает канал Дептранса t.me/DtOperativno и собирает сбои: начало, конец, причина, место' },
    { t: 8.0, text: `Сбой 16 декабря на проспекте Мира: ${Math.round(M.news.incidents[3]!.minutes)} минут без трамваев №17` },
    { t: 13.2, text: '«Примерить» переносит такой же сбой на 19 декабря: в часы сбоя посадки падают вдвое' },
    { t: 19.6, text: `Итог сразу в прогнозе: −${(M.news.scenario.baseline - M.news.scenario.total).toLocaleString('ru-RU')} посадок по сети, база видна пунктиром` },
  ],
  views: [[0, FULL], [2.2, [1020, 70, 900]], [7.8, [1020, 250, 900]], [14.8, [1020, 70, 900]], [19.4, [1020, 110, 900]], [26.5, FULL]],
  acts: [
    { t: 0, apply: night },
    { t: 3.4, at: TARGET.tab('scenario'), click: true, apply: (s) => { night(s); s.tab = 'scenario'; } },
    { t: 9.0, at: [1700, newsY + 30], apply: (s) => { night(s); s.tab = 'scenario'; s.newsHover = 3; } },
    { t: 11.6, at: [1599, newsY + 63], apply: (s) => { night(s); s.tab = 'scenario'; s.newsHover = 3; s.hot = 'try'; } },
    { t: 13.4, at: [1599, newsY + 63], click: true, dur: 1.4, apply: (s, q) => { night(s); s.tab = 'scenario'; s.newsHover = 3; s.hot = null; s.triedQ = q; s.scenario = 4; } },
    { t: 20.4, at: TARGET.tab('forecast'), click: true, apply: (s) => { night(s); s.tab = 'forecast'; s.triedQ = 1; s.scenario = 4; } },
  ],
});

// ---------------------------------------------------------------------------
// 07. Помощник
// ---------------------------------------------------------------------------

const open = (s: UiState) => { s.agentQ = 1; };

export const agentScreen = productSlide({
  id: 'agent', label: 'Помощник', num: '07 · ПОМОЩНИК ДИСПЕТЧЕРА', title: 'Вопрос словами: ответ числами и картой', dur: 28, seed: 2,
  layout: 'chat', bg: 'blue', scene: 'bridge',
  tr: { kind: 'lens', dur: 1.4, x: 880, y: 230, ring: '#C8C1EF' },
  points: [
    { t: 2.4, text: 'Плашка «Спросить» или клавиша /: вопрос словами или голосом' },
    { t: 7.4, text: 'Агент на Java: модель gpt-oss:120b вызывает 14 инструментов MCP-сервера' },
    { t: 12.8, text: 'Интерфейс слушается ответа: карта летит к маршруту, панель переключается сама' },
    { t: 19.0, text: 'Отвечает только про трамваи и только числами сервиса, память диалога в Redis' },
  ],
  views: [[0, FULL], [2.2, [1060, 0, 760]], [12.6, FULL], [18.6, [1060, 0, 760]]],
  acts: [
    { t: 3.4, at: TARGET.pill(false), click: true, dur: 0.7, apply: (s, q) => { s.agentQ = q; } },
    { t: 6.4, at: [1340, 52 + 330 - 31], click: true, apply: open },
    { t: 6.8, dur: 2.6, apply: (s, q) => { open(s); s.question = q * 0.999; } },
    { t: 10.2, at: [1226 + 393, 52 + 330 - 31], click: true, dur: 2.0, apply: (s, q) => { open(s); s.question = 1; s.steps = q * 2; } },
    { t: 12.8, dur: 1.8, apply: (s, q) => { open(s); s.question = 1; s.steps = 2; s.route = 17; s.routeQ = q; } },
    { t: 13.2, dur: 4.0, apply: (s, q) => { open(s); s.question = 1; s.steps = 2; s.route = 17; s.routeQ = 1; s.answer = q; } },
  ],
});

