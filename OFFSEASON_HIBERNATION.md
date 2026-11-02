# OFFSEASON_HIBERNATION.md — The Daily Slate (MLB)

> **STATUS: HIBERNATED since 2026-11-02 (~07:15 UTC).**
> This is a temporary operational pause, not a shutdown. Nothing in this
> document is calendar-triggered. **Reactivate only on the owner's explicit
> instruction.** No AI agent may re-enable any workflow, function, or alert
> on its own initiative.

Covers both repositories:

| Repo | Visibility | Role |
|---|---|---|
| `Wysdomos/mlb-slate` | public | pipeline code, site (GitHub Pages), healer source, results history |
| `Wysdomos/mlb-slate-archive` | private | raw BallparkPal (BPP) snapshot tarballs, `archive.yml` |

---

## 1. What was disabled

All disabling was done **operationally** through the GitHub Actions REST API
(`PUT /repos/{owner}/{repo}/actions/workflows/{id}/disable`). No workflow
files were edited, no secrets were touched, no data was removed, nothing was
deleted. Every workflow below reported `state: active` before the change and
`state: disabled_manually` after it.

### 1a. Public repo `Wysdomos/mlb-slate`

| Workflow (name) | File | Workflow ID | Original triggers (all UTC) | Before → After |
|---|---|---|---|---|
| Daily MLB Slate Build | `.github/workflows/daily.yml` | `275862916` | `schedule` 8×/day at `0 7`, `0 13`, `0 16`, `0 19`, `0 21`, `0 23`, `0 1`, `0 3`; `push` on `**.xlsx`; `workflow_dispatch` | active → **disabled_manually** |
| For The Record (grading) | `.github/workflows/grade.yml` | `296623441` | `schedule` `0 9 * * *`; `push` on `**.xlsx`; `workflow_dispatch(grade_date)` | active → **disabled_manually** |
| CI | `.github/workflows/ci.yml` | `320346607` | `pull_request`; `push` to `main`, `codex/**` | active → **disabled_manually** |
| PR Preview | `.github/workflows/preview.yml` | `347162689` | `pull_request` opened/synchronize/reopened/closed | active → **disabled_manually** |
| Backfill Grades (one-shot) | `.github/workflows/backfill-oneshot.yml` | `347206033` | orphan registration — file exists on **no** branch; cannot run | active → **disabled_manually** |
| Kalshi Verify (one-shot) | `.github/workflows/kalshi-verify.yml` | `348066060` | orphan registration — file exists on **no** branch; cannot run | active → **disabled_manually** |
| pages-build-deployment | GitHub-managed (`dynamic/pages/...`) | `269933796` | runs only when `main` is pushed | **left active on purpose** — this is what serves the site; it cannot be disabled via API and will not run because nothing pushes to `main` anymore |

Not registered, but worth knowing:

- `.github/workflows/functions-deploy.yml` exists **only** on branch
  `codex/functions-deploy`. It triggers on `push` to `main` under
  `functions/**` and would run `firebase deploy --only functions` using
  secret `FIREBASE_FUNCTIONS_DEPLOY_SA`, with a Telegram alert on failure.
  Because it is not on `main` it is not registered and cannot run. **Do not
  merge that branch during hibernation** unless you intend to arm
  auto-deploys.
- No `.github/dependabot.yml` exists in either repo. Nothing to disable.

### 1b. Private repo `Wysdomos/mlb-slate-archive`

| Workflow (name) | File | Workflow ID | Original triggers (UTC) | Before → After |
|---|---|---|---|---|
| BPP Daily Archive | `.github/workflows/archive.yml` | `318425054` | `schedule` `10 15 * * *` (11:10 AM ET); `workflow_dispatch(date)` | active → **disabled_manually** |

Env caps the archive ran with: `BPP_MIN_GAP=1.0`, `BPP_MAX_CALLS=150`.
It clones the public repo at run time and runs
`python3 -m services.bpp_client.snapshot`.

### 1c. Workflow runs

