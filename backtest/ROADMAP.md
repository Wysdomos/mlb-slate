# The Daily Slate — Product Era Roadmap
*Committed so every AI in the orchestra builds against the same map.
Source: external skill-stack research, absorbed 2026-07-13, filtered
through project doctrine (serverless, AI writes / Python runs, no
invented data).*

## Doctrine filter on the research
**Adopted**
- **Calibration discipline** — hit-rate-by-bucket with confidence
  intervals is the gate for every modeling decision. Deliverable:
  `backtest/CALIBRATION.md`, regenerated as history grows.
- **Edge math** — once real book lines flow (Odds API), every pick gets
  implied probability vs. our number. No stored price, no edge claim.
- **Tree models (XGBoost/LightGBM), conditionally** — only if the
  calibration report shows consensus buckets leave measurable room.
  Measurement era before model era.
- **True-talent regression** — regress streaks toward long-run skill;
  upgrade path for the Streaks page and RBI+.
- **pybaseball as the historical data layer** — via
  `backtest/data_access.py` only (cached, reproducible). Runs on M5.

**Skipped, on doctrine**
- Postgres / Airflow / Streamlit — Actions is the scheduler, Pages is
  the dashboard, flat JSON is the database. SQLite if backtest queries
  ever hurt.
- FastAPI in production/CI — skipped. *Amended 2026-07-13:* a read-only
  service bound to 127.0.0.1 on the M5 (`services/pybaseball_api`) is
  in-lane as a research tool. It must consume the shared data layer
  (`backtest/data_access.py`), never bypass it.
- Web scraping — API-first, always.
- Deep learning / pitch-sequence models — benched; sample size and
  maintenance cost don't justify marginal edge yet.

## Chapter sequence
1. **Odds API K-prop fallback** — built, reviewed, 36 assertions green.
   Awaiting PR flow (see HANDOFF_OddsAPI_Fallback.md). Key-gated; inert
   without secret.
2. **Backtest foundation** (this directory) — `backfill_grades.py`
   replays all slate days against real box scores (M5/Actions, network
   needed); `calibration.py` renders the report offline. 21 offline
   assertions green.
3. **pybaseball enrichment** (M5) — join `data_access.py` pulls onto
   graded picks: slice calibration by park, handedness, line height,
   rest. Answers *where* the signal lives, not just whether.
4. **Savant expansion** — barrel / hard-hit / xSLG / xERA into
   fetch_phase2.py (keyless).
5. **OpenMeteo weather** — park-adjusted context for TOTAL/HR boards.
6. **RBI+ formula** — ships after calibration baseline exists, so its
   lift is measurable, not vibes.
7. **Model question** — XGBoost seat decided by the calibration report.
8. **Alt-parlay revamp** — K combos tiers 0–2, HRR vs high hits-allowed,
   Anchor parlays require DANGER label, max 2× same player.

## Standing rules for this directory
- Grading rules mirror `grade_results.py` exactly — if the live grader
  changes, `backfill_grades.grade_pick` changes in the same PR.
- `graded_picks.json` is append-only by date; delete to regrade.
- No historical odds exist for old picks: reports show hit rates and a
  break-even reference table, never fabricated edges.
- Every file here ships with offline tests. Network code runs on M5 or
  in Actions, never assumed in the sandbox.
