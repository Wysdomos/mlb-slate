# CLAUDE HANDOFF — PyBaseball API and Player-Stats Chapter

**Project:** The Daily Slate (`Wysdomos/mlb-slate`)

**Developer:** Wysdomos

**Date:** July 13, 2026

**Purpose:** Bring Claude fully up to date on today's work, the authoritative
Firebase status, and the developer's intended direction before anything is
committed, pushed, merged, deployed, or connected to production.

---

## Read this first — authoritative current state

The infrastructure era is complete. The Firebase self-healer is **fully
functional**.

- Both `daily.yml` and `grade.yml` send Telegram failure alerts.
- Both workflows send HMAC-signed failure payloads to Firebase.
- The Firebase function retrieves the run logs, broken file, and `AGENTS.md`.
- Gemini prepares a repair on an `auto-heal/<run_id>` branch.
- Python changes pass an `ast.parse` gate before a PR can be opened.
- Telegram sends the resulting PR link.
- The flow was verified on both simple and complex forced failures.
- The healer never merges its own PR. The developer reviews and merges.
- The earlier billing-activation follow-up is resolved. Firebase remains fully
  functional. Do not reopen or reinterpret that item as an outage.
- Repository main has moved from the legacy Gemini SDK to `google-genai`.
  This later repository migration supersedes the older SDK statement in the
  original session handoff.

No Firebase code, workflow, secret, deployment, or billing setting was changed
as part of today's PyBaseball work.

---

## What Wysdomos wants to build

Wysdomos wants the M5 MacBook to become the private player-stats and
backtesting engine behind The Daily Slate.

The immediate goal is to create a stable local API around `pybaseball`. The
API should turn PyBaseball DataFrames into validated JSON that can later feed:

1. historical player-stat snapshots;
2. pandas/NumPy/SQL feature tables;
3. time-correct backtests using the existing `slate_picks_*.json` and
   `results.json` history;
4. interpretable baseline models for player and game outcomes;
5. a phone-friendly research interface after the data and models are proven;
6. optional Daily Slate integration only after human review and validation.

This is not intended to be a public commercial API today. Version 0.1 stays on
the M5, binds to `127.0.0.1`, and does not run in Firebase or GitHub Actions.

The developer also wants to grow the following skill stack through this work:

- Python, pandas, NumPy, PyBaseball, HTTP data access, and data cleaning;
- SQLite/SQL and Parquet for reproducible historical storage;
- baseball metrics and context: wOBA, wRC+, FIP/xFIP/SIERA, xERA, barrels,
  hard-hit rate, CSW, platoon splits, park factors, weather, rest, and travel;
- regression, classification, regularized linear models, XGBoost/LightGBM;
- time-based validation, calibration, Brier score, log loss, MAE/RMSE;
- FastAPI, scheduling, logging, dashboards, and phone access;
- sequence/deep-learning work only later, if clean-data baselines justify it.

The goal is a reproducible baseball research system—not an automatic betting
bot. Missing data stays missing, model output is evidence rather than a wager,
and no result reaches the production slate without review.

---

## Work completed today

### 1. Repository state verified

Codex inspected the actual local repository rather than relying only on the
older status documents.

- Local repository: `~/mlb-slate`
- Remote: `https://github.com/Wysdomos/mlb-slate.git`
- Base branch: `main`
- Base commit when the worktree was created:
  `3c235f0 Remove Phase 2.5 healer self-test scaffolding (pipeline verified)`
- Main was clean and synchronized with `origin/main` at inspection time.
- The repository contains the live Firebase implementation and signed workflow
  hooks.
- The actual `functions/requirements.txt` uses `google-genai>=1.0.0`.

### 2. Isolated review branch and worktree created

No direct edits were made on `main`.

- Review branch: `codex/pybaseball-api-v1`
- Worktree:
  `/Users/wysdomos/Documents/Codex/2026-07-10/can-you-open-wysdomos-on-github/worktrees/pybaseball-api-v1`
- Nothing has been committed or pushed.
- No PR has been opened.

### 3. Local FastAPI service built

New service location:

