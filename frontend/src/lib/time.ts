// Время интерфейса. Шкала - 01.01.2025-31.10.2026: факт, прогноз ноября-декабря 2025 и оценка 2026.
// Внутри приложения время хранится как минуты от начала шкалы: проигрывание, перемотка и положение
// трамваев считаются одной арифметикой.

export const TIMELINE_START = '2025-01-01';
export const TIMELINE_END = '2026-10-31';
export const HORIZON_START = '2025-11-01';
export const HORIZON_END = '2025-12-31';
export const MINUTES_PER_DAY = 1440;

const START_UTC = Date.UTC(2025, 0, 1);
const DAY_MS = 86_400_000;
export const TIMELINE_DAYS = Math.round((Date.UTC(2026, 9, 31) - START_UTC) / DAY_MS) + 1;
export const TIMELINE_MINUTES = TIMELINE_DAYS * MINUTES_PER_DAY;

const WEEKDAYS = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];
const WEEKDAYS_SHORT = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября',
  'октября', 'ноября', 'декабря'];
export const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь',
  'ноябрь', 'декабрь'];

export function clampMinute(m: number): number {
  return Math.min(Math.max(m, 0), TIMELINE_MINUTES - 1);
}

export function dayIndex(minute: number): number {
  return Math.floor(clampMinute(minute) / MINUTES_PER_DAY);
}

export function hourOf(minute: number): number {
  return Math.floor((clampMinute(minute) % MINUTES_PER_DAY) / 60);
}

/** Дата дня шкалы в ISO: 2025-11-03. */
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

/** «3 ноября 2025, понедельник». */
export function dayLabel(day: number, withYear = true): string {
  const d = new Date(START_UTC + day * DAY_MS);
  return `${d.getUTCDate()} ${MONTHS_GEN[d.getUTCMonth()]}${withYear ? ` ${d.getUTCFullYear()}` : ''}, ${weekdayName(day)}`;
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

/** Первый день месяца и число дней в нём для дня шкалы. */
export function monthOf(day: number): { first: number; days: number; year: number; month: number } {
  const d = new Date(START_UTC + day * DAY_MS);
  const year = d.getUTCFullYear();
  const month = d.getUTCMonth();
  const first = dayOf(`${year}-${String(month + 1).padStart(2, '0')}-01`);
  const days = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return { first, days, year, month };
}

/** Режим «Сейчас»: московское время сегодня. Шкала доходит до 31.10.2026, поэтому дата настоящая. */
export function nowOnTimeline(now = new Date()): number {
  const moscow = new Date(now.getTime() + 3 * 3_600_000);
  const iso = moscow.toISOString().slice(0, 10);
  const minutes = moscow.getUTCHours() * 60 + moscow.getUTCMinutes();
  return clampMinute(dayOf(iso) * MINUTES_PER_DAY + minutes);
}

function dayOfYear(day: number): number {
  const d = new Date(START_UTC + day * DAY_MS);
  return Math.round((d.getTime() - Date.UTC(d.getUTCFullYear(), 0, 1)) / DAY_MS) + 1;
}

/** Высота солнца над Москвой в градусах: по ней меняется свет карты. */
export function sunElevation(minute: number): number {
  const doy = dayOfYear(dayIndex(minute));
  const hoursUtc = (clampMinute(minute) % MINUTES_PER_DAY) / 60 - 3;
  const decl = -23.44 * Math.cos(((2 * Math.PI) / 365) * (doy + 10));
  const lat = 55.75;
  const hourAngle = (hoursUtc + 37.62 / 15 - 12) * 15;
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
