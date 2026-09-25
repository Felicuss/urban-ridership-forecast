import { useEffect, useRef } from 'react';
import { fmtInt } from '../../lib/format';
import { HORIZON_DAYS, dayLabel } from '../../lib/time';
import styles from './HeatMatrix.module.css';

// Тепловая карта по времени: 61 сутки по горизонтали, 24 часа по вертикали. Клик переносит прогноз
// на этот день и час. Над сеткой отметки выходных и праздников.

const RAMP = ['#0d1a2e', '#1e3a8a', '#2f6fd6', '#3a95ff', '#3ddc97', '#ffd166', '#ff7a45', '#ef4136'];

function colorFor(v: number, max: number): string {
  if (v <= 0 || max <= 0) return '#0a111c';
  const t = Math.min(Math.sqrt(v / max), 1) * (RAMP.length - 1);
  return RAMP[Math.round(t)] ?? RAMP[0]!;
}

interface Props {
  values: number[] | undefined;
  dayOff: boolean[];
  holidays: (string | null)[];
  day: number;
  hour: number;
  onPick: (day: number, hour: number) => void;
}

export function HeatMatrix({ values, dayOff, holidays, day, hour, onPick }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const tip = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
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
      const cw = w / HORIZON_DAYS;
      const ch = (h - top) / 24;
      const max = values ? Math.max(...values) : 0;
      for (let d = 0; d < HORIZON_DAYS; d++) {
        if (dayOff[d]) {
          ctx.fillStyle = holidays[d] ? '#ef4136' : 'rgba(233,238,245,0.35)';
          ctx.fillRect(d * cw + 1, 0, cw - 2, 2.5);
        }
        for (let hr = 0; hr < 24; hr++) {
          ctx.fillStyle = colorFor(values?.[d * 24 + hr] ?? 0, max);
          ctx.fillRect(d * cw + 0.5, top + hr * ch + 0.5, cw - 1, ch - 1);
        }
      }
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(day * cw + 0.5, top + hour * ch + 0.5, cw - 1, ch - 1);
      ctx.strokeStyle = 'rgba(255,255,255,0.18)';
      ctx.lineWidth = 1;
      ctx.strokeRect(day * cw + 0.5, top, cw - 1, h - top);
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [values, dayOff, holidays, day, hour]);

  const cell = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const d = Math.min(Math.max(Math.floor(((e.clientX - r.left) / r.width) * HORIZON_DAYS), 0), HORIZON_DAYS - 1);
    const hr = Math.min(Math.max(Math.floor(((e.clientY - r.top - 5) / (r.height - 5)) * 24), 0), 23);
    return { d, hr, x: e.clientX - r.left, y: e.clientY - r.top };
  };

  return (
    <div className={styles.wrap}>
      <canvas
        ref={canvas}
        className={styles.canvas}
        role="img"
        aria-label="Посадки по дням и часам горизонта"
        onClick={(e) => {
          const c = cell(e);
          onPick(c.d, c.hr);
        }}
        onMouseMove={(e) => {
          const c = cell(e);
          const t = tip.current;
          if (!t) return;
          t.style.opacity = '1';
          t.style.transform = `translate(${Math.min(c.x + 12, e.currentTarget.clientWidth - 190)}px, ${c.y - 34}px)`;
          const hol = holidays[c.d];
          t.textContent = `${dayLabel(c.d)}${hol ? ` (${hol})` : ''}, ${c.hr}:00 - ${fmtInt(values?.[c.d * 24 + c.hr])}`;
        }}
        onMouseLeave={() => {
          if (tip.current) tip.current.style.opacity = '0';
        }}
      />
      <div ref={tip} className={styles.tip} />
    </div>
  );
}
