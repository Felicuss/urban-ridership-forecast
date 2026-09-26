const INT = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const ONE = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export function fmtInt(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '-' : INT.format(Math.round(value));
}

export function fmt1(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '-' : ONE.format(value);
}

/** 12 780 000 -> «12,8 млн», 64 377 -> «64,4 тыс.» */
export function fmtCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '-';
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${ONE.format(value / 1e6)} млн`;
  if (abs >= 1e4) return `${ONE.format(value / 1e3)} тыс.`;
  return fmtInt(value);
}

/** Дробь с заданным числом знаков и десятичной запятой: 0.90741 -> «0,90741», -0.0074 -> «-0,0074». */
export function fmtFixed(value: number | null | undefined, digits: number): string {
  return value == null || !Number.isFinite(value) ? '-' : value.toFixed(digits).replace('.', ',');
}

export function fmtPct(value: number | null | undefined, signed = true): string {
  if (value == null || !Number.isFinite(value)) return '-';
  const s = ONE.format(value);
  return `${signed && value > 0 ? '+' : ''}${s} %`;
}

export function fmtTemp(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '-';
  const r = Math.round(value);
  return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r)}°`;
}

/** Коридор одной строкой: «195–297 тыс.», «16 149–24 768». */
export function fmtRange(lo: number | null | undefined, hi: number | null | undefined): string {
  if (lo == null || hi == null) return '-';
  if (Math.abs(hi) >= 1e6) return `${ONE.format(lo / 1e6)}–${ONE.format(hi / 1e6)} млн`;
  if (Math.abs(hi) >= 1e4) return `${INT.format(lo / 1e3)}–${INT.format(hi / 1e3)} тыс.`;
  return `${INT.format(lo)}–${INT.format(hi)}`;
}

/** Первая буква заглавная: «суббота» в начале фразы -> «Суббота». */
export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Форма слова для числа: plural(3, ['рейс', 'рейса', 'рейсов']) -> «рейса». */
export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(Math.round(n));
  const mod10 = a % 10;
  const mod100 = a % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}