At hibernation time there were **no in-progress, queued, waiting or
requested runs** in either repo, so nothing needed cancelling. Last runs
before the pause:

| Repo / workflow | Run # | Run ID | Started (UTC) | Event | Result |
|---|---|---|---|---|---|
| mlb-slate / Daily MLB Slate Build | 991 | `41403157826` | 2026-11-02 06:57:12 | schedule | success, no publish (guard) |
| mlb-slate / For The Record | 186 | `41323393519` | 2026-11-01 15:52:17 | schedule | success, no changes |
| mlb-slate-archive / BPP Daily Archive | 103 | `41342372538` | 2026-11-01 19:33:59 | schedule | success → `snapshots/2026-11-01.tar.gz` |

Any run newer than these in either repo means hibernation has been broken.

### 1d. API consumers that are now dormant

Every automated external call in this project runs inside one of the
disabled workflows or inside the healer (which only fires from those
workflows). Secret **names** only — values live in GitHub Actions secrets
and Firebase and were not read or changed.

| Integration | Credential (name) | Where it is called | Disabled via |
|---|---|---|---|
| BallparkPal API | `BPP_API_KEY` | `fetch_projected_mode.py`, `fetch_bpp_tabs.py`, `fetch_bpp.py` (daily); `services/bpp_client/snapshot` (archive) | daily.yml, archive.yml |
| BallDontLie | `BDL_KEY` | `fetch_props.py`, `fetch_phase2.py`, `fetch_streaks.py`, `build.py` (daily); `grade_results.py`, `backtest/backfill_grades.py` (grade) | daily.yml, grade.yml |
| The Odds API | `ODDS_API_KEY` | `fetch_props.py` fallback (daily) | daily.yml |
| Kalshi (public, no key) | — | `fetch_kalshi.py`, `services/kalshi_client` (daily) | daily.yml |
| MLB Stats API (free) | — | fetch/grade scripts (schedule, linescore, probables, box scores) | daily.yml, grade.yml |
| Baseball Savant (free) | — | `fetch_phase2.py`, cache-first (daily) | daily.yml |
| Gemini (`gemini-3.5-flash`) | `GEMINI_API_KEY` (Firebase secret) | `functions/main.py` healer only | healer has no caller (see §1f) |
| GitHub API | `GITHUB_TOKEN` (Actions built-in; separate Firebase secret for the healer) | commits/pushes in daily, grade, preview; PR creation in healer | workflows disabled; healer idle |

Local-only services (`services/pybaseball_api`) are not in CI and were never
automated. `services/kalshi_client/client.py` has a `while True` that is a
cursor-pagination loop inside a single fetch, not a daemon.

### 1e. Telegram senders (all dormant)

| # | Sender | Condition | Status |
|---|---|---|---|
| 1 | `daily.yml` → "Telegram alert on failure" | `if: failure()` | workflow disabled |
| 2 | `daily.yml` → "Notify Firebase Auto-Healer on Failure" (secondary "safety net may be down" message) | healer HTTP not 2xx | workflow disabled |
| 3 | `daily.yml` → "Alert on empty critical tabs" → `tools/check_critical_tabs.py` (the missing-data alert) | `if: always()` | workflow disabled |
| 4 | `grade.yml` → "Telegram alert on failure" | `if: failure()` | workflow disabled |
| 5 | `archive.yml` → "Telegram alert on failure" | `if: failure()` | workflow disabled |
| 6 | `functions/main.py` → `notify_mobile()` (every healer outcome, incl. self-test) | healer webhook invoked | no caller |
| 7 | `functions-deploy.yml` (unmerged branch) deploy-failure alert | n/a | not registered |

There is no other Telegram sender in either repo (grep for
`api.telegram.org` / `TELEGRAM_BOT_TOKEN` / `sendMessage`). The bot and its
credentials were **not** deleted or rotated.

### 1f. Firebase auto-healer

Source: `functions/main.py`, function `auto_heal_webhook`, config
`firebase.json` (functions codebase only — no hosting, no extensions).

