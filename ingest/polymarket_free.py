"""Polymarket crowd prices — free public API, no key, no auth.

Per match: search events by team names, keep the open event whose endDate
matches the fixture date, extract Home-win / Away-win Yes-prices +
volumes. Basketball has NO draw — accept when both H and A legs parse
(silently skip any draw leg).

Never raises — None on any failure, gap, or thin market mismatch.

Crowd prices are public-money sentiment, not model output: shown next to our
probs, never fed into the pick.
"""

import json
import logging
import time
import unicodedata
from datetime import datetime, timezone

import requests

BASE = "https://gamma-api.polymarket.com"
TIMEOUT = 20
TTL = 600
VOL_FLOOR = 5000.0

_cache: dict[str, tuple[float, object]] = {}
log = logging.getLogger(__name__)


def _get(url, params):
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
        log.warning("polymarket fetch failed %s: %s", url, e)
        return hit[1] if hit else None


def _norm(name):
    """Lowercase, de-accent — for cross-source matching."""
    s = unicodedata.normalize("NFD", (name or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _tokens(name):
    return set(_norm(name).split())


def _leg(question, home, away):
    """Classify a market question as home/away leg; None when unsure or draw."""
    q = (question or "").lower()
    if "draw" in q or "win" not in q:
        return None
    ht, at = _tokens(home), _tokens(away)
    qt = set(q.replace(".", " ").replace("-", " ").split())
    hs = len(ht & qt) if ht else 0
    aws = len(at & qt) if at else 0
    if hs > aws:
        return "home"
    if aws > hs:
        return "away"
    return None


def _price(market):
    try:
        outcomes = market.get("outcomes") or []
        prices = market.get("outcomePrices") or []
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        if isinstance(prices, str):
            prices = json.loads(prices)
        i = [str(o).lower() for o in outcomes].index("yes")
        p = float(prices[i])
        vol = float(market.get("volume") or 0)
        if 0 < p < 1:
            return round(p, 4), vol
    except (ValueError, TypeError, IndexError, AttributeError):
        pass
    return None


def crowd_lookup(home, away, date_iso):
    """{home, away, volumes, url, low_volume} or None. Never raises."""
    try:
        data = _get(f"{BASE}/public-search", {"q": f"{home} {away}"})
        if not data:
            return None
        try:
            kickoff = datetime.fromisoformat((date_iso or "").replace("Z", "+00:00"))
        except ValueError:
            return None
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        for ev in data.get("events") or []:
            if not isinstance(ev, dict) or ev.get("closed"):
                continue
            try:
                end = datetime.fromisoformat(ev.get("endDate", ""))
            except ValueError:
                continue
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if abs((end - kickoff).total_seconds()) > 36 * 3600:
                continue
            title = _tokens(ev.get("title", ""))
            if not (_tokens(home) & title and _tokens(away) & title):
                continue
            legs, vols = {}, {}
            for m in ev.get("markets") or []:
                if not isinstance(m, dict):
                    continue
                leg = _leg(m.get("question", ""), home, away)
                parsed = _price(m)
                if leg and parsed and leg not in legs:
                    legs[leg], vols[leg] = parsed
            if "home" in legs and "away" in legs:
                return {"home": legs["home"], "away": legs["away"],
                        "volumes": vols,
                        "url": f"https://polymarket.com/event/{ev.get('slug', '')}",
                        "low_volume": any(v < VOL_FLOOR for v in vols.values())}
        return None
    except Exception as e:
        log.warning("polymarket lookup failed %s v %s: %s", home, away, e)
        return None
