import { useEffect, useMemo, useState } from 'react';
import { useFactors, useRouteStops } from '../../api/queries';
import { useDaysLoad } from '../../hooks/useDispatch';
import { routeTitle } from '../../hooks/useTarget';
import { useStore } from '../../state/store';
import { fmtCompact, fmtInt } from '../../lib/format';
import { routeColor } from '../../lib/routes';
import { MINUTES_PER_DAY, dayIndex, hourOf, isoDate, monthOf, shortDate, weekStart, weekdayName } from '../../lib/time';
import { Segmented } from '../ui/Controls';
import { Icon } from '../ui/Icons';
import styles from './StationMatrix.module.css';

// Маршрут по станциям: строки - остановки по порядку в выбранную сторону, столбцы - дни недели или месяца,
// в клетке посадки на остановке за сутки или в выбранный час. Клик по клетке переносит время и выделяет
// остановку на карте. Остановки в валидациях нет, поэтому значение - посадки маршрута × доля остановки.

type Period = 'week' | 'month';
type Mode = 'day' | 'hour';

const RAMP = ['#15171c', '#26324a', '#3d5582', '#5b7bc7', '#7fa8a0', '#c9ad72', '#d68d6d', '#d06a73'];

function heat(v: number, max: number): string {
  if (v <= 0 || max <= 0) return '#101114';
  return RAMP[Math.round(Math.min(Math.sqrt(v / max), 1) * (RAMP.length - 1))] ?? RAMP[0]!;
}

