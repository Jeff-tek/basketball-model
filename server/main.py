"""Basketball Model API — NBA + EuroLeague tips.

Mirrors football-model/server/main.py structure with basketball markets
(ML + Spread + Totals; no draws, no BTTS). Engine and ingest modules are
imported defensively inside functions; when unavailable the server falls
back to a model-only tip and never forces NO BET on missing odds.
"""

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Optional

import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Basketball Model API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

LEAGUES = {"NBA": "NBA", "EuroLeague": "EuroLeague"}
ESPN_SLUGS = {"NBA": "nba", "EuroLeague": "euroleague"}
CACHE_TTL = 120  # seconds
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = Lock()

# Contract with ingest/*.py event shape:
#   {home, away, date, home_id, away_id, home_form, away_form,
#    odds: {ml_home, ml_away, spread, spread_price, total,
#           over_price, under_price,
#           open: {ml_home, ml_away, spread, total}}}
ODDS_LEGS = ("ml_home", "ml_away", "spread", "spread_price",
             "total", "over_price", "under_price")


def _cached(key: str, producer: Callable[[], Any], force: bool = False) -> Any:
    """In-memory TTL cache; producer() called on miss or expiry."""
    now = time.time()
    if not force:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and now - hit[0] < CACHE_TTL:
                return hit[1]
    value = producer()
    with _cache_lock:
        _cache[key] = (time.time(), value)
    return value


def _is_today(iso: str) -> bool:
    """True when an ISO datetime falls on today's UTC calendar day."""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date() == datetime.now(timezone.utc).date()
    except (TypeError, ValueError):
        return False


def _display_league(league: str) -> str:
    """League key → display name (identity for NBA/EuroLeague)."""
    return LEAGUES.get(league, league)


def _missing_odds_note(odds: dict) -> Optional[str]:
    """Info-only reason for missing book legs; never forces NO BET."""
    missing = [leg for leg in ODDS_LEGS if not odds.get(leg)]
    if not missing:
        return None
    return ("Book odds incomplete (" + ", ".join(missing) +
            " unavailable) — no edge check, verdict on model confidence only")


def _normalize_tip(tip: Any) -> Optional[dict]:
    """Defensively map engine.bball.build_tip output to the API envelope.

    Engine probs shape: {ML: {home, away}, spread: {home_cover, away_cover},
    total: {over, under}} → API shape: {ml, spread, totals}.
    """
    if not isinstance(tip, dict):
        return None
    probs = tip.get("probs") or {}
    ml = probs.get("ML") or {}
    spread = probs.get("spread") or {}
    total = probs.get("total") or {}
    return {
        "probs": {
            "ml": {"home": ml.get("home"), "away": ml.get("away")},
            "spread": {"home": spread.get("home_cover"),
                       "away": spread.get("away_cover")},
            "totals": {"over": total.get("over"), "under": total.get("under")},
        },
        "pick": tip.get("pick") or "Home",
        "verdict": tip.get("verdict") or "NO BET",
        "confidence": tip.get("confidence") or 0.0,
        "reasons": list(tip.get("reasons") or []),
        "models": list(tip.get("models") or []),
        "tags": [],
    }


def _model_only_tip(home_name: str, away_name: str,
                    odds: Optional[dict] = None) -> dict:
    """Structural fallback when engine.bball.build_tip is unavailable.

    Basketball analog of football's _simple_tip, but no model math inline
    (the engine owns that): emits a valid tip envelope with an explanatory
    reason. Missing odds are noted, never forced into the verdict.
    """
    reasons = ["Engine unavailable — model-only fallback, no edge check"]
    note = _missing_odds_note(odds or {})
    if note:
        reasons.append(note)
    return {
        "probs": {"ml": {"home": None, "away": None},
                  "spread": {"home": None, "away": None},
                  "totals": {"over": None, "under": None}},
        "pick": "Home",
        "verdict": "NO BET",
        "confidence": 0.0,
        "reasons": reasons,
        "models": [],
        "tags": [],
    }


