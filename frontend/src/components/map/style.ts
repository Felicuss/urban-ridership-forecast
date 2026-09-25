import type { LayerSpecification, StyleSpecification } from 'maplibre-gl';

// Подложка - тёмный стиль OpenFreeMap (векторные тайлы OpenStreetMap, без ключа). Перекрашиваем его
// в палитру интерфейса, включаем русские названия и добавляем объёмные дома по высотам из OSM.

const STYLE_URL = 'https://tiles.openfreemap.org/styles/dark';
export const FONT = ['Noto Sans Regular'];

/** Цвета подложки ночью и днём: слои, которые перекрашивает свет по времени суток. */
export const PALETTE = {
  background: ['#0d0e11', '#1e2127'],
  water: ['#11161e', '#1f2a37'],
  landuse_residential: ['#101114', '#202329'],
  landuse_park: ['#0f1411', '#1d2520'],
  landcover_wood: ['#0f1411', '#1d2520'],
  building: ['#15171b', '#2a2e36'],
  highway_minor: ['#1a1c21', '#30343c'],
  highway_major_inner: ['#20232a', '#3a3f49'],
  highway_major_casing: ['#272a32', '#454b56'],
  railway_transit: ['#1e2127', '#353a43'],
} as const;

export type PaletteLayer = keyof typeof PALETTE;

const PAINT_KEY: Record<string, string> = {
  background: 'background-color',
  fill: 'fill-color',
  line: 'line-color',
};

export function paintKey(type: string): string | undefined {
  return PAINT_KEY[type];
}

function recolor(layer: LayerSpecification): LayerSpecification {
  const colors = PALETTE[layer.id as PaletteLayer];
  const key = paintKey(layer.type);
  if (!colors || !key) return layer;
  const paint: Record<string, unknown> = { ...(layer as { paint?: Record<string, unknown> }).paint, [key]: colors[0] };
  if (layer.id === 'landcover_wood') delete paint['fill-pattern'];
  if (layer.id === 'building') paint['fill-outline-color'] = '#1d2026';
  return { ...layer, paint } as LayerSpecification;
}

function russianLabels(layer: LayerSpecification): LayerSpecification {
  if (layer.type !== 'symbol' || !layer.layout?.['text-field']) return layer;
  const isPlace = layer.id.startsWith('place') || layer.id.includes('name');
  if (!isPlace) return layer;
  const paint = { ...layer.paint, 'text-color': layer.id.startsWith('place_city') ? '#a1a1aa' : '#6b6b73',
    'text-halo-color': 'rgba(9,9,11,0.9)' };
  return { ...layer, layout: { ...layer.layout, 'text-field': ['coalesce', ['get', 'name:ru'], ['get', 'name']] },
    paint } as LayerSpecification;
}

const BUILDINGS_3D: LayerSpecification = {
  id: 'buildings-3d',
  type: 'fill-extrusion',
  source: 'openmaptiles',
  'source-layer': 'building',
  minzoom: 13.2,
  paint: {
    'fill-extrusion-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 10], 0, '#23262d', 40,
      '#30343d', 120, '#40454f'],
    'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 13.2, 0, 14.6,
      ['coalesce', ['get', 'render_height'], 10]],
    'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
    'fill-extrusion-opacity': ['interpolate', ['linear'], ['zoom'], 13.2, 0, 14, 0.88],
    'fill-extrusion-vertical-gradient': true,
  },
};

export async function loadBaseStyle(signal?: AbortSignal): Promise<StyleSpecification> {
  const res = await fetch(STYLE_URL, { signal });
  if (!res.ok) throw new Error(`подложка карты недоступна: ${res.status}`);
  const style = (await res.json()) as StyleSpecification;
  const layers: LayerSpecification[] = [];
  for (const layer of style.layers) {
    if ('source' in layer && layer.source === 'ne2_shaded') continue;
    layers.push(russianLabels(recolor(layer)));
    if (layer.id === 'building') layers.push(BUILDINGS_3D);
  }
  return { ...style, layers };
}
