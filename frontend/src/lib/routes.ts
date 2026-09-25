// Цвета маршрутов на тёмной карте: различимы между собой и не совпадают с красным акцентом интерфейса.
export const ROUTE_COLORS: Record<number, string> = {
  1: '#4aa3ff',
  5: '#ff6b8b',
  7: '#ffb020',
  11: '#3ddc97',
  12: '#b98cff',
  17: '#ff8a4c',
  25: '#2fd6e6',
  26: '#e8e36b',
  28: '#ff9ce0',
  50: '#9fb8ff',
};

export function routeColor(route: number | null | undefined): string {
  return route == null ? '#e9eef5' : (ROUTE_COLORS[route] ?? '#e9eef5');
}

/** Ссылки в Яндекс Карты: маршрут на общественном транспорте до точки или между точками. */
export function yandexRouteTo(lat: number, lon: number): string {
  return `https://yandex.ru/maps/213/moscow/?rtext=~${lat.toFixed(6)}%2C${lon.toFixed(6)}&rtt=mt`;
}

export function yandexRouteBetween(a: { lat: number; lon: number }, b: { lat: number; lon: number }): string {
  return `https://yandex.ru/maps/213/moscow/?rtext=${a.lat.toFixed(6)}%2C${a.lon.toFixed(6)}~${b.lat.toFixed(6)}%2C${b.lon.toFixed(6)}&rtt=mt`;
}

export function yandexPoint(lat: number, lon: number): string {
  return `https://yandex.ru/maps/213/moscow/?ll=${lon.toFixed(6)}%2C${lat.toFixed(6)}&pt=${lon.toFixed(6)}%2C${lat.toFixed(6)}&z=17`;
}
