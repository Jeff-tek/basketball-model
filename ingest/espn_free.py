"""Free ESPN NBA ingest — pure fetch+parse, stdlib+requests only.

Endpoints (unofficial, may change):
  scoreboard: site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard
  teams:      site.api.espn.com/apis/site/v2/sports/basketball/nba/teams
  schedule:   site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{id}/schedule?season=2026
  standings:  site.api.espn.com/apis/v2/sports/basketball/nba/standings

Odds (when posted, from scoreboard competitions[].odds[]):
  moneyline home/away (close preferred, open fallback) → decimal
  spread (home line, - = favorite) + total (over/under)
  open/close nodes carry per-side moneyLine/spread/total.

5 min TTL cache with stale fallback. Never raises — [] / None on any
failure so tips never break because of this feed.
"""
import json
import logging
import time
import unicodedata

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
STANDINGS_BASE = "https://site.api.espn.com/apis/v2/sports/basketball/nba"
TIMEOUT = 15
TTL = 300
# NOTE: send no custom User-Agent — ESPN returns 403 Access Denied for
# custom UAs but allows requests' default (verified 2026-09-15).
log = logging.getLogger(__name__)

_cache: dict[str, tuple[float, object]] = {}

_ALIASES = {
    "la": "los angeles", "ny": "new york", "nyk": "new york",
    "okc": "oklahoma city", "gs": "golden state", "gsw": "golden state",
    "sa": "san antonio", "sas": "san antonio", "no": "new orleans",
    "nop": "new orleans", "phx": "phoenix", "phi": "philadelphia",
    "lal": "los angeles", "lac": "la clippers",
}


