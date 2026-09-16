"""Tests for server/main.py — NBA + EuroLeague /tips API."""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException  # noqa: E402

from server.main import (  # noqa: E402
    _is_today, _missing_odds_note, _model_only_tip, _normalize_tip, tips,
)


def test_tips_envelope():
    """GET /tips returns {league, as_of, ttl, cron, tips}."""
    result = tips(league="NBA")
    assert set(result) == {"league", "as_of", "ttl", "cron", "tips"}
    assert result["league"] == "NBA"
    assert isinstance(result["tips"], list)


def test_tips_accepts_both_leagues():
    for league in ("NBA", "EuroLeague"):
        result = tips(league=league)
        assert result["league"] == league
        assert isinstance(result["tips"], list)


def test_tips_unknown_league_400():
    try:
        tips(league="NHL")
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400


def test_missing_odds_note_none_when_complete():
    odds = {"ml_home": 1.85, "ml_away": 2.10, "spread": -4.5,
            "spread_price": 1.91, "total": 224.5,
            "over_price": 1.91, "under_price": 1.91}
    assert _missing_odds_note(odds) is None


def test_missing_odds_note_lists_legs():
    odds = {"ml_home": 1.85}
    note = _missing_odds_note(odds)
    assert note is not None
    assert "ml_away" in note and "spread" in note and "total" in note
    assert "no edge check" in note


def test_missing_odds_note_never_says_no_bet():
    """The note is informational; it must not contain a verdict."""
    note = _missing_odds_note({})
    assert note is not None
    assert "NO BET" not in note


def test_model_only_tip_structure():
    tip = _model_only_tip("Lakers", "Celtics", {})
    assert set(tip) == {"probs", "pick", "verdict", "confidence",
                        "reasons", "models", "tags"}
    assert set(tip["probs"]) == {"ml", "spread", "totals"}
    assert set(tip["probs"]["ml"]) == {"home", "away"}
    assert set(tip["probs"]["spread"]) == {"home", "away"}
    assert set(tip["probs"]["totals"]) == {"over", "under"}
    assert tip["verdict"] == "NO BET"
    assert any("Engine unavailable" in r for r in tip["reasons"])


def test_model_only_tip_notes_missing_odds():
    tip = _model_only_tip("Lakers", "Celtics", {"ml_home": 1.85})
    assert any("Book odds incomplete" in r for r in tip["reasons"])


def test_normalize_tip_maps_engine_output():
    raw = {
        "probs": {"ML": {"home": 0.62, "away": 0.38},
                  "spread": {"home_cover": 0.55, "away_cover": 0.45},
                  "total": {"over": 0.48, "under": 0.52}},
        "pick": "Lakers -4.5", "verdict": "BET", "confidence": 71.5,
        "reasons": ["Home court edge"], "models": ["normal"], "kelly": 0.01,
    }
    tip = _normalize_tip(raw)
    assert tip["pick"] == "Lakers -4.5"
    assert tip["verdict"] == "BET"
    assert tip["confidence"] == 71.5
    assert tip["probs"]["ml"]["home"] == 0.62
    assert tip["probs"]["spread"]["home"] == 0.55
    assert tip["probs"]["totals"]["over"] == 0.48


def test_normalize_tip_none_for_non_dict():
    assert _normalize_tip(None) is None
    assert _normalize_tip("nope") is None


def test_engine_tip_integration():
    """Real engine.bball.build_tip flows through the adapter end-to-end."""
    from server import main
    ratings = {"home_off": 112.0, "home_def": 105.0,
               "away_off": 108.0, "away_def": 110.0, "home_court": 3.5}
    odds = {"ml_home": 1.85, "ml_away": 2.10, "spread": -4.5,
            "spread_price": 1.91, "total": 224.5,
            "over_price": 1.91, "under_price": 1.91}
    orig = main._ratings_from_form
    main._ratings_from_form = lambda *a, **k: ratings
    try:
        tip = main._engine_tip("Lakers", "Celtics", "1", "2",
                               odds, "nba", "NBA")
    finally:
        main._ratings_from_form = orig
    assert tip is not None
    assert set(tip["probs"]) == {"ml", "spread", "totals"}
    assert set(tip["probs"]["ml"]) == {"home", "away"}
    assert set(tip["probs"]["spread"]) == {"home", "away"}
    assert set(tip["probs"]["totals"]) == {"over", "under"}
    assert tip["verdict"] in ("BET", "MARGINAL", "NO BET")
    assert 0.0 <= tip["confidence"] <= 100.0
    assert tip["reasons"], "engine reasons expected"
    assert tip["models"], "engine models expected"


