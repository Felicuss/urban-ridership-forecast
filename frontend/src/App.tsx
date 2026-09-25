import { Suspense, lazy, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  networkLoadQuery, useCalendar, useCoefficients, useFactors, useMeta, useNetwork, useNetworkLoad, useRouteStops,
} from './api/queries';
import { useWeatherGrid } from './hooks/useWeather';
import { useStore } from './state/store';
import { useClock } from './hooks/useClock';
import { TIMELINE_DAYS, dayIndex, isoDate } from './lib/time';
import { TramLoader } from './components/boot/TramLoader';
import { CloudReveal } from './components/boot/CloudReveal';
import { TopBar } from './components/layout/TopBar';
import { RouteList } from './components/layout/RouteList';
import { Timeline } from './components/layout/Timeline';
import { MapOverlay } from './components/map/MapOverlay';
import { TramDots } from './components/ui/Controls';
import styles from './App.module.css';

// Карта и правая панель грузятся отдельными чанками параллельно с данными, пока идёт заставка.
const MapView = lazy(() => import('./components/map/MapView'));
const RightPanel = lazy(() => import('./components/panels/RightPanel'));

type Phase = 'loading' | 'clouds' | 'revealing' | 'done';

/** Трамвай виден не меньше 1,4 с, облака стоят 0,7 с перед тем, как разойтись. */
const LOADER_MIN_MS = 1400;
const CLOUDS_HOLD_MS = 700;

export function App() {
  useClock();
  const intro = useStore((s) => s.flags.intro);
  const motion = useStore((s) => s.flags.motion);
  const day = useStore((s) => dayIndex(s.minute));
  const scenario = useStore((s) => s.scenario);
  const route = useStore((s) => s.route);
  const meta = useMeta();
  const network = useNetwork();
  const factors = useFactors();
  const coefficients = useCoefficients();
  const load = useNetworkLoad(isoDate(day), scenario);
  const calendar = useCalendar();
  const weatherOn = useStore((s) => s.flags.weather);
  const weather = useWeatherGrid(isoDate(day), weatherOn);
  const routeStops = useRouteStops(route);
  const [mapReady, setMapReady] = useState(false);
  const [phase, setPhase] = useState<Phase>(intro ? 'loading' : 'done');
  usePrefetchNeighbours(day);

  useEffect(() => {
    document.documentElement.dataset.motion = motion ? 'on' : 'off';
  }, [motion]);

  const dataReady = Boolean(meta.data && network.data && factors.data && load.data && calendar.data);
  const failed = meta.error ?? network.error ?? factors.error ?? load.error;

  const [minLoader, setMinLoader] = useState(!intro);
  const [cloudsHeld, setCloudsHeld] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setMinLoader(true), LOADER_MIN_MS);
    return () => clearTimeout(t);
  }, []);
  useEffect(() => {
    if (phase !== 'clouds') return undefined;
    const t = setTimeout(() => setCloudsHeld(true), CLOUDS_HOLD_MS);
    return () => clearTimeout(t);
  }, [phase]);

  useEffect(() => {
    if (phase === 'loading' && dataReady && minLoader) setPhase('clouds');
    if (phase === 'clouds' && mapReady && cloudsHeld) setPhase('revealing');
  }, [phase, dataReady, mapReady, minLoader, cloudsHeld]);

  const steps = [
    { label: 'Модель', done: Boolean(meta.data && coefficients.data) },
    { label: 'Сеть маршрутов', done: Boolean(network.data) },
    { label: 'Внешние факторы', done: Boolean(factors.data) },
    { label: 'Прогноз на сутки', done: Boolean(load.data) },
    { label: 'Карта', done: mapReady },
  ];

  return (
    <div className={styles.app}>
      <TopBar />
      <aside className={styles.left}>
        <RouteList load={load.data} factors={factors.data} />
      </aside>
      <main className={styles.map}>
        {network.data && (
          <Suspense fallback={null}>
            <MapView
              network={network.data}
              load={load.data}
              factors={factors.data}
              calendar={calendar.data}
              weather={weatherOn ? weather.data : undefined}
              rideStopsData={routeStops.data}
              revealed={phase === 'revealing' || phase === 'done'}
              onReady={() => setMapReady(true)}
            />
          </Suspense>
        )}
        {phase === 'done' || !intro ? <MapOverlay load={load.data} weather={weatherOn ? weather.data : undefined} /> : null}
      </main>
      <aside className={styles.right}>
        <Suspense fallback={<div className={styles.pending}><TramDots label="Загружаем панель" /></div>}>
          <RightPanel />
        </Suspense>
      </aside>
      <footer className={styles.bottom}>
        <Timeline />
      </footer>
      {failed && <div className={styles.error}>Сервис прогноза не отвечает: {String(failed.message)}</div>}
      {intro && (phase === 'loading' || phase === 'clouds') && <TramLoader steps={steps} leaving={phase === 'clouds'} />}
      {intro && (phase === 'clouds' || phase === 'revealing') && (
        <CloudReveal open={phase === 'revealing'} onDone={() => setPhase('done')} />
      )}
    </div>
  );
}

/** Соседние сутки грузятся заранее: перемотка на день вперёд или назад не ждёт сети. */
function usePrefetchNeighbours(day: number) {
  const client = useQueryClient();
  const scenario = useStore((s) => s.scenario);
  useEffect(() => {
    if (Object.keys(scenario.coefficients).length || scenario.events.length) return;
    for (const d of [day - 1, day + 1]) {
      if (d < 0 || d >= TIMELINE_DAYS) continue;
      void client.prefetchQuery(networkLoadQuery(isoDate(d)));
    }
  }, [client, day, scenario]);
}
