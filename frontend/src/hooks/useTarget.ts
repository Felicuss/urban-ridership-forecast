import { useFactors, useStops, type SeriesQuery } from '../api/queries';
import type { Factors, Level } from '../api/types';
import { routeColor } from '../lib/routes';
import { useStore, type Segment } from '../state/store';

export interface Target {
  level: Level;
  id?: string;
  name: string;
  subtitle: string;
  color: string;
  route: number | null;
  segment?: Segment;
}

/** Параметры запроса прогноза для цели: для участка ещё направление и крайние остановки. */
export function targetQuery(t: Target): Pick<SeriesQuery, 'level' | 'id' | 'direction' | 'fromStop' | 'toStop'> {
  const seg = t.segment;
  return seg ? { level: t.level, id: t.id, direction: seg.direction, fromStop: seg.from, toStop: seg.to }
    : { level: t.level, id: t.id };
}

/** Конечные маршрута из расписания: «Северное Медведково - Усадьба Останкино». */
export function routeTitle(factors: Factors | undefined, route: number): string {
  return factors?.schedule.routes[String(route)]?.title ?? '';
}

/** Что сейчас прогнозируем: остановка или участок, если выбраны, иначе маршрут, иначе вся сеть. */
export function useTarget(): Target {
  const route = useStore((s) => s.route);
  const stop = useStore((s) => s.stop);
  const segment = useStore((s) => s.segment);
  const factors = useFactors().data;
  const stops = useStops().data;
  if (segment && route != null) {
    const name = (id: string) => stops?.find((x) => x.id === id)?.name ?? id;
    return { level: 'segment', id: String(route), name: `Участок маршрута ${route}`,
      subtitle: `${name(segment.from)} - ${name(segment.to)}`, color: routeColor(route), route, segment };
  }
  if (stop) {
    const s = stops?.find((x) => x.id === stop);
    return { level: 'stop', id: stop, name: s?.name ?? stop, subtitle: `Остановка, маршруты ${s?.routes.join(', ') ?? ''}`,
      color: routeColor(route ?? s?.routes[0]), route };
  }
  if (route != null) {
    return { level: 'route', id: String(route), name: `Маршрут ${route}`, subtitle: routeTitle(factors, route),
      color: routeColor(route), route };
  }
  return { level: 'network', name: 'Вся сеть', subtitle: '10 трамвайных маршрутов', color: '#e9eef5', route: null };
}
