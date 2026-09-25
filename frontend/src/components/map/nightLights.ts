import type { Map as MapLibre } from 'maplibre-gl';

// Ночные огни: тёплое свечение улиц и светящиеся окна на объёмных домах. Включаются к закату
// и гаснут к рассвету по высоте солнца; днём слои прозрачны и ничего не стоят.

const LIT_WINDOWS = 'lit-windows';
const MAJOR = ['motorway', 'trunk', 'primary'];
const STREETS = [...MAJOR, 'secondary', 'tertiary', 'minor'];
/** Окна переключаются на узор, когда огни горят больше чем наполовину. */
const WINDOWS_FROM = 0.5;

/** Узор стены с окнами 32 × 32: около 40 % окон горят тёплым светом, остальные тёмные. */
function windowsImage(): ImageData {
  const size = 32;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#1b1e25';
  ctx.fillRect(0, 0, size, size);
  const warm = ['#ffd27a', '#ffc35c', '#f6e2a6', '#ffb347'];
  let seed = 7;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  for (let row = 0; row < 4; row++) {
    for (let col = 0; col < 4; col++) {
      const lit = rand() < 0.4;
      ctx.fillStyle = lit ? warm[Math.floor(rand() * warm.length)]! : '#272b34';
      ctx.fillRect(col * 8 + 2, row * 8 + 2, 4, 4);
    }
  }
  return ctx.getImageData(0, 0, size, size);
}

/** Слои огней ставятся под сеть маршрутов и подписи. */
export function addNightLights(map: MapLibre, before: string | undefined): void {
  if (!map.hasImage(LIT_WINDOWS)) map.addImage(LIT_WINDOWS, windowsImage());
  const isStreet = ['all', ['==', ['geometry-type'], 'LineString'], ['in', ['get', 'class'], ['literal', STREETS]]];
  map.addLayer({ id: 'night-haze', type: 'line', source: 'openmaptiles', 'source-layer': 'transportation',
    filter: ['all', ['==', ['geometry-type'], 'LineString'], ['in', ['get', 'class'], ['literal', MAJOR]]],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#ff9f45', 'line-opacity': 0, 'line-blur': ['interpolate', ['linear'], ['zoom'], 9, 4, 15, 18],
      'line-width': ['interpolate', ['linear'], ['zoom'], 9, 5, 15, 34] } } as never, before);
  map.addLayer({ id: 'night-streets', type: 'line', source: 'openmaptiles', 'source-layer': 'transportation',
    filter: isStreet, layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#ffc07a', 'line-opacity': 0,
      'line-blur': ['interpolate', ['linear'], ['zoom'], 9, 0.4, 15, 3],
      'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.5, 12, 1.4, 15, 5] } } as never, before);
}

/** Сила огней от 0 (день) до 1 (ночь): улицы разгораются плавно, окна включаются после заката. */
export function setNightLights(map: MapLibre, level: number): void {
  if (!map.getLayer('night-streets')) return;
  const byClass = (major: number, other: number) =>
    ['*', level, ['match', ['get', 'class'], MAJOR, major, other]];
  map.setPaintProperty('night-streets', 'line-opacity', byClass(0.75, 0.4) as never);
  map.setPaintProperty('night-haze', 'line-opacity', level * 0.16);
  if (map.getLayer('buildings-3d')) {
    map.setPaintProperty('buildings-3d', 'fill-extrusion-pattern', level >= WINDOWS_FROM ? LIT_WINDOWS : undefined);
  }
}
