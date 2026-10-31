"""End-to-end live diagnostic for the tips pipeline.

Runs the real ingest + engine + /tips composition against the live free
sources and prints one line per stage, so a broken board reports which stage
died instead of just "no tips".

Exit codes:
  0  pipeline healthy (or a genuinely fixture-less day)
  1  fixtures exist but /tips dropped them, or the engine never engaged

Run in CI: .github/workflows/diag.yml (workflow_dispatch).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.main import _engine_tip, _fetch_events, _ratings_from_form, tips  # noqa: E402


def check(league: str, espn_key: str) -> bool:
    print(f"\n=== {league} ===")

    events = _fetch_events(league, espn_key)
    print(f"scoreboard events: {len(events)}")
    if not events:
        print("no fixtures in the current window (not a failure by itself)")
        return True

    priced = sum(1 for e in events if e.get("odds"))
    print(f"events with book odds: {priced}/{len(events)}")

    form_ok = 0
    for ev in events:
        ratings = _ratings_from_form(ev.get("home", ""), ev.get("away", ""),
                                     ev.get("home_id", ""), ev.get("away_id", ""),
                                     espn_key, league)
        if ratings:
            form_ok += 1
        tip = _engine_tip(ev.get("home", ""), ev.get("away", ""),
                          ev.get("home_id", ""), ev.get("away_id", ""),
                          ev.get("odds") or {}, espn_key, league) if ratings else None
        probs = (tip or {}).get("probs", {}).get("ml", {})
        home_ml = probs.get("home")
        ml_txt = f"{home_ml:.2f}" if home_ml is not None else "-"
        verdict = (tip or {}).get("verdict", "engine-off")
        print(f"  {ev.get('date', '')[:16]:16s} {ev.get('away', '?')[:22]:22s}"
              f" @ {ev.get('home', '?')[:22]:22s}"
              f" odds={'y' if ev.get('odds') else 'n'}"
              f" form={'y' if ratings else 'n'}"
              f" ml={ml_txt:>5s} verdict={verdict}")
    print(f"ratings resolved: {form_ok}/{len(events)}")

    board = tips(league=league)
    print(f"/tips cards: {len(board['tips'])}")
    for t in board["tips"]:
        print(f"  {t['pick']:<24s} {t['verdict']:<9s}"
              f" conf={t['confidence']:>5.1f} models={','.join(t['models']) or '-'}")

    ok = len(board["tips"]) == len(events) and form_ok == len(events)
    if len(board["tips"]) == 0:
        print("FAIL: fixtures exist but /tips rendered nothing")
    elif form_ok < len(events):
        print("FAIL: engine skipped — form/ratings never resolved")
    return ok


def main() -> int:
    ok_nba = check("NBA", "nba")
    ok_el = check("EuroLeague", "euroleague")
    print("\n" + ("PASS" if ok_nba and ok_el else "FAIL"))
    return 0 if ok_nba and ok_el else 1


if __name__ == "__main__":
    raise SystemExit(main())
