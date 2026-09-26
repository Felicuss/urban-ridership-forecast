// Цвета маршрутов: мягкая пастель (палитра Tokyo Night), различимы между собой на тёмной карте.
export const ROUTE_COLORS: Record<number, string> = {
  1: '#7aa2f7',
  5: '#f7768e',
  7: '#e0af68',
  11: '#73daca',
  12: '#bb9af7',
  17: '#ff9e64',
  25: '#7dcfff',
  26: '#b9d98a',
  28: '#f5a9c8',
  50: '#a9b1d6',
};

/** Номера десяти маршрутов по возрастанию. */
export const ROUTE_IDS: number[] = Object.keys(ROUTE_COLORS).map(Number).sort((a, b) => a - b);

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
