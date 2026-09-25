// Коды погоды WMO (Open-Meteo) в короткие подписи и тип осадков для анимации на карте.

export type Sky = 'clear' | 'cloud' | 'fog' | 'rain' | 'snow' | 'storm';

export function skyOf(code: number | null | undefined): Sky {
  if (code == null) return 'cloud';
  if (code <= 1) return 'clear';
  if (code <= 3) return 'cloud';
  if (code === 45 || code === 48) return 'fog';
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return 'snow';
  if (code >= 95) return 'storm';
  if (code >= 51) return 'rain';
  return 'cloud';
}

export const SKY_LABEL: Record<Sky, string> = {
  clear: 'ясно',
  cloud: 'облачно',
  fog: 'туман',
  rain: 'дождь',
  snow: 'снег',
  storm: 'гроза',
};

export interface HourWeather {
  temp: number | null;
  precip: number;
  snow: number;
  wind: number | null;
  sky: Sky;
}

export function weatherAt(
  w: { temp: (number | null)[][]; precip: (number | null)[][]; snow: (number | null)[][]; wind: (number | null)[][];
    code: (number | null)[][] } | undefined,
  day: number,
  hour: number,
): HourWeather | null {
  if (!w) return null;
  const at = <T>(grid: (T | null)[][]) => grid[day]?.[hour] ?? null;
  return { temp: at(w.temp), precip: at(w.precip) ?? 0, snow: at(w.snow) ?? 0, wind: at(w.wind),
    sky: skyOf(at(w.code)) };
}
