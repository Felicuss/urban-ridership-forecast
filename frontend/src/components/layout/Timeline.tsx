import { useMemo } from 'react';
import { useCalendar, useSeries } from '../../api/queries';
import { useStore } from '../../state/store';
import { MINUTES_PER_DAY, MONTHS, TIMELINE_DAYS, dayIndex, hourOf, isoDate, monthOf } from '../../lib/time';
import { fmtCompact, fmtInt } from '../../lib/format';
import { targetQuery, useTarget } from '../../hooks/useTarget';
import { HeatMatrix } from '../charts/HeatMatrix';
import { InfoTip } from '../ui/Controls';
import styles from './Timeline.module.css';

const WINDOW = 61;

/** Окно тепловой карты: два месяца от начала месяца выбранного дня, не дальше конца шкалы. */
function windowStart(day: number): number {
  return Math.max(0, Math.min(monthOf(day).first, TIMELINE_DAYS - WINDOW));
}

export function Timeline() {
  const minuteOfDay = useStore((s) => Math.floor(s.minute % MINUTES_PER_DAY));
  const day = useStore((s) => dayIndex(s.minute));
  const hour = useStore((s) => hourOf(s.minute));
  const setMinute = useStore((s) => s.setMinute);
  const scenario = useStore((s) => s.scenario);
  const calendar = useCalendar().data;
  const target = useTarget();
  const first = windowStart(day);
  const followNow = useStore((s) => s.followNow);
  const query = useMemo(() => ({ ...targetQuery(target), from: isoDate(first),
    to: isoDate(first + WINDOW - 1), granularity: 'hour' as const }), [target, first]);
  const series = useSeries(query, scenario);
  const values = useMemo(() => series.data?.points.map((p) => p.p50), [series.data]);
  const days = useMemo(() => calendar?.slice(first, first + WINDOW) ?? [], [calendar, first]);
  const at = day - first;
  const dayValues = values?.slice(at * 24, at * 24 + 24) ?? [];
  const dayTotal = dayValues.reduce((a, b) => a + b, 0);
  const max = Math.max(...dayValues, 1);
  const area = dayValues.length
    ? `M0,40 ${dayValues.map((v, i) => `L${(i / 23) * 1000},${40 - (v / max) * 36}`).join(' ')} L1000,40 Z` : '';
  const months = useMemo(() => {
    const out: { label: string; share: number }[] = [];
    let d = first;
    while (d < first + WINDOW) {
      const m = monthOf(d);
      const len = Math.min(m.first + m.days, first + WINDOW) - d;
      out.push({ label: `${MONTHS[m.month]} ${m.year}`, share: len });
      d += len;
    }
    return out;
  }, [first]);

  return (
    <div className={styles.panel}>
      <div className={styles.controls}>
        <div className={styles.dayHead}>
          <span>Сутки по часам: <b>{target.name}</b></span>
          <span className="num">{fmtInt(dayTotal)} за сутки</span>
        </div>
        <div className={styles.slider}>
          <svg viewBox="0 0 1000 40" preserveAspectRatio="none" className={styles.area} aria-hidden="true">
            <path d={area} fill={`${target.color}2a`} stroke={target.color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
          </svg>
          <input type="range" min={0} max={MINUTES_PER_DAY - 1} step={1} value={minuteOfDay} aria-label="Время суток"
            onChange={(e) => setMinute(day * MINUTES_PER_DAY + Number(e.target.value))} />
            title={followNow ? 'Выбор другого времени выключит режим «Сейчас»' : undefined}
          <div className={styles.ticks}>
            {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((t) => <span key={t}>{t}</span>)}
          </div>
        </div>
      </div>
      <div className={styles.matrix}>
        <div className={styles.matrixHead}>
          <span>
            Посадки по дням и часам
            <InfoTip>Каждая клетка - час одного дня, цвет - посадки. Сверху отмечены выходные и праздники, снизу источник:
              серый - факт, синий - прогноз модели, тёмный - оценка по сезонности. Клик переносит время.</InfoTip>
          </span>
          <span className="num muted">макс. {fmtCompact(values?.length ? Math.max(...values) : 0)} в час</span>
        </div>
        <div className={styles.matrixBody}>
          <div className={styles.hours}><span>0</span><span>12</span><span>23</span></div>
          <HeatMatrix values={values} days={days} day={day} hour={hour}
            onPick={(d, h) => setMinute(d * MINUTES_PER_DAY + h * 60 + 30)} />
        </div>
        <div className={styles.months} style={{ gridTemplateColumns: months.map((m) => `${m.share}fr`).join(' ') }}>
          {months.map((m) => <span key={m.label}>{m.label}</span>)}
        </div>
      </div>
    </div>
  );
}