def _team_form(hs: list, as_: list, home_name: str, away_name: str) -> Optional[dict]:
    """Last-5 avg points for/against + record string from schedule rows."""
    def avg(sched: list, team: str) -> Optional[tuple]:
        played = [m for m in sched if m.get("played")][-5:]
        if not played:
            return None
        pf = pa = 0
        for m in played:
            if m.get("home") == team:
                pf += m.get("home_score") or 0
                pa += m.get("away_score") or 0
            else:
                pf += m.get("away_score") or 0
                pa += m.get("home_score") or 0
        n = len(played)
        return pf / n, pa / n, n

    h = avg(hs, home_name)
    a = avg(as_, away_name)
    if not h or not a:
        return None
    hpf, hpa, hn = h
    apf, apa, an = a
    return {
        "home_points_for": hpf, "home_points_against": hpa,
        "away_points_for": apf, "away_points_against": apa,
        "home_last5": f"{hpf * hn:.0f}-{hpa * hn:.0f}/{hn}",
        "away_last5": f"{apf * an:.0f}-{apa * an:.0f}/{an}",
        "sample": min(hn, an),
    }


def _ratings_from_form(home_name: str, away_name: str, home_id: str,
                       away_id: str, espn_key: str, league: str) -> Optional[dict]:
    """Engine ratings {home_off, home_def, away_off, away_def, home_court}
    from ingest schedules. None when form data is unavailable."""
    try:
        from ingest import espn_free
        hs = _cached(f"form:{home_id}",
                     lambda: espn_free.fetch_team_schedule(home_id, espn_key))
        as_ = _cached(f"form:{away_id}",
                      lambda: espn_free.fetch_team_schedule(away_id, espn_key))
        form = _team_form(hs, as_, home_name, away_name)
    except Exception:
        return None
    if not form:
        return None
    try:
        from engine.elo import HOME_COURT_NBA, HOME_COURT_EUROLEAGUE
        home_court = HOME_COURT_EUROLEAGUE if league == "EuroLeague" else HOME_COURT_NBA
    except (ImportError, ModuleNotFoundError):
        home_court = 3.5
    return {
        "home_off": form["home_points_for"],
        "home_def": form["home_points_against"],
        "away_off": form["away_points_for"],
        "away_def": form["away_points_against"],
        "home_court": home_court,
    }


def _market_from_odds(odds: dict) -> dict:
    """Engine market dict {spread, total, home_ml, away_ml} from ingest odds."""
    return {
        "spread": odds.get("spread", 0.0),
        "total": odds.get("total", 220.0),
        "home_ml": odds.get("ml_home"),
        "away_ml": odds.get("ml_away"),
    }


def _engine_tip(home_name: str, away_name: str, home_id: str, away_id: str,
                odds: dict, espn_key: str, league: str) -> Optional[dict]:
    """Compose engine.bball.build_tip with form from ingest schedules."""
    try:
        from engine.bball import build_tip
    except (ImportError, ModuleNotFoundError):
        try:
            from engine.bball.build_tip import build_tip
        except (ImportError, ModuleNotFoundError):
            return None
    ratings = _ratings_from_form(home_name, away_name, home_id, away_id,
                                 espn_key, league)
    if not ratings:
        return None
    try:
        tip = build_tip(ratings, _market_from_odds(odds))
    except Exception:
        return None
    return _normalize_tip(tip)


def _fetch_events(league: str, espn_key: str) -> list:
    """Scoreboard events from ingest modules (defensive). [] on failure."""
    if league == "EuroLeague":
        try:
            from ingest import euroleague_api
            return _cached(f"live:{espn_key}",
                           lambda: euroleague_api.fetch_scoreboard())
        except Exception:
            pass
    try:
        from ingest import espn_free
        return _cached(f"live:{espn_key}",
                       lambda: espn_free.fetch_scoreboard(espn_key))
    except Exception:
        return []


