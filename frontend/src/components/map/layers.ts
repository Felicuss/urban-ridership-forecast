import type {
  ExpressionSpecification, FilterSpecification, GeoJSONSource, Map as MapLibre,
} from 'maplibre-gl';
import type { NetworkGeoJson, NetworkLoad } from '../../api/types';
import type { Flags } from '../../state/store';
import { ROUTE_COLORS, routeColor } from '../../lib/routes';
import { FONT } from './style';

// Слои сети. Посадки по 24 часам лежат в свойствах объектов (h0..h23 у остановок, l0..l23 у линий),
// поэтому смена часа - это только новое выражение стиля, без перезаливки данных в видеокарту.

type Feature = GeoJSON.Feature<GeoJSON.Geometry, Record<string, unknown>>;
type Collection = GeoJSON.FeatureCollection<GeoJSON.Geometry, Record<string, unknown>>;

const HEAT_RAMP: ExpressionSpecification = ['interpolate', ['linear'], ['heatmap-density'],
  0, 'rgba(10,20,40,0)', 0.12, 'rgba(30,58,138,0.55)', 0.3, '#3a95ff', 0.5, '#3ddc97', 0.68, '#ffd166',
  0.84, '#ff7a45', 1, '#ef4136'];

const BEFORE_LABELS = 'highway_name_other';

export interface Scale {
  stop: number;
  route: number;
}

export function emptyCollection(): Collection {
  return { type: 'FeatureCollection', features: [] };
}

function before(map: MapLibre): string | undefined {
  return map.getLayer(BEFORE_LABELS) ? BEFORE_LABELS : undefined;
}

export function pathFeatures(network: NetworkGeoJson): Feature[] {
  return network.features
    .filter((f) => f.properties.kind === 'path')
    .map((f) => ({ type: 'Feature', geometry: f.geometry as GeoJSON.Geometry,
      properties: { route: f.properties.route, direction: f.properties.direction,
        color: routeColor(f.properties.route) } }));
}

export function stopFeatures(network: NetworkGeoJson): Feature[] {
  return network.features
    .filter((f) => f.properties.kind === 'stop')
    .map((f) => ({ type: 'Feature', id: f.properties.stop_id, geometry: f.geometry as GeoJSON.Geometry,
      // массивы в свойствах GeoJSON карта превращает в строки: храним « 5 50 » и ищем « 5 », чтобы 5 не нашлось в 50
      properties: { id: f.properties.stop_id, name: f.properties.name, routes: ` ${(f.properties.routes ?? []).join(' ')} ` } }));
}

/** Посадки суток в свойства объектов; масштаб растёт только вверх, чтобы цвета не прыгали между днями. */
export function withLoad(paths: Feature[], stops: Feature[], load: NetworkLoad, scale: Scale) {
  const lines = paths.map((f) => {
    const values = load.routes.get(Number(f.properties.route)) ?? [];
    const props: Record<string, unknown> = { ...f.properties };
    values.forEach((v, i) => { props[`l${load.hours[i] ?? i}`] = v; scale.route = Math.max(scale.route, v); });
    return { ...f, properties: props };
  });
  const points = stops.map((f) => {
    const values = load.stops.get(String(f.properties.id)) ?? [];
    const props: Record<string, unknown> = { ...f.properties };
    values.forEach((v, i) => { props[`h${load.hours[i] ?? i}`] = v; scale.stop = Math.max(scale.stop, v); });
    return { ...f, properties: props };
  });
  return { lines, points };
}

