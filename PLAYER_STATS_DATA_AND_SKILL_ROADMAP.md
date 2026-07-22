# Player-Stats Data Layer and Skill Roadmap

**Project:** The Daily Slate

**Current mission:** Build a local PyBaseball API before connecting new data
to the daily production slate.

**Updated:** July 13, 2026

## The architecture in one view

```text
Public baseball sources
  Baseball Savant · FanGraphs · Baseball Reference · Chadwick
                         │
                         ▼
                 pybaseball library
                         │
                         ▼
       Local read-only FastAPI service on the M5
       validation · cache · limits · honest errors
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
     Historical snapshots     Backtest feature tables
      Parquet / SQLite          pandas / NumPy / SQL
              └──────────┬──────────┘
                         ▼
       Baseline models and evaluation reports
                         │
                human review + approval
                         ▼
       Optional Daily Slate pipeline integration
```

The API is a boundary, not a new data source. `pybaseball` scrapes public
baseball sources and returns pandas DataFrames. The local FastAPI service
converts selected calls to validated JSON so the backtester, notebooks, and
future UI do not each need their own scraping logic.

## Current infrastructure status

- GitHub remains the single source of truth.
- The normal Daily Slate GitHub Actions pipeline remains plain Python.
- Telegram failure alerts remain in `daily.yml` and `grade.yml`.
- The Firebase healer, signed workflow hooks, auto-heal PR creation, and
  Telegram notification loop are fully functional and verified end to end.
- The earlier billing-activation follow-up is resolved. No billing repair or
  Firebase redeployment is part of the PyBaseball work.
- The healer now uses the `google-genai` SDK; the legacy-SDK statement in the
  session handoff was superseded by the later repository migration.
- Do not change billing, redeploy Firebase, or change cloud secrets without an
  explicit developer approval gate.
- PyBaseball v0.1 is intentionally local-only and does not use Firebase.

## Build phases

### Phase 1 — Local API foundation (now)

- Wrap player lookup, batter/pitcher Statcast, and season batting/pitching
  tables.
- Keep every pybaseball call and the six-hour CSV cache in one shared data
  layer.
- Validate dates, IDs, seasons, and response sizes.
- Paginate every capped response until complete; never analyze a response with
  `truncated: true`.
- Return upstream failures; never invent missing statistics.
- Bind to `127.0.0.1` and document all endpoints through FastAPI `/docs`.
- Test route contracts with fakes so the test suite never depends on a live
  scrape.

**Exit gate:** unit/contract tests pass, cache and strict-JSON tests pass, a
complete paginated Statcast smoke load succeeds, and no production workflow
file changes.

### Phase 2 — Historical storage

- Save raw pulls as immutable dated Parquet snapshots.
- Add SQLite first for indexed local queries; consider Postgres only if the
  local workload outgrows SQLite.
- Record source, retrieval time, query, row count, and schema version with
  every snapshot.
- Fetch in bounded date chunks and resume safely after upstream failures.
- Never overwrite a historical snapshot silently.

**Exit gate:** the same input snapshot produces the same feature table, and a
data audit can trace every derived value to its source pull.

### Phase 3 — Baseball feature layer

- Batter: wOBA/wRC+, barrel rate, hard-hit rate, xSLG, chase, platoon split,
  rolling form, and playing-time opportunity.
- Pitcher: FIP/xFIP/SIERA, xERA, K%, BB%, CSW, pitch mix, velocity trend,
  handedness split, and workload/fatigue.
- Context: park factors, lineup position, bullpen use, rest/travel, weather,
  and—only after a clean source is approved—umpire effects.
- Regress small samples toward longer-term performance instead of presenting
  noisy recent rates as true talent.

**Exit gate:** feature definitions are documented, leakage checks pass, and
missing values stay missing rather than becoming fake zeroes.

### Phase 4 — Baseline modeling and honest evaluation

Start simple and earn complexity:

1. Regularized logistic/linear models for interpretable baselines.
2. XGBoost or LightGBM for nonlinear tabular interactions.
3. Time-based validation by game date—never random splits that leak the
   future into the past.
