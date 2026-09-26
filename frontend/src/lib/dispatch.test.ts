import { describe, expect, it } from 'vitest';
import type { Factors, NetworkLoad, RouteStop } from '../api/types';
import { bottlenecks, fleet, headway, intervalAdvice, neededHeadway, perTripDay, segmentShare, spansAbove } from './dispatch';
import { buildBrief, dayEvents, weatherLine } from './brief';

/** Расписание: маршрут 17 ходит раз в 6 минут в будни и раз в 10 в выходные, ночью не ходит. */
function factors(): Factors {
  const weekday = Array.from({ length: 24 }, (_, h) => (h < 5 ? null : 6));
  const weekend = Array.from({ length: 24 }, (_, h) => (h < 5 ? null : 10));
  return {
    schedule: { routes: { 17: { title: '', page: '', weekday: { headway_min: weekday, service_from: '', service_to: '' },
      weekend: { headway_min: weekend, service_from: '', service_to: '' } } } },
    events: [
      { start: '2025-11-02', end: '2025-11-09', routes: '50;7', days: 'weekends', type: 'closure', description: 'закрыт', source: '', effect: null },
      { start: '2025-11-12', end: null, routes: '7;50', days: 'all', type: 'network', description: 'запуск Т1', source: '', effect: null },
    ],
  } as unknown as Factors;
}

function load(values: number[], stops: Record<string, number[]> = {}): NetworkLoad {
  return { source: 'forecast', date: '2025-11-14', hours: [...Array(24).keys()], routes: new Map([[17, values]]),
    stops: new Map(Object.entries(stops)) };
}

const flat = (v: number) => Array.from({ length: 24 }, (_, h) => (h < 5 ? 0 : v));

describe('посадки на рейс', () => {
  it('делит посадки часа на рейсы в обе стороны по расписанию', () => {
    // 6 минут - 10 рейсов в час в каждую сторону, 20 в обе
    expect(perTripDay(factors(), 17, false, flat(4000))[8]).toBe(200);
    expect(perTripDay(factors(), 17, true, flat(4000))[8]).toBeCloseTo(4000 / 12);
  });

  it('ночью без рейсов даёт ноль, а не деление на ноль', () => {
    expect(headway(factors(), 17, false, 2)).toBeNull();
    expect(perTripDay(factors(), 17, false, flat(4000))[2]).toBe(0);
  });

  it('на участке в одну сторону делит долю участка на рейсы этой стороны', () => {
    // доля 0,25 от 4000 = 1000 посадок на 10 рейсов в эту сторону
    expect(perTripDay(factors(), 17, false, flat(4000), 0.25, true)[8]).toBe(100);
  });
});

describe('узкие места', () => {
  it('склеивает соседние часы выше порога и запоминает пик', () => {
    const v = Array(24).fill(0);
    v[7] = 190;
    v[8] = 230;
    v[9] = 200;
    v[18] = 186;
    expect(spansAbove(v, 185)).toEqual([
      { from: 7, to: 10, peak: 230, peakHour: 8 },
      { from: 18, to: 19, peak: 186, peakHour: 18 },
    ]);
  });

  it('советует интервал, при котором поток укладывается в порог', () => {
    // 4600 посадок / 185 = 25 рейсов в обе стороны, интервал 120 / 25 = 4,8 -> 4 мин
    expect(neededHeadway(4600, 185)).toBe(4);
    expect(intervalAdvice({ headway: 6, need: 4 })).toBe('интервал 6 → 4 мин');
    expect(intervalAdvice({ headway: 6, need: 2 })).toMatch(/даже интервал 3 мин не хватит/);
  });

  it('сортирует узкие места от самых острых и находит главную остановку', () => {
    const hours = flat(1000);
    hours[8] = 4600;
    const stops: RouteStop[] = [
      { direction: 0, seq: 1, stopId: 'a', name: 'Останкино', lat: 0, lon: 0, share: 0.3 },
      { direction: 0, seq: 2, stopId: 'b', name: 'ВДНХ', lat: 0, lon: 0, share: 0.2 },
    ];
    const l = load(hours, { a: Array(24).fill(10), b: Array(24).fill(50) });
    const [top, ...rest] = bottlenecks([{ day: 317, load: l, dayOff: false }], factors(), [17], 185, new Map([[17, stops]]));
    expect(rest).toHaveLength(0);
    expect(top).toMatchObject({ route: 17, from: 8, to: 9, peak: 230, headway: 6, need: 4, stop: 'ВДНХ' });
  });
});

describe('выпуск', () => {
  it('считает вагоны как оборот, делённый на интервал, с округлением вверх', () => {
    // 34 км туда и обратно на 17 км/ч - 120 минут, плюс по 5 минут на конечных - 130 минут
    const f = fleet(34_000, 17, 5, 6);
    expect(f.cycle).toBeCloseTo(130);
    expect(f.vehicles).toBe(22);
    expect(f.tripsPerHour).toBe(10);
  });

  it('складывает доли остановок участка в порядке хода', () => {
    const stops: RouteStop[] = [1, 2, 3].map((seq) => ({ direction: 1, seq, stopId: `s${seq}`, name: '', lat: 0, lon: 0, share: 0.1 * seq }));
    expect(segmentShare(stops, 1, 's3', 's2')).toBeCloseTo(0.5);
    expect(segmentShare(stops, 0, 's1', 's2')).toBe(0);
  });
});

describe('сводка смены', () => {
  it('пишет погоду диапазоном и часами осадков', () => {
    const rain = Array(24).fill(0);
    rain[9] = 0.5;
    rain[13] = 1.2;
    const w = { temp: Array.from({ length: 24 }, (_, h) => h / 4 - 2), rain, snow: Array(24).fill(0) };
    expect(weatherLine(w)).toBe('-2°…+4°, дождь 9-14 ч, 1,7 мм');
    expect(weatherLine({ ...w, rain: Array(24).fill(0) })).toBe('-2°…+4°, без осадков');
  });

  it('берёт события дня с учётом выходных и разовых изменений', () => {
    expect(dayEvents(factors(), '2025-11-08', true)).toEqual(['50, 7: закрыт']);
    expect(dayEvents(factors(), '2025-11-07', false)).toEqual([]);
    expect(dayEvents(factors(), '2025-11-12', false)).toEqual(['7, 50: запуск Т1']);
  });

  it('собирает текст для чата с пиком, тесными часами и сравнением с прошлой неделей', () => {
    const hours = flat(1000);
    hours[8] = 4600;
    const brief = buildBrief({ day: 317, calendar: undefined, load: load(hours), weekAgo: load(flat(1000)),
      factors: factors(), weather: null, routes: [17], limit: 185, scenarioEvents: [] });
    expect(brief.peakHour).toBe(8);
    expect(brief.vsWeek).toBeCloseTo((100 * 3600) / 19000);
    expect(brief.text).toContain('№17, 8-9 ч: до 230 на рейс, интервал 6 → 4 мин');
    expect(brief.text.startsWith('Сводка смены «Час пик»: 14 ноября 2025, пятница')).toBe(true);
  });
});
