import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api, getJson, unwrap, type Schemas } from './client';
import type {
  Coefficient, Factors, Granularity, Horizon, Level, Meta, NetworkGeoJson, NetworkLoad, Point, RouteInfo,
  RouteStop, Scenario, Series, Stop,
} from './types';
import { isDefaultScenario } from '../state/store';

const FOREVER = { staleTime: Infinity, gcTime: Infinity } as const;

/** Значение, которое меняется не чаще раза в delay мс: ползунки не шлют запрос на каждый пиксель. */
export function useDebounced<T>(value: T, delay = 180): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: async () => unwrap(await api.GET('/api/v1/meta')) as unknown as Meta,
    ...FOREVER,
  });
}

export function useCoefficients() {
  return useQuery({
    queryKey: ['coefficients'],
    queryFn: async () => unwrap(await api.GET('/api/v1/coefficients')) as Coefficient[],
    ...FOREVER,
  });
}

export function useRoutes() {
  return useQuery({
    queryKey: ['routes'],
    queryFn: async () => unwrap(await api.GET('/api/v1/routes')) as RouteInfo[],
    ...FOREVER,
  });
}

export function useStops() {
  return useQuery({
    queryKey: ['stops'],
    queryFn: async () => unwrap(await api.GET('/api/v1/stops')) as Stop[],
    ...FOREVER,
  });
}

export function useRouteStops(route: number | null) {
  return useQuery({
    queryKey: ['route-stops', route],
    enabled: route != null,
    queryFn: async () => unwrap(await api.GET('/api/v1/routes/{route}/stops', {
      params: { path: { route: route ?? 0 } },
    })) as RouteStop[],
    ...FOREVER,
  });
}

export function useNetwork() {
  return useQuery({
    queryKey: ['network'],
    queryFn: ({ signal }) => getJson<NetworkGeoJson>('/api/v1/network', signal),
    ...FOREVER,
  });
}

export function useFactors() {
  return useQuery({
    queryKey: ['factors'],
    queryFn: ({ signal }) => getJson<Factors>('/api/v1/factors', signal),
    ...FOREVER,
  });
}

function toLoad(r: Schemas['NetworkLoadResponse']): NetworkLoad {
  return {
    date: r.date ?? '',
    hours: r.hours ?? [],
    routes: new Map((r.routes ?? []).map((s) => [Number(s.id), s.values ?? []])),
    stops: new Map((r.stops ?? []).map((s) => [s.id ?? '', s.values ?? []])),
  };
}

/** Запрос кадров прогноза по умолчанию на дату: общий для экрана и предзагрузки соседних суток. */
export function networkLoadQuery(date: string) {
  return {
    queryKey: ['network-load', date, null] as const,
    staleTime: Infinity,
    queryFn: async () => toLoad(unwrap(await api.GET('/api/v1/network/load', { params: { query: { date } } }))),
  };
}

/** Кадры тепловой карты на сутки: посадки маршрутов и остановок по 24 часам. */
export function useNetworkLoad(date: string, scenario: Scenario) {
  const s = useDebounced(scenario);
  const custom = !isDefaultScenario(s);
  const base = networkLoadQuery(date);
  return useQuery({
    queryKey: custom ? ['network-load', date, s] : base.queryKey,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    queryFn: custom
      ? async () => toLoad(unwrap(await api.POST('/api/v1/network/load',
        { body: { date, coefficients: s.coefficients, events: s.events } })))
      : base.queryFn,
  });
}

export interface SeriesQuery {
  level: Level;
  id?: string;
  from?: string;
  to?: string;
  hours?: string;
  granularity?: Granularity;
  horizon?: Horizon;
}

function point(p: Schemas['ScenarioPointDto'] | Schemas['PointDto']): Point {
  const s = p as Schemas['ScenarioPointDto'];
  return {
    period: p.period ?? '', p50: p.p50 ?? 0, p10: p.p10 ?? 0, p90: p.p90 ?? 0,
    baseline: s.baseline, delta: s.delta, deltaPct: s.deltaPct ?? null,
  };
}

function toSeries(r: Schemas['ForecastResponse'] | Schemas['ScenarioResponse'], scenario: boolean): Series {
  const t = r.target ?? {};
  return {
    target: { level: t.level ?? '', id: t.id ?? '', name: t.name ?? '', estimate: t.estimate ?? false },
    granularity: (r.granularity ?? 'hour') as Granularity,
    from: r.from ?? '',
    to: r.to ?? '',
    points: (r.points ?? []).map(point),
    total: point(r.total ?? {}),
    notes: r.notes ?? [],
    scenario,
  };
}

/** Ряд прогноза. При изменённых ползунках - пересчёт сценария с базой и разницей в каждой точке. */
export function useSeries(q: SeriesQuery | null, scenario: Scenario) {
  const s = useDebounced(scenario);
  const custom = !isDefaultScenario(s);
  return useQuery({
    queryKey: ['series', q, custom ? s : null],
    enabled: q != null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    queryFn: async ({ signal }) => {
      const query = q as SeriesQuery;
      if (custom) {
        const body = { query, coefficients: s.coefficients, events: s.events };
        return toSeries(unwrap(await api.POST('/api/v1/forecast/scenario', { body, signal })), true);
      }
      return toSeries(unwrap(await api.GET('/api/v1/forecast', { params: { query }, signal })), false);
    },
  });
}

/** Скачать выгрузку: GET для прогноза по умолчанию, POST со сценарием. Имя файла берём из заголовка. */
export async function download(format: 'csv' | 'xlsx', q: SeriesQuery & { ids?: string[] }, scenario: Scenario) {
  const custom = !isDefaultScenario(scenario);
  const params = new URLSearchParams({ format, level: q.level });
  if (q.ids?.length) params.set('ids', q.ids.join(','));
  for (const key of ['from', 'to', 'hours', 'granularity', 'horizon'] as const) {
    const v = q[key];
    if (v) params.set(key, v);
  }
  const res = custom
    ? await fetch('/api/v1/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...Object.fromEntries(params), ids: q.ids, ...scenario }),
    })
    : await fetch(`/api/v1/export?${params}`);
  if (!res.ok) throw new Error(`выгрузка не удалась: ${res.status}`);
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const match = /filename\*=UTF-8''([^;]+)/.exec(disposition);
  const name = match ? decodeURIComponent(match[1] ?? '') : `прогноз.${format}`;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