export function addNetworkLayers(map: MapLibre, paths: Feature[], stops: Feature[]): void {
  map.addSource('paths', { type: 'geojson', data: { type: 'FeatureCollection', features: paths } });
  map.addSource('stops', { type: 'geojson', data: { type: 'FeatureCollection', features: stops }, promoteId: 'id' });
  map.addSource('trams', { type: 'geojson', data: emptyCollection() });
  map.addSource('ride', { type: 'geojson', data: emptyCollection() });
  const b = before(map);
  map.addLayer({ id: 'stops-heat', type: 'heatmap', source: 'stops', maxzoom: 16.5, paint: {
    'heatmap-weight': 0, 'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 9, 0.9, 14, 1.6],
    'heatmap-radius': ['interpolate', ['exponential', 1.6], ['zoom'], 9, 14, 12, 30, 15, 70],
    'heatmap-color': HEAT_RAMP, 'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 13, 0.9, 16, 0.35],
  } }, b);
  map.addLayer({ id: 'route-casing', type: 'line', source: 'paths', layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#04070c', 'line-width': 5, 'line-opacity': 0.8 } }, b);
  map.addLayer({ id: 'route-lines', type: 'line', source: 'paths', layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'color'], 'line-width': 2.5, 'line-opacity': 0.95 } }, b);
  map.addLayer({ id: 'stops-dot', type: 'circle', source: 'stops', minzoom: 11.2, paint: {
    'circle-radius': 3, 'circle-color': '#0b1220', 'circle-stroke-color': '#e9eef5', 'circle-stroke-width': 1.2,
    'circle-opacity': ['interpolate', ['linear'], ['zoom'], 11.2, 0, 12, 1],
    'circle-stroke-opacity': ['interpolate', ['linear'], ['zoom'], 11.2, 0, 12, 1],
  } });
  map.addLayer({ id: 'stop-selected', type: 'circle', source: 'stops', filter: ['==', ['get', 'id'], ''], paint: {
    'circle-radius': 11, 'circle-color': 'rgba(58,149,255,0.18)', 'circle-stroke-color': '#7cc0ff',
    'circle-stroke-width': 2 } });
  map.addLayer({ id: 'stops-label', type: 'symbol', source: 'stops', minzoom: 14.2, layout: {
    'text-field': ['get', 'name'], 'text-font': FONT, 'text-size': 11, 'text-offset': [0, 1.1],
    'text-anchor': 'top', 'text-max-width': 9 },
  paint: { 'text-color': '#c3cedc', 'text-halo-color': 'rgba(4,7,12,0.95)', 'text-halo-width': 1.4 } });
  map.addLayer({ id: 'trams', type: 'symbol', source: 'trams', layout: {
    'icon-image': ['concat', 'tram-', ['to-string', ['get', 'route']]], 'icon-rotate': ['get', 'bearing'],
    'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true,
    'icon-size': ['interpolate', ['linear'], ['zoom'], 10, 0.45, 13, 0.75, 16, 1.2] } });
  map.addLayer({ id: 'ride-glow', type: 'circle', source: 'ride', paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 12, 16, 30], 'circle-color': 'rgba(124,192,255,0.22)',
    'circle-blur': 0.6 } });
  map.addLayer({ id: 'ride', type: 'symbol', source: 'ride', layout: {
    'icon-image': ['concat', 'tram-', ['to-string', ['get', 'route']]], 'icon-rotate': ['get', 'bearing'],
    'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true,
    'icon-size': ['interpolate', ['linear'], ['zoom'], 10, 0.8, 16, 1.6] } });
}

export function setLoadData(map: MapLibre, lines: Feature[], points: Feature[]): void {
  (map.getSource('paths') as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features: lines });
  (map.getSource('stops') as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features: points });
}

/** Выражения для часа: вес тепловой карты, размер точки остановки, толщина линии маршрута. */
export function setHour(map: MapLibre, hour: number, scale: Scale): void {
  const stop: ExpressionSpecification = ['coalesce', ['get', `h${hour}`], 0];
  const line: ExpressionSpecification = ['coalesce', ['get', `l${hour}`], 0];
  const stopMax = Math.max(scale.stop, 1);
  const routeMax = Math.max(scale.route, 1);
  map.setPaintProperty('stops-heat', 'heatmap-weight', ['min', ['/', stop, stopMax * 0.55], 1]);
  map.setPaintProperty('stops-dot', 'circle-radius', ['interpolate', ['linear'], ['zoom'],
    11, ['+', 2, ['*', 6, ['sqrt', ['/', stop, stopMax]]]], 16, ['+', 4, ['*', 16, ['sqrt', ['/', stop, stopMax]]]]]);
  const width: ExpressionSpecification = ['+', 1.2, ['*', 7, ['sqrt', ['/', line, routeMax]]]];
  map.setPaintProperty('route-lines', 'line-width', ['interpolate', ['linear'], ['zoom'], 9, ['*', 0.6, width],
    14, ['*', 1.5, width]]);
  map.setPaintProperty('route-casing', 'line-width', ['interpolate', ['linear'], ['zoom'], 9,
    ['+', 2, ['*', 0.6, width]], 14, ['+', 3, ['*', 1.5, width]]]);
}

