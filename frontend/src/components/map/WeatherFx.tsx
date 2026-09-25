import { useEffect, useRef } from 'react';
import { precipAt, type GridPoint } from '../../lib/weatherGrid';
import { mapHandle } from './mapHandle';

// Осадки там, где они идут: частица рисуется, только если в её точке карты по сетке Open-Meteo есть дождь
// или снег, и тем плотнее, чем сильнее осадки. Нет осадков нигде - нет холста и кадров анимации.

interface Particle {
  x: number;
  y: number;
  v: number;
  r: number;
  seed: number;
}

const COUNT = 420;
const SAMPLE_EVERY = 6;

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
    const cache = new Map<Particle, { rain: number; snow: number }>();
    const resize = () => {
      el.width = el.clientWidth;
      el.height = el.clientHeight;
      parts = Array.from({ length: COUNT }, () => ({ x: Math.random() * el.width, y: Math.random() * el.height,
        v: 0.6 + Math.random(), r: 0.8 + Math.random() * 1.6, seed: Math.random() }));
      cache.clear();
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
        if (frame % SAMPLE_EVERY === 0 || !cache.has(p)) {
          const ll = map.unproject([p.x, p.y]);
          cache.set(p, precipAt(grid, ll.lng, ll.lat, hour));
        }
        const here = cache.get(p)!;
        const snow = here.snow > 0.02 && here.snow * 3 >= here.rain;
        const intensity = snow ? Math.min(here.snow * 2.5, 1) : Math.min(here.rain / 1.5, 1);
        p.y += snow ? p.v * 0.7 : p.v * 9;
        p.x += snow ? Math.sin((p.y + p.seed * 100) / 28) * 0.35 : 1.2;
        if (p.y > el.height) {
          p.y = -6;
          p.x = Math.random() * el.width;
        }
        if (p.x > el.width) p.x -= el.width;
        if (p.seed > intensity) continue;
        if (snow) {
          ctx.fillStyle = 'rgba(240,242,248,0.7)';
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
          ctx.fill();
        } else {
          ctx.strokeStyle = 'rgba(170,190,225,0.35)';
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x - 1.5, p.y - 11);
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
