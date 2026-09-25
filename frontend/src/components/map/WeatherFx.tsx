import { useEffect, useRef } from 'react';
import type { HourWeather } from '../../lib/weather';

// Осадки поверх карты в выбранный час: снежинки или струи дождя, плотность по осадкам Open-Meteo,
// наклон по ветру. Нет осадков - нет холста и нет кадров анимации.

interface Particle {
  x: number;
  y: number;
  v: number;
  r: number;
}

export function WeatherFx({ weather }: { weather: HourWeather }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const snow = weather.sky === 'snow' || weather.snow > 0.05;
  const amount = snow ? Math.max(weather.snow * 4, weather.precip) : weather.precip;
  const count = amount <= 0.02 ? 0 : Math.round(Math.min(40 + amount * 160, 420));
  const wind = Math.min((weather.wind ?? 8) / 30, 1);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext('2d');
    if (!el || !ctx || count === 0) return;
    let raf = 0;
    let parts: Particle[] = [];
    const resize = () => {
      el.width = el.clientWidth;
      el.height = el.clientHeight;
      parts = Array.from({ length: count }, () => ({ x: Math.random() * el.width, y: Math.random() * el.height,
        v: snow ? 0.4 + Math.random() * 0.8 : 7 + Math.random() * 6, r: snow ? 0.8 + Math.random() * 1.8 : 1 }));
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    const frame = () => {
      raf = requestAnimationFrame(frame);
      ctx.clearRect(0, 0, el.width, el.height);
      ctx.fillStyle = 'rgba(235,242,255,0.75)';
      ctx.strokeStyle = 'rgba(150,190,255,0.35)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (const p of parts) {
        p.y += p.v;
        p.x += snow ? wind * 0.8 + Math.sin(p.y / 30) * 0.3 : wind * 3;
        if (p.y > el.height) {
          p.y = -4;
          p.x = Math.random() * el.width;
        }
        if (p.x > el.width) p.x -= el.width;
        if (snow) {
          ctx.moveTo(p.x + p.r, p.y);
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        } else {
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x - wind * 4, p.y - 12);
        }
      }
      if (snow) ctx.fill();
      else ctx.stroke();
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [count, snow, wind]);

  if (count === 0) return null;
  return <canvas ref={canvas} aria-hidden="true"
    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 4, pointerEvents: 'none' }} />;
}