```text
services/pybaseball_api/
├── __init__.py
├── data_access.py
├── README.md
├── requirements.txt
├── requirements-dev.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   └── service.py
└── tests/
    ├── __init__.py
    └── test_api.py
```

API version: `0.1.0`

Implemented endpoints:

| Method and path | Purpose |
|---|---|
| `GET /health` | Confirm the local read-only service is running |
| `GET /v1/players/search` | Resolve Chadwick/MLBAM/FanGraphs/Retrosheet player IDs |
| `GET /v1/statcast/batter/{player_id}` | Batter pitch-level Statcast data |
| `GET /v1/statcast/pitcher/{player_id}` | Pitcher pitch-level Statcast data |
| `GET /v1/stats/batting` | FanGraphs season batting table |
| `GET /v1/stats/pitching` | FanGraphs season pitching table |

### 4. API safety boundaries implemented

- Read-only GET endpoints only.
- Intended host is `127.0.0.1`, not a public interface.
- PyBaseball imports lazily so `/health` can report before the backend loads.
- `data_access.py` is the single owner of pybaseball calls and the CSV cache.
- Non-empty complete results use a six-hour CSV cache by default.
- Player IDs must be positive integers.
- Player names have length limits.
- Statcast date ranges must be ordered and are capped at 92 inclusive days.
- Returned datasets are capped at 5,000 rows per response.
- Season-stat requests are capped at 10 seasons.
- Responses report `row_count`, `total_rows`, `offset`, `next_offset`, and
  `truncated`.
- `load_complete_dataset` follows every truncated page and raises if paging
  stalls or the final dataset is incomplete.
- Pandas timestamps, NumPy values, NaN, and NaT are serialized safely to JSON.
- Missing or broken upstream data is never replaced with fabricated data.
- Missing PyBaseball returns HTTP 503.
- An upstream scraping failure returns HTTP 502.
- Dependency direction is FastAPI → service → shared data access. It never
  reverses.
- All PyBaseball and CSV operations are isolated in `data_access.py` so the
  backend can be replaced if the package or an upstream site breaks.

### 5. Isolated M5 environment created

- Virtual environment: `.venv-pybaseball/`
- Python: `3.14.6`
- PyBaseball: `2.2.7`
- FastAPI and Uvicorn installed.
- Pytest and HTTP test support installed.
- `.venv-pybaseball/` and `.pytest_cache/` were added to `.gitignore`.
- The environment is local-only and must not be committed.

### 6. Automated tests written and passed

The contract tests use a fake service and never call live baseball sites.

Covered behavior:

- local/read-only health response;
- player ID search contract;
- response truncation metadata;
- rejection of reversed date ranges;
- rejection of Statcast ranges longer than 92 days;
- honest HTTP 502 on upstream failure.

Initial test result before Claude's follow-up review:

```text
6 passed in 0.16s
```

Claude's five follow-up findings were then applied locally:

- complete-dataset loader paginates until `truncated` is false and raises if it
  cannot make forward progress;
- second identical query uses CSV cache with zero new upstream requests;
- `inf`, `-inf`, `NaN`, and `NaT` serialize as strict valid JSON;
- `httpx2>=2.5,<3` is installed and pytest is warning-free;
- FastAPI → service → one shared data-access layer is enforced.

Latest test result after the review fixes:

```text
10 passed in 0.53s
```

### 7. Real upstream smoke tests passed

Two bounded live checks were run through the actual API:

1. Player lookup:

```text
Aaron Judge → MLBAM 592450
HTTP 200 · 1 result
```

2. Batter Statcast:

```text
Player: Aaron Judge, MLBAM 592450
Dates: 2025-07-01 through 2025-07-07
HTTP 200
Real upstream rows: 125
Returned limit: 10
truncated: true
```

This verified that PyBaseball 2.2.7 currently imports and operates on the M5's
Python 3.14 environment for the two tested calls.

### 8. Documentation added and corrected

New documentation:

- `PLAYER_STATS_DATA_AND_SKILL_ROADMAP.md`
- `services/pybaseball_api/README.md`
- this Claude handoff

Updated documentation:

