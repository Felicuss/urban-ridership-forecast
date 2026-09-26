// Спарклайн суток: 24 значения, текущий час отмечен точкой.
export function Sparkline({ values, color, hour, width = 96, height = 26 }: {
  values: number[] | undefined;
  color: string;
  hour?: number;
  width?: number;
  height?: number;
}) {
  if (!values?.length) return <svg width={width} height={height} aria-hidden="true" />;
  const max = Math.max(...values, 1);
  const x = (i: number) => (i / (values.length - 1)) * (width - 2) + 1;
  const y = (v: number) => height - 2 - (v / max) * (height - 4);
  const line = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const area = `${line}L${x(values.length - 1)},${height}L${x(0)},${height}Z`;
  const id = `sp${color.replace('#', '')}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.35" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.4" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {hour != null && values[hour] != null && (
        <circle cx={x(hour)} cy={y(values[hour] ?? 0)} r="2.4" fill="#fff" stroke={color} strokeWidth="1.2" />
      )}
    </svg>
  );
}
