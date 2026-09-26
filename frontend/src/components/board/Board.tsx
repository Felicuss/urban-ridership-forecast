import { useEffect, useState } from 'react';
import { useCalendar, useFactors, useNetworkLoad, useRouteStops } from '../../api/queries';
import type { Factors, NetworkLoad } from '../../api/types';
import { useAlerts } from '../../hooks/useDispatch';
import { centerWeather, useWeatherGrid } from '../../hooks/useWeather';
import { newsLine, useNews } from '../../hooks/useNews';
import { routeTitle } from '../../hooks/useTarget';
import { useStore } from '../../state/store';
import { CAPACITY, headway, tripsPerHour } from '../../lib/dispatch';
import { clock, dayIndex, dayLabel, hourOf, isoDate } from '../../lib/time';
import { fmtCompact, fmtInt, fmtTemp } from '../../lib/format';
import { SKY_LABEL } from '../../lib/weather';
import { ROUTE_IDS, routeColor } from '../../lib/routes';
import { Sparkline } from '../charts/Sparkline';
import { Icon } from '../ui/Icons';
import styles from './Board.module.css';

// Табло на большой экран диспетчерской: крупные числа по одному маршруту, маршруты сменяются сами каждые
// CYCLE_MS, внизу все маршруты сразу. Время берётся из шкалы: в режиме «Сейчас» табло живое.

const CYCLE_MS = 8000;

interface RouteNow {
  route: number;
  now: number;
  next: number;
  perTrip: number | null;
  hw: number | null;
  hours: number[];
}

function routeNow(route: number, load: NetworkLoad | undefined, factors: Factors | undefined, dayOff: boolean,
  hour: number): RouteNow {
  const hours = load?.routes.get(route) ?? [];
  const hw = headway(factors, route, dayOff, hour);
  const now = hours[hour] ?? 0;
  return { route, now, next: hours[Math.min(hour + 1, 23)] ?? 0, hw, hours, perTrip: hw ? now / tripsPerHour(hw) : null };
}

function tone(perTrip: number | null): string {
  if (perTrip == null) return styles.idle ?? '';
  if (perTrip > CAPACITY) return styles.hot ?? '';
  return perTrip > 0.8 * CAPACITY ? (styles.warm ?? '') : (styles.calm ?? '');
}

export function Board() {
  const setBoardOpen = useStore((s) => s.setBoardOpen);
  const minute = useStore((s) => s.minute);
  const scenario = useStore((s) => s.scenario);
  const followNow = useStore((s) => s.followNow);
  const day = dayIndex(minute);
  const hour = hourOf(minute);
  const load = useNetworkLoad(isoDate(day), scenario).data;
  const factors = useFactors().data;
  const dayOff = useCalendar().data?.[day]?.dayOff ?? false;
  const weather = centerWeather(useWeatherGrid(isoDate(day)).data, hour);
  const hidden = useStore((s) => s.hiddenRoutes);
  // все маршруты скрыты фильтром - табло всё равно показывает сеть целиком, пустым оно не бывает
  const shown = ROUTE_IDS.filter((r) => !hidden.includes(r));
  const routes = (shown.length ? shown : ROUTE_IDS).map((r) => routeNow(r, load, factors, dayOff, hour));
  const running = routes.filter((r) => r.now > 0);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const spot = running.length ? running[index % running.length]! : routes[0]!;

  useEffect(() => {
    if (paused || running.length < 2) return undefined;
    const t = setInterval(() => setIndex((i) => i + 1), CYCLE_MS);
    return () => clearInterval(t);
  }, [paused, running.length]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setBoardOpen(false);
      if (e.key === ' ') {
        e.preventDefault();
        setPaused((p) => !p);
      }
      if (e.key === 'ArrowRight') setIndex((i) => i + 1);
      if (e.key === 'ArrowLeft') setIndex((i) => i + running.length - 1);
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [setBoardOpen, running.length]);

  useEffect(() => () => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
  }, []);

  const total = routes.reduce((a, r) => a + r.now, 0);

  return (
    <div className={styles.board} role="dialog" aria-label="Табло диспетчерской">
      <header className={styles.top}>
        <div className={styles.brand}>Час пик <span>табло</span></div>
        <div className={styles.when}>
          <b className="num">{clock(minute)}</b>
          <span>{dayLabel(day)}{followNow ? '' : ' · не текущее время'}</span>
        </div>
        {weather && <div className={styles.weather}><b className="num">{fmtTemp(weather.temp)}</b>{SKY_LABEL[weather.sky]}</div>}
        <div className={styles.net}>
          <span>вся сеть в этот час</span>
          <b className="num">{fmtCompact(total)}</b>
        </div>
        <button type="button" className={styles.close} onClick={() => setBoardOpen(false)} aria-label="Закрыть табло"
          title="Закрыть табло (Esc)"><Icon.close /></button>
      </header>

      <Spotlight key={spot.route} spot={spot} factors={factors} load={load} hour={hour} />

      <div className={styles.progress} aria-hidden="true">
        {!paused && running.length > 1 && <i key={`${spot.route}-${index}`} style={{ animationDuration: `${CYCLE_MS}ms` }} />}
      </div>

      <nav className={styles.strip} aria-label="Все маршруты">
        {routes.map((r) => (
          <button key={r.route} type="button" className={`${styles.tile} ${tone(r.perTrip)} ${r.route === spot.route ? styles.tileOn : ''}`}
            style={{ '--c': routeColor(r.route) } as React.CSSProperties}
            onClick={() => { const i = running.findIndex((x) => x.route === r.route); if (i >= 0) { setIndex(i); setPaused(true); } }}>
            <span className={styles.tileNo}>{r.route}</span>
            <b className="num">{r.perTrip != null && r.now > 0 ? fmtInt(r.perTrip) : '-'}</b>
            <small>{r.now > 0 ? 'на рейс' : 'не ходит'}</small>
          </button>
        ))}
      </nav>

      <Ticker day={day} />
      <p className={styles.help}>{paused ? 'Смена маршрутов на паузе' : 'Маршруты сменяются каждые 8 секунд'}.
        Пробел - пауза, стрелки - листать, Esc - выйти.</p>
    </div>
  );
}

