// Лёгкие SVG-графики для вкладки факторов: линия и столбики с подписями и отметкой текущего момента.

interface MiniProps {
  values: (number | null)[];
  labels?: string[];
  color?: string;
  mark?: number;
  highlight?: (i: number) => boolean;
  height?: number;
  format?: (v: number) => string;
}

const W = 340;

/** Подписи оси: начало, середина и конец ряда; labels идут по одной на каждое значение. */
function ticks(n: number): number[] {
  return n > 2 ? [0, Math.floor((n - 1) / 2), n - 1] : [0];
}

function anchor(i: number, n: number): 'start' | 'middle' | 'end' {
  return i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle';
}

function extent(values: (number | null)[]): [number, number] {
  const v = values.filter((x): x is number => x != null && Number.isFinite(x));
  if (!v.length) return [0, 1];
  const lo = Math.min(...v);
  const hi = Math.max(...v);
  return lo === hi ? [lo - 1, hi + 1] : [lo, hi];
}

export function MiniLine({ values, labels, color = '#3a95ff', mark, height = 70, format }: MiniProps) {
  const [lo, hi] = extent(values);
  const pad = 4;
  const x = (i: number) => pad + (i / Math.max(values.length - 1, 1)) * (W - 2 * pad);
  const y = (v: number) => height - 14 - ((v - lo) / (hi - lo)) * (height - 22);
  let d = '';
  values.forEach((v, i) => {
    if (v == null) return;
    d += `${d && values[i - 1] != null ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  const markValue = mark != null ? values[mark] : null;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} role="img" aria-hidden="true">
      {lo < 0 && hi > 0 && <line x1={pad} x2={W - pad} y1={y(0)} y2={y(0)} stroke="rgba(160,190,230,0.18)" strokeDasharray="3 3" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
      {mark != null && markValue != null && (
        <>
          <line x1={x(mark)} x2={x(mark)} y1={2} y2={height - 14} stroke="#ef4136" strokeWidth="1.2" />
          <circle cx={x(mark)} cy={y(markValue)} r="3" fill="#fff" stroke={color} />
          <text x={Math.min(x(mark) + 5, W - 40)} y={10} fill="#e9eef5" fontSize="10" fontFamily="JetBrains Mono Variable, monospace">
            {format ? format(markValue) : markValue}
          </text>
        </>
      )}
      {labels && ticks(values.length).map((i) => (
        <text key={i} x={x(i)} y={height - 2} fill="#6b7a8f" fontSize="9.5" textAnchor={anchor(i, values.length)}>
          {labels[i]}
        </text>
      ))}
    </svg>
  );
}

export function MiniBars({ values, labels, color = '#3a95ff', mark, highlight, height = 70 }: MiniProps) {
  const [, hi] = extent(values);
  const top = Math.max(hi, 0) || 1;
  const bw = (W - 8) / values.length;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} role="img" aria-hidden="true">
      {values.map((v, i) => {
        const h = v == null ? 0 : (Math.max(v, 0) / top) * (height - 18);
        const on = mark === i || highlight?.(i);
        return <rect key={i} x={4 + i * bw + 0.5} y={height - 14 - h} width={Math.max(bw - 1, 1)} height={h} rx="1.5"
          fill={on ? '#ffd166' : color} opacity={on ? 1 : 0.72} />;
      })}
      {labels && ticks(values.length).map((i) => (
        <text key={i} x={4 + i * bw + bw / 2} y={height - 2} fill="#6b7a8f" fontSize="9.5"
          textAnchor={anchor(i, values.length)}>{labels[i]}</text>
      ))}
    </svg>
  );
}