/** embedded - виджет в сплите или панелях: без рамки поверх карты, без кнопки закрытия и без Esc. */
export function StationMatrix({ route, embedded = false }: { route: number; embedded?: boolean }) {
  const setOpen = useStore((s) => s.setMatrixOpen);
  const day = useStore((s) => dayIndex(s.minute));
  const hour = useStore((s) => hourOf(s.minute));
  const setMinute = useStore((s) => s.setMinute);
  const stop = useStore((s) => s.stop);
  const selectStop = useStore((s) => s.selectStop);
  const factors = useFactors().data;
  const stops = useRouteStops(route).data;
  const [period, setPeriod] = useState<Period>('week');
  const [mode, setMode] = useState<Mode>('day');
  const [direction, setDirection] = useState(0);

  const first = period === 'week' ? weekStart(day) : monthOf(day).first;
  const count = period === 'week' ? 7 : monthOf(day).days;
  const { days, pending } = useDaysLoad(first, count);
  const rows = useMemo(() => (stops ?? []).filter((s) => s.direction === direction).sort((a, b) => a.seq - b.seq), [stops, direction]);
  const ends = useMemo(() => [0, 1].map((d) => {
    const s = (stops ?? []).filter((x) => x.direction === d).sort((a, b) => a.seq - b.seq);
    return s.length ? `до «${s[s.length - 1]!.name}»` : `направление ${d + 1}`;
  }), [stops]);

  // посадки маршрута по дням: за сутки или в выбранный час
  const routeByDay = days.map(({ day: d, load }) => {
    const hours = load.routes.get(route) ?? [];
    return { day: d, value: mode === 'day' ? hours.reduce((a, b) => a + b, 0) : hours[hour] ?? 0 };
  });
  const cell = (share: number, value: number) => share * value;
  const max = Math.max(...rows.flatMap((s) => routeByDay.map((r) => cell(s.share, r.value))), 1);
  // доля остановки постоянна, поэтому самая загруженная клетка - на пересечении самой крупной остановки и дня
  const peakDay = routeByDay.length ? routeByDay.reduce((a, x) => (x.value > a.value ? x : a)).day : -1;
  const peakStop = rows.length ? rows.reduce((a, x) => (x.share > a.share ? x : a)).stopId : '';

  useEffect(() => {
    if (embedded) return undefined;
    const key = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
      }
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [setOpen, embedded]);

  const color = routeColor(route);
  const label = mode === 'day' ? 'посадок за сутки' : `посадок в ${hour}:00-${hour + 1}:00`;

  return (
    <section className={embedded ? styles.embedded : styles.panel} style={{ '--c': color } as React.CSSProperties} aria-label={`Маршрут ${route} по станциям`}>
      <header className={styles.head}>
        <span className={styles.badge}>{route}</span>
        <div className={styles.title}>
          <h2>По станциям и дням</h2>
          <p>{routeTitle(factors, route) || `Маршрут ${route}`} · {label}</p>
        </div>
        {!embedded && (
          <button type="button" className={styles.close} aria-label="Закрыть (Esc)" title="Закрыть (Esc)" onClick={() => setOpen(false)}>
            <Icon.close />
          </button>
        )}
      </header>
      <div className={styles.controls}>
        <Segmented value={period} onChange={setPeriod} label="Период"
          options={[{ value: 'week', label: 'Неделя', hint: 'Понедельник-воскресенье выбранного дня' },
            { value: 'month', label: 'Месяц', hint: 'Все дни месяца выбранного дня' }]} />
        <Segmented value={mode} onChange={setMode} label="Что в клетке"
          options={[{ value: 'day', label: 'За сутки', hint: 'Посадки на остановке за сутки' },
            { value: 'hour', label: `В ${hour}:00`,
              hint: `Посадки в выбранный час; час меняется на шкале или клавишами ${embedded ? 'Shift + ' : ''}↑ ↓` }]} />
        <Segmented value={String(direction)} onChange={(v) => setDirection(Number(v))} label="Направление"
          options={[{ value: '0', label: ends[0] ?? 'туда', hint: 'Остановки по ходу движения' },
            { value: '1', label: ends[1] ?? 'обратно', hint: 'Остановки по ходу движения' }]} />
      </div>
      {mode === 'hour' && (
        <div className={styles.hours} role="group" aria-label="Час">
          {Array.from({ length: 24 }, (_, h) => (
            <button key={h} type="button" className={h === hour ? styles.hourOn : styles.hour}
              onClick={() => setMinute(day * MINUTES_PER_DAY + h * 60 + 30)}>{h}</button>
          ))}
        </div>
      )}
      <div className={styles.scroll}>
        <table className={period === 'week' ? styles.grid : styles.gridDense}>
          <thead>
            <tr>
              <th className={styles.stopHead}>Остановка</th>
              {routeByDay.map((r) => (
                <th key={r.day} className={r.day === day ? styles.dayOn : undefined}>
                  <button type="button" onClick={() => setMinute(r.day * MINUTES_PER_DAY + hour * 60 + 30)}
                    title={`${weekdayName(r.day)}, ${shortDate(isoDate(r.day))}: перейти к этому дню`}>
                    {period === 'week' ? <>{weekdayName(r.day, true)}<small>{shortDate(isoDate(r.day))}</small></>
                      : isoDate(r.day).slice(8, 10).replace(/^0/, '')}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.stopId} className={s.stopId === stop ? styles.rowOn : undefined}>
                <th className={styles.stopName} title={s.name}>
                  <button type="button" onClick={() => selectStop(s.stopId === stop ? null : s.stopId)}>
                    <i>{s.seq}</i>{s.name}
                  </button>
                </th>
                {routeByDay.map((r) => {
                  const v = cell(s.share, r.value);
                  const isPeak = s.stopId === peakStop && r.day === peakDay;
                  return (
                    <td key={r.day} style={{ background: heat(v, max) }}
                      className={`${r.day === day ? styles.cellDay : ''} ${isPeak ? styles.cellPeak : ''}`}
                      title={`${s.name}, ${weekdayName(r.day, true)} ${shortDate(isoDate(r.day))}: ${fmtInt(v)} ${label}`}
                      onClick={() => { setMinute(r.day * MINUTES_PER_DAY + hour * 60 + 30); selectStop(s.stopId); }}>
                      {period === 'week' ? fmtInt(v) : ''}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th className={styles.stopName}>Весь маршрут</th>
              {routeByDay.map((r) => (
                <td key={r.day} className={r.day === day ? styles.cellDay : undefined} title={`${fmtInt(r.value)} ${label}`}>
                  {period === 'week' ? fmtCompact(r.value) : ''}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      <p className={styles.note}>
        {pending ? 'Загружаем дни… ' : ''}Остановки посадки в валидациях нет: посадки маршрута делятся по долям остановок,
        это оценка. Белая рамка - самая загруженная клетка. Клик по клетке переносит время и выделяет остановку на карте.
        {embedded ? ' Клавиши: Shift + ← → - день, Shift + ↑ ↓ - час.'
          : ' Клавиши: S - открыть и закрыть, ← → - день, ↑ ↓ - час, Esc - закрыть.'}
      </p>
    </section>
  );
}
