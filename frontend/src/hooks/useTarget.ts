import { useFactors, useStops } from '../api/queries';
import type { Factors, Level } from '../api/types';
import { routeColor } from '../lib/routes';
import { useStore } from '../state/store';

export interface Target {
  level: Level;
  id?: string;
  name: string;
  subtitle: string;
  color: string;
  route: number | null;
}

/** Конечные маршрута из расписания: «Северное Медведково - Усадьба Останкино». */
export function routeTitle(factors: Factors | undefined, route: number): string {
  return factors?.schedule.routes[String(route)]?.title ?? '';
}

/** Что сейчас прогнозируем: остановка, если выбрана, иначе маршрут, иначе вся сеть. */
export function useTarget(): Target {
  const route = useStore((s) => s.route);
  const stop = useStore((s) => s.stop);
  const factors = useFactors().data;
  const stops = useStops().data;
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
