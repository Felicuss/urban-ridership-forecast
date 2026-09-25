// Время прогноза. Горизонт - 61 сутки с 01.11.2025, внутри приложения время хранится как минуты
// от начала горизонта: так проигрывание, перемотка и положение трамваев считаются одной арифметикой.

export const HORIZON_START = '2025-11-01';
export const HORIZON_DAYS = 61;
export const MINUTES_PER_DAY = 1440;
export const HORIZON_MINUTES = HORIZON_DAYS * MINUTES_PER_DAY;

const START_UTC = Date.UTC(2025, 10, 1);
const DAY_MS = 86_400_000;

const WEEKDAYS = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];
const WEEKDAYS_SHORT = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября',
  'октября', 'ноября', 'декабря'];
const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь',
  'ноябрь', 'декабрь'];

export function clampMinute(m: number): number {
  return Math.min(Math.max(m, 0), HORIZON_MINUTES - 1);
}

export function dayIndex(minute: number): number {
  return Math.floor(clampMinute(minute) / MINUTES_PER_DAY);
}

export function hourOf(minute: number): number {
  return Math.floor((clampMinute(minute) % MINUTES_PER_DAY) / 60);
}

/** Дата дня горизонта в ISO: 2025-11-03. */
export function isoDate(day: number): string {
  return new Date(START_UTC + day * DAY_MS).toISOString().slice(0, 10);
}

export function dayOf(iso: string): number {
  return Math.round((Date.parse(`${iso}T00:00:00Z`) - START_UTC) / DAY_MS);
}

/** День недели: 0 - понедельник. */
export function weekday(day: number): number {
  return (new Date(START_UTC + day * DAY_MS).getUTCDay() + 6) % 7;
}

export function weekdayName(day: number, short = false): string {
  return (short ? WEEKDAYS_SHORT : WEEKDAYS)[weekday(day)] ?? '';
}

/** «3 ноября, понедельник». */
export function dayLabel(day: number): string {
  const d = new Date(START_UTC + day * DAY_MS);
  return `${d.getUTCDate()} ${MONTHS_GEN[d.getUTCMonth()]}, ${weekdayName(day)}`;
}

export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

export function monthLabel(period: string): string {
  const [y, m] = period.split('-').map(Number);
  return `${MONTHS[(m ?? 1) - 1]} ${y}`;
}

export function clock(minute: number): string {
  const m = clampMinute(minute) % MINUTES_PER_DAY;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(Math.floor(m % 60)).padStart(2, '0')}`;
}

/**
 * Режим «Сейчас»: прогноз построен на ноябрь-декабрь 2025, поэтому берём текущее время суток и такой же
 * день недели во второй неделе горизонта (10-16 ноября, без праздников и событий по выходным).
 */
export function nowInHorizon(now = new Date()): number {
  const moscow = new Date(now.getTime() + (180 + now.getTimezoneOffset()) * 60_000);
  const dow = (moscow.getDay() + 6) % 7;
  const day = 9 + dow; // 10.11.2025 - понедельник, индекс 9
  return day * MINUTES_PER_DAY + moscow.getHours() * 60 + moscow.getMinutes();
}

/** Высота солнца над горизонтом в градусах для Москвы: по ней меняется свет карты. */
export function sunElevation(minute: number): number {
  const day = dayIndex(minute);
  const doy = 305 + day; // 1 ноября - 305-й день года
  const hoursUtc = (clampMinute(minute) % MINUTES_PER_DAY) / 60 - 3;
  const decl = -23.44 * Math.cos(((2 * Math.PI) / 365) * (doy + 10));
  const lat = 55.75;
  const lon = 37.62;
  const solarTime = hoursUtc + lon / 15;
  const hourAngle = (solarTime - 12) * 15;
  const rad = Math.PI / 180;
  const sinEl = Math.sin(lat * rad) * Math.sin(decl * rad)
    + Math.cos(lat * rad) * Math.cos(decl * rad) * Math.cos(hourAngle * rad);
  return Math.asin(sinEl) / rad;
}

/** Азимут солнца, градусы от севера по часовой: направление света для объёмных домов. */
export function sunAzimuth(minute: number): number {
  const hours = (clampMinute(minute) % MINUTES_PER_DAY) / 60;
  return ((hours - 12.5) * 15 + 180 + 360) % 360;
}
