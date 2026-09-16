# Basketball Port — Football Batches (Window View + Crowd Snapshots + ESPN Dates Merge)

Goal: apply football-model commits 24b8239 (window view + crowd 12%), 635b749
(startup init_db), bf359d1 (ESPN ?dates= merge) to /root/basketball-model,
adapted for no-draw basketball markets (ML + Spread + Totals; crowd = H/A only).
Loop: code → push → Actions CI → Vercel. No local installs/builds.
Git identity: Jeff-tek <75492107+Jeff-tek@users.noreply.github.com>.

## Source batches (football)
- 24b8239: db.py CrowdSnapshot + record/history/trend; engine crowd_1x2 @0.12
  excluded from agree gap; server crowd-before-tip, snapshot persist,
  crowdTrend, /crowd-trend, window view (drop today gate, skip post, sort by
  date), warm.yml, frontend 15-min poll + staleness badge + trend arrows.
- 635b749: FastAPI startup hook → init_db() best-effort.
- bf359d1: fetch_scoreboard merges default window + ?dates=YYYYMMDD, dedupe by id.

## Basketball adaptations (no draw!)
- Crowd shape H/A only: {home, away, volumes, url, low_volume}; trend
  {homeDelta, awayDelta, since}; NO draw leg anywhere.
- Engine signature: build_tip(ratings, market, elo_probs, form_probs,
  crowd_ml=None, crowd_weight=0.12).
- polymarket_free: accept event when home+away legs present (no draw needed);
  local _norm (no openmodel_free in this repo).
- ESPN dates merge: NBA only (espn_free.fetch_scoreboard takes no slug);
  EuroLeague uses euroleague_free (season API) — untouched.
- server: keep _is_today helper unused (tests import it); ev.get("state","pre")
  default so old fake events still pass; envelope gains ttl + cron.

## Units (parallel, files only — NO commit/push by agents)
- [x] Unit 1 backend: NEW db.py, requirements.txt, server/main.py
- [x] Unit 2 engine: engine/bball.py (46/46 green)
- [x] Unit 3 ingest: ingest/espn_free.py, NEW ingest/polymarket_free.py (37/37 green)
- [x] Unit 4 frontend+workflow+tests: tips.ts, ModelVisuals.tsx, page.tsx,
      NEW .github/workflows/warm.yml, tests/test_server.py
- [x] Verified + shipped 991c97c main->main 2026-09-16. py_compile clean,
      engine 46/46, ingest 37/37, server suite via CI (no fastapi locally).

## Gotchas
- NEVER `git add -A`; explicit paths only. Agents must NOT commit/push.
- No local npm/pip; verify via py_compile + `python3 tests/test_*.py`.
- test_server.py imports fastapi — runs in CI, not locally.
- db.py mirrors football (module-level create_engine from DATABASE_URL);
  all server/db imports lazy inside try/except so missing DB never breaks /tips.
- Vercel needs DATABASE_URL (Neon) + PROD_URL repo secret after push.

## Resume
- `git status --short` in /root/basketball-model, read this file.
- Delete only on explicit user confirmation.
