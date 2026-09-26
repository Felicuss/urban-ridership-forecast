import type { GeoJSONSource, ImageSource, Map as MapLibre } from 'maplibre-gl';
import { GRID_BOUNDS, edgeFade, precipAt, SNOW_CM_TO_MM, type GridPoint } from '../../lib/weatherGrid';
import { before } from './layers';
import { FONT } from './style';

// Погода на карте там, где она есть. Осадки - одна гладкая заливка поверх города: сетка 5 × 5 Open-Meteo
// разворачивается в картинку 48 × 48, значения между узлами по обратным расстояниям. Картинка привязана к
// координатам, поэтому едет и масштабируется вместе с картой. Край сетки обведён пунктиром с подписью: за
// ним данных нет. Где осадки кончаются внутри сетки, проходит своя линия - граница дождя или снега.
// Температура подписана по районам.

const LABEL_ROWS = new Set([0, 2, 4]);
const SIZE = 48;
/** 1,5 мм воды в час - полная насыщенность заливки. */
const FULL_MM = 1.5;
/** Снег светлый и на тёмной карте заметнее дождя, поэтому его заливка прозрачнее. */
const RAIN_ALPHA = 0.3;
const SNOW_ALPHA = 0.14;
const RAIN: [number, number, number] = [110, 160, 235];
const SNOW: [number, number, number] = [236, 241, 255];
const CORNERS: [[number, number], [number, number], [number, number], [number, number]] = [
  [GRID_BOUNDS.west, GRID_BOUNDS.north], [GRID_BOUNDS.east, GRID_BOUNDS.north],
  [GRID_BOUNDS.east, GRID_BOUNDS.south], [GRID_BOUNDS.west, GRID_BOUNDS.south],
];

/** Осадки слабее 0,1 мм в час не считаются: по этой линии проходит граница дождя или снега. */
const WET_MM = 0.1;
const BORDER: GeoJSON.Feature = { type: 'Feature', properties: { label: 'край данных о погоде' },
  geometry: { type: 'LineString', coordinates: [...CORNERS, CORNERS[0]] } };

let current: GridPoint[] = [];
const edges = new Map<number, GeoJSON.FeatureCollection>();
const frames = new Map<number, Promise<ImageBitmap>>();

function label(t: number | null | undefined): string {
  if (t == null) return '';
  const r = Math.round(t);
  return `${r > 0 ? '+' : ''}${r}°`;
}

export function addWeatherLayer(map: MapLibre): void {
  map.addSource('weather-grid', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addSource('precip', { type: 'image', coordinates: CORNERS });
  // под домами, линиями маршрутов и подписями: заливка не глушит город, а лежит на нём
  map.addLayer({ id: 'precip-radar', type: 'raster', source: 'precip', paint: {
    'raster-opacity': 1, 'raster-resampling': 'linear', 'raster-fade-duration': 0 } },
  map.getLayer('buildings-3d') ? 'buildings-3d' : before(map));
  map.addSource('weather-border', { type: 'geojson', data: { type: 'FeatureCollection', features: [BORDER] } });
  map.addLayer({ id: 'weather-border', type: 'line', source: 'weather-border', paint: {
    'line-color': 'rgba(200,215,240,0.55)', 'line-width': 1.4, 'line-dasharray': [3, 3] } });
  map.addLayer({ id: 'weather-border-label', type: 'symbol', source: 'weather-border', layout: {
    'symbol-placement': 'line', 'symbol-spacing': 420, 'text-field': ['get', 'label'], 'text-font': FONT,
    'text-size': 11, 'text-offset': [0, -0.8], 'text-keep-upright': true },
  paint: { 'text-color': 'rgba(210,222,245,0.8)', 'text-halo-color': 'rgba(10,10,12,0.9)', 'text-halo-width': 1.2 } });
  map.addSource('precip-edge', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({ id: 'precip-edge', type: 'line', source: 'precip-edge', paint: {
    'line-color': ['get', 'color'], 'line-width': 1.6, 'line-opacity': 0.85 } });
  map.addLayer({ id: 'weather-temp', type: 'symbol', source: 'weather-grid', maxzoom: 13.5,
    filter: ['==', ['get', 'label'], true], layout: {
      'text-field': ['get', 't0'], 'text-font': FONT, 'text-size': 12, 'text-allow-overlap': true,
      'text-ignore-placement': true },
    paint: { 'text-color': '#e7dcc4', 'text-halo-color': 'rgba(10,10,12,0.9)', 'text-halo-width': 1.5,
      'text-opacity': ['interpolate', ['linear'], ['zoom'], 12.5, 0.85, 13.5, 0] } });
}

export function setWeatherData(map: MapLibre, grid: GridPoint[] | undefined): void {
  current = grid ?? [];
  frames.clear();
  edges.clear();
  const features = current.map((p, i) => {
    const props: Record<string, unknown> = { label: LABEL_ROWS.has(Math.floor(i / 5)) && LABEL_ROWS.has(i % 5) };
    for (let h = 0; h < 24; h++) props[`t${h}`] = label(p.temp[h]);
    return { type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] }, properties: props };
  });
  (map.getSource('weather-grid') as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features });
}

