import { useEffect, useRef } from 'react';
import { Map as MapLibre, setWorkerUrl, type GeoJSONSource, type MapLayerMouseEvent } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { Factors, NetworkGeoJson, NetworkLoad, RouteStop } from '../../api/types';
import { useStore } from '../../state/store';
import { dayIndex, hourOf, isoDate } from '../../lib/time';
import { fmtInt } from '../../lib/format';
import { loadBaseStyle } from './style';
import { applyDaylight } from './daylight';
import {
  addNetworkLayers, addTramIcons, ensureMetro, pathFeatures, setHour, setLoadData, setSelection, setVisibility,
  stopFeatures, withLoad, type Scale,
} from './layers';
import { buildLines, headway, tramCollection, tramsAt, type Line } from './trams';
import { RideRunner, rideStops } from './ride';
import { addWeatherLayer, loadWeatherDay, setWeatherHour } from './weatherGrid';
import { mapHandle } from './mapHandle';
import styles from './MapView.module.css';

// MapLibre 6 грузит воркер отдельным модулем: собираем его через Vite и отдаём адрес явно.
setWorkerUrl(workerUrl);

const MOSCOW: [number, number] = [37.62, 55.755];
const FRAME_MS = 33;

interface Props {
  network: NetworkGeoJson;
  load: NetworkLoad | undefined;
  factors: Factors | undefined;
  rideStopsData: RouteStop[] | undefined;
  revealed: boolean;
  onReady: () => void;
}

export default function MapView({ network, load, factors, rideStopsData, revealed, onReady }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const ready = useRef(false);
  const scale = useRef<Scale>({ stop: 1, route: 1 });
  const lines = useRef<Line[]>(buildLines(network));
  const data = useRef({ load, factors, rideStopsData });
  const onReadyRef = useRef(onReady);

  useEffect(() => {
    data.current = { load, factors, rideStopsData };
    onReadyRef.current = onReady;
  });

  useEffect(() => {
    const abort = new AbortController();
    let map: MapLibre | null = null;
    loadBaseStyle(abort.signal).then((style) => {
      if (!container.current) return;
      map = new MapLibre({
        container: container.current, style, center: MOSCOW, zoom: 9.6, pitch: 0, bearing: 0,
        maxPitch: 70, minZoom: 8.5, maxZoom: 18.5, attributionControl: { compact: true },
        canvasContextAttributes: { antialias: true },
      });
      mapRef.current = map;
      mapHandle.current = map;
      map.on('load', () => {
        if (!map) return;
        addTramIcons(map);
        addNetworkLayers(map, pathFeatures(network), stopFeatures(network));
        addWeatherLayer(map);
        bindPointer(map, tooltip.current);
        ready.current = true;
        syncAll(map);
        onReadyRef.current();
      });
    }).catch(() => onReadyRef.current());
    return () => {
      abort.abort();
      mapHandle.current = null;
      map?.remove();
    };
  }, [network]);

  useEffect(() => {
    const map = mapRef.current;
    if (!revealed || !map) return;
    // на узком экране вся сеть видна только с меньшим приближением
    const narrow = map.getContainer().clientWidth < 700;
    map.flyTo({ center: [37.6, 55.765], zoom: narrow ? 10.1 : 11.4, pitch: narrow ? 30 : 48, bearing: -14,
      duration: 2600, essential: true });
  }, [revealed]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready.current || !load) return;
    const { lines: l, points } = withLoad(pathFeatures(network), stopFeatures(network), load, scale.current);
    setLoadData(map, l, points);
    setHour(map, hourOf(useStore.getState().minute), scale.current);
  }, [load, network]);

  useEffect(() => {
    let last = -1;
    let lastHour = -1;
    let lastDay = -1;
    let lastLight = -1;
    let lastTrams = -1;
    let lastLoad: NetworkLoad | undefined;
    let raf = 0;
    let runner: RideRunner | null = null;
    let runnerKey = '';
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      const map = mapRef.current;
      if (!map || !ready.current || now - last < FRAME_MS) return;
      last = now;
      const s = useStore.getState();
      const hour = hourOf(s.minute);
      if (hour !== lastHour) {
        lastHour = hour;
        setHour(map, hour, scale.current);
        setWeatherHour(map, hour);
      }
      const day = dayIndex(s.minute);
      if (day !== lastDay && s.flags.weather) {
        lastDay = day;
        loadWeatherDay(map, isoDate(day));
      }
      if (Math.abs(s.minute - lastLight) >= 5) {
        lastLight = s.minute;
        applyDaylight(map, s.minute, s.flags.daylight);
      }
      // вагоны пересчитываются, только когда сдвинулось время или пришли новые посадки
      if (s.flags.trams && (s.minute !== lastTrams || data.current.load !== lastLoad)) {
        lastTrams = s.minute;
        lastLoad = data.current.load;
        drawTrams(map, s.minute);
      }
      const key = s.ride ? `${s.ride.route}:${s.ride.direction}:${s.ride.startedAt}` : '';
      if (key !== runnerKey) {
        runner?.clear();
        runner = s.ride ? makeRunner(map, s.ride.route, s.ride.direction, s.ride.hour, s.ride.speed, s.ride.startedAt) : null;
        runnerKey = key;
      }
      if (runner && s.ride) {
        const f = runner.frame(now, true);
        const p = s.rideProgress;
        if (!p || p.passed !== f.passed || p.finished !== f.finished) s.setRideProgress(f);
        if (f.finished) s.stopRide();
      }
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => useStore.subscribe((s, prev) => {
    const map = mapRef.current;
    if (!map || !ready.current) return;
    if (s.flags !== prev.flags) {
      if (s.flags.metro) void ensureMetro(map).then(() => setVisibility(map, useStore.getState().flags));
      setVisibility(map, s.flags);
      if (!s.flags.trams) (map.getSource('trams') as GeoJSONSource | undefined)?.setData(tramCollection([]));
      if (s.flags.trams && !prev.flags.trams) drawTrams(map, s.minute);
    }
    if (s.route !== prev.route || s.stop !== prev.stop) setSelection(map, s.route, s.stop);
    if (s.route !== prev.route && s.route != null && !s.ride) fitRoute(map, s.route);
  }), []);

  function drawTrams(map: MapLibre, minute: number) {
    const { load: l, factors: f } = data.current;
    const day = dayIndex(minute);
    const dayOff = f?.calendar[day]?.day_off ?? false;
    const trams = tramsAt(lines.current, minute, f, dayOff, l);
    (map.getSource('trams') as GeoJSONSource | undefined)?.setData(tramCollection(trams));
  }

  function makeRunner(map: MapLibre, route: number, direction: number, hour: number, speed: number, startedAt: number) {
    const line = lines.current.find((x) => x.route === route && x.direction === direction);
    const { load: l, factors: f, rideStopsData: stops } = data.current;
    if (!line || !stops) return null;
    const day = dayIndex(useStore.getState().minute);
    const h = headway(f, route, f?.calendar[day]?.day_off ?? false, hour) ?? 10;
    const hourLoad = l?.routes.get(route)?.[l.hours.indexOf(hour)] ?? 0;
    return new RideRunner(map, line, rideStops(line, stops, hourLoad, h), speed, startedAt);
  }

  function fitRoute(map: MapLibre, route: number) {
    const coords = lines.current.filter((x) => x.route === route).flatMap((x) => x.path.coords);
    if (coords.length === 0) return;
    const lons = coords.map((c) => c[0]);
    const lats = coords.map((c) => c[1]);
    map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 80, pitch: 45, duration: 1200, maxZoom: 14 });
  }

  function syncAll(map: MapLibre) {
    const s = useStore.getState();
    setVisibility(map, s.flags);
    if (s.flags.metro) void ensureMetro(map).then(() => setVisibility(map, useStore.getState().flags));
    setSelection(map, s.route, s.stop);
    const l = data.current.load;
    if (l) {
      const { lines: ls, points } = withLoad(pathFeatures(network), stopFeatures(network), l, scale.current);
      setLoadData(map, ls, points);
    }
    setHour(map, hourOf(s.minute), scale.current);
    applyDaylight(map, s.minute, s.flags.daylight);
  }

  return (
    <div className={styles.wrap}>
      <div ref={container} className={styles.map} />
      <div ref={tooltip} className={styles.tooltip} />
    </div>
  );
}

