import type { Tip } from "../lib/tips";
import { OddsRadar, CrowdBars } from "./ModelVisuals";
import TeamDuel from "./TeamDuel";

const pct = (p: number | null | undefined): string =>
  typeof p === "number" && Number.isFinite(p) ? `${(p * 100).toFixed(0)}%` : "–";

export const fmtDate = (iso: string): string => {
  if (!iso) return "TBD";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16).replace("T", " ");
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const verdictClass = (v: Tip["verdict"]): string =>
  v === "BET" ? "bet" : v === "MARGINAL" ? "marginal" : "nobet";

const fmtSpread = (line: number | null | undefined): string => {
  if (typeof line !== "number" || !Number.isFinite(line)) return "–";
  return line > 0 ? `+${line.toFixed(1)}` : line.toFixed(1);
};

const fmtTotal = (line: number | null | undefined): string => {
  if (typeof line !== "number" || !Number.isFinite(line)) return "–";
  return line.toFixed(1);
};

export default function TipCard({ t }: { t: Tip }) {
  const vc = verdictClass(t.verdict);
  const edgePos = t.edge.value > 0;
  const noBook = t.bookOdds.ml_home == null || t.bookOdds.ml_away == null;
  const ph = t.probs.ml.home;
  const pa = t.probs.ml.away;
  const fh = t.fair.ml.home;
  const fa = t.fair.ml.away;
  const homeCover = t.probs.spread.home;
  const over = t.probs.totals.over;
  const under = t.probs.totals.under;
  const spreadLine = t.bookOdds.spread;
  const totalLine = t.bookOdds.total;
  const homeHot = (homeCover ?? 0) >= 0.5;
  const overHot = (over ?? 0) >= 0.5;

  return (
    <article className="tip-card">
      <div className="tip-top">
        <div className="tip-matchup">
          {t.home} <span className="vs">@</span> {t.away}
        </div>
        <div className="tip-meta">
          <span>{fmtDate(t.date)}</span>
          {t.homeForm && (
            <span>
              Form {t.homeForm} · {t.awayForm}
            </span>
          )}
          {t.homePace > 0 && (
            <span>
              Pace {t.homePace.toFixed(1)} – {t.awayPace.toFixed(1)}
            </span>
          )}
          {t.models && t.models.length > 1 && (
            <span>Models: {t.models.join(" + ")}</span>
          )}
        </div>
      </div>

      <div className={`tip-band ${vc}`}>
        <div className="word">{t.verdict}</div>
        <div className="tip-pickbox">
          Pick<b>{t.pick}</b>
          <span className={`edge-badge ${edgePos ? "pos" : "neg"}`}>
            {edgePos ? `+${(t.edge.value * 100).toFixed(1)}%` : noBook ? "no odds" : "no edge"}
          </span>
        </div>
      </div>

      <div className="tip-body">
        <div className="market-rows">
          {/* Moneyline */}
          <div className="market-row">
            <div className="market-name">ML</div>
            <div className="market-side">
              <b>{pct(ph)}</b>
              <small>fair {pct(fh)}</small>
            </div>
            <div className="market-side">
              <b>{pct(pa)}</b>
              <small>fair {pct(fa)}</small>
            </div>
          </div>

          {/* Spread */}
          <div className="market-row">
            <div className="market-name">Spread</div>
            <div className={`market-side ${homeHot ? "hot" : ""}`}>
              <b>
                {t.home} {fmtSpread(spreadLine)}
              </b>
              <small>{pct(homeCover)} cover</small>
            </div>
            <div className={`market-side ${!homeHot ? "hot" : ""}`}>
              <b>{t.away} {fmtSpread(spreadLine != null ? -spreadLine : null)}</b>
              <small>{pct(homeCover != null ? 1 - homeCover : null)} cover</small>
            </div>
          </div>

          {/* Totals */}
          <div className="market-row">
            <div className="market-name">Totals</div>
            <div className={`market-side ${overHot ? "hot" : ""}`}>
              <b>Over {fmtTotal(totalLine)}</b>
              <small>{pct(over)}</small>
            </div>
            <div className={`market-side ${!overHot ? "hot" : ""}`}>
              <b>Under {fmtTotal(totalLine)}</b>
              <small>{pct(under)}</small>
            </div>
          </div>
        </div>

        <div className="tip-meta" style={{ marginBottom: 8 }}>
          <span className="confidence-badge">
            <span className="dot" />
            Confidence {t.confidence.toFixed(0)}%
          </span>
          <span className={`verdict-pill ${vc}`}>{t.verdict}</span>
        </div>

        {t.lineMove && (
          <div className="steam-line">
            Line move:{" "}
            {["Home", "Away", "Spread", "Total"]
              .filter((k) => t.lineMove?.[k as keyof typeof t.lineMove])
              .map((k) => `${k} ${t.lineMove?.[k as keyof typeof t.lineMove]}`)
              .join(" · ")}
          </div>
        )}

        <div className="viz-stack">
          <OddsRadar t={t} />
          <div className="viz-duel-row">
            <CrowdBars t={t} />
            <TeamDuel t={t} />
          </div>
        </div>

        {t.crowd && (
          <div className="crowd-box">
            <div className="crowd-title">Crowd market</div>
            <div className="crowd-bars">
              <div className="crowd-bar-row">
                <span className="crowd-k">{t.home}</span>
                <div className="crowd-track">
                  <div
                    className="fill"
                    style={{ width: `${Math.round(t.crowd.home * 100)}%` }}
                  />
                </div>
                <span className="crowd-v">{pct(t.crowd.home)}</span>
              </div>
              <div className="crowd-bar-row">
                <span className="crowd-k">{t.away}</span>
                <div className="crowd-track">
                  <div
                    className="fill"
                    style={{ width: `${Math.round(t.crowd.away * 100)}%` }}
                  />
                </div>
                <span className="crowd-v">{pct(t.crowd.away)}</span>
              </div>
            </div>
            {t.crowd.low_volume && (
              <div className="crowd-low">Low volume — treat with caution</div>
            )}
          </div>
        )}

        <div className="tip-reasons">
          {t.reasons.map((r) => (
            <div key={r} className="tip-reason">
              {r}
            </div>
          ))}
        </div>

        {t.crowd?.url && (
          <div style={{ margin: "10px 0 2px" }}>
            <a className="source-link" href={t.crowd.url} target="_blank" rel="noreferrer">
              Crowd market ↗
            </a>
          </div>
        )}

        <div className="source-links">
          {t.sources.map((s) => (
            <a
              key={s.name}
              className="source-link"
              href={s.url}
              target="_blank"
              rel="noreferrer"
            >
              {s.name}
            </a>
          ))}
        </div>
      </div>
    </article>
  );
}
