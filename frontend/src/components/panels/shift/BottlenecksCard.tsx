import { useMemo, useState } from 'react';
import { useFactors } from '../../../api/queries';
import { useDaysLoad, useManyRouteStops } from '../../../hooks/useDispatch';
import { useStore } from '../../../state/store';
import { CAPACITY, bottlenecks, intervalAdvice } from '../../../lib/dispatch';
import { MINUTES_PER_DAY, dayIndex, isoDate, shortDate, weekdayName } from '../../../lib/time';
import { fmtInt, plural } from '../../../lib/format';
import { ROUTE_IDS, routeColor } from '../../../lib/routes';
import { Card, TramDots } from '../../ui/Controls';
import panels from '../Panels.module.css';
import styles from './Shift.module.css';

const DAYS = 7;
const SHOWN = 8;

/** Рейтинг узких мест на неделю вперёд: где и когда на рейс входит больше людей, чем помещается в вагон. */
export function BottlenecksCard() {
  const day = useStore((s) => dayIndex(s.minute));
  const setMinute = useStore((s) => s.setMinute);
  const selectRoute = useStore((s) => s.selectRoute);
  const factors = useFactors().data;
  const { days, pending } = useDaysLoad(day, DAYS);
  const stops = useManyRouteStops(ROUTE_IDS);
  const [limit, setLimit] = useState(CAPACITY);
  const [all, setAll] = useState(false);
  const list = useMemo(() => bottlenecks(days, factors, ROUTE_IDS, limit, stops), [days, factors, limit, stops]);
  const byRoute = list.reduce((m, b) => m.set(b.route, (m.get(b.route) ?? 0) + 1), new Map<number, number>());
  const worst = [...byRoute.entries()].sort((a, b) => b[1] - a[1])[0];

  return (
    <Card id="shift-bottlenecks" title={`Узкие места на ${DAYS} дней`}
      info="Маршрут, день и часы, где посадок на один рейс больше порога. Рейсы - по расписанию transport.mos.ru, посадки - прогноз по умолчанию без сценария. Остановка - где в час пика входит больше всего людей. Клик по строке показывает этот час на карте.">
      <div className={panels.coefHead}>
        <span>Порог посадок на рейс</span>
        <span className={panels.coefValue}>{limit}</span>
      </div>
      <input className={panels.range} type="range" min={100} max={300} step={5} value={limit} aria-label="Порог посадок на рейс"
        style={{ '--fill': `${((limit - 100) / 200) * 100}%` } as React.CSSProperties} onChange={(e) => setLimit(Number(e.target.value))} />
      {pending && days.length === 0 ? <TramDots label="Считаем неделю" /> : (
        <>
          <p className={styles.meta}>
            {list.length === 0
              ? `За ${days.length} ${plural(days.length, ['день', 'дня', 'дней'])} везде меньше ${limit} посадок на рейс.`
              : `${list.length} ${plural(list.length, ['отрезок', 'отрезка', 'отрезков'])} на ${byRoute.size}`
                + ` ${plural(byRoute.size, ['маршруте', 'маршрутах', 'маршрутах'])}`
                + (worst ? `, чаще всего №${worst[0]}` : '') + '.'}
          </p>
          <ol className={styles.rows}>
            {list.slice(0, all ? list.length : SHOWN).map((b) => (
              <li key={`${b.day}-${b.route}-${b.from}`}>
                <button type="button" className={styles.rowBtn} title="Показать этот день, час и маршрут"
                  onClick={() => { selectRoute(b.route); setMinute(b.day * MINUTES_PER_DAY + b.peakHour * 60 + 30); }}>
                  <span className={styles.badge} style={{ '--c': routeColor(b.route) } as React.CSSProperties}>{b.route}</span>
                  <span>{weekdayName(b.day, true)} {shortDate(isoDate(b.day))}, {b.from}-{b.to} ч:
                    до <b className="num">{fmtInt(b.peak)}</b> на рейс</span>
                  <small>{intervalAdvice(b)}{b.stop ? `; больше всего входят на «${b.stop}»` : ''}</small>
                </button>
              </li>
            ))}
          </ol>
          {list.length > SHOWN && (
            <button type="button" className={styles.more} onClick={() => setAll((v) => !v)}>
              {all ? 'Свернуть' : `Показать все ${list.length}`}
            </button>
          )}
        </>
      )}
    </Card>
  );
}
