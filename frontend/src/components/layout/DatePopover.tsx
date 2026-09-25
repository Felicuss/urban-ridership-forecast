import { useEffect, useRef } from 'react';
import type { Factors } from '../../api/types';
import { HORIZON_DAYS, weekday } from '../../lib/time';
import styles from './DatePopover.module.css';

const MONTHS = [{ name: 'Ноябрь 2025', first: 0, days: 30 }, { name: 'Декабрь 2025', first: 30, days: 31 }];
const HEAD = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

/** Календарь горизонта: два месяца, выходные светлее, праздники красным, рабочая суббота жёлтым. */
export function DatePopover({ day, onPick, onClose, calendar }: {
  day: number;
  onPick: (day: number) => void;
  onClose: () => void;
  calendar: Factors['calendar'] | undefined;
}) {
  const box = useRef<HTMLDivElement>(null);
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

  return (
    <div ref={box} className={styles.pop} role="dialog" aria-label="Выбор даты прогноза">
      {MONTHS.map((m) => (
        <div key={m.name}>
          <div className={styles.month}>{m.name}</div>
          <div className={styles.grid}>
            {HEAD.map((h) => <span key={h} className={styles.head}>{h}</span>)}
            {Array.from({ length: weekday(m.first) }, (_, i) => <span key={`e${i}`} />)}
            {Array.from({ length: m.days }, (_, i) => {
              const d = m.first + i;
              const c = calendar?.[d];
              const cls = [styles.day, d === day ? styles.sel : '', c?.day_off ? styles.off : '',
                c?.holiday ? styles.hol : '', c && !c.day_off && c.dow === 5 ? styles.work : ''].join(' ');
              return (
                <button key={d} type="button" className={cls} disabled={d >= HORIZON_DAYS}
                  title={c?.holiday ?? undefined} onClick={() => onPick(d)}>
                  {i + 1}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <p className={styles.note}>Прогноз построен на 01.11-31.12.2025. Красным - праздники, жёлтым - рабочая суббота 1 ноября.</p>
    </div>
  );
}
