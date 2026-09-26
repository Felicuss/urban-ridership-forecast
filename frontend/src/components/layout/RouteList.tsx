import { useCalendar, useRouteStops } from '../../api/queries';
import type { Factors, NetworkLoad } from '../../api/types';
import { useStore } from '../../state/store';
import { dayIndex, hourOf } from '../../lib/time';
import { fmtCompact, fmtInt } from '../../lib/format';
import { ROUTE_COLORS, routeColor, yandexRouteBetween } from '../../lib/routes';
import { routeTitle } from '../../hooks/useTarget';
import { headway } from '../../lib/dispatch';
import { Sparkline } from '../charts/Sparkline';
import { InfoTip } from '../ui/Controls';
import { Icon } from '../ui/Icons';
import { Search } from './Search';
import styles from './RouteList.module.css';

const ROUTES = Object.keys(ROUTE_COLORS).map(Number);

function sum(values: number[] | undefined): number {
  return values ? values.reduce((a, b) => a + b, 0) : 0;
}

export function RouteList({ load, factors }: { load: NetworkLoad | undefined; factors: Factors | undefined }) {
  const route = useStore((s) => s.route);
  const selectRoute = useStore((s) => s.selectRoute);
  const hidden = useStore((s) => s.hiddenRoutes);
  const visible = ROUTES.filter((r) => r === route || !hidden.includes(r));
  const hour = useStore((s) => hourOf(s.minute));
  const sourceLabel = load?.source === 'fact' ? 'факт' : load?.source === 'outlook' ? 'оценка' : 'прогноз';
  const totals = new Map(ROUTES.map((r) => [r, sum(load?.routes.get(r))]));
  const network = [...totals.values()].reduce((a, b) => a + b, 0);
  const networkHours = Array.from({ length: 24 }, (_, h) => ROUTES.reduce((a, r) => a + (load?.routes.get(r)?.[h] ?? 0), 0));
  const max = Math.max(...totals.values(), 1);

  return (
    <div className={styles.panel} data-tour="routes">
      <Search />
      <header className={styles.head}>
        <h2>Маршруты</h2>
        <InfoTip>Посадки - успешные валидации за сутки по прогнозу. Кривая - посадки по часам, точка - выбранный час.
          Полоса - доля маршрута в посадках сети за сутки.</InfoTip>
      </header>
      <button type="button" className={route == null ? styles.rowActive : styles.row} onClick={() => selectRoute(null)}>
        <span className={styles.badgeAll}>все</span>
        <span className={styles.name}>
          <b>Вся сеть</b>
          <small>{fmtInt(network)} посадок за сутки, {sourceLabel}</small>
        </span>
        <Sparkline values={networkHours} color="#e9eef5" hour={hour} width={78} />
      </button>
      <div className={styles.list}>
        {visible.map((r) => {
          const total = totals.get(r) ?? 0;
          const color = routeColor(r);
          return (
            <button key={r} type="button" className={route === r ? styles.rowActive : styles.row}
              onClick={() => selectRoute(route === r ? null : r)} style={{ '--c': color } as React.CSSProperties}>
              <span className={styles.badge}>{r}</span>
              <span className={styles.name}>
                <b className="num">{total > 0 ? fmtCompact(total) : 'нет рейсов'}</b>
                <small>{routeTitle(factors, r) || 'маршрут'}</small>
                <span className={styles.share}><i style={{ width: `${(100 * total) / max}%` }} /></span>
              </span>
              <Sparkline values={load?.routes.get(r)} color={color} hour={hour} width={78} />
            </button>
          );
        })}
      </div>
      {route != null && <RouteCard key={route} route={route} factors={factors} load={load} hour={hour} />}
    </div>
  );
}

