"""Basketball Elo model — 2-way win prob + expected margin.

Pure functions, no I/O. Adapts football elo.py for basketball:
no draws, parametric home-court advantage (NBA +3.5 / EuroLeague +4.0).

Elo → win probability via standard logistic, → expected point margin
via linear scale. Provides a second opinion for the bball.py ensemble.
"""

import math

# ── Constants ──────────────────────────────────────────────

HOME_COURT_NBA = 3.5         # Home-court advantage in Elo points, NBA
HOME_COURT_EUROLEAGUE = 4.0  # Home-court advantage in Elo points, EuroLeague
MARGIN_SCALE = 0.05          # Elo-point diff → point margin (empirical)


# ── Core Elo ──────────────────────────────────────────────

def elo_win_prob(rating_a: float, rating_b: float) -> float:
    """P(A beats B) = 1 / (1 + 10^((B − A) / 400))."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def elo_expected_margin(elo_home: float, elo_away: float,
                        home_court: float = HOME_COURT_NBA) -> float:
    """Expected point margin (positive = home favored).

    Translates the Elo differential (with home-court offset) into a
    point spread via a linear scale factor.
    """
    return ((elo_home + home_court) - elo_away) * MARGIN_SCALE


# ── Composite ─────────────────────────────────────────────

def match_prob(elo_home: float, elo_away: float,
               home_court: float = HOME_COURT_NBA) -> dict:
    """{home, away, exp_margin} from Elo ratings. Pure function.

    Returns a dict with home and away win probabilities and the
    expected point margin for informational purposes.
    """
    hp = elo_win_prob(elo_home + home_court, elo_away)
    margin = elo_expected_margin(elo_home, elo_away, home_court)
    return {"home": hp, "away": 1.0 - hp, "exp_margin": round(margin, 2)}
