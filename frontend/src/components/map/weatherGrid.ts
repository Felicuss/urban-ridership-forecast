import type { GeoJSONSource, Map as MapLibre } from 'maplibre-gl';
import type { GridPoint } from '../../lib/weatherGrid';
import { FONT } from './style';

// Погода на карте там, где она есть: радар дождя и снега по узлам сетки 5 × 5 (Open-Meteo) и температура
// по районам. Значения по 24 часам лежат в свойствах точек, смена часа - только новое выражение стиля.

const LABEL_ROWS = new Set([0, 2, 4]);

function label(t: number | null | undefined): string {
  if (t == null) return '';
  const r = Math.round(t);
  return `${r > 0 ? '+' : ''}${r}°`;
}

export function addWeatherLayer(map: MapLibre): void {
  map.addSource('weather-grid', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  const radius = ['interpolate', ['exponential', 2], ['zoom'], 9, 34, 11, 130, 13, 520] as const;
  map.addLayer({ id: 'rain-radar', type: 'heatmap', source: 'weather-grid', maxzoom: 15, paint: {
    'heatmap-weight': 0, 'heatmap-radius': radius as never, 'heatmap-intensity': 0.9,
    'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(90,140,220,0)', 0.25,
      'rgba(110,160,230,0.16)', 0.6, 'rgba(120,170,240,0.28)', 1, 'rgba(150,190,255,0.4)'],
    'heatmap-opacity': 0.9 } });
  map.addLayer({ id: 'snow-radar', type: 'heatmap', source: 'weather-grid', maxzoom: 15, paint: {
    'heatmap-weight': 0, 'heatmap-radius': radius as never, 'heatmap-intensity': 0.9,
    'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(230,236,250,0)', 0.25,
      'rgba(230,236,250,0.12)', 0.6, 'rgba(235,240,252,0.22)', 1, 'rgba(245,248,255,0.34)'],
    'heatmap-opacity': 0.9 } });
  map.addLayer({ id: 'weather-temp', type: 'symbol', source: 'weather-grid', maxzoom: 13.5,
    filter: ['==', ['get', 'label'], true], layout: {
      'text-field': ['get', 't0'], 'text-font': FONT, 'text-size': 12, 'text-allow-overlap': true,
      'text-ignore-placement': true },
    paint: { 'text-color': '#e7dcc4', 'text-halo-color': 'rgba(10,10,12,0.9)', 'text-halo-width': 1.5,
      'text-opacity': ['interpolate', ['linear'], ['zoom'], 12.5, 0.85, 13.5, 0] } });
}

export function setWeatherData(map: MapLibre, grid: GridPoint[] | undefined): void {
  const features = (grid ?? []).map((p, i) => {
    const props: Record<string, unknown> = { label: LABEL_ROWS.has(Math.floor(i / 5)) && LABEL_ROWS.has(i % 5) };
    for (let h = 0; h < 24; h++) {
      props[`t${h}`] = label(p.temp[h]);
      props[`r${h}`] = p.rain[h] ?? 0;
      props[`s${h}`] = p.snow[h] ?? 0;
    }
    return { type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] }, properties: props };
  });
  (map.getSource('weather-grid') as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features });
}

export function setWeatherHour(map: MapLibre, hour: number): void {
  if (!map.getLayer('weather-temp')) return;
  map.setLayoutProperty('weather-temp', 'text-field', ['get', `t${hour}`]);
  // 2 мм/ч дождя и 1 см/ч снега - полная насыщенность радара
  map.setPaintProperty('rain-radar', 'heatmap-weight', ['min', ['/', ['coalesce', ['get', `r${hour}`], 0], 2], 1]);
  map.setPaintProperty('snow-radar', 'heatmap-weight', ['min', ['/', ['coalesce', ['get', `s${hour}`], 0], 1], 1]);
}
