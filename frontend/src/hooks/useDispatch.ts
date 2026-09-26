import { useQueries } from '@tanstack/react-query';
import { api, unwrap } from '../api/client';
import { networkLoadQuery, useCalendar, useFactors } from '../api/queries';
import type { NetworkLoad, RouteStop } from '../api/types';
import { useStore, type AlertRule } from '../state/store';
import { TIMELINE_DAYS, dayIndex, isoDate } from '../lib/time';
import { perTripDay, segmentShare, spansAbove, type HourSpan } from '../lib/dispatch';

// Данные для вкладки «Смена», табло и колокольчика: прогноз на несколько дней вперёд и остановки
// маршрутов. Запросы общие с картой через кэш TanStack Query, повторно не грузятся.

/** Кадры прогноза по умолчанию на count дней с дня start: для узких мест недели. */
export function useDaysLoad(start: number, count: number) {
  const days = Array.from({ length: count }, (_, i) => start + i).filter((d) => d >= 0 && d < TIMELINE_DAYS);
  const results = useQueries({ queries: days.map((d) => networkLoadQuery(isoDate(d))) });
  const calendar = useCalendar().data;
  const loaded = days.flatMap((day, i) => {
    const load = results[i]?.data;
    return load ? [{ day, load, dayOff: calendar?.[day]?.dayOff ?? false }] : [];
  });
  return { days: loaded, pending: loaded.length < days.length };
}

/** Остановки нескольких маршрутов: для главной остановки узкого места и долей участков. */
export function useManyRouteStops(routes: number[]): Map<number, RouteStop[]> {
  const unique = [...new Set(routes)];
  const results = useQueries({
    queries: unique.map((route) => ({
      queryKey: ['route-stops', route],
      staleTime: Infinity,
      gcTime: Infinity,
      queryFn: async () => unwrap(await api.GET('/api/v1/routes/{route}/stops', { params: { path: { route } } })) as RouteStop[],
    })),
  });
  return new Map(unique.flatMap((route, i) => (results[i]?.data ? [[route, results[i].data] as const] : [])));
}

export interface AlertState {
  rule: AlertRule;
  /** Посадок на рейс по часам на завтра: на весь маршрут в обе стороны или на участок в его сторону. */
  values: number[];
  spans: HourSpan[];
  max: number;
  maxHour: number;
}

/** День, на который проверяются подписки: следующий за выбранным. */
export function useTomorrow(): number {
  return useStore((s) => Math.min(dayIndex(s.minute) + 1, TIMELINE_DAYS - 1));
}

/** Проверка подписок на завтра: где поток на рейс выше порога. */
export function useAlerts(): { day: number; states: AlertState[]; pending: boolean } {
  const rules = useStore((s) => s.alerts);
  const day = useTomorrow();
  const { days } = useDaysLoad(day, 1);
  const factors = useFactors().data;
  const stops = useManyRouteStops(rules.filter((r) => r.segment).map((r) => r.route));
  const entry = days[0];
  if (!entry) return { day, states: [], pending: rules.length > 0 };
  return { day, pending: false, states: rules.map((rule) => evaluate(rule, entry.load, entry.dayOff, factors, stops)) };
}

function evaluate(rule: AlertRule, load: NetworkLoad, dayOff: boolean, factors: Parameters<typeof perTripDay>[0],
  stops: Map<number, RouteStop[]>): AlertState {
  const hours = load.routes.get(rule.route);
  const seg = rule.segment;
  const values = seg
    ? perTripDay(factors, rule.route, dayOff, hours, segmentShare(stops.get(rule.route), seg.direction, seg.from, seg.to), true)
    : perTripDay(factors, rule.route, dayOff, hours);
  const max = Math.max(...values, 0);
  return { rule, values, spans: spansAbove(values, rule.limit), max, maxHour: values.indexOf(max) };
}
