# Basketball-Model — Progress / Checkpoint

Goal: greenfield clone of football-model for basketball (NBA + EuroLeague).
Markets: ML + Spread + Totals. Engine: adapted ensemble (Normal margin/total + Elo).
Scope: full clone (cards + crowd + line move + PnL). Odds: ESPN free primary, The Odds API free fallback.
Style: basketball-themed CSS (orange/court). Loop: code → push → CI → Vercel. No local builds.
Git identity: Jeff-tek <75492107+Jeff-tek@users.noreply.github.com>.

## Spec (confirmed)
- Leagues: NBA + EuroLeague
- Markets: ML + Spread + Totals (no draws, no BTTS)
- Engine: adapted ensemble, Normal dist (not Poisson), safest-pick + agreement gate
- Repo: greenfield minimal at /root/basketball-model
- Scope: full clone incl. Tips cards + crowd + lineMove + PnL
- Odds: ESPN free only primary (+ free fallback chain: euroleague_api, balldontlie, Odds API 500/mo)
- Verdict: BET>=70 / MARGINAL>=55 / else NO BET; missing odds = note only, never force NO BET

## Todos
- [x] Scaffold dirs + PROGRESS.md
- [x] engine: Normal margin/total + Elo ensemble
- [x] ingest: ESPN NBA + euroleague_api + odds fallback
- [x] server: /tips API (mirrors football server/main.py; engine/ingest imported defensively)
- [x] frontend: cards + basketball CSS (page.tsx, lib/tips.ts, TipCard.tsx, LeagueTabs.tsx, globals.css)
- [ ] tests + Vercel config (server tests done; ingest tests done; Vercel config done — remaining: full-suite CI wiring)
- Verified 2026-09-15: py_compile OK all modules; 46/46 unittest OK (engine+ingest); test_server needs fastapi → CI per no-local-install loop
- [ ] Push as Jeff-tek (awaiting user go-ahead)

## Changed files
- NEW /root/basketball-model/ (scaffold)
- NEW engine/__init__.py — package marker
- NEW engine/elo.py — 2-way Elo: elo_win_prob, elo_expected_margin, match_prob; HCA NBA +3.5 / EuroLeague +4.0, MARGIN_SCALE 0.05
- NEW engine/bball.py — Normal ensemble: _normal_cdf (math.erf), expected_margin/total, prob_ml/spread/total, fair/devig/edge/kelly, build_tip (slate {Home ML, Away ML, Home -spread, Away +spread, Over, Under}, BET>=0.70/MARGINAL>=0.55/NO BET + AGREE_GAP 0.15 downgrade)
- NEW tests/test_engine.py — 46 unittest cases, all pass (`python3 -m unittest discover -s tests -v`)
- NEW frontend/app/page.tsx — client tips board, NBA/EuroLeague tabs, refresh, loading/error/empty states
- NEW frontend/app/lib/tips.ts — Tip type (ml/spread/totals), getTips/getLive fetchers
- NEW frontend/app/components/TipCard.tsx — ML/Spread/Totals rows, confidence badge, verdict pill, reasons, crowd bars, line move
- NEW frontend/app/components/LeagueTabs.tsx — accessible tab switcher with counts
- NEW frontend/app/globals.css — court theme: --court #EA580C, hardwood tan, black/white, bounce-in cards, court-line divider
- NEW server/main.py — FastAPI /tips (NBA|EuroLeague) + /health; CORS open; bookOdds{ml_home,ml_away,spread,spread_price,total,over_price,under_price}; missing odds = note-only, never forces NO BET; model-only fallback when engine unavailable; crowd + lineMove display blocks; adapters _ratings_from_form (home_off/home_def/away_off/away_def/home_court) + _market_from_odds (spread/total/home_ml/away_ml) → engine.bball.build_tip; _normalize_tip maps engine probs{ML,spread,total} → API {ml,spread,totals}
- NEW server/__init__.py, tests/__init__.py
- NEW requirements.txt — fastapi, uvicorn[standard], requests
- NEW vercel.json — @vercel/python build on server/main.py, /api/* → server/main.py
- NEW tests/test_server.py — 17 tests (envelope, league 400, missing-odds note, model-only fallback, normalize, engine-tip integration, _is_today, no-NO-BET-on-missing-odds, non-today filter); all PASS via `python tests/test_server.py` (fastapi in venv)
- NEW ingest/espn_free.py — NBA scoreboard/teams/schedule/standings + spread/total/ML open-close odds (DraftKings preferred), TTL 300s stale-fallback cache, _norm/_match fuzzy team matching (LA→Los Angeles etc.), never raises
- NEW ingest/euroleague_free.py — official api-live.euroleague.net: v1/results XML (whole season, scores+played), v2/competitions/E/seasons (current season = first winner:null), v3 .../rounds/{n}/basicstandings (round = max played gameday); TTL 600s; no odds here (→ odds_free); never raises
- NEW ingest/odds_free.py — The Odds API v4 basketball_nba + basketball_euroleague, h2h/spreads/totals decimal, key from env ODDS_API_KEY, called only on demand, no key → []/None, standings always []; match_game() fuzzy-joins odds games to ESPN names
- NEW ingest/__init__.py (empty package marker)
- FIX 2026-09-15 Vercel 404 on `/`: API-only deploy — vercel.json lacked frontend build/route + frontend/ lacked Next scaffold. Added frontend/package.json, next.config.mjs, tsconfig.json, app/layout.tsx; vercel.json now dual-build + /(.*)→frontend/$1 (mirrors football-model).
- NEW tests/test_ingest.py — 37 tests (espn 20 / euroleague 9 / odds 8), all PASS via `python3 tests/test_ingest.py` (no pytest needed; sys.path bootstrap included)

## Data sources (free only)
- ESPN free: NBA scoreboard/schedules/standings + nba/lines (spread/total/ML open-close)
- euroleague_api (giasemidis, free): EuroLeague calendar/standings/boxscore/pbp
- balldontlie.io free: NBA backup
- Basketball-Reference: historical PS/G PA/G priors only
- The Odds API free 500/mo: h2h/spreads/totals fallback
- Polymarket public: crowd display only (EuroLeague expect None)

## Gotchas
- Poisson unusable (~110 pts) → Normal on margin + total
- EuroLeague ESPN thin → euroleague_api primary
- Spreads need -110 normalization; totals ~220
- Home court ~+3.5 NBA, ~+4 EuroLeague (tune later)
- NEVER `git add -A` if tarballs appear; explicit paths only
- Functional style, pure functions, never raise in ingest
- EuroLeague official host is api-live.euroleague.net (api.euroleague.net 403s); v1/results is XML (parse with xml.etree), v2/v3 are JSON
- EuroLeague season code = E{startYear} (E2026 = 2026-27); current = first season with winner:null; pre-season standings emit NaN winPercentage → _to_float rejects non-finite
- ESPN NBA odds live in scoreboard competitions[].odds[] (moneyline home/away + spread + overUnder + open/close nodes); empty during offseason
- The Odds API: no standings endpoint (returns []); free tier 500 req/mo — only call on demand, never at import
- ESPN 403s custom User-Agents — never set headers in ingest requests

## Resume
- `git status --short` in /root/basketball-model, read this file, continue first unchecked todo.
- Ingest done: espn_free (NBA), euroleague_free (EL), odds_free (Odds API fallback). Tests: `python3 tests/test_ingest.py` (37 pass).
- Next: wire ingest into server/main.py adapters (fetch_scoreboard/fetch_schedules/fetch_standings per league), then CI wiring for the full test suite.
- Delete only on explicit user confirmation.
