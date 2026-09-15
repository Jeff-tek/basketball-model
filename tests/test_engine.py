"""Tests for basketball engine: engine/bball.py + engine/elo.py.

Structure and import tests.  Verifies pure-function contracts:
Normal CDF via math.erf, market probs sum to 1, build_tip shape,
Elo 2-way with home-court advantage.

Runs with stdlib unittest (no pytest required):
    python -m unittest discover -s tests -v
    python tests/test_engine.py
"""

import math
import os
import sys
import unittest

# Make `engine` importable when running from repo root or tests/ dir
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine.elo import (  # noqa: E402
    elo_win_prob,
    elo_expected_margin,
    match_prob,
    HOME_COURT_NBA,
    HOME_COURT_EUROLEAGUE,
    MARGIN_SCALE,
)
from engine.bball import (  # noqa: E402
    _normal_cdf,
    expected_margin,
    expected_total,
    prob_ml,
    prob_spread,
    prob_total,
    fair,
    devig,
    edge_vs_book,
    kelly_fraction,
    build_tip,
    KELLY_CAP,
    BET_BAND,
    MARGINAL_BAND,
    AGREE_GAP,
    DEFAULT_SIGMA,
)


class TestImports(unittest.TestCase):
    """Verify all public symbols import cleanly."""

    def test_elo_imports(self):
        self.assertTrue(callable(elo_win_prob))
        self.assertTrue(callable(elo_expected_margin))
        self.assertTrue(callable(match_prob))

    def test_bball_imports(self):
        self.assertTrue(callable(_normal_cdf))
        self.assertTrue(callable(expected_margin))
        self.assertTrue(callable(expected_total))
        self.assertTrue(callable(prob_ml))
        self.assertTrue(callable(prob_spread))
        self.assertTrue(callable(prob_total))
        self.assertTrue(callable(build_tip))

    def test_constants(self):
        self.assertEqual(KELLY_CAP, 0.02)
        self.assertEqual(BET_BAND, 0.70)
        self.assertEqual(MARGINAL_BAND, 0.55)
        self.assertEqual(AGREE_GAP, 0.15)
        self.assertEqual(DEFAULT_SIGMA, 11.5)
        self.assertEqual(HOME_COURT_NBA, 3.5)
        self.assertEqual(HOME_COURT_EUROLEAGUE, 4.0)


class TestElo(unittest.TestCase):
    """Elo module pure-function tests."""

    def test_equal_ratings(self):
        self.assertAlmostEqual(elo_win_prob(1500, 1500), 0.5, places=10)

    def test_higher_rating_favored(self):
        self.assertGreater(elo_win_prob(1600, 1400), 0.5)

    def test_win_prob_bounds(self):
        for a, b in [(1000, 2000), (2000, 1000), (1500, 1500)]:
            p = elo_win_prob(a, b)
            self.assertGreater(p, 0.0)
            self.assertLess(p, 1.0)

    def test_expected_margin_home_favored(self):
        m = elo_expected_margin(1600, 1400, HOME_COURT_NBA)
        self.assertGreater(m, 0.0)

    def test_euroleague_hca_larger(self):
        m_nba = elo_expected_margin(1500, 1500, HOME_COURT_NBA)
        m_euro = elo_expected_margin(1500, 1500, HOME_COURT_EUROLEAGUE)
        self.assertGreater(m_euro, m_nba)

    def test_match_prob_sums_to_one(self):
        p = match_prob(1500, 1500)
        self.assertAlmostEqual(p["home"] + p["away"], 1.0, places=10)

    def test_match_prob_has_margin(self):
        p = match_prob(1600, 1400)
        self.assertIn("exp_margin", p)
        self.assertGreater(p["exp_margin"], 0.0)


