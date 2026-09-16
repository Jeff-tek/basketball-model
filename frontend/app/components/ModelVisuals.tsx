import type { Tip } from "../lib/tips";

const SIZE = 260;
const C = SIZE / 2;
const R = 92;

const pt = (i: number, n: number, v: number): [number, number] => {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const r = Math.max(0, Math.min(1, v)) * R;
  return [C + r * Math.cos(a), C + r * Math.sin(a)];
};

const poly = (vals: number[]): string =>
  vals.map((v, i) => pt(i, vals.length, v).join(",")).join(" ");

const num = (v: number | null | undefined): number =>
  typeof v === "number" && Number.isFinite(v) ? v : 0;

export function OddsRadar({ t }: { t: Tip }) {
  const axes = ["Home", "Away", "Cover", "Over", "Under"];
  const vals = [
    num(t.probs.ml.home),
    num(t.probs.ml.away),
    num(t.probs.spread.home),
    num(t.probs.totals.over),
    num(t.probs.totals.under),
  ];
  const rings = [0.25, 0.5, 0.75, 1];
  return (
    <div className="viz-block">
      <div className="viz-title">Model shape</div>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="radar" role="img" aria-label="Model probability radar">
        {rings.map((r) => (
          <polygon
            key={r}
            points={poly(Array(axes.length).fill(r))}
            className="radar-ring"
          />
        ))}
        {axes.map((_, i) => {
          const [x, y] = pt(i, axes.length, 1);
          return <line key={i} x1={C} y1={C} x2={x} y2={y} className="radar-spoke" />;
        })}
        <polygon points={poly(vals)} className="radar-area" />
        {vals.map((v, i) => {
          const [x, y] = pt(i, axes.length, v);
          const [lx, ly] = pt(i, axes.length, 1.18);
          return (
            <g key={i}>
              <circle cx={x} cy={y} r={4} className="radar-dot" />
              <text x={lx} y={ly} textAnchor="middle" className="radar-label">
                {axes[i]} {(v * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function CrowdBars({ t }: { t: Tip }) {
  if (!t.crowd) return null;
  const tr = t.crowdTrend ?? null;
  const rows = [
    { k: "H", m: num(t.probs.ml.home), c: num(t.crowd.home), dt: tr?.homeDelta ?? null },
    { k: "A", m: num(t.probs.ml.away), c: num(t.crowd.away), dt: tr?.awayDelta ?? null },
  ];
  return (
    <div className="viz-block">
      <div className="viz-title">
        Crowd vs Model
        {t.crowd.low_volume && <span className="thin-flag">thin market</span>}
      </div>
      <div className="duel-rows">
        {rows.map((r) => {
          const d = r.c - r.m;
          return (
            <div key={r.k} className="duel-row">
              <span className="duel-k">{r.k}</span>
              <div className="duel-track">
                <div className="duel-model" style={{ width: `${r.m * 100}%` }} />
                <div
                  className="duel-crowd"
                  style={{ left: `${Math.min(r.c, 0.985) * 100}%` }}
                  title={`Crowd ${(r.c * 100).toFixed(0)}%`}
                />
              </div>
              <span className={`duel-d ${d > 0.005 ? "hot" : d < -0.005 ? "cold" : ""}`}>
                {d > 0.005 ? `+${(d * 100).toFixed(0)}` : `${(d * 100).toFixed(0)}`}
              </span>
              {r.dt != null && Math.abs(r.dt) >= 0.005 && (
                <span
                  className={`duel-d ${r.dt > 0 ? "hot" : "cold"}`}
                  title={`Crowd trend since ${tr?.since ? new Date(tr.since).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "earlier"}`}
                >
                  {r.dt > 0 ? `▲${(r.dt * 100).toFixed(0)}` : `▼${(Math.abs(r.dt) * 100).toFixed(0)}`}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="duel-legend">
        <span className="lg-model">bar = model</span>
        <span className="lg-crowd">tick = crowd</span>
      </div>
    </div>
  );
}