@app.get("/tips")
def tips(league: str = "NBA") -> dict:
    """Today's NBA/EuroLeague tips: ML + Spread + Totals."""
    if league not in LEAGUES:
        raise HTTPException(400, f"unknown league: {league}")
    espn_key = ESPN_SLUGS[league]
    events = _fetch_events(league, espn_key)

    tips_list = []
    for ev in events:
        home_name = ev.get("home", "")
        away_name = ev.get("away", "")
        match_date = ev.get("date", "")
        odds = ev.get("odds") or {}
        open_odds = odds.get("open") or {}
        home_id = ev.get("home_id", "")
        away_id = ev.get("away_id", "")
        home_form = ev.get("home_form", "")
        away_form = ev.get("away_form", "")

        if not _is_today(match_date):
            continue
        ml_home = odds.get("ml_home")
        ml_away = odds.get("ml_away")
        if ml_home and ml_away and min(ml_home, ml_away) <= 1:
            continue

        # Compose engine.bball.build_tip when available, else model-only.
        # Partial boards (a leg OFF/missing) still render as model-only cards.
        tip = _engine_tip(home_name, away_name, home_id, away_id,
                          odds, espn_key, _display_league(league))
        if not tip:
            tip = _model_only_tip(home_name, away_name, odds)
        note = _missing_odds_note(odds)
        if note:
            tip["reasons"].append(note)

        sources = [
            {"name": "ESPN",
             "url": f"https://www.espn.com/nba/scoreboard/_/league/{espn_key}"},
            {"name": "OddsPortal", "url": "https://www.oddsportal.com/basketball/"},
            {"name": "BetExplorer", "url": "https://www.betexplorer.com/basketball/"},
            {"name": "ToolsGambling", "url": "https://www.toolsgambling.com/live-odds"},
            {"name": "OddsGPT", "url": "https://www.oddsgpt.com/poisson-model"},
        ]
        if tip.get("tags"):
            sources.append({"name": "The Open Model", "url": "https://theopenmodel.com"})

        # Crowd (Polymarket public money) — display only, never feeds the pick
        crowd = None
        try:
            from ingest.polymarket_free import crowd_lookup
            crowd = _cached(f"crowd:{home_name}|{away_name}",
                            lambda: crowd_lookup(home_name, away_name, match_date))
        except Exception:
            crowd = None

        # Line movement (open → close, decimal) — display only
        line_move = None
        try:
            moves = {}
            for label, close_v, open_v in (
                    ("ML Home", ml_home, open_odds.get("ml_home")),
                    ("ML Away", ml_away, open_odds.get("ml_away")),
                    ("Spread", odds.get("spread"), open_odds.get("spread")),
                    ("Total", odds.get("total"), open_odds.get("total"))):
                if (isinstance(open_v, (int, float)) and open_v > 1
                        and isinstance(close_v, (int, float))
                        and abs(open_v - close_v) > 0.005):
                    moves[label] = f"{open_v:.2f} → {close_v:.2f}"
            line_move = moves or None
        except Exception:
            line_move = None

        if line_move:
            tip["reasons"].append(
                "Steam: " + ", ".join(f"{k} {v}" for k, v in line_move.items()))
        if crowd:
            tip["reasons"].append(
                f"Crowd (Polymarket): H {crowd['home']:.0%} / A {crowd['away']:.0%}"
                + (" — thin market, treat lightly" if crowd["low_volume"] else ""))
            ml = tip["probs"]["ml"]
            if not crowd["low_volume"] and isinstance(ml.get("home"), (int, float)) \
                    and isinstance(ml.get("away"), (int, float)):
                diffs = [(label, crowd[key] - ml[side])
                         for label, key, side in
                         (("Home", "home", "home"), ("Away", "away", "away"))]
                hot, d = max(diffs, key=lambda kv: kv[1])
                if d > 0.10:
                    tip["reasons"].append(f"Crowd hotter on {hot} than model (+{d:.0%})")
            sources.append({"name": "Polymarket", "url": crowd["url"]})

        tips_list.append({
            "home": home_name, "away": away_name,
            "date": match_date,
            "probs": tip["probs"],
            "pick": tip["pick"], "verdict": tip["verdict"],
            "confidence": tip["confidence"],
            "reasons": tip["reasons"],
            "bookOdds": {"ml_home": ml_home, "ml_away": ml_away,
                         "spread": odds.get("spread"),
                         "spread_price": odds.get("spread_price"),
                         "total": odds.get("total"),
                         "over_price": odds.get("over_price"),
                         "under_price": odds.get("under_price")},
            "lineMove": line_move,
            "models": tip.get("models", []),
            "crowd": crowd,
            "sources": sources,
            "homeForm": home_form, "awayForm": away_form,
        })

    return {"league": league, "as_of": datetime.now(timezone.utc).isoformat(),
            "tips": tips_list}


@app.get("/health")
def health() -> dict:
    return {"ok": True}