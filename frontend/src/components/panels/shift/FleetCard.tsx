import { useState } from 'react';
import { useCalendar, useFactors, useNetwork, useNetworkLoad } from '../../../api/queries';
import { useStore } from '../../../state/store';
import { MIN_HEADWAY, SPEED_KMH, fleet, headway, routeLength, tripsPerHour } from '../../../lib/dispatch';
import { dayIndex, isoDate } from '../../../lib/time';
import { fmt1, fmtInt, plural } from '../../../lib/format';
import { ROUTE_IDS } from '../../../lib/routes';
import { Card, Kpi } from '../../ui/Controls';
import panels from '../Panels.module.css';
import styles from './Shift.module.css';

/** Отстой на конечной по умолчанию, минуты: подбирается под свою конечную. */
const LAYOVER_MIN = 5;
const MAX_HEADWAY = 20;

/**
 * Калькулятор выпуска: интервал в выбранные часы превращается в число вагонов на линии, посадки на рейс
 * по прогнозу и вагоно-часы. Рядом те же числа по расписанию transport.mos.ru.
 */
export function FleetCard() {
  const selected = useStore((s) => s.route);
  const day = useStore((s) => dayIndex(s.minute));
  const scenario = useStore((s) => s.scenario);
  const factors = useFactors().data;
  const network = useNetwork().data;
  const dayOff = useCalendar().data?.[day]?.dayOff ?? false;
  const load = useNetworkLoad(isoDate(day), scenario).data;
  const [route, setRoute] = useState(selected ?? 17);
  const [from, setFrom] = useState(7);
  const [to, setTo] = useState(10);
  const [hw, setHw] = useState<number | null>(null);
  const [speed, setSpeed] = useState(SPEED_KMH);
  const [layover, setLayover] = useState(LAYOVER_MIN);

  const hours = Array.from({ length: Math.max(to - from, 1) }, (_, i) => from + i);
  const scheduled = hours.map((h) => headway(factors, route, dayOff, h));
  const running = scheduled.filter((x): x is number => x != null);
  const baseHw = running.length ? Math.min(...running) : 10;
  const interval = hw ?? baseHw;
  const length = routeLength(network, route);
  const plan = fleet(length, speed, layover, interval);
  const boardings = hours.map((h) => load?.routes.get(route)?.[h] ?? 0);
  const perTripNew = Math.max(...boardings.map((b) => b / tripsPerHour(interval)));
  const perTripNow = Math.max(...boardings.map((b, i) => (scheduled[i] ? b / tripsPerHour(scheduled[i]!) : 0)));
  const vehiclesNow = Math.max(...scheduled.map((x) => (x ? fleet(length, speed, layover, x).vehicles : 0)));
  const hoursNow = scheduled.reduce<number>((a, x) => a + (x ? fleet(length, speed, layover, x).vehicles : 0), 0);
  // пока ползунок не трогали, показываем расписание как есть: часы с разным интервалом не сводятся к одному
  const custom = hw != null;
  const hoursNew = custom ? plan.vehicles * hours.length : hoursNow;
  const vehiclesShown = custom ? plan.vehicles : vehiclesNow;
  const perTripShown = custom ? perTripNew : perTripNow;

  return (
    <Card id="shift-fleet" title="Калькулятор выпуска"
      info={`Оборот - рейс туда и обратно по длине трассы на средней скорости плюс отстой на обеих конечных. Вагонов на линии = оборот ÷ интервал с округлением вверх. Рейсы считаются в каждую сторону. Пока ползунок не тронут, числа - по расписанию. Вагоно-часы - вагоны, умноженные на часы отрезка. Посадки на рейс - прогноз на выбранный день. Трасса №${route}: ${fmt1(length / 1000)} км туда и обратно.`}>
      <div className={styles.form}>
        <label className={styles.field}>
          <span>Маршрут</span>
          <select value={route} onChange={(e) => { setRoute(Number(e.target.value)); setHw(null); }}>
            {ROUTE_IDS.map((r) => <option key={r} value={r}>№{r}</option>)}
          </select>
        </label>
        <label className={styles.field}>
          <span>Часы</span>
          <span className={styles.pair}>
            <input type="number" min={0} max={23} value={from} aria-label="С часа"
              onChange={(e) => { const v = clamp(Number(e.target.value), 0, 23); setFrom(v); if (v >= to) setTo(v + 1); }} />
            <input type="number" min={1} max={24} value={to} aria-label="До часа"
              onChange={(e) => { const v = clamp(Number(e.target.value), 1, 24); setTo(v); if (v <= from) setFrom(v - 1); }} />
          </span>
        </label>
      </div>
      <div className={panels.coefHead}>
        <span>Интервал, мин {hw == null && <small className={styles.hint}>как по расписанию</small>}</span>
        <span className={panels.coefValue}>{interval}</span>
      </div>
      <input className={panels.range} type="range" min={MIN_HEADWAY} max={MAX_HEADWAY} step={1} value={interval}
        aria-label="Интервал движения" style={{ '--fill': `${((interval - MIN_HEADWAY) / (MAX_HEADWAY - MIN_HEADWAY)) * 100}%` } as React.CSSProperties}
        onChange={(e) => setHw(Number(e.target.value))} />
      <div className={styles.kpis2}>
        <Kpi label="Вагонов на линии" value={vehiclesShown} sub={`по расписанию ${vehiclesNow || '-'}`}
          tone={vehiclesShown > vehiclesNow ? 'down' : undefined} />
        <Kpi label="Посадок на рейс" value={fmtInt(perTripShown)} sub={`по расписанию ${fmtInt(perTripNow)}`}
          tone={perTripShown < perTripNow ? 'up' : undefined} />
        <Kpi label="Вагоно-часов" value={hoursNew} sub={`по расписанию ${hoursNow || '-'}, ${from}–${to} ч`} />
        <Kpi label="Оборот" value={`${Math.round(plan.cycle)} мин`} sub={`${fmtTrips(plan.tripsPerHour)} в час`} />
      </div>
      <div className={styles.form}>
        <label className={styles.field}>
          <span>Скорость, км/ч</span>
          <input type="number" min={8} max={30} value={speed} onChange={(e) => setSpeed(clamp(Number(e.target.value), 8, 30))} />
        </label>
        <label className={styles.field}>
          <span>Отстой, мин</span>
          <input type="number" min={0} max={30} value={layover} onChange={(e) => setLayover(clamp(Number(e.target.value), 0, 30))} />
        </label>
      </div>
    </Card>
  );
}

function clamp(v: number, lo: number, hi: number): number {
  return Number.isFinite(v) ? Math.min(Math.max(Math.round(v), lo), hi) : lo;
}

/** «10 рейсов», «7,5 рейса». */
function fmtTrips(n: number): string {
  return Number.isInteger(n) ? `${n} ${plural(n, ['рейс', 'рейса', 'рейсов'])}` : `${fmt1(n)} рейса`;
}