def _norm(name):
    """Lowercase, de-accent, expand city aliases — for cross-source matching."""
    s = unicodedata.normalize("NFD", (name or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace(".", " ").replace("-", " ")
    return " ".join(_ALIASES.get(t, t) for t in s.split())


def _match(name, keys):
    """Exact normalized match, else token-subset match (shorter ⊆ longer)."""
    n = _norm(name)
    if n in keys:
        return n
    nt = set(n.split())
    for k in keys:
        kt = set(k.split())
        if nt and kt and (nt <= kt or kt <= nt):
            return k
    return None


def _fix_pvt(obj):
    """ESPN sometimes serves .pvt hosts; normalize to .com recursively."""
    if isinstance(obj, dict):
        return {k: _fix_pvt(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix_pvt(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace(".pvt.", ".com.")
    return obj


def _get(url, params=None):
    """GET JSON with TTL cache; stale fallback; None on any failure (never raise)."""
    now = time.time()
    qs = "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    key = url + ("?" + qs if qs else "")
    hit = _cache.get(key)
    if hit and now - hit[0] < TTL:
        return hit[1]
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = _fix_pvt(r.json())
        _cache[key] = (now, data)
        return data
    except Exception as e:
        log.warning("espn fetch failed %s: %s", url, e)
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


def _dec_or_none(f):
    return round(f, 3) if isinstance(f, float) and f > 1 else None


def decimal_to_american(dec):
    """Decimal odds → American string (+135 / -110). None when unusable."""
    try:
        profit = float(dec) - 1.0
    except (TypeError, ValueError):
        return None
    if profit >= 1.0:
        return f"+{round(profit * 100):.0f}"
    if profit > 0:
        return f"-{round(100 / profit):.0f}"
    return None


def american_to_decimal(v):
    """American odds (+135, -110, 'EVEN') → decimal. Decimal input passes through."""
    if isinstance(v, str):
        s = v.strip().upper()
        if s in ("EVEN", "EV"):
            return 2.0
        if s[:1] in ("+", "-"):
            v = _to_int(s)
            if v is None:
                return None
        else:
            return _dec_or_none(_to_float(s))
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and abs(v) < 100:
        return _dec_or_none(float(v))
    ml = _to_int(v)
    if not ml:
        return None
    return round(1 + ml / 100, 3) if ml > 0 else round(1 + 100 / abs(ml), 3)


def _score(c):
    """Competitor score: plain string on scoreboards, {value/displayValue} dict on schedules."""
    s = c.get("score")
    if isinstance(s, dict):
        return _to_int(s.get("value", s.get("displayValue")))
    return _to_int(s)


def _record(c):
    """'12-5' overall record from competitor records; '' when absent."""
    recs = c.get("records") or []
    if isinstance(recs, list) and recs:
        r = recs[0]
        if isinstance(r, dict):
            return r.get("summary", "")
    return ""


def _competitors(comp):
    out = {}
    for c in comp.get("competitors", []) or []:
        if not isinstance(c, dict):
            continue
        team = c.get("team", {}) or {}
        side = c.get("homeAway", "away")
        out[side] = {
            "id": str(team.get("id", "")),
            "name": team.get("displayName") or team.get("shortDisplayName") or "",
            "score": _score(c),
            "record": _record(c),
        }
    return out


def _ml(moneyline, side):
    """Close American line preferred, open as fallback → decimal."""
    if not isinstance(moneyline, dict):
        return None
    leg = moneyline.get(side) or {}
    if not isinstance(leg, dict):
        return None
    for key in ("close", "open"):
        node = leg.get(key) or {}
        if isinstance(node, dict) and node.get("odds") is not None:
            dec = american_to_decimal(node.get("odds"))
            if dec:
                return dec
    return None


def _side_lines(node):
    """{home, away, spread, total} from an odds open/close node."""
    out = {"home": None, "away": None, "spread": None, "total": None}
    if not isinstance(node, dict):
        return out
    for side in ("home", "away"):
        leg = node.get(side) or {}
        if not isinstance(leg, dict):
            continue
        if leg.get("moneyLine") is not None:
            out[side] = american_to_decimal(leg.get("moneyLine"))
        if out["spread"] is None and leg.get("spread") is not None:
            out["spread"] = _to_float(leg.get("spread"))
        if out["total"] is None and leg.get("total") is not None:
            out["total"] = _to_float(leg.get("total"))
    return out


def _odds(comp):
    """Decimal ML + spread + total from DraftKings; {} when absent/incomplete."""
    entries = comp.get("odds") or []
    if not isinstance(entries, list):
        return {}
    dicts = [o for o in entries if isinstance(o, dict)]
    dk = next((o for o in dicts if (o.get("provider") or {}).get("name") == "DraftKings"), None)
    cands = ([dk] + [o for o in dicts if o is not dk]) if dk else dicts
    for o in cands:
        ml = o.get("moneyline")
        h, a = _ml(ml, "home"), _ml(ml, "away")
        if not (h and a):
            continue
        spread = _to_float(o.get("spread"))
        if spread is None:
            spread = _to_float((o.get("homeTeamOdds") or {}).get("spread"))
        total = _to_float(o.get("overUnder"))
        if total is None:
            total = _to_float((o.get("homeTeamOdds") or {}).get("total"))
        return {
            "provider": (o.get("provider") or {}).get("name", ""),
            "home": h, "away": a,
            "spread": spread,
            "total": total,
            "open": _side_lines(o.get("open")),
            "close": _side_lines(o.get("close")),
        }
    return {}


def _parse_event(ev):
    comps = ev.get("competitions", []) or []
    if not comps:
        return None
    comp = comps[0]
    teams = _competitors(comp)
    if "home" not in teams or "away" not in teams:
        return None
    status = (comp.get("status", {}) or {}).get("type", {}) or {}
    return {
        "id": str(ev.get("id", "")),
        "date": ev.get("date", ""),
        "home": teams["home"]["name"],
        "away": teams["away"]["name"],
        "home_id": teams["home"]["id"],
        "away_id": teams["away"]["id"],
        "home_score": teams["home"]["score"],
        "away_score": teams["away"]["score"],
        "state": status.get("state", "pre"),
        "detail": status.get("shortDetail", ""),
        "home_record": teams["home"].get("record", ""),
        "away_record": teams["away"].get("record", ""),
        "odds": _odds(comp),
    }


def fetch_scoreboard():
    """Live + upcoming NBA games.

    Merges ESPN's default window with an explicit today-date query —
    the default window lags on matchdays (ESPN still serving yesterday's
    FTs while today's fixtures only exist under ?dates=YYYYMMDD).
    """
    from datetime import datetime, timezone
    data = _get(f"{BASE}/scoreboard")
    events = list((data.get("events", []) or []) if data else [])
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    dated = _get(f"{BASE}/scoreboard", params={"dates": today})
    if dated:
        events += dated.get("events", []) or []
    seen = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        key = str(ev.get("id")) if ev.get("id") is not None else \
            f"{ev.get('date')}|{ev.get('name')}"
        seen[key] = ev
    return [m for m in (_parse_event(ev) for ev in seen.values()) if m]


def fetch_teams():
    """NBA team list (id, name, abbreviation)."""
    data = _get(f"{BASE}/teams")
    if not data:
        return []
    out = []
    for grp in data.get("sports", []) or []:
        for lg in grp.get("leagues", []) or []:
            for t in lg.get("teams", []) or []:
                team = t.get("team", {}) or {}
                out.append({
                    "id": str(team.get("id", "")),
                    "name": team.get("displayName") or team.get("shortDisplayName") or "",
                    "abbr": team.get("abbreviation", ""),
                })
    return out


def fetch_team_schedule(team_id, season="2026"):
    """Played NBA games for a team (form source). Team IDs are global in ESPN."""
    data = _get(f"{BASE}/teams/{team_id}/schedule", params={"season": season})
    if not data:
        return []
    out = []
    for ev in data.get("events", []) or []:
        m = _parse_event(ev)
        if m and m["state"] == "post":
            out.append({**m, "played": True})
    return out


def fetch_schedules(season="2026"):
    """All NBA games in a season (aggregated per-team schedules, deduped)."""
    teams = fetch_teams()
    seen, out = set(), []
    for t in teams:
        for m in fetch_team_schedule(t["id"], season=season):
            if m["id"] and m["id"] in seen:
                continue
            seen.add(m["id"])
            out.append(m)
    return out


def fetch_standings():
    """NBA standings table (conference children flattened)."""
    data = _get(f"{STANDINGS_BASE}/standings")
    if not data:
        return []
    rows = []
    for child in data.get("children", []) or []:
        entries = ((child.get("standings", {}) or {}).get("entries", []) or [])
        for i, e in enumerate(entries, start=1):
            team = e.get("team", {}) or {}
            stats = {s.get("name"): s.get("value") for s in e.get("stats", []) or []}
            streak = stats.get("streak")
            rows.append({
                "rank": i,
                "team": team.get("displayName") or team.get("shortDisplayName") or "",
                "team_id": str(team.get("id", "")),
                "wins": _to_int(stats.get("wins")),
                "losses": _to_int(stats.get("losses")),
                "win_pct": _to_float(stats.get("winPercent")),
                "games_behind": _to_float(stats.get("gamesBehind")),
                "streak": streak if isinstance(streak, str) else "",
                "avg_points_for": _to_float(stats.get("avgPointsFor")),
                "avg_points_against": _to_float(stats.get("avgPointsAgainst")),
            })
    return rows