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

export function fmtPct(value: number | null | undefined, signed = true): string {
  if (value == null || !Number.isFinite(value)) return '-';
  const s = ONE.format(value);
  return `${signed && value > 0 ? '+' : ''}${s} %`;
}

export function fmtTemp(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '-';
  const r = Math.round(value);
  return `${r > 0 ? '+' : ''}${r}°`;
}

/** Коридор одной строкой: «195-297 тыс.», «16 149-24 768». */
export function fmtRange(lo: number | null | undefined, hi: number | null | undefined): string {
  if (lo == null || hi == null) return '-';
  if (Math.abs(hi) >= 1e6) return `${ONE.format(lo / 1e6)}-${ONE.format(hi / 1e6)} млн`;
  if (Math.abs(hi) >= 1e4) return `${INT.format(lo / 1e3)}-${INT.format(hi / 1e3)} тыс.`;
  return `${INT.format(lo)}-${INT.format(hi)}`;
}