- **Trigger type:** `@https_fn.on_request` — plain HTTPS webhook. There is
  **no** Cloud Scheduler / Pub/Sub / Firestore trigger anywhere in
  `functions/` or `firebase.json`. It cannot fire by itself.
- **Authentication:** HMAC-SHA256 over the request body with
  `WEBHOOK_SECRET`; fails **closed** (401) if the secret is missing or the
  signature is wrong.
- **Only callers:** the `if: failure()` steps in `daily.yml` and `grade.yml`.
  Both are disabled, so a workflow failure can no longer reach the healer.
- **What it does when called:** fetch run logs (GitHub API, with retry
  delays) → find traceback → fetch broken file + first 3,000 chars of
  `AGENTS.md` → Gemini → `ast.parse` gate → branch `auto-heal/<run_id>` →
  open PR → Telegram at every step. A signed payload with `"selftest": true`
  only calls Gemini once and reports to Telegram.
- **Hibernation effect:** the deployed function is left deployed and
  untouched. An idle HTTPS function makes zero Gemini, GitHub or Telegram
  calls and has no scheduled cost driver. Billing, deployment, and cloud
  secrets were **not** modified.
- **Not verifiable from the hibernation session:** whether the *deployed*
  revision matches `functions/main.py` on `main`, and whether any Cloud
  Scheduler job exists in the Firebase/GCP project. See §10.

---

## 2. Why it was disabled