function RouteCard({ route, factors, load, hour }: {
  route: number;
  factors: Factors | undefined;
  load: NetworkLoad | undefined;
  hour: number;
}) {
  const stops = useRouteStops(route).data;
  const day = useStore((s) => dayIndex(s.minute));
  const startRide = useStore((s) => s.startRide);
  const ride = useStore((s) => s.ride);
  const stopRide = useStore((s) => s.stopRide);
  const calendar = useCalendar().data;
  const dayOff = calendar?.[day]?.dayOff ?? false;
  const h = headway(factors, route, dayOff, hour);
  const hourLoad = load?.routes.get(route)?.[hour] ?? 0;
  const perTrip = h ? hourLoad / (2 * (60 / h)) : null;
  const schedule = factors?.schedule.routes[String(route)];
  const dir = (d: number) => stops?.filter((s) => s.direction === d) ?? [];
  const ends = (d: number) => {
    const s = dir(d);
    return s.length ? { from: s[0]!, to: s[s.length - 1]! } : null;
  };
  const a = ends(0);
  const b = ends(1);
  const stopsOpen = useStore((s) => s.stopsOpen);
  const setStopsOpen = useStore((s) => s.setStopsOpen);
  const matrixOpen = useStore((s) => s.matrixOpen);
  const setMatrixOpen = useStore((s) => s.setMatrixOpen);
  const stopCount = Math.max(dir(0).length, dir(1).length);

  return (
    <section className={styles.card} style={{ '--c': routeColor(route) } as React.CSSProperties}>
      <div className={styles.cardStats}>
        <div>
          <span className={styles.label}>Интервал сейчас</span>
          <b className="num">{h ? `${h} мин` : '-'}</b>
        </div>
        <div>
          <span className={styles.label}>Рейсов в час</span>
          <b className="num">{h ? Math.round(60 / h) : '-'}</b>
        </div>
        <div>
          <span className={styles.label}>
            Посадок на рейс
            <InfoTip>Посадки маршрута в этот час делим на число рейсов в обе стороны по расписанию transport.mos.ru.
              Это поток входящих, а не наполнение салона: выходы пассажиров в данных не видны.</InfoTip>
          </span>
          <b className="num">{perTrip != null ? fmtInt(perTrip) : '-'}</b>
        </div>
      </div>
      <div className={styles.ride}>
        {ride ? (
          <button type="button" className={styles.rideStop} onClick={stopRide}>Остановить поездку</button>
        ) : (
          [a && { d: 0, e: a }, b && { d: 1, e: b }].filter(Boolean).map((x) => x && (
            <button key={x.d} type="button" className={styles.rideBtn} disabled={hourLoad <= 0}
              onClick={() => startRide(route, x.d)} title={hourLoad <= 0 ? 'В этот час маршрут не возит пассажиров' : undefined}>
              <Icon.tram />
              <span>Пустить трамвай<small>до «{x.e.to.name}»</small></span>
            </button>
          ))
        )}
      </div>
      <button type="button" className={stopsOpen ? styles.stopsBtnOn : styles.stopsBtn} aria-expanded={stopsOpen}
        onClick={() => setStopsOpen(!stopsOpen)} title="Список остановок с посадками и выбор участка маршрута">
        <span>Остановки и участок</span>
        <small className="num">{stopCount || ''}</small>
        <Icon.next />
      </button>
      <button type="button" className={matrixOpen ? styles.stopsBtnOn : styles.stopsBtn} aria-expanded={matrixOpen}
        onClick={() => setMatrixOpen(!matrixOpen)} title="Посадки на каждой остановке по дням недели или месяца (клавиша S)">
        <span>Станции по дням</span>
        <small>S</small>
        <Icon.next />
      </button>
      <div className={styles.links}>
        {schedule?.page && <a href={schedule.page} target="_blank" rel="noopener noreferrer">
          Расписание на transport.mos.ru <Icon.external /></a>}
        {a && <a href={yandexRouteBetween(a.from, a.to)} target="_blank" rel="noopener noreferrer">
          Маршрут в Яндекс Картах <Icon.external /></a>}
      </div>
    </section>
  );
}
