import { useEffect, useRef } from 'react';
import { SNOW_CM_TO_MM, edgeFade, precipAt, type GridPoint } from '../../lib/weatherGrid';
import { mapHandle } from './mapHandle';

// Осадки там, где они идут: частица живёт в координатах карты, поэтому при сдвиге и зуме едет вместе с ней,
// а падает по экрану. Рисуется, только если в её точке по сетке Open-Meteo есть дождь или снег, и гаснет
// на краю сетки там же, где заливка осадков. Нет осадков нигде - нет холста и кадров анимации.

interface Particle {
  lng: number;
  lat: number;
  v: number;
  r: number;
  seed: number;
  intensity: number;
  snow: boolean;
}

const COUNT = 420;
const SAMPLE_EVERY = 6;
/** Запас за краем экрана, после которого частица возрождается внутри. */
const MARGIN = 24;

export function WeatherFx({ grid, hour }: { grid: GridPoint[] | undefined; hour: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const anyPrecip = Boolean(grid?.some((p) => (p.rain[hour] ?? 0) > 0.05 || (p.snow[hour] ?? 0) > 0.02));

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext('2d');
    if (!el || !ctx || !grid || !anyPrecip) return;
    let raf = 0;
    let frame = 0;
    let parts: Particle[] = [];

    const place = (p: Particle, x: number, y: number) => {
      const map = mapHandle.current;
      if (!map) return;
      const ll = map.unproject([x, y]);
      p.lng = ll.lng;
      p.lat = ll.lat;
      sample(p);
    };
    const sample = (p: Particle) => {
      const { rain, snow } = precipAt(grid, p.lng, p.lat, hour);
      const snowMm = snow * SNOW_CM_TO_MM;
      p.snow = snowMm > 0.03 && snowMm * 2 >= rain;
      p.intensity = (p.snow ? Math.min(snowMm / 1.2, 1) : Math.min(rain / 1.5, 1)) * edgeFade(p.lng, p.lat);
    };
    const resize = () => {
      el.width = el.clientWidth;
      el.height = el.clientHeight;
      parts = Array.from({ length: COUNT }, () => {
        const p: Particle = { lng: 0, lat: 0, v: 0.6 + Math.random(), r: 0.8 + Math.random() * 1.6,
          seed: Math.random(), intensity: 0, snow: false };
        place(p, Math.random() * el.width, Math.random() * el.height);
        return p;
      });
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    const draw = () => {
      raf = requestAnimationFrame(draw);
      frame += 1;
      const map = mapHandle.current;
      if (!map) return;
      ctx.clearRect(0, 0, el.width, el.height);
      for (const p of parts) {
        const s = map.project([p.lng, p.lat]);
        const off = s.x < -MARGIN || s.x > el.width + MARGIN || s.y < -MARGIN * 4 || s.y > el.height + MARGIN;
        if (off) {
          // упала за нижний край - сверху, ушла вбок при сдвиге карты - в случайное место кадра
          const fell = s.y > el.height && s.x >= -MARGIN && s.x <= el.width + MARGIN;
          place(p, Math.random() * el.width, fell ? -6 : Math.random() * el.height);
          continue;
        }
        const x = s.x + (p.snow ? Math.sin((s.y + p.seed * 100) / 28) * 0.35 : 1.2);
        const y = s.y + (p.snow ? p.v * 0.7 : p.v * 9);
        const ll = map.unproject([x, y]);
        p.lng = ll.lng;
        p.lat = ll.lat;
        if (frame % SAMPLE_EVERY === 0) sample(p);
        if (p.seed > p.intensity) continue;
        if (p.snow) {
          ctx.fillStyle = 'rgba(240,242,248,0.7)';
          ctx.beginPath();
          ctx.arc(x, y, p.r, 0, Math.PI * 2);
          ctx.fill();
        } else {
          ctx.strokeStyle = 'rgba(170,190,225,0.35)';
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x - 1.5, y - 11);
          ctx.stroke();
        }
      }
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [grid, hour, anyPrecip]);

  if (!anyPrecip) return null;
  return <canvas ref={canvas} aria-hidden="true"
    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 4, pointerEvents: 'none' }} />;
}
