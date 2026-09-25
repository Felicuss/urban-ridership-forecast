import type { Map as MapLibre } from 'maplibre-gl';
import { sunAzimuth, sunElevation } from '../../lib/time';
import { setNightLights } from './nightLights';
import { PALETTE, paintKey, type PaletteLayer } from './style';

// Свет по времени суток по высоте солнца над Москвой. Три состояния, а не два: ночь с холодным лунным
// светом, сумерки с фиолетовым небом, оранжевым горизонтом и низким тёплым светом на домах, и день.
// К закату загораются улицы и окна домов, к рассвету гаснут.

type Rgb = [number, number, number];

function rgb(c: string): Rgb {
  const n = Number.parseInt(c.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function css(c: Rgb): string {
  return `rgb(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])})`;
}

function mix(a: Rgb, b: Rgb, t: number): Rgb {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

function smooth(from: number, to: number, x: number): number {
  const t = Math.min(Math.max((x - from) / (to - from), 0), 1);
  return t * t * (3 - 2 * t);
}

interface Weights {
  night: number;
  dusk: number;
  day: number;
}

/** Доли ночи, сумерек и дня по высоте солнца в градусах, в сумме 1. */
function weights(elevation: number): Weights {
  const up = smooth(-10, -2, elevation);
  const day = smooth(0, 12, elevation);
  return { night: 1 - up, dusk: up * (1 - day), day: up * day };
}

function blendRgb(w: Weights, night: string, dusk: string, day: string): Rgb {
  const [n, d, y] = [rgb(night), rgb(dusk), rgb(day)];
  return [0, 1, 2].map((i) => n[i]! * w.night + d[i]! * w.dusk + y[i]! * w.day) as Rgb;
}

function blend(w: Weights, night: string, dusk: string, day: string): string {
  return css(blendRgb(w, night, dusk, day));
}

/** Сумеречный цвет слоя подложки: между ночным и дневным, с тёплым розовым оттенком. */
function duskOf(night: string, day: string): string {
  const c = mix(mix(rgb(night), rgb(day), 0.35), rgb('#5b3b46'), 0.22);
  return `#${c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`;
}

const DUSK = Object.fromEntries(Object.entries(PALETTE).map(([id, [night, day]]) => [id, duskOf(night, day)]));

/** Огни от 0 до 1: начинают гореть, когда солнце ниже 4°, в полную силу с -6°. */
function lightsLevel(elevation: number): number {
  return 1 - smooth(-6, 4, elevation);
}

export function applyDaylight(map: MapLibre, minute: number, enabled: boolean): void {
  const elevation = sunElevation(minute);
  // без смены суток карта остаётся в ночной палитре, но без огней: чистая тёмная тема
  const w = enabled ? weights(elevation) : { night: 1, dusk: 0, day: 0 };
  for (const [id, [night, day]] of Object.entries(PALETTE)) {
    const layer = map.getLayer(id as PaletteLayer);
    const key = layer ? paintKey(layer.type) : undefined;
    if (key) map.setPaintProperty(id, key as 'fill-color', blend(w, night, DUSK[id]!, day));
  }
  const polar = 90 - Math.max(elevation, 4);
  map.setLight({ anchor: 'map', position: [1.4, sunAzimuth(minute), polar],
    color: blend(w, '#8fa6d6', '#ffae73', '#fff4e6'), intensity: 0.2 * w.night + 0.5 * w.dusk + 0.5 * w.day });
  map.setSky({
    'sky-color': blend(w, '#05070c', '#241f3d', '#415570'),
    'horizon-color': blend(w, '#0e1219', '#d98256', '#aeb9c8'),
    'fog-color': blend(w, '#090b10', '#3b2833', '#4b5563'),
    'sky-horizon-blend': 0.5,
    'horizon-fog-blend': 0.6,
    'fog-ground-blend': 0.2,
    'atmosphere-blend': 0.6,
  });
  setNightLights(map, enabled ? lightsLevel(elevation) : 0);
  const root = document.documentElement.style;
  root.setProperty('--sky-a', blend(w, '#0d0f13', '#1d1720', '#1c2029'));
  const glow = blendRgb(w, '#7aa2f7', '#ff8c5a', '#ffd6a0').map(Math.round);
  const alpha = 0.045 * w.night + 0.1 * w.dusk + 0.06 * w.day;
  root.setProperty('--sky-glow', `rgba(${glow.join(',')},${alpha.toFixed(3)})`);
}