export function setWeatherHour(map: MapLibre, hour: number): void {
  if (!map.getLayer('weather-temp')) return;
  map.setLayoutProperty('weather-temp', 'text-field', ['get', `t${hour}`]);
  const grid = current;
  let frame = frames.get(hour);
  if (!frame) {
    frame = createImageBitmap(precipCanvas(grid, hour));
    frames.set(hour, frame);
  }
  let edge = edges.get(hour);
  if (!edge) {
    edge = precipEdge(grid, hour);
    edges.set(hour, edge);
  }
  (map.getSource('precip-edge') as GeoJSONSource | undefined)?.setData(edge);
  void frame.then((image) => {
    // пока картинка готовилась, могли прийти другая дата или час: тогда она уже не нужна
    if (grid !== current) return;
    (map.getSource('precip') as ImageSource | undefined)?.updateImage({ image, coordinates: CORNERS });
  });
}

/** Картинка осадков часа: цвет от дождя к снегу, прозрачность по силе осадков и по краю сетки. */
function precipCanvas(grid: GridPoint[], hour: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext('2d');
  if (!ctx || grid.length === 0) return canvas;
  const img = ctx.createImageData(SIZE, SIZE);
  const { west, east, south, north } = GRID_BOUNDS;
  for (let y = 0; y < SIZE; y++) {
    const lat = north - ((y + 0.5) / SIZE) * (north - south);
    for (let x = 0; x < SIZE; x++) {
      const lon = west + ((x + 0.5) / SIZE) * (east - west);
      const { rain, snow } = precipAt(grid, lon, lat, hour);
      const snowMm = snow * SNOW_CM_TO_MM;
      const total = rain + snowMm;
      const k = total > 0 ? snowMm / total : 0;
      const i = (y * SIZE + x) * 4;
      img.data[i] = RAIN[0] + (SNOW[0] - RAIN[0]) * k;
      img.data[i + 1] = RAIN[1] + (SNOW[1] - RAIN[1]) * k;
      img.data[i + 2] = RAIN[2] + (SNOW[2] - RAIN[2]) * k;
      const alpha = RAIN_ALPHA + (SNOW_ALPHA - RAIN_ALPHA) * k;
      img.data[i + 3] = 255 * alpha * Math.min(total / FULL_MM, 1) * edgeFade(lon, lat);
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

/** Осадки воды в мм в час в узлах мелкой сетки над областью данных: строки с севера на юг. */
function wetField(grid: GridPoint[], hour: number): { values: number[][]; snowy: boolean } {
  const { west, east, south, north } = GRID_BOUNDS;
  let rainSum = 0;
  let snowSum = 0;
  const values = Array.from({ length: SIZE + 1 }, (_, y) => {
    const lat = north - (y / SIZE) * (north - south);
    return Array.from({ length: SIZE + 1 }, (_, x) => {
      const { rain, snow } = precipAt(grid, west + (x / SIZE) * (east - west), lat, hour);
      rainSum += rain;
      snowSum += snow * SNOW_CM_TO_MM;
      return rain + snow * SNOW_CM_TO_MM;
    });
  });
  return { values, snowy: snowSum >= rainSum };
}

/**
 * Граница осадков внутри сетки: изолиния WET_MM методом marching squares. Если осадки идут по всей сетке или
 * их нет нигде, линии нет: тогда граница совпадает с краем данных.
 */
function precipEdge(grid: GridPoint[], hour: number): GeoJSON.FeatureCollection {
  if (grid.length === 0) return { type: 'FeatureCollection', features: [] };
  const { values, snowy } = wetField(grid, hour);
  const { west, east, south, north } = GRID_BOUNDS;
  const lon = (x: number) => west + (x / SIZE) * (east - west);
  const lat = (y: number) => north - (y / SIZE) * (north - south);
  const segments: [number, number][][] = [];
  const cut = (a: number, b: number) => (WET_MM - a) / (b - a || 1e-9);
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      const tl = values[y]![x]!;
      const tr = values[y]![x + 1]!;
      const br = values[y + 1]![x + 1]!;
      const bl = values[y + 1]![x]!;
      const points: [number, number][] = [];
      if ((tl >= WET_MM) !== (tr >= WET_MM)) points.push([lon(x + cut(tl, tr)), lat(y)]);
      if ((tr >= WET_MM) !== (br >= WET_MM)) points.push([lon(x + 1), lat(y + cut(tr, br))]);
      if ((bl >= WET_MM) !== (br >= WET_MM)) points.push([lon(x + cut(bl, br)), lat(y + 1)]);
      if ((tl >= WET_MM) !== (bl >= WET_MM)) points.push([lon(x), lat(y + cut(tl, bl))]);
      if (points.length === 2) segments.push(points);
      if (points.length === 4) segments.push([points[0]!, points[1]!], [points[2]!, points[3]!]);
    }
  }
  const color = snowy ? 'rgba(236,241,255,0.9)' : 'rgba(130,175,245,0.95)';
  return { type: 'FeatureCollection', features: segments.length === 0 ? [] : [{ type: 'Feature', properties: { color },
    geometry: { type: 'MultiLineString', coordinates: segments } }] };
}