- `AGENTS.md`
  - Firebase is documented as fully functional.
  - The later `google-genai` migration is recorded.
  - The PyBaseball API is moved to the current roadmap priority.
- `PROJECT_STATUS.md`
  - Replaced stale Phase 2 setup claims with the verified live-healer state.
  - Added the PyBaseball branch checklist and test results.
- `.gitignore`
  - Ignores the new virtual environment and pytest cache.

---

## What was deliberately not changed

- No commit to `main`.
- No commit on the review branch yet.
- No GitHub push.
- No pull request.
- No merge.
- No deployment.
- No Firebase or Google Cloud operation.
- No billing operation.
- No secret creation, viewing, copying, or rotation.
- No `.github/workflows` edit.
- No change to `functions/main.py`, `functions/requirements.txt`, or
  `firebase.json`.
- No change to the live Daily Slate HTML or generated JSON.
- No connection from the new API to the daily production pipeline.
- No database, Parquet snapshot job, backtest, or model built yet.

---

## Current uncommitted branch state

Expected modified tracked files:

```text
.gitignore
AGENTS.md
PROJECT_STATUS.md
```

Expected new files/directories:

```text
CLAUDE_HANDOFF_PYBASEBALL_API_2026-07-13.md
PLAYER_STATS_DATA_AND_SKILL_ROADMAP.md
services/pybaseball_api/
```

Before review, confirm with:

```bash
cd /Users/wysdomos/Documents/Codex/2026-07-10/can-you-open-wysdomos-on-github/worktrees/pybaseball-api-v1
git status --short --branch
git diff --check
python3 -c 'import ast, pathlib; [ast.parse(p.read_text(), filename=str(p)) for p in pathlib.Path("services/pybaseball_api").rglob("*.py")]'
.venv-pybaseball/bin/python -m pytest services/pybaseball_api/tests -q
```

---

## Requested Claude review

Claude should review this as architect/reviewer, not merge or deploy it.

Please answer these points explicitly:

1. Does keeping v0.1 local-only and outside CI/Firebase match the safest
   architecture for the player-stats chapter?
2. Are the six endpoints the correct minimum stable contract?
3. Are the 92-day/5,000-row/10-season limits appropriate for M5 backtesting?
4. Are error handling and JSON serialization honest enough for Daily Slate
   guardrails?
5. Should this service stay in `mlb-slate` or move to a separate repository
   before it gains storage and models?
6. What should be the first precisely defined backtest target after API review?
7. Is any important acceptance test missing before the developer authorizes a
   commit or draft PR?

Claude should inspect the branch/worktree files directly if running through
Claude Code on the M5. Claude Project cannot inspect the unpushed branch from
GitHub yet, so this document is the authoritative update until the developer
approves a push.

---

## Recommended next sequence — approval gates preserved

1. Claude reviews the architecture and current uncommitted diff.
2. Codex/Claude Code addresses review findings locally.
3. Run all tests and the two bounded smoke checks again if code changes.
4. Developer explicitly approves commit and push.
5. Open a review PR; do not merge it.
6. Claude independently reviews the PR diff.
7. Developer decides whether to merge.
8. After merge, define one backtest target before adding storage or models.

No step grants permission for a later step automatically.

---

## Team lanes remain unchanged

| Team member | Lane |
|---|---|
| Claude | Architect, specification, and independent review |
| Codex / Claude Code | Local implementation, tests, branches, and PR preparation |
| Antigravity | Parallel historical backtests after snapshots stabilize |
| Perplexity / Comet | Live-source, availability, terms, lineup, injury, and weather research |
| Gemini | Large-table analysis and live healer reasoning; checklist-gated |
| AI Studio | Large structured-payload testing outside production |
| Wysdomos | Approves secrets, billing, deployment, commits, pushes, merges, and product direction |

Working loop: **Claude plans → Codex/Claude Code builds → Claude reviews →
Wysdomos merges.**

---

## Bottom line

Today's work established and validated a private, read-only PyBaseball API
foundation on the M5 without changing the fully functional Firebase healer or
the production Daily Slate pipeline. The next action is independent Claude
review—not a push, merge, deployment, database, or model build.
