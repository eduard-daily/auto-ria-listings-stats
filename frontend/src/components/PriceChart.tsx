import type { Snapshot } from "../api";
import { formatDateTime, formatMoney } from "../format";

const WIDTH = 720;
const HEIGHT = 260;
const MARGIN = { top: 24, right: 24, bottom: 32, left: 72 };
const MIN_LABEL_GAP = 56; // px between price labels in the chart's own coordinates
const PLOT_PAD = 32; // keeps the first and last point, and their labels, off the axis labels

interface Point {
  time: number;
  value: number;
  observedAt: string;
  changed: boolean;
  dropped: boolean; // a price cut: the step's vertical line arrives from above
}

function niceStep(range: number, ticks: number): number {
  const raw = range / ticks;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  return (normalized < 1.5 ? 1 : normalized < 3 ? 2 : normalized < 7 ? 5 : 10) * magnitude;
}

function yScale(values: number[]) {
  let min = Math.min(...values);
  let max = Math.max(...values);
  // Show at least 10% of the price, so a small move does not fill the chart like a cliff.
  const minRange = max * 0.1;
  if (max - min < minRange) {
    const middle = (min + max) / 2;
    min = middle - minRange / 2;
    max = middle + minRange / 2;
  }
  const pad = (max - min) * 0.15;
  min -= pad;
  max += pad;
  const step = niceStep(max - min, 4);
  const low = Math.floor(min / step) * step;
  const high = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let tick = low; tick <= high + step / 2; tick += step) ticks.push(tick);
  return { low, high, ticks };
}

const day = (time: number) => new Date(time).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/** Price history as a step line: a price holds until the next observation shows a different one. */
export function PriceChart({ snapshots, currency }: { snapshots: Snapshot[]; currency: string | null }) {
  const points: Point[] = snapshots
    .filter((s) => s.fetch_ok && s.listed_price != null && s.listed_currency === currency)
    .map((s) => ({ time: new Date(s.observed_at).getTime(), value: s.listed_price!, observedAt: s.observed_at, changed: false, dropped: false }))
    .sort((a, b) => a.time - b.time);
  points.forEach((p, i) => {
    p.changed = i > 0 && points[i - 1].value !== p.value;
    p.dropped = p.changed && p.value < points[i - 1].value;
  });
  if (points.length === 0) return <p className="muted empty">No price observations yet.</p>;

  const { low, high, ticks } = yScale(points.map((p) => p.value));
  const innerWidth = WIDTH - MARGIN.left - MARGIN.right;
  const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const first = points[0].time;
  const last = points.at(-1)!.time;
  const x = (time: number) =>
    last === first
      ? MARGIN.left + innerWidth / 2
      : MARGIN.left + PLOT_PAD + ((time - first) / (last - first)) * (innerWidth - 2 * PLOT_PAD);
  const y = (value: number) => MARGIN.top + (1 - (value - low) / (high - low)) * innerHeight;
  const bottom = MARGIN.top + innerHeight;

  let line = `M${x(points[0].time)},${y(points[0].value)}`;
  for (const p of points.slice(1)) line += ` H${x(p.time)} V${y(p.value)}`;
  const area = `${line} V${bottom} H${x(first)} Z`;

  // Label the first and last point and every change, skipping labels that would collide.
  let lastLabelX = -Infinity;
  const labelled = new Set<Point>();
  for (const p of points) {
    const wanted = p === points[0] || p === points.at(-1) || p.changed;
    if (wanted && x(p.time) - lastLabelX >= MIN_LABEL_GAP) {
      labelled.add(p);
      lastLabelX = x(p.time);
    }
  }

  return (
    <svg className="chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Price history">
      {ticks.map((tick) => (
        <g key={tick}>
          <line className="chart-grid" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(tick)} y2={y(tick)} />
          <text className="chart-axis" x={MARGIN.left - 8} y={y(tick)} textAnchor="end" dominantBaseline="middle">
            {formatMoney(tick, currency)}
          </text>
        </g>
      ))}
      <text className="chart-axis" x={x(first)} y={HEIGHT - 8} textAnchor={last === first ? "middle" : "start"}>
        {day(first)}
      </text>
      {last !== first && (
        <text className="chart-axis" x={x(last)} y={HEIGHT - 8} textAnchor="end">
          {day(last)}
        </text>
      )}
      <path className="chart-area" d={area} />
      <path className="chart-line" d={line} />
      {points.map((p) => (
        <g key={p.observedAt}>
          <circle className={p.changed ? "chart-dot chart-dot-change" : "chart-dot"} cx={x(p.time)} cy={y(p.value)} r={p.changed ? 5 : 3.5}>
            <title>
              {formatMoney(p.value, currency)} · {formatDateTime(p.observedAt)}
            </title>
          </circle>
          {labelled.has(p) && (
            <text className="chart-label" x={x(p.time)} y={y(p.value) + (p.dropped ? 22 : -12)} textAnchor="middle">
              {formatMoney(p.value, currency)}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}
