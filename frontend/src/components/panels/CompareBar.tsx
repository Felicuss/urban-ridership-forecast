import type { Horizon, Series } from '../../api/types';
import { useStore } from '../../state/store';
import {
  TIMELINE_DAYS, TIMELINE_END, TIMELINE_START, dayOf, isoDate, monthLabel, monthOf, shortDate, weekStart, weekdayName,
} from '../../lib/time';
import { fmtCompact, fmtPct } from '../../lib/format';
import { COMPARE_COLOR } from '../charts/BandChart';
import styles from './Panels.module.css';

// Сравнение двух дат рядом: второй ряд на том же графике и разница итогов. Для суток сравниваются часы,
// для месяца - дни по порядку. Быстрые варианты держат тот же день недели: неделя и 52 недели назад.

interface Option {
  label: string;
  day: number;
}

function options(day: number, horizon: Horizon): Option[] {
  if (horizon === 'day' || horizon === 'week') {
    return [
      { label: 'неделей раньше', day: day - 7 },
      { label: 'год назад', day: day - 364 },
      { label: 'через год', day: day + 364 },
    ].filter((o) => o.day >= 0 && o.day < TIMELINE_DAYS);
  }
  const m = monthOf(day);
  const first = (year: number, month: number) => dayOf(`${year}-${String(month + 1).padStart(2, '0')}-01`);
  const prev = m.month === 0 ? first(m.year - 1, 11) : first(m.year, m.month - 1);
  return [
    { label: 'месяцем раньше', day: prev },
    { label: 'год назад', day: first(m.year - 1, m.month) },
    { label: 'через год', day: first(m.year + 1, m.month) },
  ].filter((o) => o.day >= 0 && o.day < TIMELINE_DAYS);
}

/**
 * День второй даты: быстрый вариант считается от выбранного дня (вторник сравнивается со вторником и после
 * смены даты), дата из календаря остаётся той, что выбрали.
 */
export function useCompareDay(day: number, horizon: Horizon): number | null {
  const compareDay = useStore((s) => s.compareDay);
  const preset = useStore((s) => s.comparePreset);
  if (preset == null) return compareDay;
  return options(day, horizon).find((o) => o.label === preset)?.day ?? null;
}

/** Подпись второй даты: «7.11, пт» для суток, «неделя с 3.11» для недели, «ноябрь 2025» для месяца. */
export function compareLabel(day: number, horizon: Horizon): string {
  if (horizon === 'day') return `${shortDate(isoDate(day))}, ${weekdayName(day, true)}`;
  if (horizon === 'week') return `неделя с ${shortDate(isoDate(weekStart(day)))}`;
  return monthLabel(isoDate(day).slice(0, 7));
}

export function CompareBar({ day, horizon, series, other }: {
  day: number;
  horizon: Horizon;
  series: Series;
  other: Series | undefined;
}) {
  const compareDay = useCompareDay(day, horizon);
  const preset = useStore((s) => s.comparePreset);
  const setCompareDay = useStore((s) => s.setCompareDay);
  const setComparePreset = useStore((s) => s.setComparePreset);
  if (horizon === 'year') return null;
  const opts = options(day, horizon);
  const delta = other && other.total.p50 > 0 ? (100 * (series.total.p50 - other.total.p50)) / other.total.p50 : null;
  return (
    <div className={styles.compare}>
      <div className={styles.row} role="group" aria-label="Сравнить с другой датой">
        <span className={styles.compareLabel}>Сравнить с</span>
        <button type="button" className={compareDay == null ? styles.chipOn : styles.chip} aria-pressed={compareDay == null}
          onClick={() => setCompareDay(null)}>
          нет</button>
        {opts.map((o) => (
          <button key={o.label} type="button" className={preset === o.label ? styles.chipOn : styles.chip}
            aria-pressed={preset === o.label} onClick={() => setComparePreset(o.label)}>{o.label}</button>
        ))}
        <input className={styles.input} type="date" min={TIMELINE_START} max={TIMELINE_END} aria-label="Другая дата"
          value={compareDay != null ? isoDate(compareDay) : ''}
          onChange={(e) => setCompareDay(e.target.value ? dayOf(e.target.value) : null)} />
      </div>
      {compareDay != null && (
        <p className={styles.note}>
          <i className={styles.compareSwatch} style={{ background: COMPARE_COLOR }} />
          {compareLabel(compareDay, horizon)}: {other ? fmtCompact(other.total.p50) : '…'}
          {delta != null && <>, выбранный период <b className={delta >= 0 ? styles.up : styles.down}>{fmtPct(delta)}</b> к нему</>}
        </p>
      )}
    </div>
  );
}
