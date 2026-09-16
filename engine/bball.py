"""Normal-distribution basketball ensemble engine.

Pure functions — no I/O, no deps beyond stdlib math.
Given home/away offensive/defensive ratings, returns ML, spread, total probs.
Elo provides a second ML opinion; ensemble averages across models.
Verdict: BET >= 0.70 / MARGINAL >= 0.55 / else NO BET with agreement-gate.

Mirrors football-model/engine/tips.py function shapes and return keys.
"""

import math
from typing import Dict, List, Optional

from .elo import elo_win_prob, HOME_COURT_NBA, HOME_COURT_EUROLEAGUE

# ── Constants ──────────────────────────────────────────────

KELLY_CAP = 0.02
BET_BAND = 0.70       # pick prob >= this → BET
MARGINAL_BAND = 0.55  # pick prob >= this → MARGINAL
AGREE_GAP = 0.15      # max ML spread across models tolerated before downgrade
DEFAULT_SIGMA = 11.5  # stdev of NBA game point margins
CROWD_WEIGHT = 0.12   # Polymarket crowd ensemble vote (caller skips thin markets)


# ── Normal distribution ────────────────────────────────────

def _normal_cdf(x: float, mu: float = 0.0, sigma: float = DEFAULT_SIGMA) -> float:
    """Normal CDF via math.erf.  P(X <= x) where X ~ N(mu, sigma²).

    Pure function.  For basketball: mu is expected margin or total,
    sigma is game-score standard deviation (~11.5 NBA).
    """
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))


# ── Expected scores from ratings ──────────────────────────

def expected_margin(home_off: float, home_def: float,
                    away_off: float, away_def: float,
                    home_court: float = HOME_COURT_NBA) -> float:
    """Expected home-minus-away point differential.

    off rating: higher = better (points scored per game)
    def rating: lower = better (points allowed per game)

    Model: home_pts = (home_off + away_def) / 2, i.e. the home
    offense meets the away defense.  vice versa for away_pts.
    Home-court added on top.
    """
    home_pts = (home_off + away_def) / 2.0
    away_pts = (away_off + home_def) / 2.0
    return home_pts - away_pts + home_court


def expected_total(home_off: float, home_def: float,
                   away_off: float, away_def: float) -> float:
    """Expected combined points from both teams.

    Same per-team model as expected_margin, summed.
    """
    home_pts = (home_off + away_def) / 2.0
    away_pts = (away_off + home_def) / 2.0
    return home_pts + away_pts


# ── Market probabilities ──────────────────────────────────

def prob_ml(mu: float, sigma: float = DEFAULT_SIGMA) -> Dict[str, float]:
    """{home, away} moneyline from expected margin.

    P(home wins) = P(margin > 0) = 1 − CDF(0, mu, sigma).
    """
    p_home = 1.0 - _normal_cdf(0.0, mu, sigma)
    return {"home": p_home, "away": 1.0 - p_home}


def prob_spread(mu: float, spread: float,
                sigma: float = DEFAULT_SIGMA) -> Dict[str, float]:
    """P(home covers -spread) and P(away covers +spread).

    spread: negative = home favored (e.g. -5.5).
    P(home covers) = P(margin > |spread|).
    """
    line = abs(spread)
    p_home = 1.0 - _normal_cdf(line, mu, sigma)
    return {"home_cover": p_home, "away_cover": 1.0 - p_home}


def prob_total(mu_total: float, line: float,
               sigma: float = DEFAULT_SIGMA) -> Dict[str, float]:
    """P(over) and P(under) on the total line.

    P(over) = P(combined > line) = 1 − CDF(line, mu_total, sigma).
    """
    p_over = 1.0 - _normal_cdf(line, mu_total, sigma)
    return {"over": p_over, "under": 1.0 - p_over}


# ── Odds / edge / Kelly ──────────────────────────────────

def fair(prob: float) -> float:
    """Fair decimal odds = 1 / prob.  Raises if prob <= 0."""
    return 1.0 / prob


