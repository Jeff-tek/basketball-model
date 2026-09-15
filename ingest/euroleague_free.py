"""Official EuroLeague API (api-live.euroleague.net) — free, no key, no auth.

Swagger: https://api-live.euroleague.net/swagger/index.html
Endpoints (verified 2026-09-15):
  seasons:    GET /v2/competitions/E/seasons
              → {"data": [{"code": "E2025", "startDate": ..., "endDate": ..., "winner": null}], "total": N}
  results:    GET /v1/results?seasonCode=E2025
              → XML <results><game>…</game></results> — whole season, scores + played flag
  standings:  GET /v3/competitions/E/seasons/E2025/rounds/{n}/basicstandings
              → {"teams": [{"position", "gamesWon", "gamesLost", "winPercentage", "club": {...}}]}

Competition code "E" = EuroLeague; season code "E{startYear}" (E2025 = 2025-26).
No odds here — EuroLeague lines come from The Odds API (odds_free).
Graceful fallback: any failure returns [] / None (never raises). The host
may 403 from some regions; that is handled the same as any other failure.
"""
import json
import logging
import time
import xml.etree.ElementTree as ET

import requests

BASE = "https://api-live.euroleague.net"
TIMEOUT = 20
TTL = 600  # 10 min
log = logging.getLogger(__name__)

_cache: dict[str, tuple[float, object]] = {}


def _fetch(url, params=None):
    """GET text with TTL cache; stale fallback; None on any failure (never raise)."""
    now = time.time()
    qs = "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    key = url + ("?" + qs if qs else "")
    hit = _cache.get(key)
    if hit and now - hit[0] < TTL:
        return hit[1]
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        _cache[key] = (now, r.text)
        return r.text
    except Exception as e:
        log.warning("euroleague fetch failed %s: %s", url, e)
        return hit[1] if hit else None


def _get(url, params=None):
    """GET JSON with TTL cache; None on any failure (never raise)."""
    text = _fetch(url, params)
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


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


def _current_season():
    """Current EuroLeague season code ('E2025'); None on failure."""
    data = _get(f"{BASE}/v2/competitions/E/seasons")
    if not isinstance(data, dict):
        return None
    seasons = data.get("data") or []
    for s in seasons:
        if isinstance(s, dict) and not s.get("winner"):
            return s.get("code")
    s = seasons[0] if seasons else None
    return s.get("code") if isinstance(s, dict) else None


def _parse_game(el):
    """One <game> element from the v1 results XML → dict; None when unusable."""
    def tag(name):
        node = el.find(name)
        return node.text if node is not None and node.text else ""

    home, away = tag("hometeam"), tag("awayteam")
    if not home or not away:
        return None
    played = tag("played").strip().lower() == "true"
    hs, as_ = _to_int(tag("homescore")), _to_int(tag("awayscore"))
    state = "post" if played else ("in" if (hs is not None or as_ is not None) else "pre")
    return {
        "id": tag("gamecode"),
        "date": tag("date"),
        "home": home,
        "away": away,
        "home_id": tag("homecode"),
        "away_id": tag("awaycode"),
        "home_score": hs,
        "away_score": as_,
        "state": state,
        "detail": tag("round"),
        "round": _to_int(tag("gameday")),
        "odds": {},
    }


def _results(season_code):
    """Parsed games for a season code; [] on any failure."""
    if not season_code:
        return []
    text = _fetch(f"{BASE}/v1/results", {"seasonCode": season_code})
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    return [g for g in (_parse_game(el) for el in root.iter("game")) if g]


def fetch_scoreboard(season=None):
    """Upcoming + live EuroLeague games (current season by default)."""
    games = _results(season or _current_season())
    return [g for g in games if g["state"] != "post"]


def fetch_schedules(season=None):
    """All EuroLeague games for a season; played flag on finished."""
    games = _results(season or _current_season())
    return [{**g, "played": g["state"] == "post"} for g in games]


def _last5(form):
    """['W','L','W'] → 'WLW'; '' when absent."""
    if not isinstance(form, list):
        return ""
    return "".join(str(f)[:1] for f in form if f)


def fetch_standings(season=None):
    """EuroLeague standings for the latest completed round."""
    season_code = season or _current_season()
    if not season_code:
        return []
    games = _results(season_code)
    rnd = max((g["round"] for g in games if g["state"] == "post"), default=1)
    data = _get(f"{BASE}/v3/competitions/E/seasons/{season_code}/rounds/{rnd}/basicstandings")
    if not data:
        return []
    rows = []
    for s in data.get("teams", []) or []:
        if not isinstance(s, dict):
            continue
        club = s.get("club") or {}
        pct = str(s.get("winPercentage") or "").rstrip("%")
        rows.append({
            "rank": _to_int(s.get("position")),
            "team": club.get("name") or club.get("abbreviatedName") or "",
            "team_id": str(club.get("code", "")),
            "wins": _to_int(s.get("gamesWon")),
            "losses": _to_int(s.get("gamesLost")),
            "win_pct": _to_float(pct),
            "streak": _last5(s.get("last5Form")),
            "points_for": _to_float(s.get("pointsFor")),
            "points_against": _to_float(s.get("pointsAgainst")),
        })
    return rows