def test_is_today_now():
    assert _is_today(datetime.now(timezone.utc).isoformat())


def test_is_today_past():
    assert not _is_today("2020-01-01T00:00:00Z")


def test_is_today_garbage():
    assert not _is_today("not-a-date")


def test_missing_odds_never_forces_no_bet():
    """Missing odds append an info reason; verdict stays model-driven."""
    from server import main
    fake_events = [{
        "home": "Lakers", "away": "Celtics",
        "date": datetime.now(timezone.utc).isoformat(),
        "home_id": "1", "away_id": "2",
        "odds": {"ml_home": 1.85},
    }]
    orig_fetch, orig_engine = main._fetch_events, main._engine_tip
    main._fetch_events = lambda league, espn_key: fake_events
    main._engine_tip = lambda *a, **k: {
        "probs": {"ml": {"home": 0.6, "away": 0.4},
                  "spread": {"home": None, "away": None},
                  "totals": {"over": None, "under": None}},
        "pick": "Lakers", "verdict": "BET", "confidence": 72.0,
        "reasons": ["Model edge"], "models": ["bball"], "tags": [],
    }
    try:
        result = main.tips(league="NBA")
    finally:
        main._fetch_events, main._engine_tip = orig_fetch, orig_engine
    assert result["tips"], "expected at least one tip"
    t = result["tips"][0]
    assert t["verdict"] == "BET", "missing odds must not force NO BET"
    assert any("Book odds incomplete" in r for r in t["reasons"])
    assert t["bookOdds"]["ml_home"] == 1.85
    assert t["bookOdds"]["ml_away"] is None
    assert t["bookOdds"]["spread"] is None


def test_tips_model_only_fallback():
    """Engine unavailable → model-only tip envelope, no crash."""
    from server import main
    fake_events = [{
        "home": "Lakers", "away": "Celtics",
        "date": datetime.now(timezone.utc).isoformat(),
        "home_id": "1", "away_id": "2",
        "odds": {},
    }]
    orig_fetch, orig_engine = main._fetch_events, main._engine_tip
    main._fetch_events = lambda league, espn_key: fake_events
    main._engine_tip = lambda *a, **k: None
    try:
        result = main.tips(league="NBA")
    finally:
        main._fetch_events, main._engine_tip = orig_fetch, orig_engine
    assert result["tips"]
    t = result["tips"][0]
    assert t["verdict"] == "NO BET"
    assert any("Engine unavailable" in r for r in t["reasons"])
    assert t["bookOdds"]["ml_home"] is None


def test_tips_skips_non_today():
    """Post-state events filtered; pre-match with old dates kept; no state → pre."""
    from server import main
    fake_events = [
        {
            "home": "Lakers", "away": "Celtics",
            "date": datetime.now(timezone.utc).isoformat(),
            "home_id": "1", "away_id": "2",
            "state": "post",  # (a) post → filtered
            "odds": {"ml_home": 1.85, "ml_away": 2.10},
        },
        {
            "home": "Warriors", "away": "Heat",
            "date": "2020-01-01T00:00:00Z",
            "home_id": "3", "away_id": "4",
            "state": "pre",  # (b) pre-match + old date → kept
            "odds": {"ml_home": 1.85, "ml_away": 2.10},
        },
        {
            "home": "Nuggets", "away": "Mavericks",
            "date": datetime.now(timezone.utc).isoformat(),
            "home_id": "5", "away_id": "6",
            # (c) no state → server defaults to "pre"
            "odds": {"ml_home": 1.85, "ml_away": 2.10},
        },
    ]
    orig_fetch = main._fetch_events
    main._fetch_events = lambda league, espn_key: fake_events
    try:
        result = main.tips(league="NBA")
    finally:
        main._fetch_events = orig_fetch
    names = [(t["home"], t["away"]) for t in result["tips"]]
    assert ("Lakers", "Celtics") not in names, "post-state should be filtered"
    assert ("Warriors", "Heat") in names, "pre-match with old date should be kept"
    assert ("Nuggets", "Mavericks") in names, "no state defaults to pre"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")