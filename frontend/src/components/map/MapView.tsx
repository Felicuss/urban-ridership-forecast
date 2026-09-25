import { useEffect, useRef } from 'react';
import { Map as MapLibre, setWorkerUrl, type GeoJSONSource, type MapLayerMouseEvent } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { CalendarDay, Factors, NetworkGeoJson, NetworkLoad, RouteStop } from '../../api/types';
import type { GridPoint } from '../../lib/weatherGrid';
import { useStore } from '../../state/store';
import { dayIndex, hourOf, sunElevation } from '../../lib/time';
import { fmtInt } from '../../lib/format';
import { loadBaseStyle } from './style';
import { applyDaylight } from './daylight';
import {
  addNetworkLayers, addTramIcons, ensureMetro, pathFeatures, setHour, setLoadData, setSelection, setVisibility,
  stopFeatures, TRAMS_3D_ZOOM, withLoad, type Scale,
} from './layers';
import { buildLines, headway, tramBodies, tramCollection, tramScale, tramsAt, type Line, type TramState } from './trams';
import { RideRunner, rideStops } from './ride';
import { addWeatherLayer, setWeatherData, setWeatherHour } from './weatherGrid';
import { mapHandle } from './mapHandle';
import { segmentBounds, segmentShape } from './segment';
import { routeColor } from '../../lib/routes';
import styles from './MapView.module.css';

// MapLibre 6 грузит воркер отдельным модулем: собираем его через Vite и отдаём адрес явно.
setWorkerUrl(workerUrl);

const MOSCOW: [number, number] = [37.62, 55.755];
const FRAME_MS = 33;

interface Props {
  network: NetworkGeoJson;
  load: NetworkLoad | undefined;
  factors: Factors | undefined;
  calendar: CalendarDay[] | undefined;
  weather: GridPoint[] | undefined;
  rideStopsData: RouteStop[] | undefined;
  revealed: boolean;
  onReady: () => void;
}

export default function MapView({ network, load, factors, calendar, weather, rideStopsData, revealed, onReady }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const ready = useRef(false);
  const scale = useRef<Scale>({ stop: 1, route: 1 });
  const lines = useRef<Line[]>(buildLines(network));
  const data = useRef({ load, factors, calendar, rideStopsData });
  const rideTram = useRef<TramState | null>(null);
  const onReadyRef = useRef(onReady);

  useEffect(() => {
    data.current = { load, factors, calendar, rideStopsData };
    onReadyRef.current = onReady;
  });

  useEffect(() => {
    // остановки маршрута приходят позже выбора участка: как только они есть, участок рисуется
    const map = mapRef.current;
    if (map && ready.current) drawSegment(map, false);
  }, [rideStopsData]);

  useEffect(() => {
    const abort = new AbortController();
    let map: MapLibre | null = null;
    loadBaseStyle(abort.signal).then((style) => {
      if (!container.current) return;
      map = new MapLibre({
        // положение карты пишется в адрес (#map=zoom/lat/lon/bearing/pitch): ссылкой на вид можно поделиться
        container: container.current, style, center: MOSCOW, zoom: 9.6, pitch: 0, bearing: 0, hash: 'map',
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
        // вагоны в кадре пересчитываются и без хода времени, когда карту сдвинули или приблизили
        map.on('moveend', () => drawTrams(map!, useStore.getState().minute));
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
    // вид из ссылки не перебиваем облётом
    if (window.location.hash.includes('map=')) return;
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
    const map = mapRef.current;
    if (!map || !ready.current) return;
    setWeatherData(map, weather);
    setWeatherHour(map, hourOf(useStore.getState().minute));
  }, [weather]);

  useEffect(() => {
    let last = -1;
    let lastHour = -1;
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
        rideTram.current = null;
        runner = s.ride ? makeRunner(map, s.ride.route, s.ride.direction, s.ride.hour, s.ride.speed, s.ride.startedAt) : null;
        runnerKey = key;
      }
      if (runner && s.ride) {
        const f = runner.frame(now, true);
        rideTram.current = { at: f.at, bearing: f.bearing, route: s.ride.route };
        if (s.flags.trams && s.flags.buildings && map.getZoom() >= TRAMS_3D_ZOOM) drawTrams(map, s.minute);
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
    if (s.viewMode !== prev.viewMode) {
      map.easeTo(s.viewMode === 'top' ? { pitch: 0, bearing: 0, duration: 700 } : { pitch: 55, duration: 700 });
    }
    if (s.route !== prev.route && s.route != null && !s.ride && !s.segment) fitRoute(map, s.route);
    if (s.segment !== prev.segment || s.route !== prev.route) drawSegment(map, s.segment !== prev.segment);
  }), []);

  function drawTrams(map: MapLibre, minute: number) {
    const s = useStore.getState();
    if (!s.flags.trams) return;
    const { load: l, factors: f, calendar: cal } = data.current;
    const dayOff = cal?.[dayIndex(minute)]?.dayOff ?? false;
    const trams = tramsAt(lines.current, minute, f, dayOff, l);
    (map.getSource('trams') as GeoJSONSource | undefined)?.setData(tramCollection(trams));
    // объёмные вагоны только в кадре и только на крупном плане: остальные не видны и не стоят ничего
    const zoom = map.getZoom();
    const bodies = zoom >= TRAMS_3D_ZOOM && s.flags.buildings;
    const bounds = map.getBounds();
    const visible = bodies ? [...trams, ...(rideTram.current ? [rideTram.current] : [])]
      .filter((t) => bounds.contains(t.at)).map((t) => ({ ...t, color: routeColor(t.route) })) : [];
    const night = sunElevation(minute) < -4;
    (map.getSource('trams-3d') as GeoJSONSource | undefined)?.setData(tramBodies(visible, tramScale(zoom), night));
  }

  /** Подсветка выбранного участка; при новом участке камера наводится на него. */
  function drawSegment(map: MapLibre, focus: boolean) {
    const s = useStore.getState();
    const shape = segmentShape(lines.current, s.route, s.segment, data.current.rideStopsData);
    (map.getSource('segment') as GeoJSONSource | undefined)?.setData(shape);
    const bounds = focus && !s.ride ? segmentBounds(shape) : null;
    if (bounds) map.fitBounds(bounds, { padding: 90, maxZoom: 15.2, duration: 900 });
  }

  function makeRunner(map: MapLibre, route: number, direction: number, hour: number, speed: number, startedAt: number) {
    const line = lines.current.find((x) => x.route === route && x.direction === direction);
    const { load: l, factors: f, rideStopsData: stops } = data.current;
    if (!line || !stops) return null;
    const day = dayIndex(useStore.getState().minute);
    const h = headway(f, route, data.current.calendar?.[day]?.dayOff ?? false, hour) ?? 10;
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
    drawSegment(map, false);
    if (s.flags.metro) void ensureMetro(map).then(() => setVisibility(map, useStore.getState().flags));
    setSelection(map, s.route, s.stop);
    const l = data.current.load;
    if (l) {
      const { lines: ls, points } = withLoad(pathFeatures(network), stopFeatures(network), l, scale.current);
      setLoadData(map, ls, points);
    }
    setHour(map, hourOf(s.minute), scale.current);
    setWeatherData(map, weather);
    setWeatherHour(map, hourOf(s.minute));
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

