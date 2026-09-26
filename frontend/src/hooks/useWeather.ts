import { useQuery } from '@tanstack/react-query';
import { useDebounced } from '../api/queries';
import { CENTER_INDEX, SNOW_CM_TO_MM, fetchWeatherGrid, type GridPoint } from '../lib/weatherGrid';
import { skyOf, type HourWeather } from '../lib/weather';

/** Почасовая погода сетки 5 × 5 за дату. Нет сети или даты в прогнозе - слой погоды просто пустой. */
export function useWeatherGrid(date: string, enabled = true) {
  // при листании дней стрелками запрос уходит за день, на котором остановились: иначе Open-Meteo отвечает 429
  const settled = useDebounced(date, 400);
  return useQuery({
    queryKey: ['weather-grid', settled],
    enabled,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    retry: 0,
    queryFn: ({ signal }) => fetchWeatherGrid(settled, signal),
  });
}

/** Погода центра Москвы в час: для шапки и вкладки факторов. */
export function centerWeather(grid: GridPoint[] | undefined, hour: number): HourWeather | null {
  const c = grid?.[CENTER_INDEX];
  if (!c) return null;
  return { temp: c.temp[hour] ?? null, precip: (c.rain[hour] ?? 0) + (c.snow[hour] ?? 0) * SNOW_CM_TO_MM, snow: c.snow[hour] ?? 0,
    wind: c.wind[hour] ?? null, sky: skyOf(c.code[hour]) };
}