4. Calibration, Brier score, log loss, MAE/RMSE, and reliability plots as
   appropriate to each target.
5. Compare every model with a naive baseline and, where available, the market
   closing line.

Candidate targets include strikeouts, hits, home runs, earned runs, team
runs, and win probability. A model result is research evidence, not an
automatic wager or site pick.

**Exit gate:** out-of-sample improvement is repeatable across multiple time
windows and all experiments can be reproduced from versioned data.

### Phase 5 — Daily tool and phone workflow

- Schedule local ETL → features → model → report only after the backtest gate.
- Present model probability, market-implied probability, uncertainty, data
  freshness, and missing-source warnings together.
- Add a Streamlit or existing-site view only after the underlying API contract
  stabilizes.
- Keep manual approval between research output and any production slate
  change.

### Phase 6 — Advanced work (optional, later)

- Pitch-sequence models for next-pitch, chase, or contact-quality research.
- Neural models only when sample size and baseline results justify them.
- Tracking/video computer vision only as a separate research project with a
  legal data source.
- Experiment tracking with MLflow or Weights & Biases if local reports become
  difficult to compare.

Deep learning is not a prerequisite for the first useful player-stats system.
Clean data, domain-aware features, and time-correct evaluation have priority.

## Personal skill stack, in order

| Stage | Skills to practice | Daily Slate application |
|---|---|---|
| 1. Data | Python, pandas, NumPy, pybaseball, HTTP APIs | Clean player and pitch tables |
| 2. Storage | SQL, SQLite, Parquet, schema/version design | Reproducible historical snapshots |
| 3. Domain | wOBA, wRC+, FIP/xFIP/SIERA, barrel, CSW, park/context | Realistic baseball features |
| 4. Models | Regression, classification, Ridge/Lasso, XGBoost/LightGBM | Baseline player/game projections |
| 5. Evaluation | Time splits, calibration, Brier/log loss, MAE/RMSE | Prove an edge is not overfit |
| 6. Delivery | FastAPI, scheduling, logging, Streamlit/Plotly | M5 service and phone-friendly output |
| 7. Advanced | Sequences, neural nets, computer vision | Optional pitch/video research |

Basic scraping with BeautifulSoup or browser automation is a last resort. Use
documented APIs and the PyBaseball adapter first, respect source terms, cache
requests, and keep the service private unless a public-deployment review says
otherwise.

## AI team lanes for this chapter

| Team member | Assignment |
|---|---|
| Claude | Architecture/specification and independent PR review |
| Codex / Claude Code | Build the API, tests, storage jobs, and review branch |
| Antigravity | Parallel historical backtests after data snapshots are stable |
| Perplexity / Comet | Verify source availability, terms, lineups, injuries, and weather |
| Gemini | Large CSV exploration and healer runtime only; checklist-gated |
| AI Studio | Test large structured payloads outside production |
| Developer | Approve secrets, billing, deployment, merges, and product decisions |

The working loop remains: **Claude plans → Codex/Claude Code builds → Claude
reviews → developer merges.** Builders do not approve their own work.

## Near-term backlog after API v0.1

1. Run one short live player lookup and one seven-day Statcast smoke test.
2. Decide the first backtest target and exact outcome definition.
3. Add immutable Parquet snapshots plus a source manifest.
4. Build a leakage-safe train/test timeline from `slate_picks_*.json` and
   `results.json`.
5. Expand Savant metrics: barrel rate, hard-hit rate, xSLG, and xERA.
6. Add The Odds API only after request budgeting and secret handling are
   specified.
7. Add Open-Meteo weather and ballpark coordinates for dynamic context.

## References

- [PyBaseball repository and function overview](https://github.com/jldbc/pybaseball)
- [PyBaseball player ID lookup](https://github.com/jldbc/pybaseball/blob/master/docs/playerid_lookup.md)
- [PyBaseball 2.2.7 on PyPI](https://pypi.org/project/pybaseball/)
- [FastAPI response-model documentation](https://fastapi.tiangolo.com/tutorial/response-model/)
- [FastAPI query validation](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/)
