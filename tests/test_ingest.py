"""Tests for ingest/espn_free.py + euroleague_free.py + odds_free.py — mocked HTTP, no network.

Runnable via `python tests/test_ingest.py` (no pytest needed) or pytest.
"""
import json
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests as _req


def _clear_caches():
    """Drop module TTL caches so mocked URLs never short-circuit across tests."""
    import ingest.espn_free as e
    import ingest.euroleague_free as el
    import ingest.odds_free as o
    e._cache.clear()
    el._cache.clear()
    o._cache.clear()


def _mock_get(payload):
    r = MagicMock()
    r.status_code = 200
    if isinstance(payload, str):
        r.text = payload
        r.json.return_value = payload
    else:
        r.text = json.dumps(payload)
        r.json.return_value = payload
    r.raise_for_status = MagicMock()
    return r


def _mock_get_error(status=500):
    r = MagicMock()
    r.status_code = status
    r.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return r


def _dispatch(responses):
    """requests.get side_effect dispatching on URL substring → mocked response."""
    def _side_effect(url, params=None, timeout=None, **kw):
        for needle, payload in responses:
            if needle in url:
                return _mock_get(payload)
        raise AssertionError(f"unexpected url {url}")
    return _side_effect


# ============================== espn_free ==============================


def _odds_entry(home_ml="-330", away_ml="+260", spread=-7.5, total=224.5):
    return {
        "provider": {"name": "DraftKings"},
        "details": "BOS -7.5",
        "spread": spread,
        "overUnder": total,
        "moneyline": {
            "home": {"odds": home_ml, "open": {"odds": "-320"}, "close": {"odds": home_ml}},
            "away": {"odds": away_ml, "open": {"odds": "+250"}, "close": {"odds": away_ml}},
        },
        "open": {
            "home": {"moneyLine": -320, "spread": -7.5, "total": 224.5},
            "away": {"moneyLine": 250, "spread": 7.5, "total": 224.5},
        },
        "close": {
            "home": {"moneyLine": -330, "spread": -7.5, "total": 224.5},
            "away": {"moneyLine": 260, "spread": 7.5, "total": 224.5},
        },
    }


def _event(ev_id="401700001", state="pre", home_id="2", away_id="28",
           home_name="Boston Celtics", away_name="Toronto Raptors",
           home_score="0", away_score="0", odds=None):
    return {
        "id": ev_id,
        "date": "2026-10-03T19:00Z",
        "name": f"{home_name} vs {away_name}",
        "competitions": [{
            "competitors": [
                {"team": {"id": home_id, "displayName": home_name},
                 "homeAway": "home", "score": home_score,
                 "records": [{"name": "overall", "summary": "12-5"}]},
                {"team": {"id": away_id, "displayName": away_name},
                 "homeAway": "away", "score": away_score,
                 "records": [{"name": "overall", "summary": "9-8"}]},
            ],
            "status": {"type": {"state": state, "shortDetail": "Scheduled" if state == "pre" else "Final"}},
            "odds": odds if odds is not None else [_odds_entry()],
        }],
    }


def _scoreboard_resp(events=None):
    return {"events": events or []}


def _schedule_resp(events=None):
    return {"events": events or []}


def _teams_resp(teams=None):
    return {"sports": [{"leagues": [{"teams": [{"team": t} for t in (teams or [])]}]}]}


def _standings_resp(entries=None):
    return {"children": [{"standings": {"entries": entries or []}}]}


def _standing_entry(team_id="2", team_name="Boston Celtics", wins=12, losses=5,
                    win_pct=0.706, gb=0.0, streak="W3", pf=118.2, pa=110.1):
    return {
        "team": {"id": team_id, "displayName": team_name, "shortDisplayName": team_name},
        "stats": [
            {"name": "wins", "value": wins},
            {"name": "losses", "value": losses},
            {"name": "winPercent", "value": win_pct},
            {"name": "gamesBehind", "value": gb},
            {"name": "streak", "value": streak},
            {"name": "avgPointsFor", "value": pf},
            {"name": "avgPointsAgainst", "value": pa},
        ],
    }


@patch("ingest.espn_free.requests.get")
def test_scoreboard_empty_events(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_scoreboard_resp())
    from ingest.espn_free import fetch_scoreboard
    assert fetch_scoreboard() == []
    # default window + explicit today-date query
    assert mock_get.call_count == 2


