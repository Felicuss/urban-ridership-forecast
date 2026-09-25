import { useEffect, useRef } from 'react';
import type { CalendarDay } from '../../api/types';
import { fmtInt } from '../../lib/format';
import { dayLabel, dayOf } from '../../lib/time';
import styles from './HeatMatrix.module.css';

// Тепловая карта по времени: дни окна по горизонтали, 24 часа по вертикали. Клик переносит время на этот
// день и час. Над сеткой отметки выходных и праздников, под ней - источник: факт, прогноз или оценка.

const RAMP = ['#15171c', '#26324a', '#3d5582', '#5b7bc7', '#7fa8a0', '#c9ad72', '#d68d6d', '#d06a73'];
const SOURCE_COLOR: Record<string, string> = { fact: '#a1a1aa', forecast: '#7aa2f7', outlook: '#52525b' };

function colorFor(v: number, max: number): string {
  if (v <= 0 || max <= 0) return '#101114';
  const t = Math.min(Math.sqrt(v / max), 1) * (RAMP.length - 1);
  return RAMP[Math.round(t)] ?? RAMP[0]!;
}

interface Props {
  values: number[] | undefined;
  days: CalendarDay[];
  day: number;
  hour: number;
  onPick: (day: number, hour: number) => void;
}

export function HeatMatrix({ values, days, day, hour, onPick }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const first = days[0] ? dayOf(days[0].date) : 0;
  const n = days.length;

  useEffect(() => {
    const el = canvas.current;
    if (!el || n === 0) return;
    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = el.clientWidth;
      const h = el.clientHeight;
      el.width = Math.round(w * dpr);
      el.height = Math.round(h * dpr);
      const ctx = el.getContext('2d');
      if (!ctx) return;
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);
      const top = 5;
      const bottom = 3;
      const cw = w / n;
      const ch = (h - top - bottom) / 24;
      const max = values?.length ? Math.max(...values) : 0;
      days.forEach((c, d) => {
        if (c.dayOff) {
          ctx.fillStyle = c.holiday ? '#e5737d' : 'rgba(244,244,245,0.3)';
          ctx.fillRect(d * cw + 1, 0, cw - 2, 2.5);
        }
        for (let hr = 0; hr < 24; hr++) {
          ctx.fillStyle = colorFor(values?.[d * 24 + hr] ?? 0, max);
          ctx.fillRect(d * cw + 0.5, top + hr * ch + 0.5, cw - 1, ch - 1);
        }
        ctx.fillStyle = SOURCE_COLOR[c.source] ?? '#52525b';
        ctx.fillRect(d * cw, h - 2, cw, 2);
      });
      const at = day - first;
      if (at >= 0 && at < n) {
        ctx.strokeStyle = '#f4f4f5';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(at * cw + 0.5, top + hour * ch + 0.5, cw - 1, ch - 1);
        ctx.strokeStyle = 'rgba(244,244,245,0.2)';
        ctx.lineWidth = 1;
        ctx.strokeRect(at * cw + 0.5, top, cw - 1, h - top - bottom);
      }
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [values, days, day, hour, first, n]);

  const cell = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const d = Math.min(Math.max(Math.floor(((e.clientX - r.left) / r.width) * n), 0), n - 1);
    const hr = Math.min(Math.max(Math.floor(((e.clientY - r.top - 5) / (r.height - 8)) * 24), 0), 23);
    return { d, hr, x: e.clientX - r.left, y: e.clientY - r.top };
  };

  return (
    <div className={styles.wrap}>
      <canvas
        ref={canvas}
        className={styles.canvas}
        role="img"
        aria-label="Посадки по дням и часам"
        onClick={(e) => {
          const c = cell(e);
          onPick(first + c.d, c.hr);
        }}
        onMouseMove={(e) => {
          const c = cell(e);
          const t = tip.current;
          const info = days[c.d];
          if (!t || !info) return;
          t.style.opacity = '1';
          t.style.transform = `translate(${Math.min(c.x + 12, e.currentTarget.clientWidth - 230)}px, ${c.y - 34}px)`;
          const src = info.source === 'fact' ? 'факт' : info.source === 'forecast' ? 'прогноз' : 'оценка';
          t.textContent = `${dayLabel(first + c.d)}${info.holiday ? ` (${info.holiday})` : ''}, ${c.hr}:00 - `
            + `${fmtInt(values?.[c.d * 24 + c.hr])}, ${src}`;
        }}
        onMouseLeave={() => {
          if (tip.current) tip.current.style.opacity = '0';
        }}
      />
      <div ref={tip} className={styles.tip} />
    </div>
  );
}
