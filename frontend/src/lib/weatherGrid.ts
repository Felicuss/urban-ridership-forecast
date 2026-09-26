// Погода по районам Москвы на любую дату шкалы: сетка 5 × 5 точек, почасово, Open-Meteo.
// Прошлые даты - архив (ERA5), последние 90 дней и ближайшие 16 - прогнозный API. Запрос идёт из
// браузера напрямую: Open-Meteo отдаёт CORS и не требует ключа.

export const GRID_LATS = [55.56, 55.65, 55.74, 55.83, 55.92];
export const GRID_LONS = [37.36, 37.485, 37.61, 37.735, 37.86];
export const CENTER_INDEX = 12;
/** Open-Meteo отдаёт снег в сантиметрах: 7 см снега - 10 мм воды. */
export const SNOW_CM_TO_MM = 10 / 7;

/** Область сетки с запасом в полшага за крайними узлами: за ней данных о погоде нет. */
export const GRID_BOUNDS = {
  west: 37.36 - 0.0625,
  east: 37.86 + 0.0625,
  south: 55.56 - 0.045,
  north: 55.92 + 0.045,
};
/** Доля области у края, на которой осадки плавно гаснут. */
const FADE = 0.12;

/** 1 внутри сетки и плавно до 0 к её краю: заливка осадков и частицы обрываются на одной границе. */
export function edgeFade(lon: number, lat: number): number {
  const u = (lon - GRID_BOUNDS.west) / (GRID_BOUNDS.east - GRID_BOUNDS.west);
  const v = (lat - GRID_BOUNDS.south) / (GRID_BOUNDS.north - GRID_BOUNDS.south);
  const d = Math.min(u, 1 - u, v, 1 - v);
  if (d <= 0) return 0;
  const t = Math.min(d / FADE, 1);
  return t * t * (3 - 2 * t);
}

export interface GridPoint {
  lat: number;
  lon: number;
  temp: (number | null)[];
  rain: (number | null)[];
  snow: (number | null)[];
  code: (number | null)[];
  wind: (number | null)[];
  windDir: (number | null)[];
}

interface OpenMeteoPoint {
  hourly: Record<string, (number | null)[]>;
}

const HOURLY = 'temperature_2m,rain,showers,snowfall,weather_code,wind_speed_10m,wind_direction_10m';
const DAY_MS = 86_400_000;

function endpoint(date: string): string {
  const age = (Date.now() - Date.parse(`${date}T00:00:00Z`)) / DAY_MS;
  if (age < -15) throw new Error('прогноз погоды дальше 16 дней не выпускается');
  return age > 85 ? 'https://archive-api.open-meteo.com/v1/archive' : 'https://api.open-meteo.com/v1/forecast';
}

export async function fetchWeatherGrid(date: string, signal?: AbortSignal): Promise<GridPoint[]> {
  const points = GRID_LATS.flatMap((lat) => GRID_LONS.map((lon) => [lat, lon] as const));
  const params = new URLSearchParams({
    latitude: points.map((p) => p[0]).join(','),
    longitude: points.map((p) => p[1]).join(','),
    start_date: date,
    end_date: date,
    hourly: HOURLY,
    timezone: 'Europe/Moscow',
  });
  const res = await fetch(`${endpoint(date)}?${params}`, { signal });
  if (!res.ok) throw new Error(`Open-Meteo: ${res.status}`);
  const body = (await res.json()) as OpenMeteoPoint[] | OpenMeteoPoint;
  const list = Array.isArray(body) ? body : [body];
  return list.map((pt, i) => {
    const h = pt.hourly;
    const rain = (h.rain ?? []).map((v, j) => (v ?? 0) + (h.showers?.[j] ?? 0));
    return { lat: points[i]![0], lon: points[i]![1], temp: h.temperature_2m ?? [], rain, snow: h.snowfall ?? [],
      code: h.weather_code ?? [], wind: h.wind_speed_10m ?? [], windDir: h.wind_direction_10m ?? [] };
  });
}

/** Осадки в точке по обратным расстояниям до узлов сетки: дождь в мм/ч и снег в см/ч. */
export function precipAt(grid: GridPoint[], lon: number, lat: number, hour: number): { rain: number; snow: number } {
  let wSum = 0;
  let rain = 0;
  let snow = 0;
  for (const p of grid) {
    const dx = (p.lon - lon) * 0.56;
    const dy = p.lat - lat;
    const w = 1 / (dx * dx + dy * dy + 1e-5);
    wSum += w;
    rain += w * (p.rain[hour] ?? 0);
    snow += w * (p.snow[hour] ?? 0);
  }
  return { rain: rain / wSum, snow: snow / wSum };
}
