import { Suspense, lazy, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  networkLoadQuery, useCalendar, useCoefficients, useFactors, useMeta, useNetwork, useNetworkLoad, useRouteStops,
} from './api/queries';
import { useWeatherGrid } from './hooks/useWeather';
import { useStore } from './state/store';
import { useClock } from './hooks/useClock';
import { useHotkeys } from './hooks/useHotkeys';
import { TIMELINE_DAYS, dayIndex, isoDate } from './lib/time';
import { LEAVE_MS, TramLoader } from './components/boot/TramLoader';
import { TopBar } from './components/layout/TopBar';
import { RouteList } from './components/layout/RouteList';
import { StopsPanel } from './components/layout/StopsPanel';
import { Timeline } from './components/layout/Timeline';
import { MapOverlay } from './components/map/MapOverlay';
import { StationMatrix } from './components/panels/StationMatrix';
import { PanelsBoard, SplitPane } from './components/layout/Workspace';
import { useLayout } from './state/layout';
import { TramDots } from './components/ui/Controls';
import { Tour, tourSeen } from './components/tour/Tour';
import styles from './App.module.css';

// Карта и правая панель грузятся отдельными чанками параллельно с данными, пока идёт заставка.
const MapView = lazy(() => import('./components/map/MapView'));
const RightPanel = lazy(() => import('./components/panels/RightPanel'));
const Board = lazy(() => import('./components/board/Board').then((m) => ({ default: m.Board })));

type Phase = 'loading' | 'leaving' | 'done';

/** Трамвай виден не меньше 1,4 с, даже если данные пришли из кэша. */
const LOADER_MIN_MS = 1400;
/** Подложка идёт с внешнего tiles.openfreemap.org: при медленной сети заставка не ждёт её дольше 10 с. */
const MAP_WAIT_MS = 10000;

export function App() {
  useClock();
  useHotkeys();
  const intro = useStore((s) => s.flags.intro);
  const motion = useStore((s) => s.flags.motion);
  const day = useStore((s) => dayIndex(s.minute));
  const scenario = useStore((s) => s.scenario);
  const route = useStore((s) => s.route);
  const stopsOpen = useStore((s) => s.stopsOpen);
  const boardOpen = useStore((s) => s.boardOpen);
  const matrixOpen = useStore((s) => s.matrixOpen);
  const layout = useLayout((s) => s.mode);
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
  useEffect(() => {
    const t = setTimeout(() => setMinLoader(true), LOADER_MIN_MS);
    const map = setTimeout(() => setMapReady(true), MAP_WAIT_MS);
    return () => {
      clearTimeout(t);
      clearTimeout(map);
    };
  }, []);

  // трамвай уезжает в тоннель, только когда готовы и данные, и карта: под заставкой уже всё нарисовано
  useEffect(() => {
    if (phase === 'loading' && dataReady && mapReady && minLoader) setPhase('leaving');
  }, [phase, dataReady, mapReady, minLoader]);
  useEffect(() => {
    if (phase !== 'leaving') return undefined;
    const t = setTimeout(() => setPhase('done'), motion ? LEAVE_MS : 0);
    return () => clearTimeout(t);
  }, [phase, motion]);

  // первый вход: тур по разделам, когда заставка ушла и данные на экране
  useEffect(() => {
    if (phase !== 'done' || !dataReady || boardOpen || tourSeen()) return undefined;
    const t = setTimeout(() => useStore.getState().setTourOpen(true), 800);
    return () => clearTimeout(t);
  }, [phase, dataReady, boardOpen]);

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
        {stopsOpen && route != null && <StopsPanel key={route} route={route} load={load.data} />}
      </aside>
      <main className={styles.map} data-layout={layout}>
        <div className={styles.mapPane} hidden={layout === 'panels'} data-tour="map">
          {network.data && (
            <Suspense fallback={null}>
              <MapView
                network={network.data}
                load={load.data}
                factors={factors.data}
                calendar={calendar.data}
                weather={weatherOn ? weather.data : undefined}
                rideStopsData={routeStops.data}
                revealed={phase !== 'loading'}
                onReady={() => setMapReady(true)}
              />
            </Suspense>
          )}
          {phase === 'done' || !intro ? <MapOverlay load={load.data} weather={weatherOn ? weather.data : undefined} /> : null}
          {matrixOpen && route != null && <StationMatrix key={route} route={route} />}
        </div>
        {layout === 'split' && <SplitPane />}
        {layout === 'panels' && <PanelsBoard />}
      </main>
      <aside className={styles.right} data-tour="panel">
        <Suspense fallback={<div className={styles.pending}><TramDots label="Загружаем панель" /></div>}>
          <RightPanel />
        </Suspense>
      </aside>
      <footer className={styles.bottom} data-tour="timeline">
        <Timeline />
      </footer>
      {failed && <div className={styles.error}>Сервис прогноза не отвечает: {String(failed.message)}</div>}
      {intro && phase !== 'done' && <TramLoader steps={steps} leaving={phase === 'leaving'} />}
      {boardOpen && <Suspense fallback={null}><Board /></Suspense>}
      <Tour />
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
