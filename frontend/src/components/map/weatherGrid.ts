import type { GeoJSONSource, Map as MapLibre } from 'maplibre-gl';
import { FONT } from './style';

// Погода по районам: сетка 3 × 3 точек над Москвой, почасовой архив Open-Meteo за выбранные сутки.
// Запрос идёт из браузера напрямую (Open-Meteo отдаёт CORS), результат кэшируется по дате.
// Нет сети - слой просто пустой, в шапке остаётся погода центра из данных сервиса.

const LATS = [55.61, 55.75, 55.89];
const LONS = [37.42, 37.62, 37.82];
const cache = new Map<string, Promise<GeoJSON.FeatureCollection>>();

interface OpenMeteoPoint {
  latitude: number;
  longitude: number;
  hourly: { temperature_2m: (number | null)[]; precipitation: (number | null)[]; snowfall: (number | null)[] };
}

function label(t: number | null | undefined, p: number | null | undefined, s: number | null | undefined): string {
  if (t == null) return '';
  const r = Math.round(t);
  const temp = `${r > 0 ? '+' : ''}${r}°`;
  if ((s ?? 0) > 0.05) return `${temp} снег`;
  if ((p ?? 0) > 0.1) return `${temp} дождь`;
  return temp;
}

async function fetchGrid(date: string): Promise<GeoJSON.FeatureCollection> {
  const points = LATS.flatMap((lat) => LONS.map((lon) => [lat, lon] as const));
  const params = new URLSearchParams({
    latitude: points.map((p) => p[0]).join(','),
    longitude: points.map((p) => p[1]).join(','),
    start_date: date,
    end_date: date,
    hourly: 'temperature_2m,precipitation,snowfall',
    timezone: 'Europe/Moscow',
  });
  const res = await fetch(`https://archive-api.open-meteo.com/v1/archive?${params}`);
  if (!res.ok) throw new Error(`Open-Meteo: ${res.status}`);
  const body = (await res.json()) as OpenMeteoPoint[] | OpenMeteoPoint;
  const list = Array.isArray(body) ? body : [body];
  return {
    type: 'FeatureCollection',
    features: list.map((pt, i) => {
      const props: Record<string, string> = {};
      for (let h = 0; h < 24; h++) {
        props[`w${h}`] = label(pt.hourly.temperature_2m[h], pt.hourly.precipitation[h], pt.hourly.snowfall[h]);
      }
      const [lat, lon] = points[i] ?? [pt.latitude, pt.longitude];
      return { type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] }, properties: props };
    }),
  };
}

export function addWeatherLayer(map: MapLibre): void {
  map.addSource('weather-grid', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({ id: 'weather-grid', type: 'symbol', source: 'weather-grid', maxzoom: 13.5, layout: {
    'text-field': ['get', 'w0'], 'text-font': FONT, 'text-size': 12.5, 'text-allow-overlap': true,
    'text-ignore-placement': true },
  paint: { 'text-color': '#ffe3b0', 'text-halo-color': 'rgba(4,7,12,0.95)', 'text-halo-width': 1.6,
    'text-opacity': ['interpolate', ['linear'], ['zoom'], 12.5, 0.9, 13.5, 0] } });
}

export function setWeatherHour(map: MapLibre, hour: number): void {
  if (map.getLayer('weather-grid')) map.setLayoutProperty('weather-grid', 'text-field', ['get', `w${hour}`]);
}

export function loadWeatherDay(map: MapLibre, date: string): void {
  if (!cache.has(date)) cache.set(date, fetchGrid(date));
  cache.get(date)!
    .then((data) => (map.getSource('weather-grid') as GeoJSONSource | undefined)?.setData(data))
    .catch(() => cache.delete(date));
}