- The 2026 MLB season is over. From 2026-10-08 to 2026-11-02 the daily
  build ran ~8 times a day (runs #≈800–991) and the archive ran daily, each
  run calling BallparkPal, BallDontLie, The Odds API and Kalshi for slates
  that do not exist. Every one of those daily runs ended in "No changes"
  because `tools/projected_publish_guard.py` correctly refused to publish a
  degenerate Projected Mode build (`PROJECTED_MIN_HR=50`,
  `PROJECTED_MIN_HITS=50`). API quota and Actions minutes were being spent
  for nothing.
- Any transient provider outage during the offseason would have produced
  Telegram failure alerts and healer invocations (Gemini spend) for a
  pipeline that has nothing to build.
- The owner asked for the project to be completely quiet until explicitly
  reactivated, with all history preserved.

---

## 3. How to verify it remains disabled

Run these from any machine with `gh` authenticated as `Wysdomos`
(they are read-only and cost nothing):

```bash
gh api repos/Wysdomos/mlb-slate/actions/workflows --jq '.workflows[] | "\(.state)\t\(.name)\t\(.path)"'
```

```bash
gh api repos/Wysdomos/mlb-slate-archive/actions/workflows --jq '.workflows[] | "\(.state)\t\(.name)\t\(.path)"'
```

Expected: every row is `disabled_manually` **except** `pages-build-deployment`,
which stays `active`.

```bash
gh run list -R Wysdomos/mlb-slate --limit 5
```

```bash
gh run list -R Wysdomos/mlb-slate-archive --limit 5
```

Expected: no run newer than daily #991 (2026-11-02 06:57 UTC) or archive
#103 (2026-11-01 19:33 UTC). Also:

- GitHub UI → each repo → **Actions** → every workflow shows the yellow
  "This workflow was disabled manually" banner.
- `main` of `mlb-slate` has no commit after `9c12599` ("For The Record:
  graded latest slate", 2026-10-08 16:11 UTC) other than reviewed PR merges.
- `main` of `mlb-slate-archive` has no commit after `a65e424` ("Archive BPP
  snapshot 2026-11-01").
- The Telegram chat receives nothing from the bot.
- Provider dashboards (BallparkPal, BallDontLie, The Odds API, Google AI
  Studio for Gemini) show zero calls after 2026-11-02.
- Firebase console → Functions → `auto_heal_webhook` → Logs: no invocations
  after 2026-11-02.

Note: GitHub also auto-disables scheduled workflows after 60 days of repo
inactivity. If a workflow later shows "disabled because of inactivity"
instead of "disabled manually", that is fine — it is still off, and the
re-enable step in §4 is identical.

---

## 4. How to safely restart everything

**Only after the owner says so.** Do the pre-flight first; it costs no API
credits.

### 4a. Pre-flight (no spend)

1. Read `AGENTS.md`, `PROJECT_STATUS.md` and this file. Review every PR and
   branch merged during the offseason; confirm the four workflow files on
   `main` are the ones you intend to run.
2. Confirm secrets still exist (Settings → Secrets and variables → Actions):
   - `mlb-slate`: `BPP_API_KEY`, `BDL_KEY`, `ODDS_API_KEY`,
     `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WEBHOOK_SECRET`,
     `FIREBASE_WEBHOOK_URL`
   - `mlb-slate-archive`: `BPP_API_KEY`, `TELEGRAM_BOT_TOKEN`,
     `TELEGRAM_CHAT_ID`
3. Confirm provider subscriptions/keys are active (BallparkPal, BallDontLie,
   The Odds API) and check their quotas and any API changes since October
   2026. Confirm the Gemini key and the healer's GitHub token have not
   expired (fine-grained PATs expire).
4. Decide the 2027 season boundary for grading **before** enabling
   `grade.yml` (see §8).
5. Confirm there is **no** `slate_picks_*.json`, `day_data.json` or
   `build-stamp.json` on `main` dated inside the offseason. As of
   hibernation the newest is the 2026-10-07 slate.

### 4b. Re-enable order

Re-enable with either form (by file name or by ID):

```bash
gh workflow enable ci.yml -R Wysdomos/mlb-slate
```

```bash
gh api -X PUT repos/Wysdomos/mlb-slate/actions/workflows/320346607/enable
```

Recommended order, verifying each step before the next:

1. **CI** (`ci.yml`, `320346607`) and **PR Preview** (`preview.yml`,
   `347162689`) — touch no sports APIs. Open a trivial PR to confirm both
   run and the preview URL comment appears.
2. **Telegram** — nothing to enable; test as in §6.
3. **Healer** — self-test as in §4c (one small Gemini call).
4. **Grading** (`grade.yml`, `296623441`) — follow §8 exactly. Do **not**
   enable before the first 2027 slate has been built and played.
5. **Daily build** (`daily.yml`, `275862916`) — enable, then trigger one
   `workflow_dispatch` manually and watch the run end-to-end. With no
   workbook uploaded it runs in Projected Mode and the publish guard will
   skip publishing until BPP returns ≥50 HR rows and ≥50 hit rows — that is
   expected preseason behaviour, not a bug.
6. **Archive** (`archive.yml`, `318425054`) — follow §7.
7. Leave the two orphan one-shots (`347206033`, `348066060`) disabled; they
   have no file to run. Delete their run history if you want them out of
   the Actions sidebar (optional, not done).

### 4c. Healer self-test (one Gemini call, no repo change)

The `FIREBASE_WEBHOOK_URL` and `WEBHOOK_SECRET` are GitHub secrets; use
their values locally, never commit them.

```bash
PAYLOAD='{"repository":"Wysdomos/mlb-slate","run_id":"selftest","sha":"selftest","selftest":true}'
SIG=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')
curl -s -X POST "$FIREBASE_WEBHOOK_URL" -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=$SIG" -d "$PAYLOAD"
```

Expected: HTTP 200 with "Healer self-test passed" and the same message in
Telegram. A 401 means the secret or URL is wrong; a "self-test FAILED"
means the Gemini key or model needs attention. Fix those before enabling
`daily.yml`, otherwise the first real failure will not be caught.

---

## 5. API integrations that need testing before full reactivation

Test each **once**, cheaply, in this order. Do not loop.

| Integration | Where used | Cheap test | Watch for |
|---|---|---|---|
| BallparkPal | `services/bpp_client/`, `fetch_bpp*.py`, `fetch_projected_mode.py`, archive snapshot | one `archive.yml` `workflow_dispatch` with an explicit date (§7), or `python3 -m services.bpp_client.snapshot --date YYYY-MM-DD --output-dir /tmp/x` with `BPP_MAX_CALLS=5` | 401/403 (key), schema changes in the 4 `BP_` tabs, rate-limit gaps (`BPP_MIN_GAP`) |
| BallDontLie | `fetch_props.py`, `fetch_phase2.py`, `fetch_streaks.py`, `grade_results.py`, `backfill_grades.py` | first manual `daily.yml` dispatch (steps are `continue-on-error`) | endpoint changes; K-prop gaps noted in `AGENTS.md`; new rate limits |
| The Odds API | `fetch_props.py` fallback (`HANDOFF OddsAPI Fallback.md`) | same daily dispatch; check the step log for quota headers | monthly request quota — metered; confirm plan is still active |
| Kalshi | `fetch_kalshi.py`, `services/kalshi_client` | same daily dispatch; caps `KALSHI_MAX_MARKET_PAGES=2`, `KALSHI_MAX_ORDERBOOK_CALLS=20` | series ticker renames for the new season; payload shape (`KalshiApiPayloadError`) |
| MLB Stats API | schedule, probables, linescore, box scores in fetch/grade scripts | same daily dispatch; grading dispatch (§8) | season/schedule endpoints for 2027; `hydrate=probablePitcher` still valid |
| Baseball Savant | `fetch_phase2.py` (cache-first) | same daily dispatch | CSV column drift; the cache may be stale from 2026 — expect a cold fetch |
| Gemini | healer only | §4c self-test | model `gemini-3.5-flash` still available; key valid |
| hrtargets.com | HR results authority (per `AGENTS.md`) | first grading dispatch | page/format changes |

Known issue carried into hibernation, **not** fixed and out of scope here:
the missing-data alert from `tools/check_critical_tabs.py`
(`CRITICAL_TABS=Park_Factors,SP_Projections`). Expect it on the first
preseason runs until BPP publishes sims.

---

## 6. How to resume Telegram notifications

Nothing was disabled on the Telegram side — the bot token and chat ID
secrets are intact in both repos and in Firebase. Alerts stop because the
workflows that send them are disabled. They resume automatically the moment
each workflow is re-enabled.

To confirm the bot still works **before** re-enabling anything (uses the
secret values locally, never in a commit):

```bash
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" -d text="Daily Slate: reactivation test"
```

If the chat has been archived or the bot was blocked in Telegram, unblock
it and re-run. The `TELEGRAM_DRY_RUN=1` env var makes
`tools/check_critical_tabs.py` print instead of send if you want a silent
first run.

---

## 7. How to restart private archiving

1. Pre-flight §4a (especially: `BPP_API_KEY` present in
   `mlb-slate-archive`; BPP subscription active).
2. Make sure `services/bpp_client/` on **public `main`** is the version you
   want — the archive workflow clones public `main` at run time.
3. Re-enable:

   ```bash
   gh api -X PUT repos/Wysdomos/mlb-slate-archive/actions/workflows/318425054/enable
   ```

4. Run **one** manual dispatch with an explicit date (a real 2027 slate
   date, or a known 2026 date if you only want to prove the key works):

   ```bash
   gh workflow run archive.yml -R Wysdomos/mlb-slate-archive -f date=YYYY-MM-DD
   ```

5. Confirm `snapshots/YYYY-MM-DD.tar.gz` lands on `main` and that the
   tarball contains `YYYY-MM-DD/manifest.json`. If the date already existed,
   the workflow prints "No change" and commits nothing (safe).
6. Only then let the `10 15 * * *` schedule run. Do not add offseason dates;
   there is no slate to snapshot and BPP will return empty payloads.

The archive repo **must remain private** — the payloads are under a
personal-use license (see its `README.md`).

---

## 8. How to resume grading without accidentally backfilling the offseason

### What grading does today

- `grade.yml` runs `grade_results.py` → `build_record.py` →
  `backtest/backfill_grades.py`, then commits `record.html`,
  `results.json`, `backtest/graded_picks.json`.
- `grade_results.py` picks the slate to grade in this priority: explicit
  `GRADE_DATE` env → the date on the newest workbook's `HR_Results` tab →
  the **newest `slate_picks_*.json` by date**. It appends a per-day entry to
  `results.json["history"]`; `season.w/l` is the **sum over all history
  entries** since 2026-06-15.
- `backfill_grades.py` is idempotent **per date**: any date already in
  `graded_picks.json["dates"]` is skipped. With date arguments only those
  dates are processed. To regrade, delete that date from `"dates"`.

### State frozen at hibernation (do not let these move during the pause)

| File | Value |
|---|---|
| `results.json` | `updated: "10-7 graded"`, `season: {w: 490, l: 2437}`, `history`: 84 entries 2026-06-15 → 10-7 |
| `backtest/graded_picks.json` | 83 dates 2026-06-15 → 2026-10-07, 18,003 rows (≈13.8 MB) |
| `slate_picks_*.json` | 84 files, newest `slate_picks_10-7.json` |
| `build-stamp.json` | `slate_date 2026-10-07`, `mode projected`, built 2026-10-08T02:22:31Z |
| `record.html`, `index.html`, `k-report.html`, `streaks.html`, `scout.html` | as built for the 2026-10-07 slate |

### Safe resumption procedure

1. **Decide the season boundary first.** Because `season` is a running sum,
   the first 2027 grade would be added to the 2026 totals. Before enabling
   `grade.yml`, choose one: (a) archive 2026 by copying `results.json` to a
   dated file (e.g. `results_2026.json`) and seed a fresh `results.json`
   history, or (b) consciously keep a cumulative all-time record. Do this
   in a reviewed PR, never in the workflow.
2. Verify there are no offseason artefacts to grade:
   `ls slate_picks_*.json` must show nothing newer than `10-7` until the
   first 2027 slate is actually built by `daily.yml`.
3. Do **not** re-enable `grade.yml` until the first 2027 slate has been
   built **and the games have been played**. Otherwise the 05:00 ET
   schedule would grade an unplayed slate or re-pick 10-7.
4. First grading run: manual, explicit date, no schedule:

   ```bash
   gh api -X PUT repos/Wysdomos/mlb-slate/actions/workflows/296623441/enable
   ```

   ```bash
   gh workflow run grade.yml -R Wysdomos/mlb-slate -f grade_date=M-D
   ```

   where `M-D` is the first played 2027 slate. Check the run log:
   `backfill_grades.py` should report all 2026 dates as "already
   backfilled" and process only the new date.
5. Inspect the resulting commit (`record.html`, `results.json`,
   `graded_picks.json`) before letting the daily schedule continue. If
   anything looks wrong, revert that single commit; the 2026 data is
   unchanged underneath.
6. Never delete `graded_picks.json` to "start fresh" — that triggers a full
   re-grade of every 2026 slate against the live MLB Stats API.

---

## 9. What was deliberately NOT touched (preservation)

- All historical data on `main` of `mlb-slate`: 84 `slate_picks*.json`,
  `results.json`, `backtest/graded_picks.json`, `day_data.json`,
  `built_sections.json`, `k_props.json`, `k_savant_data.json`,
  `kalshi_markets.json`, `kalshi_matches.json`, `streaks_live.json`,
  `build-stamp.json`, all HTML pages, the `MLB Slate 7-29-26.xlsx`
  workbook, `artifacts/`, `docs/`, every `SESSION_STATUS_*.md`.
- All 94 BPP snapshots in `mlb-slate-archive/snapshots/`
  (`2026-07-22.tar.gz` → `2026-11-01.tar.gz`, ≈16 MB). Repo stays private.
- The GitHub Pages site `https://wysdomos.github.io/mlb-slate/` keeps
  serving the last built 2026-10-07 slate as a static historical reference;
  `pages-build-deployment` was left active so it can still deploy if a
  reviewed PR is ever merged.
- Both repositories, all branches, all Actions secrets, the Telegram bot and
  chat, the Firebase project, the deployed `auto_heal_webhook` function and
  its secrets, billing.
- Workflow files: unchanged. Re-enabling is a single API call per workflow.
- Historical results were **not** overwritten with offseason data: the
  publish guard had already prevented that for every run since 2026-10-08.

---

## 10. Items that could NOT be verified from the hibernation session

The session's API proxy blocked these endpoints and had no cloud
credentials. They are expected to be fine, but confirm them manually once:

| Check | How | Why it matters |
|---|---|---|
| Repository webhooks (both repos) | Settings → Webhooks | an external service hooked to `push`/`workflow_run` could still call out. None are known. |
| Actions secrets still present | Settings → Secrets and variables → Actions | they were not touched, but the list could not be read to prove it |
| Repo-level Actions setting | Settings → Actions → General | left as-is (Actions still enabled so manual dispatch remains possible). Optional harder lock: "Disable actions" for the repo during the offseason |
| Deployed healer matches `functions/main.py` and no Cloud Scheduler jobs exist | Firebase console → Functions; GCP console → Cloud Scheduler | the repo shows HTTP-only; only the console can confirm the deployed revision |
| Live site loads | open `https://wysdomos.github.io/mlb-slate/` and `/build-stamp.json` (should show `slate_date 2026-10-07`) | outbound `github.io` was blocked from the session |
| Device-side automation | the M5 Mac (`launchd`/`crontab`), iPhone Shortcuts, Perplexity/Comet tasks | anything that uploads an `.xlsx` or calls provider APIs directly is outside GitHub. An upload no longer starts a build, but a local script would still spend credits |
| Telegram is quiet | watch the chat for 24–48 h | end-to-end proof |

---

## Appendix A — Original schedule in Eastern Time (for restoration)

| Workflow | UTC cron | ET (EDT / EST) |
|---|---|---|
| daily.yml | `0 7` | 3:00 AM / 2:00 AM |
| daily.yml | `0 13` | 9:00 AM / 8:00 AM |
| daily.yml | `0 16` | 12:00 PM / 11:00 AM |
| daily.yml | `0 19` | 3:00 PM / 2:00 PM |
| daily.yml | `0 21` | 5:00 PM / 4:00 PM |
| daily.yml | `0 23` | 7:00 PM / 6:00 PM |
| daily.yml | `0 1` | 9:00 PM / 8:00 PM |
| daily.yml | `0 3` | 11:00 PM / 10:00 PM |
| grade.yml | `0 9` | 5:00 AM / 4:00 AM |
| archive.yml | `10 15` | 11:10 AM / 10:10 AM |

## Appendix B — Repo state at hibernation

| Item | Value |
|---|---|
| `mlb-slate` `main` HEAD | `9c12599ae5044ae6f037241e13e310cdb4492c7f` — "For The Record: graded latest slate" (2026-10-08 16:11 UTC) |
| last pipeline publish | `ba90a17` — "Auto-update: __PROJECTED_MODE__" (2026-10-08 02:22 UTC) |
| `mlb-slate-archive` `main` HEAD | `a65e424baeed31f53dfcb312ec902217d6d8c238` — "Archive BPP snapshot 2026-11-01" |
| total Actions runs, `mlb-slate` | 2,425 |
| total Actions runs, `mlb-slate-archive` | 103 |
| open PRs at hibernation | none in either repo |
| branches, `mlb-slate` | `main`, `claude/docs-housekeeping`, `codex/chapter-n-fixes`, `codex/chapter-o-headlines`, `codex/functions-deploy`, `codex/hrr-calibration`, `feat/kalshi-pipeline` |
| branches, `mlb-slate-archive` | `main` |
| `main` branch protection, `mlb-slate` | none configured |

*Hibernation performed 2026-11-02 via a reviewed Claude Code session. This
file is documentation only; it changes no runtime behaviour.*
