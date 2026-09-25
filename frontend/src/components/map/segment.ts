import type { RouteStop } from '../../api/types';
import type { Segment } from '../../state/store';
import { pointAt, projectOnPath, type LngLat } from '../../lib/geo';
import type { Line } from './trams';

// Выбранный участок маршрута на карте: кусок трассы между проекциями первой и последней остановки
// и кольца на концах. Пустая коллекция, если участок не выбран или остановки ещё не загрузились.

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };

export function segmentShape(lines: Line[], route: number | null, segment: Segment | null,
  stops: RouteStop[] | undefined): GeoJSON.FeatureCollection {
  if (route == null || !segment || !stops) return EMPTY;
  const line = lines.find((l) => l.route === route && l.direction === segment.direction);
  const stopAt = (id: string) => stops.find((s) => s.stopId === id && s.direction === segment.direction);
  const a = stopAt(segment.from);
  const b = stopAt(segment.to);
  if (!line || !a || !b) return EMPTY;
  const da = projectOnPath(line.path, [a.lon, a.lat]);
  const db = projectOnPath(line.path, [b.lon, b.lat]);
  const [from, to] = da <= db ? [da, db] : [db, da];
  const inner = line.path.coords.filter((_, i) => (line.path.cum[i] ?? 0) > from && (line.path.cum[i] ?? 0) < to);
  const coords: LngLat[] = [pointAt(line.path, from).at, ...inner, pointAt(line.path, to).at];
  const end = (at: LngLat): GeoJSON.Feature => ({ type: 'Feature', geometry: { type: 'Point', coordinates: at },
    properties: {} });
  return {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: {} },
      end([a.lon, a.lat]),
      end([b.lon, b.lat]),
    ],
  };
}

/** Рамка участка для камеры: юго-западный и северо-восточный углы. */
export function segmentBounds(shape: GeoJSON.FeatureCollection): [LngLat, LngLat] | null {
  const line = shape.features.find((f) => f.geometry.type === 'LineString');
  if (!line || line.geometry.type !== 'LineString') return null;
  const pts = line.geometry.coordinates as LngLat[];
  const lons = pts.map((p) => p[0]);
  const lats = pts.map((p) => p[1]);
  return [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]];
}
