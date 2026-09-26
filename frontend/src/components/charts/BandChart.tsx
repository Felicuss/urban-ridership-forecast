import { useEffect, useRef } from 'react';
import uPlot, { type AlignedData, type Options } from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { fmtCompact, fmtInt } from '../../lib/format';
import styles from './BandChart.module.css';

// Ряд с коридором p10-p90 на uPlot (canvas, около 50 КБ): медиана, коридор, база сценария пунктиром,
// факт прошлых периодов серым, план прошедших дней голубым пунктиром. Экземпляр создаётся один раз, дальше только setData.

export interface BandSeries {
  labels: string[];
  p50: number[];
  p10: number[];
  p90: number[];
  baseline?: (number | null)[];
  /** Подпись пунктира в подсказке: «база» для сценария, «восстановлено» для пропуска в данных. */
  baselineLabel?: string;
  history?: (number | null)[];
  /** Ряд другой даты для сравнения и его подпись в подсказке. */
  compare?: (number | null)[];
  compareLabel?: string;
  /** План прошедших дней: прогноз, сделанный накануне. */
  plan?: (number | null)[];
}

interface Props {
  data: BandSeries;
  color: string;
  cursorIndex?: number;
  height?: number;
  onPick?: (index: number) => void;
}

/** Ряд сравнения: тёплый цвет, чтобы не путать с базой сценария (белый пунктир) и фактом (серый). */
export const COMPARE_COLOR = '#f5c07a';
/** План прошедших дней: холодный пунктир, отличный от базы сценария и сравнения. */
export const PLAN_COLOR = '#7dcfff';

function css(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
}

function options(width: number, height: number, color: string, labels: string[], onPick?: (i: number) => void): Options {
  const grid = { stroke: 'rgba(160,190,230,0.07)', width: 1 };
  const tick = { stroke: 'rgba(160,190,230,0.12)', width: 1, size: 4 };
  return {
    width, height, padding: [8, 6, 0, 2],
    legend: { show: false },
    cursor: { y: false, points: { size: 6 }, drag: { x: false, y: false } },
    scales: { x: { time: false } },
    series: [
      {},
      { label: 'p90', stroke: 'transparent', points: { show: false } },
      { label: 'p10', stroke: 'transparent', points: { show: false } },
      { label: 'прогноз', stroke: color, width: 2, points: { show: false } },
      { label: 'база', stroke: 'rgba(233,238,245,0.55)', width: 1.4, dash: [5, 4], points: { show: false } },
      { label: 'факт', stroke: css('--muted'), width: 1.2, points: { show: false } },
      { label: 'сравнение', stroke: COMPARE_COLOR, width: 1.6, dash: [2, 3], points: { show: false } },
      { label: 'план', stroke: PLAN_COLOR, width: 1.6, dash: [6, 4], points: { show: false } },
    ],
    bands: [{ series: [1, 2], fill: `${color}2e` }],
    axes: [
      { stroke: css('--muted'), grid, ticks: tick, font: '11px Onest Variable, system-ui', size: 26,
        values: (_u, splits) => splits.map((v) => labels[Math.round(v)] ?? '') },
      { stroke: css('--muted'), grid, ticks: tick, font: '10.5px JetBrains Mono Variable, monospace', size: 50,
        values: (_u, splits) => splits.map(axisValue) },
    ],
    hooks: {
      ready: [(u) => {
        u.over.addEventListener('click', () => {
          const i = u.cursor.idx;
          if (i != null && onPick) onPick(i);
        });
      }],
    },
  };
}

/** Подпись оси без дробей: 12 000 -> «12 тыс», 2 500 000 -> «2,5 млн». */
function axisValue(v: number): string {
  if (Math.abs(v) >= 1e6) return `${fmtCompact(v).replace(' млн', '')} млн`;
  if (Math.abs(v) >= 1000) return `${Math.round(v / 1000)} тыс`;
  return String(Math.round(v));
}

function aligned(d: BandSeries): AlignedData {
  const x = d.labels.map((_, i) => i);
  const none = d.labels.map(() => null);
  return [x, d.p90, d.p10, d.p50, d.baseline ?? none, d.history ?? none, d.compare ?? none, d.plan ?? none] as AlignedData;
}

export function BandChart({ data, color, cursorIndex, height = 180, onPick }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const tip = useRef<HTMLDivElement>(null);
  const marker = useRef<HTMLDivElement | null>(null);
  const latest = useRef({ data, onPick });

  useEffect(() => {
    latest.current = { data, onPick };
  });

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const u = new uPlot(options(el.clientWidth, height, color, data.labels, (i) => latest.current.onPick?.(i)),
      aligned(data), el);
    u.hooks.setCursor = [(p) => {
      const i = p.cursor.idx;
      const t = tip.current;
      if (!t) return;
      if (i == null) {
        t.style.opacity = '0';
        return;
      }
      const d = latest.current.data;
      const base = d.baseline?.[i];
      const other = d.compare?.[i];
      const plan = d.plan?.[i];
      t.style.opacity = '1';
      t.textContent = `${d.labels[i] ?? ''}: ${fmtInt(d.p50[i])} (${fmtInt(d.p10[i])}-${fmtInt(d.p90[i])})`
        + (base != null ? `, ${d.baselineLabel ?? 'база'} ${fmtInt(base)}` : '')
        + (other != null ? `, ${d.compareLabel ?? 'сравнение'} ${fmtInt(other)}` : '')
        + (plan != null ? `, план ${fmtInt(plan)}` : '');
    }];
    const m = document.createElement('div');
    m.className = styles.now ?? '';
    u.over.appendChild(m);
    marker.current = m;
    plot.current = u;
    const ro = new ResizeObserver(() => u.setSize({ width: el.clientWidth, height }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      u.destroy();
      plot.current = null;
      marker.current = null;
    };
    // пересоздаём только при смене цвета, высоты или числа точек: подписи оси зашиты в опции
  }, [color, height, data.labels.length, data.labels[0]]);

  useEffect(() => {
    plot.current?.setData(aligned(data));
  }, [data]);

  useEffect(() => {
    const u = plot.current;
    const m = marker.current;
    if (!u || !m) return;
    m.style.opacity = cursorIndex == null ? '0' : '1';
    if (cursorIndex != null) m.style.transform = `translateX(${u.valToPos(cursorIndex, 'x')}px)`;
  }, [cursorIndex, data]);

  return (
    <div className={styles.wrap}>
      <div ref={box} className={styles.chart} />
      <div ref={tip} className={styles.tip} />
    </div>
  );
}
