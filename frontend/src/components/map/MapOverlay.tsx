import { useState } from 'react';
import type { NetworkLoad } from '../../api/types';
import type { GridPoint } from '../../lib/weatherGrid';
import { useStops } from '../../api/queries';
import { FLAG_LABELS, useStore, type Flags } from '../../state/store';
import { hourOf, sunElevation } from '../../lib/time';
import { fmtInt } from '../../lib/format';
import { ROUTE_COLORS, routeColor, yandexPoint, yandexRouteTo } from '../../lib/routes';
import { Sparkline } from '../charts/Sparkline';
import { Icon } from '../ui/Icons';
import { WeatherFx } from './WeatherFx';
import { flyTo, mapHandle } from './mapHandle';
import styles from './MapOverlay.module.css';

const DOCK: { key: keyof Flags; short: string }[] = [
  { key: 'heat', short: 'Теплокарта' },
  { key: 'lines', short: 'Линии' },
  { key: 'stops', short: 'Остановки' },
  { key: 'trams', short: 'Трамваи' },
  { key: 'metro', short: 'Метро' },
  { key: 'buildings', short: '3D-дома' },
  { key: 'weather', short: 'Погода' },
  { key: 'satellite', short: 'Спутник' },
];

export function MapOverlay({ load, weather }: { load: NetworkLoad | undefined; weather: GridPoint[] | undefined }) {
  const flags = useStore((s) => s.flags);
  const setFlag = useStore((s) => s.setFlag);
  const hour = useStore((s) => hourOf(s.minute));
  const night = useStore((s) => sunElevation(s.minute) < -4);
  const viewMode = useStore((s) => s.viewMode);
  const setViewMode = useStore((s) => s.setViewMode);
  const source = load?.source === 'fact' ? 'факт' : load?.source === 'outlook' ? 'оценка' : 'прогноз';

  return (
    <>
      {flags.weather && <WeatherFx grid={weather} hour={hour} />}
      <div className={styles.view} role="group" aria-label="Вид карты">
        <button type="button" aria-pressed={viewMode === 'top'} className={viewMode === 'top' ? styles.viewOn : ''}
          onClick={() => setViewMode('top')} title="Карта сверху, без наклона">Сверху</button>
        <button type="button" aria-pressed={viewMode === 'perspective'}
          className={viewMode === 'perspective' ? styles.viewOn : ''} onClick={() => setViewMode('perspective')}
          title="Наклон камеры; объёмные дома включаются отдельно">Перспектива</button>
        <button type="button" onClick={() => mapHandle.current?.easeTo({ bearing: 0, duration: 600 })}
          title="Повернуть карту на север">На север</button>
      </div>
      <nav className={styles.dock} aria-label="Слои карты">
        {DOCK.map((d) => (
          <button key={d.key} type="button" aria-pressed={flags[d.key]} title={FLAG_LABELS[d.key].hint}
            className={flags[d.key] ? styles.dockOn : styles.dockBtn} onClick={() => setFlag(d.key, !flags[d.key])}>
            <i />{d.short}
          </button>
        ))}
        <RouteFilter />
      </nav>
      <div className={styles.legend}>
        <div className={styles.legendRow}>
          <span>Посадки в {hour}:00-{hour + 1}:00, {source}</span>
          <span className={styles.ramp} />
          <span className={styles.rampLabels}><small>мало</small><small>много</small></span>
        </div>
        <div className={styles.legendNote}>
          Толщина линии - посадки маршрута в этот час. {night ? 'Ночь: вагоны' : 'Вагоны'} идут с интервалом по расписанию.
        </div>
      </div>
      <StopCard load={load} hour={hour} />
      <RideCard />
    </>
  );
}