def devig(odds: Dict[str, float]) -> Dict[str, float]:
    """Remove bookmaker margin (proportional devig): fair odds per outcome."""
    implied = {k: 1.0 / v for k, v in odds.items() if v and v > 1.0}
    total = sum(implied.values())
    if total <= 0.0:
        return {}
    return {k: 1.0 / (v / total) for k, v in implied.items()}


def edge_vs_book(prob: float, odds: float) -> float:
    """Expected edge = prob * odds − 1.  Positive = value."""
    return prob * odds - 1.0


def kelly_fraction(prob: float, odds: float, half: bool = True) -> float:
    """Kelly criterion fraction.  half=True → cap at half-Kelly, max KELLY_CAP."""
    ev = edge_vs_book(prob, odds)
    if ev <= 0:
        return 0.0
    f = ev / (odds - 1.0) if odds > 1.0 else 0.0
    if half:
        f *= 0.5
    return min(f, KELLY_CAP)


# ── Orchestrator ──────────────────────────────────────────

def _norm_ml(d: Optional[Dict]) -> Optional[Dict[str, float]]:
    """Normalize a {home, away} dict to sum 1; None when unusable."""
    if not d:
        return None
    try:
        t = d["home"] + d["away"]
    except (KeyError, TypeError):
        return None
    if t <= 0:
        return None
    return {"home": d["home"] / t, "away": d["away"] / t}


