"use client";

import { useCallback, useEffect, useState } from "react";
import { getTips, type TipsResponse } from "./lib/tips";
import TipCard from "./components/TipCard";
import LeagueTabs from "./components/LeagueTabs";

const LEAGUES = ["NBA", "EuroLeague"] as const;

export default function TipsPage() {
  const [league, setLeague] = useState<(typeof LEAGUES)[number]>("NBA");
  const [data, setData] = useState<TipsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const load = useCallback(async (lg: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getTips(lg);
      setData(res);
      setUpdatedAt(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tips");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(league);
    const id = setInterval(() => void load(league), 15 * 60 * 1000);
    return () => clearInterval(id);
  }, [league, load]);

  return (
    <div className="wrap">
      <header className="masthead">
        <div>
          <div className="kicker">Basketball Model</div>
          <h1 className="title">
            <span className="ball-mark" aria-hidden="true" />
            Tips Board
          </h1>
        </div>
        <p className="sub">
          ML · Spread · Totals — ensemble model picks with crowd and line-move context.
        </p>
      </header>

      <div className="tips-head">
        <LeagueTabs
          leagues={LEAGUES}
          active={league}
          counts={data ? { [data.league]: data.tips.length } : {}}
          onChange={(lg) => setLeague(lg as (typeof LEAGUES)[number])}
        />
        <div className="tips-controls">
          <button
            className="refresh"
            onClick={() => void load(league)}
            disabled={loading}
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {data && (
        <div className="tips-meta">
          League {data.league} · as of {data.as_of} · TTL {data.ttl}s · cron {data.cron}
          {updatedAt != null && !loading && ` · updated ${new Date(updatedAt).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`}
        </div>
      )}

      {error && <div className="err">{error}</div>}

      {loading && <div className="empty">Loading tips…</div>}

      {!loading && !error && data && data.tips.length === 0 && (
        <div className="empty">No tips for {league} right now.</div>
      )}

      {!loading && !error && data && data.tips.length > 0 && (
        <div className="tips-list">
          {data.tips.map((t) => (
            <TipCard key={`${t.home}-${t.away}-${t.date}`} t={t} />
          ))}
        </div>
      )}

      <div className="court-divider" aria-hidden="true" />

      <div className="disclaimer">
        <b>Disclaimer</b>
        <span>
          Model outputs are informational only. Basketball is high-variance — no
          pick is a guarantee. Bet responsibly, 21+.
        </span>
      </div>
    </div>
  );
}