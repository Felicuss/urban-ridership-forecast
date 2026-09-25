import type { Map as MapLibre } from 'maplibre-gl';
import { sunAzimuth, sunElevation } from '../../lib/time';
import { PALETTE, paintKey, type PaletteLayer } from './style';

// Свет по времени суток: высота солнца над Москвой в выбранную минуту задаёт, насколько карта
// светлее ночной палитры, направление света для объёмных домов и цвет неба у горизонта.

function hex(c: string): [number, number, number] {
  const n = Number.parseInt(c.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mix(a: string, b: string, t: number): string {
  const x = hex(a);
  const y = hex(b);
  const c = x.map((v, i) => Math.round(v + ((y[i] ?? v) - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

/** 0 - ночь, 1 - день; сумерки плавно между ними. */
export function daylightLevel(minute: number): number {
  const e = sunElevation(minute);
  const t = Math.min(Math.max((e + 7) / 17, 0), 1);
  return t * t * (3 - 2 * t);
}

export function applyDaylight(map: MapLibre, minute: number, enabled: boolean): number {
  const t = enabled ? daylightLevel(minute) : 0;
  for (const [id, [night, day]] of Object.entries(PALETTE)) {
    const layer = map.getLayer(id as PaletteLayer);
    const key = layer ? paintKey(layer.type) : undefined;
    if (key) map.setPaintProperty(id, key as 'fill-color', mix(night, day, t));
  }
  const azimuth = sunAzimuth(minute);
  const polar = 90 - Math.max(sunElevation(minute), 8);
  map.setLight({ anchor: 'map', position: [1.4, azimuth, polar], color: t > 0.3 ? '#fff4e0' : '#9db6ff',
    intensity: 0.25 + 0.35 * t });
  map.setSky({
    'sky-color': mix('#05080f', '#2a4a78', t),
    'horizon-color': mix('#0d1726', '#9fb8d8', t),
    'fog-color': mix('#070b12', '#3a5270', t),
    'sky-horizon-blend': 0.5,
    'horizon-fog-blend': 0.6,
    'fog-ground-blend': 0.2,
    'atmosphere-blend': 0.6,
  });
  const root = document.documentElement.style;
  root.setProperty('--sky-a', mix('#0b1422', '#1d3350', t));
  root.setProperty('--sky-glow', `rgba(${t > 0.4 ? '255,200,120' : '58,149,255'},${(0.05 + 0.08 * t).toFixed(3)})`);
  return t;
}
