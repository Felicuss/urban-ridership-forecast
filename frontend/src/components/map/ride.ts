import type { GeoJSONSource, Map as MapLibre } from 'maplibre-gl';
import type { RouteStop } from '../../api/types';
import { pointAt, projectOnPath, type LngLat } from '../../lib/geo';
import { SPEED_M_PER_MIN, type Line } from './trams';

// Поездка одного вагона от первой до последней остановки. Сколько сядет на каждой остановке за
// рейс: посадки маршрута в этот час × доля остановки ÷ число рейсов в час в одну сторону.

const RIDE_ZOOM = 17.4;
const RIDE_PITCH = 62;

export interface RideStop {
  name: string;
  distance: number;
  perTrip: number;
}

export function rideStops(line: Line, stops: RouteStop[], hourLoad: number, headwayMin: number): RideStop[] {
  const tripsPerHour = 60 / headwayMin;
  return stops
    .filter((s) => s.direction === line.direction)
    .map((s) => ({ name: s.name, distance: projectOnPath(line.path, [s.lon, s.lat]),
      perTrip: (hourLoad * s.share) / tripsPerHour }))
    .sort((a, b) => a.distance - b.distance);
}

export interface RideFrame {
  at: LngLat;
  bearing: number;
  passed: number;
  boarded: number;
  stopName: string;
  finished: boolean;
}

export class RideRunner {
  private bearing: number | null = null;

  constructor(
    private readonly map: MapLibre,
    private readonly line: Line,
    private readonly stops: RideStop[],
    private readonly speed: number,
    private readonly startedAt: number,
  ) {}

  /** Кадр поездки: двигает вагон и камеру, возвращает, сколько остановок пройдено и сколько село. */
  frame(now: number, follow: boolean): RideFrame {
    const meters = ((now - this.startedAt) / 60_000) * SPEED_M_PER_MIN * this.speed;
    const { at, bearing } = pointAt(this.line.path, meters);
    (this.map.getSource('ride') as GeoJSONSource | undefined)?.setData({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: at },
        properties: { route: this.line.route, bearing } }],
    });
    if (follow) {
      const prev = this.bearing ?? this.map.getBearing();
      const diff = ((bearing - prev + 540) % 360) - 180;
      this.bearing = prev + diff * 0.04;
      const zoom = this.map.getZoom();
      const pitch = this.map.getPitch();
      this.map.jumpTo({ center: at, bearing: this.bearing, zoom: zoom + (RIDE_ZOOM - zoom) * 0.05,
        pitch: pitch + (RIDE_PITCH - pitch) * 0.05 });
    }
    let passed = 0;
    let boarded = 0;
    let stopName = this.stops[0]?.name ?? '';
    for (const s of this.stops) {
      if (s.distance > meters) break;
      passed += 1;
      boarded += s.perTrip;
      stopName = s.name;
    }
    return { at, bearing, passed, boarded, stopName, finished: meters >= this.line.path.length };
  }

  clear(): void {
    (this.map.getSource('ride') as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features: [] });
  }
}
