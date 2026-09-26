/** A candidate's folded dip as a thin line (hours from mid-dip, median flux). Data graphic, not decoration. */
export function Sparkline({ points, height = 48, label }: { points: [number, number][]; height?: number; label: string }) {
  if (points.length < 3) return null;
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [lo, hi] = [Math.min(...ys), Math.max(...ys)];
  const pad = (hi - lo) * 0.2 || 1e-4;
  const W = 320;
  const X = (x: number) => ((x - x0) / (x1 - x0)) * W;
  const Y = (y: number) => 4 + ((hi + pad - y) / (hi - lo + 2 * pad)) * (height - 8);
  const d = points.map(([x, y], i) => `${i ? "L" : "M"}${X(x).toFixed(1)} ${Y(y).toFixed(1)}`).join("");
  return (
    <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" width="100%" height={height} role="img" aria-label={label} style={{ display: "block" }}>
      <path d={d} fill="none" stroke="var(--ink)" strokeWidth="1.25" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}