@patch("ingest.espn_free.requests.get")
def test_scoreboard_parses_match(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_scoreboard_resp([_event()]))
    from ingest.espn_free import fetch_scoreboard
    m = fetch_scoreboard()[0]
    assert m["home"] == "Boston Celtics"
    assert m["away"] == "Toronto Raptors"
    assert m["home_id"] == "2"
    assert m["away_id"] == "28"
    assert m["state"] == "pre"
    assert m["home_score"] == 0
    assert m["away_score"] == 0
    assert m["home_record"] == "12-5"
    assert m["away_record"] == "9-8"
    assert m["odds"]["home"] == round(1 + 100 / 330, 3)
    assert m["odds"]["away"] == 3.6
    assert m["odds"]["spread"] == -7.5
    assert m["odds"]["total"] == 224.5


@patch("ingest.espn_free.requests.get")
def test_scoreboard_live_match(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_scoreboard_resp([_event(state="in", home_score="55", away_score="48")]))
    from ingest.espn_free import fetch_scoreboard
    m = fetch_scoreboard()[0]
    assert m["state"] == "in"
    assert m["home_score"] == 55
    assert m["away_score"] == 48


@patch("ingest.espn_free.requests.get")
def test_scoreboard_http_error_returns_empty(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get_error(403)
    from ingest.espn_free import fetch_scoreboard
    assert fetch_scoreboard() == []


@patch("ingest.espn_free.requests.get")
def test_scoreboard_timeout_returns_empty(mock_get):
    _clear_caches()
    mock_get.side_effect = _req.exceptions.Timeout()
    from ingest.espn_free import fetch_scoreboard
    assert fetch_scoreboard() == []


@patch("ingest.espn_free.requests.get")
def test_scoreboard_malformed_json_returns_empty(mock_get):
    _clear_caches()
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status = MagicMock()
    r.json.side_effect = ValueError("bad json")
    mock_get.return_value = r
    from ingest.espn_free import fetch_scoreboard
    assert fetch_scoreboard() == []


@patch("ingest.espn_free.requests.get")
def test_scoreboard_missing_odds(mock_get):
    _clear_caches()
    ev = _event()
    ev["competitions"][0].pop("odds", None)
    mock_get.return_value = _mock_get(_scoreboard_resp([ev]))
    from ingest.espn_free import fetch_scoreboard
    assert fetch_scoreboard()[0]["odds"] == {}


@patch("ingest.espn_free.requests.get")
def test_scoreboard_no_custom_user_agent(mock_get):
    # ESPN 403s custom User-Agents; requests' default must pass through untouched.
    _clear_caches()
    mock_get.return_value = _mock_get(_scoreboard_resp())
    from ingest.espn_free import fetch_scoreboard
    fetch_scoreboard()
    _, kwargs = mock_get.call_args
    assert "User-Agent" not in kwargs.get("headers", {})


@patch("ingest.espn_free.requests.get")
def test_odds_open_close_captured(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_scoreboard_resp([_event()]))
    from ingest.espn_free import fetch_scoreboard
    odds = fetch_scoreboard()[0]["odds"]
    assert odds["open"] == {"home": round(1 + 100 / 320, 3), "away": 3.5,
                            "spread": -7.5, "total": 224.5}
    assert odds["close"] == {"home": round(1 + 100 / 330, 3), "away": 3.6,
                             "spread": -7.5, "total": 224.5}


@patch("ingest.espn_free.requests.get")
def test_odds_open_fallback(mock_get):
    _clear_caches()
    ev = _event()
    ml = ev["competitions"][0]["odds"][0]["moneyline"]
    ml["home"] = {"open": {"odds": "-110"}}
    mock_get.return_value = _mock_get(_scoreboard_resp([ev]))
    from ingest.espn_free import fetch_scoreboard
    assert fetch_scoreboard()[0]["odds"]["home"] == round(1 + 100 / 110, 3)


@patch("ingest.espn_free.requests.get")
def test_odds_incomplete_moneyline_skipped(mock_get):
    _clear_caches()
    ev = _event()
    ev["competitions"][0]["odds"][0]["moneyline"].pop("away")
    mock_get.return_value = _mock_get(_scoreboard_resp([ev]))
    from ingest.espn_free import fetch_scoreboard
    assert fetch_scoreboard()[0]["odds"] == {}


def test_american_to_decimal():
    from ingest.espn_free import american_to_decimal as d
    assert d("+135") == 2.35
    assert d("-110") == round(1 + 100 / 110, 3)
    assert d(240) == 3.4
    assert d("EVEN") == 2.0
    assert d(1.8) == 1.8
    assert d("2.5") == 2.5
    assert d(None) is None
    assert d("bogus") is None


def test_decimal_to_american():
    from ingest.espn_free import decimal_to_american as a
    assert a(2.35) == "+135"
    assert a(1.91) == "-110"
    assert a(2.0) == "+100"
    assert a(1.0) is None
    assert a(None) is None
    assert a("bogus") is None


def test_norm_aliases():
    from ingest.espn_free import _norm
    assert _norm("LA Clippers") == "los angeles clippers"
    assert _norm("Oklahoma City Thunder") == "oklahoma city thunder"
    assert _norm("New York Knicks") == "new york knicks"
    assert _norm(None) == ""


def test_match_token_subset():
    from ingest.espn_free import _match
    keys = {"boston celtics", "toronto raptors"}
    assert _match("Boston Celtics", keys) == "boston celtics"
    assert _match("Celtics", keys) == "boston celtics"
    assert _match("LA Lakers", keys) is None


@patch("ingest.espn_free.requests.get")
def test_schedule_dict_score_parsed(mock_get):
    """Schedule endpoints return score as {value/displayValue} dict, not a string."""
    _clear_caches()
    ev = _event(state="post", home_score="112", away_score="104")
    for c in ev["competitions"][0]["competitors"]:
        raw = c["score"]
        c["score"] = {"value": float(raw), "displayValue": raw}
    mock_get.return_value = _mock_get(_schedule_resp([ev]))
    from ingest.espn_free import fetch_team_schedule
    result = fetch_team_schedule("2")
    assert len(result) == 1
    assert result[0]["home_score"] == 112
    assert result[0]["away_score"] == 104
    assert result[0]["played"] is True


@patch("ingest.espn_free.requests.get")
def test_schedule_filters_non_played(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_schedule_resp([_event(state="pre")]))
    from ingest.espn_free import fetch_team_schedule
    assert fetch_team_schedule("2") == []


@patch("ingest.espn_free.requests.get")
def test_fetch_teams_parses(mock_get):
    _clear_caches()
    teams = [{"id": "2", "displayName": "Boston Celtics", "abbreviation": "BOS"},
             {"id": "28", "displayName": "Toronto Raptors", "abbreviation": "TOR"}]
    mock_get.return_value = _mock_get(_teams_resp(teams))
    from ingest.espn_free import fetch_teams
    result = fetch_teams()
    assert len(result) == 2
    assert result[0] == {"id": "2", "name": "Boston Celtics", "abbr": "BOS"}


@patch("ingest.espn_free.requests.get")
def test_fetch_schedules_aggregates_deduped(mock_get):
    _clear_caches()
    teams = [{"id": "2", "displayName": "Boston Celtics", "abbreviation": "BOS"},
             {"id": "28", "displayName": "Toronto Raptors", "abbreviation": "TOR"}]
    played = _event(state="post", home_score="112", away_score="104")
    mock_get.side_effect = _dispatch([
        ("/basketball/nba/teams/2/schedule", _schedule_resp([played])),
        ("/basketball/nba/teams/28/schedule", _schedule_resp([played])),
        ("/basketball/nba/teams", _teams_resp(teams)),
    ])
    from ingest.espn_free import fetch_schedules
    result = fetch_schedules()
    assert len(result) == 1  # same game seen from both teams, deduped
    assert result[0]["home"] == "Boston Celtics"


@patch("ingest.espn_free.requests.get")
def test_standings_parses_entry(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_standings_resp([_standing_entry()]))
    from ingest.espn_free import fetch_standings
    s = fetch_standings()[0]
    assert s["team"] == "Boston Celtics"
    assert s["team_id"] == "2"
    assert s["wins"] == 12
    assert s["losses"] == 5
    assert s["win_pct"] == 0.706
    assert s["streak"] == "W3"
    assert s["rank"] == 1


@patch("ingest.espn_free.requests.get")
def test_standings_http_error_returns_empty(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get_error(502)
    from ingest.espn_free import fetch_standings
    assert fetch_standings() == []


@patch("ingest.espn_free.requests.get")
def test_standings_missing_stat_returns_none(mock_get):
    _clear_caches()
    entry = _standing_entry()
    entry["stats"] = [{"name": "wins", "value": 50}]
    mock_get.return_value = _mock_get(_standings_resp([entry]))
    from ingest.espn_free import fetch_standings
    s = fetch_standings()[0]
    assert s["wins"] == 50
    assert s["losses"] is None


# ============================== euroleague_free ==============================


def _game_xml(g):
    score = ""
    if g.get("hs") is not None:
        score += f"<homescore>{g['hs']}</homescore>"
    if g.get("as") is not None:
        score += f"<awayscore>{g['as']}</awayscore>"
    return (
        f"<game><round>RS</round><gameday>{g['gameday']}</gameday>"
        f"<date>{g['date']}</date><time>20:00</time>"
        f"<gamenumber>{g['num']}</gamenumber><gamecode>{g['code']}</gamecode>"
        f"<group>Regular Season</group>"
        f"<hometeam>{g['home']}</hometeam><homecode>{g['homecode']}</homecode>"
        f"{score}"
        f"<awayteam>{g['away']}</awayteam><awaycode>{g['awaycode']}</awaycode>"
        f"<played>{str(g['played']).lower()}</played></game>"
    )


def _results_xml(games=None):
    return "<results>" + "".join(_game_xml(g) for g in (games or [])) + "</results>"


def _upcoming_game():
    return {"gameday": 6, "date": "Oct 24, 2025", "num": 55, "code": "E2025_55",
            "home": "VIRTUS BOLOGNA", "homecode": "VIR",
            "away": "REAL MADRID", "awaycode": "MAD",
            "hs": None, "as": None, "played": False}


def _played_game():
    return {"gameday": 5, "date": "Oct 17, 2025", "num": 47, "code": "E2025_47",
            "home": "KOSNER BASKONIA VITORIA-GASTEIZ", "homecode": "BAS",
            "away": "PARTIZAN MOZZART BET BELGRADE", "awaycode": "PAR",
            "hs": 79, "as": 91, "played": True}


def _standings_team(position=1, code="ULK", name="Fenerbahce Beko Istanbul",
                    won=1, lost=0, pct="100%", form=None):
    return {
        "position": position,
        "gamesPlayed": 1, "gamesWon": won, "gamesLost": lost,
        "club": {"code": code, "name": name, "abbreviatedName": "Fenerbahce"},
        "winPercentage": pct,
        "pointsFor": 96, "pointsAgainst": 77,
        "last5Form": form or ["W"],
    }


@patch("ingest.euroleague_free.requests.get")
def test_euro_scoreboard_empty(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_results_xml())
    from ingest.euroleague_free import fetch_scoreboard
    assert fetch_scoreboard(season="E2025") == []


@patch("ingest.euroleague_free.requests.get")
def test_euro_scoreboard_parses_xml(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_results_xml([_upcoming_game(), _played_game()]))
    from ingest.euroleague_free import fetch_scoreboard
    result = fetch_scoreboard(season="E2025")
    assert len(result) == 1  # played game filtered out
    m = result[0]
    assert m["home"] == "VIRTUS BOLOGNA"
    assert m["away"] == "REAL MADRID"
    assert m["home_id"] == "VIR"
    assert m["away_id"] == "MAD"
    assert m["state"] == "pre"
    assert m["home_score"] is None
    assert m["round"] == 6


@patch("ingest.euroleague_free.requests.get")
def test_euro_scoreboard_http_error_returns_empty(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get_error(403)
    from ingest.euroleague_free import fetch_scoreboard
    assert fetch_scoreboard(season="E2025") == []


@patch("ingest.euroleague_free.requests.get")
def test_euro_schedules_played_flag(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get(_results_xml([_played_game(), _upcoming_game()]))
    from ingest.euroleague_free import fetch_schedules
    result = fetch_schedules(season="E2025")
    assert len(result) == 2
    played = next(g for g in result if g["id"] == "E2025_47")
    assert played["played"] is True
    assert played["state"] == "post"
    assert played["home_score"] == 79
    assert played["away_score"] == 91
    upcoming = next(g for g in result if g["id"] == "E2025_55")
    assert upcoming["played"] is False


@patch("ingest.euroleague_free.requests.get")
def test_euro_schedules_bad_xml_returns_empty(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get("<results><game><hometeam>broken")
    from ingest.euroleague_free import fetch_schedules
    assert fetch_schedules(season="E2025") == []


@patch("ingest.euroleague_free.requests.get")
def test_euro_standings_parses(mock_get):
    _clear_caches()
    mock_get.side_effect = _dispatch([
        ("/v2/competitions/E/seasons", {"data": [{"code": "E2025", "winner": None}], "total": 1}),
        ("/v1/results", _results_xml([_played_game()])),
        ("/v3/competitions/E/seasons/E2025/rounds/5/basicstandings",
         {"teams": [_standings_team()]}),
    ])
    from ingest.euroleague_free import fetch_standings
    s = fetch_standings()[0]
    assert s["rank"] == 1
    assert s["team"] == "Fenerbahce Beko Istanbul"
    assert s["team_id"] == "ULK"
    assert s["wins"] == 1
    assert s["losses"] == 0
    assert s["win_pct"] == 100.0
    assert s["streak"] == "W"
    assert s["points_for"] == 96.0


@patch("ingest.euroleague_free.requests.get")
def test_euro_standings_http_error_returns_empty(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get_error(500)
    from ingest.euroleague_free import fetch_standings
    assert fetch_standings() == []


@patch("ingest.euroleague_free.requests.get")
def test_euro_current_season_none_returns_empty(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get_error(403)
    from ingest.euroleague_free import fetch_scoreboard
    assert fetch_scoreboard() == []


# ============================== odds_free ==============================


def _odds_game(gid="abc123", home="Boston Celtics", away="Toronto Raptors",
               h2h=(1.45, 2.8), spread=(-7.5, 1.91), total=(224.5, 1.91)):
    markets = [
        {"key": "h2h", "outcomes": [
            {"name": home, "price": h2h[0]}, {"name": away, "price": h2h[1]}]},
        {"key": "spreads", "outcomes": [
            {"name": home, "price": spread[1], "point": spread[0]},
            {"name": away, "price": spread[1], "point": -spread[0]}]},
        {"key": "totals", "outcomes": [
            {"name": "Over", "price": total[1], "point": total[0]},
            {"name": "Under", "price": total[1], "point": total[0]}]},
    ]
    return {
        "id": gid,
        "sport_key": "basketball_nba",
        "commence_time": "2026-10-03T19:00:00Z",
        "home_team": home,
        "away_team": away,
        "bookmakers": [{"key": "draftkings", "title": "DraftKings", "markets": markets}],
    }


def _scores_game(gid="abc123", home="Boston Celtics", away="Toronto Raptors",
                 hs=112, as_=104, completed=True):
    return {"id": gid, "sport_key": "basketball_nba",
            "commence_time": "2026-10-03T19:00:00Z",
            "home_team": home, "away_team": away,
            "home_score": hs, "away_score": as_, "completed": completed}


@patch.dict(os.environ, {}, clear=True)
def test_odds_no_key_returns_empty():
    _clear_caches()
    from ingest.odds_free import fetch_scoreboard, fetch_schedules
    assert fetch_scoreboard() == []
    assert fetch_schedules() == []


@patch.dict(os.environ, {"ODDS_API_KEY": "test-key"})
@patch("ingest.odds_free.requests.get")
def test_odds_scoreboard_parses(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get([_odds_game()])
    from ingest.odds_free import fetch_scoreboard
    m = fetch_scoreboard()[0]
    assert m["home"] == "Boston Celtics"
    assert m["away"] == "Toronto Raptors"
    assert m["state"] == "pre"
    assert m["odds"]["provider"] == "draftkings"
    assert m["odds"]["home"] == 1.45
    assert m["odds"]["away"] == 2.8
    assert m["odds"]["spread"] == -7.5
    assert m["odds"]["spread_odds"] == 1.91
    assert m["odds"]["total"] == 224.5
    assert m["odds"]["total_odds"] == 1.91
    assert m["odds"]["open"] == {}
    assert m["odds"]["close"] == {}


@patch.dict(os.environ, {"ODDS_API_KEY": "test-key"})
@patch("ingest.odds_free.requests.get")
def test_odds_scoreboard_http_error_returns_empty(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get_error(401)
    from ingest.odds_free import fetch_scoreboard
    assert fetch_scoreboard() == []


@patch.dict(os.environ, {"ODDS_API_KEY": "test-key"})
@patch("ingest.odds_free.requests.get")
def test_odds_scores_parses_results(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get([_scores_game()])
    from ingest.odds_free import fetch_schedules
    m = fetch_schedules()[0]
    assert m["played"] is True
    assert m["state"] == "post"
    assert m["home_score"] == 112
    assert m["away_score"] == 104


@patch.dict(os.environ, {"ODDS_API_KEY": "test-key"})
@patch("ingest.odds_free.requests.get")
def test_odds_scores_unplayed(mock_get):
    _clear_caches()
    mock_get.return_value = _mock_get([_scores_game(hs=None, as_=None, completed=False)])
    from ingest.odds_free import fetch_schedules
    m = fetch_schedules()[0]
    assert m["played"] is False
    assert m["state"] == "pre"
    assert m["home_score"] is None


def test_odds_standings_always_empty():
    from ingest.odds_free import fetch_standings
    assert fetch_standings() == []
    assert fetch_standings("euroleague") == []


def test_odds_match_game_fuzzy():
    from ingest.odds_free import match_game
    g = {"home": "Boston Celtics", "away": "Toronto Raptors"}
    assert match_game(g, "Boston Celtics", "Toronto Raptors") is True
    assert match_game(g, "Celtics", "Raptors") is True
    assert match_game(g, "LA Lakers", "Toronto Raptors") is False
    assert match_game(None, "A", "B") is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t(); print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")