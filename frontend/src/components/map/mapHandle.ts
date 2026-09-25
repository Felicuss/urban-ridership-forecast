import type { Map as MapLibre } from 'maplibre-gl';

/** Экземпляр карты для компонентов вне модуля карты: перелёт к остановке, погодные метки. */
export const mapHandle: { current: MapLibre | null } = { current: null };

export function flyTo(lon: number, lat: number, zoom = 15): void {
  mapHandle.current?.flyTo({ center: [lon, lat], zoom, pitch: 55, speed: 1.2, essential: true });
}
