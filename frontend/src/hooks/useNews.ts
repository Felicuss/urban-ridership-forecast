import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import type { ScenarioEvent } from '../api/types';

// Сбои из оперативных новостей Дептранса (t.me/DtOperativno): пара «задерживаются трамваи» и «движение
// восстановлено», превращённая сервисом в события сценария по часам. Архив 2025 года лежит в артефактах,
// свежие сообщения сервис дочитывает из канала сам.

export interface NewsIncident {
  id: string;
  routes: number[];
  start: string;
  /** Пусто, пока движение не восстановлено. */
  end: string | null;
  minutes: number | null;
  cause: string;
  causeLabel: string;
  location: string;
  sourceUrl: string;
  recoveryUrl: string | null;
  /** Сбой попал в прогнозный горизонт и уже учтён в прогнозе v25. */
  inForecast: boolean;
  /** Откуда сбой: архив, проверенный вручную, или живая лента канала. */
  origin: 'archive' | 'live';
  events: ScenarioEvent[];
}

export interface NewsFeed {
  incidents: NewsIncident[];
  /** Доля посадок, которая теряется за час полной остановки: оценка по сбоям 2025 года. */
  alpha: number;
  /** Откуда оценка: скрипт, число сбоев и часов. */
  alphaSource: string;
  liveCheckedAt: string | null;
  liveError: string | null;
}

export function useNewsFeed() {
  return useQuery({
    queryKey: ['news'],
    staleTime: 5 * 60_000,
    queryFn: ({ signal }) => getJson<NewsFeed>('/api/v1/news', signal),
  });
}

/** Только список сбоев: для сводки смены и табло. */
export function useNews() {
  const feed = useNewsFeed();
  return { ...feed, data: feed.data?.incidents };
}

function clockOf(iso: string): string {
  return iso.slice(11, 16);
}

/** «сбой №12, 10:28-11:09 (40 мин): технические причины». */
export function newsLine(n: NewsIncident): string {
  const span = n.end ? `${clockOf(n.start)}-${clockOf(n.end)} (${Math.round(n.minutes ?? 0)} мин)` : `с ${clockOf(n.start)}, ещё идёт`;
  return `сбой ${n.routes.map((r) => `№${r}`).join(', ')}, ${span}: ${n.causeLabel}`;
}
