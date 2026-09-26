import type { Map as MapLibre } from 'maplibre-gl';

// Ночные огни: слабое тёплое свечение улиц, над магистралями еле заметный ореол. Включаются к закату
// и гаснут к рассвету по высоте солнца; днём слои прозрачны и ничего не стоят.

const MAJOR = ['motorway', 'trunk', 'primary'];
const STREETS = [...MAJOR, 'secondary', 'tertiary', 'minor'];
const MAJOR_OPACITY = 0.28;
const MINOR_OPACITY = 0.12;
const HAZE_OPACITY = 0.05;

/** Слои огней ставятся под сеть маршрутов и подписи. */
export function addNightLights(map: MapLibre, before: string | undefined): void {
  const isStreet = ['all', ['==', ['geometry-type'], 'LineString'], ['in', ['get', 'class'], ['literal', STREETS]]];
  map.addLayer({ id: 'night-haze', type: 'line', source: 'openmaptiles', 'source-layer': 'transportation',
    filter: ['all', ['==', ['geometry-type'], 'LineString'], ['in', ['get', 'class'], ['literal', MAJOR]]],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#d9a066', 'line-opacity': 0, 'line-blur': ['interpolate', ['linear'], ['zoom'], 9, 4, 15, 16],
      'line-width': ['interpolate', ['linear'], ['zoom'], 9, 4, 15, 26] } } as never, before);
  map.addLayer({ id: 'night-streets', type: 'line', source: 'openmaptiles', 'source-layer': 'transportation',
    filter: isStreet, layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#e3b98a', 'line-opacity': 0,
      'line-blur': ['interpolate', ['linear'], ['zoom'], 9, 0.4, 15, 2.5],
      'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.5, 12, 1.2, 15, 4] } } as never, before);
}

/** Сила огней от 0 (день) до 1 (ночь). */
export function setNightLights(map: MapLibre, level: number): void {
  if (!map.getLayer('night-streets')) return;
  map.setPaintProperty('night-streets', 'line-opacity',
    ['*', level, ['match', ['get', 'class'], MAJOR, MAJOR_OPACITY, MINOR_OPACITY]] as never);
  map.setPaintProperty('night-haze', 'line-opacity', level * HAZE_OPACITY);
}
