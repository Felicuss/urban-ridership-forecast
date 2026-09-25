import { useEffect, useRef, useState } from 'react';
import type { CalendarDay } from '../../api/types';
import { HORIZON_START, MONTHS, TIMELINE_DAYS, dayOf, monthOf, nowOnTimeline, weekday } from '../../lib/time';
import { Icon } from '../ui/Icons';
import styles from './DatePopover.module.css';

const HEAD = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
const SOURCE_NOTE: Record<string, string> = {
  fact: 'факт валидаций',
  forecast: 'прогноз модели',
  outlook: 'оценка по сезонности',
};

/** Календарь шкалы: листается по месяцам, выходные светлее, праздники красным, снизу - источник данных месяца. */
export function DatePopover({ day, onPick, onClose, calendar }: {
  day: number;
  onPick: (day: number) => void;
  onClose: () => void;
  calendar: CalendarDay[] | undefined;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [first, setFirst] = useState(() => monthOf(day).first);
  const month = monthOf(first);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) onClose();
    };
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [onClose]);

  const shift = (months: number) => {
    const d = new Date(Date.UTC(month.year, month.month + months, 1));
    const target = dayOf(d.toISOString().slice(0, 10));
    if (target >= 0 && target < TIMELINE_DAYS) setFirst(target);
  };
  const source = calendar?.[first]?.source ?? 'forecast';

  return (
    <div ref={box} className={styles.pop} role="dialog" aria-label="Выбор даты">
      <div className={styles.head}>
        <button type="button" onClick={() => shift(-1)} aria-label="Предыдущий месяц" disabled={first === 0}><Icon.prev /></button>
        <div className={styles.month}>
          {MONTHS[month.month]} {month.year}
          <small className={styles[source]}>{SOURCE_NOTE[source]}</small>
        </div>
        <button type="button" onClick={() => shift(1)} aria-label="Следующий месяц"
          disabled={first + month.days >= TIMELINE_DAYS}><Icon.next /></button>
      </div>
      <div className={styles.grid}>
        {HEAD.map((h) => <span key={h} className={styles.headDay}>{h}</span>)}
        {Array.from({ length: weekday(first) }, (_, i) => <span key={`e${i}`} />)}
        {Array.from({ length: month.days }, (_, i) => {
          const d = first + i;
          const c = calendar?.[d];
          const cls = [styles.day, d === day ? styles.sel : '', c?.dayOff ? styles.off : '', c?.holiday ? styles.hol : '',
            c && !c.dayOff && c.dayOfWeek >= 5 ? styles.work : ''].join(' ');
          return (
            <button key={d} type="button" className={cls} disabled={d >= TIMELINE_DAYS} title={c?.holiday ?? undefined}
              onClick={() => onPick(d)}>
              {i + 1}
            </button>
          );
        })}
      </div>
      <div className={styles.jumps}>
        <button type="button" onClick={() => onPick(dayOf(HORIZON_START) + 9)}>Прогноз ноября 2025</button>
        <button type="button" onClick={() => onPick(Math.floor(nowOnTimeline() / 1440))}>Сегодня</button>
      </div>
      <p className={styles.note}>
        Январь-октябрь 2025 - факт, ноябрь-декабрь 2025 - прогноз модели, 2026 год - оценка по сезонному индексу.
        Красным - праздники, жёлтым - рабочие выходные.
      </p>
    </div>
  );
}