class TestNormalCDF(unittest.TestCase):
    """Normal CDF via math.erf."""

    def test_zero_at_mean(self):
        self.assertAlmostEqual(_normal_cdf(0.0, 0.0, 1.0), 0.5, places=10)

    def test_one_sigma(self):
        p = _normal_cdf(1.0, 0.0, 1.0)
        self.assertGreater(p, 0.84)
        self.assertLess(p, 0.85)  # ~84.13%

    def test_negative_one_sigma(self):
        p = _normal_cdf(-1.0, 0.0, 1.0)
        self.assertGreater(p, 0.15)
        self.assertLess(p, 0.16)  # ~15.87%

    def test_symmetry(self):
        for x in (0.5, 1.0, 2.0, 3.0):
            self.assertAlmostEqual(
                _normal_cdf(x, 0, 1) + _normal_cdf(-x, 0, 1), 1.0, places=10
            )

    def test_matches_math_erf(self):
        """Cross-check against direct math.erf formula."""
        x, mu, sigma = 3.0, 1.0, 2.0
        expected = 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))
        self.assertAlmostEqual(_normal_cdf(x, mu, sigma), expected, places=12)


class TestExpectedScores(unittest.TestCase):
    """Expected margin and total from ratings."""

    def test_equal_teams_margin_is_hca(self):
        m = expected_margin(110, 110, 110, 110, 3.5)
        self.assertAlmostEqual(m, 3.5, places=10)

    def test_better_home_offense(self):
        # home_pts = (115 + 110)/2 = 112.5, away_pts = (110 + 110)/2 = 110
        m = expected_margin(115, 110, 110, 110, 0)
        self.assertAlmostEqual(m, 2.5, places=10)

    def test_equal_teams_total(self):
        t = expected_total(110, 110, 110, 110)
        self.assertAlmostEqual(t, 220.0, places=10)

    def test_total_uses_both_ratings(self):
        # home_pts = (115 + 112)/2 = 113.5, away_pts = (105 + 108)/2 = 106.5
        t = expected_total(115, 108, 105, 112)
        self.assertAlmostEqual(t, 220.0, places=10)

    def test_bad_defense_raises_total(self):
        t = expected_total(110, 120, 110, 120)
        self.assertGreater(t, 220.0)


class TestMarketProbs(unittest.TestCase):
    """Market probability functions."""

    def test_ml_sums_to_one(self):
        m = prob_ml(5.0, 11.5)
        self.assertAlmostEqual(m["home"] + m["away"], 1.0, places=10)

    def test_home_favored_ml(self):
        m = prob_ml(5.0, 11.5)
        self.assertGreater(m["home"], 0.5)

    def test_spread_sums_to_one(self):
        s = prob_spread(5.0, -5.5, 11.5)
        self.assertAlmostEqual(s["home_cover"] + s["away_cover"], 1.0, places=10)

    def test_total_sums_to_one(self):
        t = prob_total(220.0, 220.5, 11.5)
        self.assertAlmostEqual(t["over"] + t["under"], 1.0, places=10)

    def test_high_total_line_favors_under(self):
        t = prob_total(220.0, 230.0, 11.5)
        self.assertGreater(t["under"], t["over"])

    def test_favored_team_covers(self):
        """Home favored by 7, spread -5.5 → home covers more than half."""
        s = prob_spread(7.0, -5.5, 11.5)
        self.assertGreater(s["home_cover"], 0.5)

    def test_positive_spread_handled(self):
        """Spread given as +5.5 (away favored) works symmetrically."""
        s = prob_spread(-7.0, 5.5, 11.5)
        self.assertGreater(s["away_cover"], 0.5)


class TestOddsHelpers(unittest.TestCase):
    """fair / devig / edge / kelly."""

    def test_fair(self):
        self.assertAlmostEqual(fair(0.5), 2.0, places=10)

    def test_devig_removes_margin(self):
        odds = {"home": 1.91, "away": 1.91}  # 104.7% book
        fair_odds = devig(odds)
        self.assertAlmostEqual(
            1.0 / fair_odds["home"] + 1.0 / fair_odds["away"], 1.0, places=10
        )

    def test_edge_positive(self):
        self.assertGreater(edge_vs_book(0.6, 2.0), 0.0)

    def test_kelly_zero_on_no_edge(self):
        self.assertEqual(kelly_fraction(0.4, 2.0), 0.0)

    def test_kelly_capped(self):
        kf = kelly_fraction(0.9, 1.5)
        self.assertLessEqual(kf, KELLY_CAP)