function Spotlight({ spot, factors, load, hour }: { spot: RouteNow; factors: Factors | undefined; load: NetworkLoad | undefined;
  hour: number }) {
  const stops = useRouteStops(spot.route).data;
  const top = (stops ?? [])
    .map((s) => ({ name: s.name, v: load?.stops.get(s.stopId)?.[hour] ?? 0 }))
    .filter((s, i, all) => all.findIndex((x) => x.name === s.name) === i)
    .sort((a, b) => b.v - a.v).slice(0, 3);
  const trend = spot.next - spot.now;
  return (
    <section className={styles.spot} style={{ '--c': routeColor(spot.route) } as React.CSSProperties}>
      <div className={styles.spotHead}>
        <span className={styles.spotNo}>{spot.route}</span>
        <div>
          <h2>{routeTitle(factors, spot.route) || `Маршрут ${spot.route}`}</h2>
          <p>{hour}:00-{hour + 1}:00 · прогноз посадок</p>
        </div>
      </div>
      <div className={styles.numbers}>
        <div><span>посадок в час</span><b className="num">{fmtInt(spot.now)}</b></div>
        <div className={tone(spot.perTrip)}><span>на один рейс</span><b className="num">{spot.perTrip != null ? fmtInt(spot.perTrip) : '-'}</b>
          <small>{spot.perTrip != null && spot.perTrip > CAPACITY ? `больше ${CAPACITY}: вагон переполнен` : `вагон ${CAPACITY} человек`}</small></div>
        <div><span>интервал</span><b className="num">{spot.hw ? `${spot.hw} мин` : '-'}</b><small>по расписанию</small></div>
        <div><span>следующий час</span><b className="num">{fmtInt(spot.next)}</b>
          <small className={trend > 0 ? styles.upText : styles.downText}>{trend > 0 ? '▲' : trend < 0 ? '▼' : '='} {fmtInt(Math.abs(trend))}</small></div>
      </div>
      <div className={styles.curve}>
        <div className={styles.curveBox}>
          <Sparkline values={spot.hours} color={routeColor(spot.route)} width={960} height={140} />
          <i className={styles.nowLine} style={{ left: `${(hour / 23) * 100}%` }} />
        </div>
        <div className={styles.axis}><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div>
      </div>
      {top.length > 0 && (
        <p className={styles.stops}>Больше всего входят: {top.map((s) => `${s.name} ${fmtInt(s.v)}`).join(' · ')}</p>
      )}
    </section>
  );
}

/** Бегущая строка: сработавшие оповещения на завтра и сбои из новостей за этот день. */
function Ticker({ day }: { day: number }) {
  const { states } = useAlerts();
  const news = useNews().data?.filter((n) => n.start.slice(0, 10) === isoDate(day)) ?? [];
  const items = [
    ...states.filter((s) => s.spans.length).map((s) => `Завтра №${s.rule.route}${s.rule.segment ? ` (${s.rule.segment.label})` : ''}: `
      + s.spans.map((x) => `${x.from}-${x.to} ч до ${fmtInt(x.peak)} на рейс`).join(', ')),
    ...news.map((n) => `Сегодня ${newsLine(n)}`),
  ];
  if (items.length === 0) return null;
  return <div className={styles.ticker}><span>{items.join('   •   ')}</span></div>;
}
