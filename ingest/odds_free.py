"""The Odds API v4 — free tier (500 req/mo), key from env ODDS_API_KEY.

Docs: https://the-odds-api.com
Endpoints:
  odds:   GET /v4/sports/{sport}/odds/?apiKey=KEY&regions=us&markets=h2h,spreads,totals&oddsFormat=decimal
  scores: GET /v4/sports/{sport}/scores/?apiKey=KEY&days=3

Sport keys: basketball_nba, basketball_euroleague.
Called only on demand — no network at import, no key → [] / None.
No standings from this source (returns []).
"""
import json
import logging
import os
import time

import requests

BASE = "https://api.the-odds-api.com/v4/sports"
TIMEOUT = 15
TTL = 300  # 5 min
MARKETS = "h2h,spreads,totals"
SPORTS = {"nba": "basketball_nba", "euroleague": "basketball_euroleague"}
_REGIONS = {"nba": "us", "euroleague": "eu"}

log = logging.getLogger(__name__)

_cache: dict[str, tuple[float, object]] = {}


def _key():
    return os.environ.get("ODDS_API_KEY", "").strip()


def _get(url, params):
    """GET JSON with TTL cache; stale fallback; None on any failure (never raise)."""
    now = time.time()
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    hit = _cache.get(key)
    if hit and now - hit[0] < TTL:
        return hit[1]
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        _cache[key] = (now, r.json())
        return r.json()
    except Exception as e:
        log.warning("odds-api fetch failed %s: %s", url, e)
        return hit[1] if hit else None


def _to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _market(bk, key):
    for m in bk.get("markets") or []:
        if isinstance(m, dict) and m.get("key") == key:
            return m
    return None


def _outcome(market, name):
    for o in market.get("outcomes") or []:
        if isinstance(o, dict) and o.get("name") == name:
            return o
    return None


def _parse_game(g):
    """One odds game → dict; None when unusable."""
    if not isinstance(g, dict):
        return None
    home, away = g.get("home_team", ""), g.get("away_team", "")
    if not home or not away:
        return None
    odds = {}
    for bk in g.get("bookmakers") or []:
        if not isinstance(bk, dict):
            continue
        h2h = _market(bk, "h2h")
        ho, ao = (_outcome(h2h, home), _outcome(h2h, away)) if h2h else (None, None)
        if not (ho and ao):
            continue
        spread = spread_odds = total = total_odds = None
        spreads = _market(bk, "spreads")
        if spreads:
            so = _outcome(spreads, home)
            if so:
                spread = _to_float(so.get("point"))
                spread_odds = _to_float(so.get("price"))
        totals = _market(bk, "totals")
        if totals:
            to = _outcome(totals, "Over")
            if to:
                total = _to_float(to.get("point"))
                total_odds = _to_float(to.get("price"))
        odds = {
            "provider": bk.get("key", ""),
            "home": _to_float(ho.get("price")),
            "away": _to_float(ao.get("price")),
            "spread": spread,
            "spread_odds": spread_odds,
            "total": total,
            "total_odds": total_odds,
            "open": {},
            "close": {},
        }
        break
    return {
        "id": str(g.get("id", "")),
        "date": g.get("commence_time", ""),
        "home": home,
        "away": away,
        "home_id": "",
        "away_id": "",
        "home_score": None,
        "away_score": None,
        "state": "pre",
        "detail": "",
        "odds": odds,
    }


def fetch_scoreboard(sport="nba"):
    """Upcoming games with h2h/spreads/totals odds. [] without a key."""
    key = _key()
    if not key:
        return []
    sport_key = SPORTS.get(sport, sport)
    data = _get(f"{BASE}/{sport_key}/odds",
                {"apiKey": key, "regions": _REGIONS.get(sport, "us"),
                 "markets": MARKETS, "oddsFormat": "decimal"})
    if not isinstance(data, list):
        return []
    return [g for g in (_parse_game(x) for x in data) if g]


def fetch_schedules(sport="nba", days=3):
    """Recent + upcoming game results from /scores/. [] without a key."""
    key = _key()
    if not key:
        return []
    sport_key = SPORTS.get(sport, sport)
    data = _get(f"{BASE}/{sport_key}/scores", {"apiKey": key, "days": days})
    if not isinstance(data, list):
        return []
    out = []
    for g in data:
        if not isinstance(g, dict):
            continue
        home, away = g.get("home_team", ""), g.get("away_team", "")
        if not home or not away:
            continue
        completed = bool(g.get("completed"))
        out.append({
            "id": str(g.get("id", "")),
            "date": g.get("commence_time", ""),
            "home": home,
            "away": away,
            "home_id": "",
            "away_id": "",
            "home_score": _to_int(g.get("home_score")),
            "away_score": _to_int(g.get("away_score")),
            "state": "post" if completed else "pre",
            "detail": "",
            "odds": {},
            "played": completed,
        })
    return out


def fetch_standings(sport="nba"):
    """The Odds API has no standings — always []."""
    return []


def match_game(game, home, away):
    """True when an odds game's teams fuzzy-match ESPN home/away names."""
    from ingest.espn_free import _match, _norm
    if not isinstance(game, dict):
        return False
    keys = {_norm(game.get("home", "")), _norm(game.get("away", ""))}
    return _match(home, keys) is not None and _match(away, keys) is not None