export function setSelection(map: MapLibre, route: number | null, stop: string | null): void {
  const dim = (on: number, off: number): ExpressionSpecification | number =>
    route == null ? on : ['case', ['==', ['get', 'route'], route], on, off];
  map.setPaintProperty('route-lines', 'line-opacity', dim(0.95, 0.18));
  map.setPaintProperty('route-casing', 'line-opacity', dim(0.8, 0.1));
  map.setPaintProperty('trams', 'icon-opacity', dim(1, 0.3));
  map.setPaintProperty('stops-heat', 'heatmap-opacity', ['interpolate', ['linear'], ['zoom'], 13,
    route == null ? 0.9 : 0.35, 16, route == null ? 0.35 : 0.15]);
  map.setFilter('stop-selected', ['==', ['get', 'id'], stop ?? ''] as FilterSpecification);
  const onRoute: FilterSpecification | null = route == null ? null
    : ['in', ` ${route} `, ['get', 'routes']] as unknown as FilterSpecification;
  map.setFilter('stops-dot', onRoute);
  map.setFilter('stops-label', onRoute);
}

const VISIBILITY: Record<string, (keyof Flags)[]> = {
  'stops-heat': ['heat'],
  'route-lines': ['lines'],
  'route-casing': ['lines'],
  'stops-dot': ['stops'],
  'stop-selected': ['stops'],
  'stops-label': ['stops', 'labels'],
  trams: ['trams'],
  'buildings-3d': ['buildings'],
  'metro-lines': ['metro'],
  'metro-stations': ['metro'],
  'metro-labels': ['metro', 'labels'],
  'weather-grid': ['weather'],
};

export function setVisibility(map: MapLibre, flags: Flags): void {
  for (const [id, keys] of Object.entries(VISIBILITY)) {
    if (map.getLayer(id)) {
      map.setLayoutProperty(id, 'visibility', keys.every((k) => flags[k]) ? 'visible' : 'none');
    }
  }
}

/** Метро грузится один раз при первом включении слоя. */
export async function ensureMetro(map: MapLibre): Promise<void> {
  if (map.getSource('metro')) return;
  const data = (await (await fetch('/data/metro.geojson')).json()) as GeoJSON.FeatureCollection;
  if (map.getSource('metro')) return;
  map.addSource('metro', { type: 'geojson', data });
  const b = map.getLayer('stops-heat') ? 'stops-heat' : before(map);
  map.addLayer({ id: 'metro-lines', type: 'line', source: 'metro', filter: ['==', ['get', 'kind'], 'line'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'colour'], 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1.6, 15, 4.5],
      'line-opacity': 0.55 } }, b);
  map.addLayer({ id: 'metro-stations', type: 'circle', source: 'metro', filter: ['==', ['get', 'kind'], 'station'],
    minzoom: 10.5, paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10.5, 1.8, 15, 4.5],
      'circle-color': '#f4f7fb', 'circle-stroke-color': '#070b12', 'circle-stroke-width': 1 } }, b);
  map.addLayer({ id: 'metro-labels', type: 'symbol', source: 'metro', filter: ['==', ['get', 'kind'], 'station'],
    minzoom: 13, layout: { 'text-field': ['concat', 'М ', ['get', 'name']], 'text-font': FONT, 'text-size': 10.5,
      'text-offset': [0, -1.1], 'text-anchor': 'bottom' },
    paint: { 'text-color': '#e6b2b0', 'text-halo-color': 'rgba(4,7,12,0.95)', 'text-halo-width': 1.3 } });
}

/** Иконка трамвая сверху: кузов в цвете маршрута, светлая крыша, тёмная маска спереди (вверху). */
export function addTramIcons(map: MapLibre): void {
  const ratio = 2;
  const w = 14 * ratio;
  const h = 44 * ratio;
  for (const [route, color] of Object.entries(ROUTE_COLORS)) {
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) continue;
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.beginPath();
    ctx.roundRect(1, 2, w - 2, h - 3, 6 * ratio);
    ctx.fill();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(2, 1, w - 4, h - 4, 5 * ratio);
    ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.fillRect(w / 2 - 2 * ratio, 10 * ratio, 4 * ratio, h - 16 * ratio);
    ctx.fillStyle = '#0d1117';
    ctx.beginPath();
    ctx.roundRect(3, 2, w - 6, 7 * ratio, [5 * ratio, 5 * ratio, 1, 1]);
    ctx.fill();
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    for (const y of [16, 30]) ctx.fillRect(2, y * ratio, w - 4, 1.5 * ratio);
    const data = ctx.getImageData(0, 0, w, h);
    if (map.hasImage(`tram-${route}`)) map.removeImage(`tram-${route}`);
    map.addImage(`tram-${route}`, data, { pixelRatio: ratio });
  }
}