class TestBuildTip(unittest.TestCase):
    """Orchestrator: build_tip returns correct shape."""

    RATINGS = {"home_off": 112, "home_def": 108, "away_off": 105, "away_def": 115}
    MARKET = {"spread": -5.5, "total": 220.5}

    def test_returns_all_keys(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        for key in ("pick", "verdict", "confidence", "reasons", "probs",
                    "slate", "fair_odds", "models", "kelly", "edge",
                    "edge_market"):
            self.assertIn(key, tip, f"Missing key: {key}")

    def test_slate_has_six_markets(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        self.assertEqual(len(tip["slate"]), 6)

    def test_slate_keys(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        for key in ("Home ML", "Away ML", "Home -5.5", "Away +5.5",
                    "Over", "Under"):
            self.assertIn(key, tip["slate"], f"Missing slate key: {key}")

    def test_verdict_values(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        self.assertIn(tip["verdict"], ("BET", "MARGINAL", "NO BET"))

    def test_confidence_is_percentage(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        self.assertGreaterEqual(tip["confidence"], 0.0)
        self.assertLessEqual(tip["confidence"], 100.0)

    def test_models_list(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        self.assertIn("normal", tip["models"])

    def test_elo_second_opinion(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET,
                        elo_probs={"home": 0.6, "away": 0.4})
        self.assertIn("elo", tip["models"])
        self.assertEqual(len(tip["models"]), 2)

    def test_form_third_opinion(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET,
                        elo_probs={"home": 0.6, "away": 0.4},
                        form_probs={"home": 0.55, "away": 0.45})
        self.assertEqual(len(tip["models"]), 3)

    def test_no_market_odds_still_works(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        self.assertIsNone(tip["edge"])

    def test_edge_display_with_odds(self):
        market = dict(self.MARKET, home_ml=1.8, away_ml=2.1)
        tip = build_tip(ratings=self.RATINGS, market=market,
                        elo_probs={"home": 0.6, "away": 0.4})
        self.assertIsNotNone(tip["edge"])
        self.assertIsNotNone(tip["edge_market"])

    def test_probs_shape(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        self.assertIn("ML", tip["probs"])
        self.assertIn("spread", tip["probs"])
        self.assertIn("total", tip["probs"])
        self.assertAlmostEqual(
            tip["probs"]["ML"]["home"] + tip["probs"]["ML"]["away"], 1.0, places=4
        )

    def test_reasons_nonempty(self):
        tip = build_tip(ratings=self.RATINGS, market=self.MARKET)
        self.assertGreater(len(tip["reasons"]), 0)

    def test_strong_favorite_gets_bet(self):
        """Overwhelming favorite → pick prob >= 0.70 → BET."""
        tip = build_tip(
            ratings={"home_off": 120, "home_def": 100,
                     "away_off": 100, "away_def": 120},
            market={"spread": -12.5, "total": 220.5},
        )
        self.assertEqual(tip["verdict"], "BET")

    def test_agreement_gate_downgrades(self):
        """Split models (ML spread > AGREE_GAP) downgrades verdict."""
        tip = build_tip(
            ratings=self.RATINGS,
            market=self.MARKET,
            elo_probs={"home": 0.99, "away": 0.01},  # strongly disagrees
        )
        # normal ML home ~0.82 → BET; elo 0.99 → gap 0.17 > 0.15 → split
        # BET downgraded to MARGINAL
        self.assertEqual(tip["verdict"], "MARGINAL")


if __name__ == "__main__":
    unittest.main()