function StopCard({ load, hour }: { load: NetworkLoad | undefined; hour: number }) {
  const stopId = useStore((s) => s.stop);
  const selectStop = useStore((s) => s.selectStop);
  const selectRoute = useStore((s) => s.selectRoute);
  const stops = useStops().data;
  const stop = stops?.find((s) => s.id === stopId);
  if (!stopId || !stop) return null;
  const values = load?.stops.get(stop.id);
  const total = values?.reduce((a, b) => a + b, 0) ?? 0;
  return (
    <section className={styles.stop} aria-label={`Остановка ${stop.name}`}>
      <header>
        <div>
          <h3>{stop.name}</h3>
          <div className={styles.chips}>
            {stop.routes.map((r) => (
              <button key={r} type="button" style={{ '--c': routeColor(r) } as React.CSSProperties}
                onClick={() => { selectRoute(r); selectStop(stop.id); }}>{r}</button>
            ))}
          </div>
        </div>
        <button type="button" className={styles.close} aria-label="Закрыть" onClick={() => selectStop(null)}>
          <Icon.close />
        </button>
      </header>
      <div className={styles.stopStats}>
        <div><span>в {hour}:00</span><b className="num">{fmtInt(values?.[hour])}</b></div>
        <div><span>за сутки</span><b className="num">{fmtInt(total)}</b></div>
        <Sparkline values={values} color={routeColor(stop.routes[0])} hour={hour} width={110} height={30} />
      </div>
      <p className={styles.estimate}>Оценка: прогноз маршрутов разложен по долям остановок. Источник координат:
        {stop.source === 'reference' ? ' справочник организаторов' : ' OpenStreetMap'}.</p>
      <div className={styles.stopLinks}>
        <button type="button" onClick={() => flyTo(stop.lon, stop.lat, 16.2)}>Приблизить</button>
        <a href={yandexRouteTo(stop.lat, stop.lon)} target="_blank" rel="noopener noreferrer">
          Как доехать <Icon.external /></a>
        <a href={yandexPoint(stop.lat, stop.lon)} target="_blank" rel="noopener noreferrer">
          Яндекс Карты <Icon.external /></a>
      </div>
    </section>
  );
}

function RideCard() {
  const ride = useStore((s) => s.ride);
  const progress = useStore((s) => s.rideProgress);
  const stopRide = useStore((s) => s.stopRide);
  if (!ride || !progress) return null;
  return (
    <section className={styles.ride} style={{ '--c': routeColor(ride.route) } as React.CSSProperties} aria-live="polite">
      <div className={styles.rideHead}>
        <span className={styles.rideBadge}>{ride.route}</span>
        <div>
          <b>Поездка в {ride.hour}:00</b>
          <small>{progress.stopName ? `остановка «${progress.stopName}»` : 'отправление'}</small>
        </div>
        <button type="button" className={styles.close} aria-label="Остановить поездку" onClick={stopRide}><Icon.close /></button>
      </div>
      <div className={styles.rideStats}>
        <div><span>пройдено остановок</span><b className="num">{progress.passed}</b></div>
        <div><span>сели в вагон</span><b className="num">{fmtInt(progress.boarded)}</b></div>
      </div>
      <p>Сколько сядет за один рейс в этот час: посадки маршрута ÷ рейсы по расписанию × доля остановки.
        Скорость показа ×{ride.speed}.</p>
    </section>
  );
}

const ROUTES = Object.keys(ROUTE_COLORS).map(Number);

/** Какие маршруты видны на карте: линии, вагоны и остановки скрытых маршрутов пропадают. */
function RouteFilter() {
  const hidden = useStore((s) => s.hiddenRoutes);
  const toggleRoute = useStore((s) => s.toggleRoute);
  const setHiddenRoutes = useStore((s) => s.setHiddenRoutes);
  const [open, setOpen] = useState(false);
  const shown = ROUTES.length - hidden.length;
  return (
    <div className={styles.filterWrap}>
      <button type="button" className={hidden.length ? styles.dockOn : styles.dockBtn} aria-expanded={open}
        title="Показать или скрыть маршруты на карте" onClick={() => setOpen((v) => !v)}>
        <i />Маршруты {shown}/{ROUTES.length}
      </button>
      {open && (
        <div className={styles.filter} role="group" aria-label="Маршруты на карте">
          <div className={styles.filterChips}>
            {ROUTES.map((r) => (
              <button key={r} type="button" aria-pressed={!hidden.includes(r)}
                className={hidden.includes(r) ? styles.chipOff : styles.chipOn}
                style={{ '--c': routeColor(r) } as React.CSSProperties} onClick={() => toggleRoute(r)}>{r}</button>
            ))}
          </div>
          <div className={styles.filterActions}>
            <button type="button" onClick={() => setHiddenRoutes([])}>Показать все</button>
            <button type="button" onClick={() => setHiddenRoutes(ROUTES)}>Скрыть все</button>
          </div>
        </div>
      )}
    </div>
  );
}
