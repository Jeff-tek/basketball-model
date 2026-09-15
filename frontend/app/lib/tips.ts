const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export type TeamMeta = {
  team: string;
  rank: number | null;
  wins: number | null;
  losses: number | null;
  winPct: number | null;
  streak: string | null;
  pf: number | null;
  pa: number | null;
} | null;

type ProbNull = number | null;

export type Tip = {
  home: string;
  away: string;
  date: string;
  probs: {
    ml: { home: ProbNull; away: ProbNull };
    spread: { home: ProbNull; away: ProbNull };
    totals: { over: ProbNull; under: ProbNull };
  };
  fair: {
    ml: { home: ProbNull; away: ProbNull };
    spread: { home: ProbNull; away: ProbNull };
    totals: { over: ProbNull; under: ProbNull };
  };
  edge: { market: string; value: number };
  pick: string;
  verdict: "BET" | "MARGINAL" | "NO BET" | "PASS";
  reasons: string[];
  confidence: number;
  models: string[];
  crowd: {
    home: number;
    away: number;
    volumes: { home: number; away: number };
    url: string;
    low_volume: boolean;
  } | null;
  lineMove: { Home?: string; Away?: string; Spread?: string; Total?: string } | null;
  sources: { name: string; url: string }[];
  homeForm: string;
  awayForm: string;
  homePace: number;
  awayPace: number;
  bookOdds: {
    ml_home: number | null;
    ml_away: number | null;
    spread: number | null;
    spread_price: number | null;
    total: number | null;
    over_price: number | null;
    under_price: number | null;
  };
  teamMeta?: { home: TeamMeta; away: TeamMeta };
};

export type TipsResponse = {
  league: string;
  as_of: string;
  ttl: number;
  cron: string;
  tips: Tip[];
};

export async function getTips(league: string): Promise<TipsResponse> {
  const r = await fetch(`${API}/tips?league=${encodeURIComponent(league)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export type LiveScore = {
  home: string;
  away: string;
  home_score: number | null;
  away_score: number | null;
  state: string;
};

export async function getLive(league: string): Promise<LiveScore[]> {
  const r = await fetch(`${API}/live?league=${encodeURIComponent(league)}`, { cache: "no-store" });
  if (!r.ok) return [];
  return r.json();
}