def build_tip(
    ratings: Dict,
    market: Dict,
    elo_probs: Optional[Dict] = None,
    form_probs: Optional[Dict] = None,
    crowd_ml: Optional[Dict] = None,
    crowd_weight: float = CROWD_WEIGHT,
) -> Dict:
    """Compute safest pick from ratings, market lines, and optional 2nd opinions.

    ratings:   {home_off, home_def, away_off, away_def, home_court?, sigma?}
    market:    {spread, total, home_ml?, away_ml?}  (odds optional)
    elo_probs: optional {home, away} from Elo model
    form_probs: optional {home, away} from form/ratings model
    crowd_ml:  optional Polymarket {home, away} sentiment (pass None for
        thin/quiet markets). Weighted at crowd_weight (default 0.12) so late
        money nudges the ensemble without overriding the models.

    Method: Normal model provides ML + spread + total probs.
    Elo and form provide alternative ML opinions.
    Ensemble averages all ML opinions (crowd weighted); spread/total from Normal only.
    Safest pick across all 6 markets.  Verdict from probability bands;
    base models disagreeing (ML spread > AGREE_GAP, crowd excluded) downgrades one band.
    Confidence = pick prob %.
    """
    h_off = ratings["home_off"]
    h_def = ratings["home_def"]
    a_off = ratings["away_off"]
    a_def = ratings["away_def"]
    hca = ratings.get("home_court", HOME_COURT_NBA)
    sigma = ratings.get("sigma", DEFAULT_SIGMA)

    spread = market.get("spread", 0.0)
    total_line = market.get("total", 220.0)

    # Expected margin and total from ratings
    mu = expected_margin(h_off, h_def, a_off, a_def, hca)
    mu_tot = expected_total(h_off, h_def, a_off, a_def)

    # Normal model ML
    normal_ml = prob_ml(mu, sigma)

    # Ensemble ML across voting models (crowd weighted, excluded from gap)
    votes: Dict[str, Dict[str, float]] = {"normal": normal_ml}
    for name, opinion in (("elo", elo_probs), ("form", form_probs)):
        n = _norm_ml(opinion) if opinion else None
        if n:
            votes[name] = n
    weights = {name: 1.0 for name in votes}
    cn = _norm_ml(crowd_ml) if crowd_ml else None
    if cn:
        votes["crowd"] = cn
        weights["crowd"] = crowd_weight if crowd_weight and crowd_weight > 0 else CROWD_WEIGHT
    total_w = sum(weights.values())
    ens_ml = {k: sum(votes[n][k] * weights[n] for n in votes) / total_w
              for k in ("home", "away")}

    # Spread and total from Normal model
    sp = prob_spread(mu, spread, sigma)
    tp = prob_total(mu_tot, total_line, sigma)

    # Safest-pick slate — mirrors football but with basketball markets
    slate = {
        "Home ML": ens_ml["home"],
        "Away ML": ens_ml["away"],
        f"Home {spread:+.1f}": sp["home_cover"],
        f"Away {-spread:+.1f}": sp["away_cover"],
        "Over": tp["over"],
        "Under": tp["under"],
    }
    pick = max(slate, key=lambda k: slate[k])
    prob = slate[pick]

    # Agreement across base voting models (crowd excluded — sentiment nudges, never caps)
    base = {n: v for n, v in votes.items() if n != "crowd"}
    gap = max(
        max(v[k] for v in base.values()) - min(v[k] for v in base.values())
        for k in ("home", "away")
    )
    agree = gap <= AGREE_GAP

    # Verdict from bands, downgraded a notch on disagreement
    if prob >= BET_BAND:
        verdict = "BET"
    elif prob >= MARGINAL_BAND:
        verdict = "MARGINAL"
    else:
        verdict = "NO BET"
    if not agree and len(base) > 1:
        verdict = {"BET": "MARGINAL", "MARGINAL": "NO BET"}.get(verdict, verdict)

    confidence = round(prob * 100, 1)

    # Edge vs book (display only) on ensembled ML
    ml_odds = {
        "home": market.get("home_ml"),
        "away": market.get("away_ml"),
    }
    best_key, best_edge = None, -999.0
    for key, prob_val in ens_ml.items():
        odds_val = ml_odds.get(key)
        if odds_val is None:
            continue
        ev = edge_vs_book(prob_val, odds_val)
        if ev > best_edge:
            best_edge = ev
            best_key = key

    # Fair odds
    fair_ml = {k: round(fair(v), 2) for k, v in ens_ml.items()}
    fair_spread = {"home_cover": round(fair(sp["home_cover"]), 2),
                   "away_cover": round(fair(sp["away_cover"]), 2)}
    fair_total = {"over": round(fair(tp["over"]), 2),
                  "under": round(fair(tp["under"]), 2)}

    # Kelly on best ML edge (display only)
    best_odds = ml_odds.get(best_key) if best_key else None
    kf = kelly_fraction(ens_ml[best_key], best_odds) if best_key and best_odds else 0.0

    # Reasons
    reasons: List[str] = []
    reasons.append(f"Ratings: H({h_off:.1f}o/{h_def:.1f}d) vs A({a_off:.1f}o/{a_def:.1f}d)")
    reasons.append(f"Expected: margin {mu:+.1f}, total {mu_tot:.1f}, sigma={sigma}")
    for name, v in votes.items():
        reasons.append(f"{name.capitalize()} ML: {v['home']:.2%} / {v['away']:.2%}")
    reasons.append(f"Ensembled ML: {ens_ml['home']:.2%} / {ens_ml['away']:.2%}")
    reasons.append(f"Spread {spread:+.1f}: cover {sp['home_cover']:.2%} / "
                   f"{sp['away_cover']:.2%}")
    reasons.append(f"Total {total_line:.1f}: over {tp['over']:.2%} / "
                   f"{tp['under']:.2%}")
    reasons.append(f"Safest: {pick} ({prob:.1%}) across {len(slate)} markets")
    reasons.append(
        f"Models {'agree' if agree else 'split'} (ML spread {gap:.2f})"
        + (" — verdict capped" if not agree and len(base) > 1 else "")
    )
    if best_key:
        reasons.append(f"Value check: {best_key} edge {best_edge:+.2%} vs book")
    reasons.append(f"Kelly (half, cap {KELLY_CAP:.0%}): {kf:.4f}")

    return {
        "pick": pick,
        "probs": {
            "ML": {k: round(v, 4) for k, v in ens_ml.items()},
            "spread": {k: round(v, 4) for k, v in sp.items()},
            "total": {k: round(v, 4) for k, v in tp.items()},
        },
        "slate": {k: round(v, 4) for k, v in slate.items()},
        "fair_odds": {"ML": fair_ml, "spread": fair_spread, "total": fair_total},
        "edge": round(best_edge, 4) if best_key else None,
        "edge_market": best_key,
        "verdict": verdict,
        "reasons": reasons,
        "confidence": confidence,
        "models": sorted(votes),
        "kelly": round(kf, 4),
    }
