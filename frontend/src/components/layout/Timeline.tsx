import { useMemo } from 'react';
import { useSeries } from '../../api/queries';
import type { Factors } from '../../api/types';
import { SPEEDS, useStore, type Speed } from '../../state/store';
import { HORIZON_START, MINUTES_PER_DAY, dayIndex, hourOf, isoDate } from '../../lib/time';
import { fmtCompact } from '../../lib/format';
import { useTarget } from '../../hooks/useTarget';
import { HeatMatrix } from '../charts/HeatMatrix';
import { InfoTip } from '../ui/Controls';
import { Icon } from '../ui/Icons';
import styles from './Timeline.module.css';

const SPEED_HINT: Record<Speed, string> = {
  1: 'настоящее время',
  60: 'минута за секунду',
  300: '5 минут за секунду',
  900: '15 минут за секунду',
  3600: 'сутки за 24 секунды',
};

export function Timeline({ factors }: { factors: Factors | undefined }) {
  const minuteOfDay = useStore((s) => Math.floor(s.minute % MINUTES_PER_DAY));
  const day = useStore((s) => dayIndex(s.minute));
  const hour = useStore((s) => hourOf(s.minute));
  const playing = useStore((s) => s.playing);
  const speed = useStore((s) => s.speed);
  const togglePlay = useStore((s) => s.togglePlay);
  const setSpeed = useStore((s) => s.setSpeed);
  const setMinute = useStore((s) => s.setMinute);
  const scenario = useStore((s) => s.scenario);
  const target = useTarget();
  const horizonQuery = useMemo(() => ({ level: target.level, id: target.id, from: HORIZON_START,
    to: isoDate(60), granularity: 'hour' as const }), [target.level, target.id]);
  const series = useSeries(horizonQuery, scenario);
  const values = useMemo(() => series.data?.points.map((p) => p.p50), [series.data]);
  const dayValues = values?.slice(day * 24, day * 24 + 24) ?? [];
  const dayOff = useMemo(() => factors?.calendar.map((c) => c.day_off) ?? [], [factors]);
  const holidays = useMemo(() => factors?.calendar.map((c) => c.holiday) ?? [], [factors]);
  const max = Math.max(...dayValues, 1);
  const area = dayValues.length
    ? `M0,40 ${dayValues.map((v, i) => `L${(i / 23) * 1000},${40 - (v / max) * 36}`).join(' ')} L1000,40 Z` : '';

  return (
    <div className={styles.panel}>
      <div className={styles.controls}>
        <div className={styles.row}>
          <button type="button" className={styles.play} onClick={togglePlay} aria-label={playing ? 'Пауза' : 'Пустить время'}>
            {playing ? <Icon.pause /> : <Icon.play />}
          </button>
          <div className={styles.speeds} role="radiogroup" aria-label="Скорость времени">
            {SPEEDS.map((s) => (
              <button key={s} type="button" role="radio" aria-checked={s === speed} title={SPEED_HINT[s]}
                className={s === speed ? styles.speedOn : styles.speed} onClick={() => setSpeed(s)}>
                ×{s}
              </button>
            ))}
          </div>
          <span className={styles.hint}>{playing ? SPEED_HINT[speed] : 'время на паузе'}</span>
        </div>
        <div className={styles.slider}>
          <svg viewBox="0 0 1000 40" preserveAspectRatio="none" className={styles.area} aria-hidden="true">
            <path d={area} fill={`${target.color}33`} stroke={target.color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
          </svg>
          <input type="range" min={0} max={MINUTES_PER_DAY - 1} step={1} value={minuteOfDay}
            aria-label="Время суток"
            onChange={(e) => setMinute(day * MINUTES_PER_DAY + Number(e.target.value))} />
          <div className={styles.ticks}>
            {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((t) => <span key={t}>{t}</span>)}
          </div>
        </div>
      </div>
      <div className={styles.matrix}>
        <div className={styles.matrixHead}>
          <span>
            Посадки по дням и часам: <b>{target.name}</b>
            <InfoTip>Каждая клетка - час одного дня горизонта, цвет - прогноз посадок. Сверху белым отмечены выходные,
              красным праздники. Клик переносит карту и графики на этот день и час.</InfoTip>
          </span>
          <span className="num muted">макс. {fmtCompact(values ? Math.max(...values) : 0)} в час</span>
        </div>
        <div className={styles.matrixBody}>
          <div className={styles.hours}><span>0</span><span>12</span><span>23</span></div>
          <HeatMatrix values={values} dayOff={dayOff} holidays={holidays} day={day} hour={hour}
            onPick={(d, h) => setMinute(d * MINUTES_PER_DAY + h * 60 + 30)} />
        </div>
        <div className={styles.months}><span>ноябрь</span><span>декабрь</span></div>
      </div>
    </div>
  );
}
