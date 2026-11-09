// The overhaul's two small charts (Nov 4): a trend line beside a hero number, and units over time as an area. Plain
// SVG, colored from the theme: green when the run ends up, red when down.
const path = (pts: number[], w: number, h: number, pad = 4) => {
  const lo = Math.min(...pts), hi = Math.max(...pts), span = hi - lo || 1;
  const x = (i: number) => (pts.length === 1 ? w : (i / (pts.length - 1)) * (w - pad * 2) + pad);
  const y = (v: number) => h - pad - ((v - lo) / span) * (h - pad * 2);
  return { d: pts.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" "), end: [x(pts.length - 1), y(pts[pts.length - 1])] as const,
           zero: lo < 0 && hi > 0 ? y(0) : null };
};

export function Spark({ points, label, width = 120, height = 44 }: { points: number[]; label: string; width?: number; height?: number }) {
  if (points.length < 2) return null;
  const up = points[points.length - 1] >= points[0];
  const { d, end } = path(points, width, height, 6);
  const color = up ? "var(--pos)" : "var(--neg)";
  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} width={width} height={height}>
      <path d={d} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={end[0]} cy={end[1]} r={4} fill={color} />
    </svg>
  );
}

/** Units over time: the line, a soft fill under it and a hairline at zero. Stretches to its box's width. */
export function AreaChart({ points, label, height = 110 }: { points: number[]; label: string; height?: number }) {
  if (points.length < 2) return null;
  const w = 390, up = points[points.length - 1] >= 0;
  const { d, zero } = path(points, w, height, 3);
  const color = up ? "var(--pos)" : "var(--neg)";
  const id = up ? "area-up" : "area-down";
  return (
    <svg className="areachart" viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" role="img" aria-label={label} height={height}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".28" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      <path d={`${d} L${w - 3} ${height} L3 ${height} Z`} fill={`url(#${id})`} />
      {zero !== null && <line x1="0" x2={w} y1={zero} y2={zero} stroke="var(--line-2, var(--line))" strokeWidth={1} vectorEffect="non-scaling-stroke" strokeDasharray="3 4" />}
      <path d={d} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
