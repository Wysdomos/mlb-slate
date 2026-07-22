# THE DAILY SLATE — PROJECT STATUS

**Updated:** July 13, 2026

**Repo:** github.com/Wysdomos/mlb-slate

**Live:** wysdomos.github.io/mlb-slate

**Product chapter:** Player-stats data layer

## Production platform

- [x] Automated workbook → GitHub Actions → GitHub Pages pipeline
- [x] Main slate, K Report, Streaks, Scout, and For The Record outputs
- [x] Prior-day grading through `grade_results.py`
- [x] Conflict-aware workflow push retries
- [x] Telegram failure alerts on daily and grading workflows
- [x] Self-healer code, HMAC hooks, syntax gate, PR creation, and notifications
  previously verified on simple and complex forced failures
- [x] Healer migrated to the current `google-genai` SDK on repository main

## Cloud healer status — fully functional

The Firebase function, signed workflow calls, Gemini diagnosis, syntax gate,
auto-heal PR creation, and Telegram notification loop were verified end to end
on both simple and complex forced failures. The developer confirms Firebase is
still fully functional and the earlier billing-activation follow-up is resolved.

- Telegram failure alerts remain the first-line notification.
- Repository main has migrated the healer from the legacy SDK to
  `google-genai`.
- The healer remains failure-only and never merges its own PRs.
- Do not change billing, deploy Firebase, rotate cloud configuration, or edit
  cloud secrets without explicit developer approval.

No tokens, chat IDs, API keys, or secret values belong in this file.

## M5 development environment

- [x] Homebrew, Xcode tools, Git, GitHub CLI, Node 24, and Python installed
- [x] `~/mlb-slate` connected to `Wysdomos/mlb-slate`
- [x] VS Code, Claude Code, and Codex local/cloud access
- [x] iPhone remote-control read-only test
- [x] Firebase CLI authenticated and self-healer fully operational
- [ ] Antigravity first-open against `~/mlb-slate`

## Current review branch — PyBaseball API v0.1

Branch: `codex/pybaseball-api-v1`

- [x] Local-only FastAPI service structure
- [x] Read-only player lookup endpoint
- [x] Read-only batter and pitcher Statcast endpoints
- [x] Read-only season batting and pitching endpoints
- [x] Date, season, ID, and row-limit validation
- [x] One shared data layer for pybaseball calls and six-hour CSV caching
- [x] Honest 502/503 responses for upstream/dependency failure
- [x] Route tests use fakes and do not scrape live sites
- [x] Pagination contract with `offset`, `next_offset`, and truncation guard
- [x] Strict JSON conversion for `inf`, `-inf`, `NaN`, and `NaT`
- [x] Identical-call CSV cache test proves zero new upstream requests
- [x] `httpx2` development dependency installed; pytest warning removed
- [x] Install the isolated development environment (Python 3.14)
- [x] Run unit/contract tests (10 passed, warning-free)
- [x] Run one bounded live player-lookup smoke test (Aaron Judge → 592450)
- [x] Run one bounded seven-day Statcast smoke test (125 real rows)
- [ ] Independent Claude review
- [ ] Developer approval to push/open a PR

This branch does not modify `.github/workflows`, Firebase, the production
website, or existing slate output files.

## Product roadmap

The developer moved PyBaseball to the front of the next chapter. Full details,
skill progression, model gates, and team lanes are in
`PLAYER_STATS_DATA_AND_SKILL_ROADMAP.md`.

1. Local PyBaseball API and stable JSON contracts
2. Immutable Parquet/SQLite historical snapshots
3. Leakage-safe feature tables and baseline backtests
4. Savant barrel/hard-hit/xSLG/xERA expansion
5. The Odds API with a request budget and secret-management plan
6. Open-Meteo weather and dynamic park context
7. Phone-friendly research view only after model validation

## Standing guardrails

- GitHub is the single source of truth.
- No AI in normal CI; the live cloud healer is a failure-only exception.
- Never commit directly to `main`; use a review branch and PR.
- The developer approves every merge, deployment, billing action, and secret.
- Never fabricate missing data or prop lines.
- Preserve frozen design tokens and existing site behavior.
- Run `ast.parse` after every Python edit.
- Backtests use time-ordered validation and versioned source snapshots.