/** Подсказка при наведении и выбор кликом: остановка - посадки в этот час, линия - маршрут. */
function bindPointer(map: MapLibre, tip: HTMLDivElement | null) {
  const show = (e: MapLayerMouseEvent, html: string) => {
    if (!tip) return;
    tip.innerHTML = html;
    tip.style.transform = `translate(${e.point.x + 14}px, ${e.point.y + 14}px)`;
    tip.style.opacity = '1';
    map.getCanvas().style.cursor = 'pointer';
  };
  const hide = () => {
    if (tip) tip.style.opacity = '0';
    map.getCanvas().style.cursor = '';
  };
  const esc = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  map.on('mousemove', 'stops-dot', (e) => {
    const p = e.features?.[0]?.properties ?? {};
    const hour = hourOf(useStore.getState().minute);
    show(e, `<b>${esc(p.name)}</b><span>маршруты ${esc(String(p.routes).trim().replaceAll(' ', ', '))}</span>`
      + `<span>${fmtInt(Number(p[`h${hour}`] ?? 0))} посадок в ${hour}:00-${hour + 1}:00</span>`);
  });
  map.on('mousemove', 'route-lines', (e) => {
    if (map.queryRenderedFeatures(e.point, { layers: ['stops-dot'] }).length) return;
    const p = e.features?.[0]?.properties ?? {};
    const hour = hourOf(useStore.getState().minute);
    show(e, `<b>Маршрут ${esc(p.route)}</b><span>${fmtInt(Number(p[`l${hour}`] ?? 0))} посадок в ${hour}:00-${hour + 1}:00</span>`);
  });
  map.on('mouseleave', 'stops-dot', hide);
  map.on('mouseleave', 'route-lines', hide);
  map.on('click', 'stops-dot', (e) => {
    const id = e.features?.[0]?.properties?.id;
    if (id) useStore.getState().selectStop(String(id));
  });
  map.on('click', 'route-lines', (e) => {
    if (map.queryRenderedFeatures(e.point, { layers: ['stops-dot'] }).length) return;
    const route = Number(e.features?.[0]?.properties?.route);
    if (Number.isFinite(route)) useStore.getState().selectRoute(route);
  });
}

