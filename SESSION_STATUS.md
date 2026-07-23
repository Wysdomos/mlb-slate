# SESSION STATUS — 2026-07-23 — Claude Code

## 1. WHAT I DID
- PR #16 `feat/healer-visibility` — **MERGED + DEPLOYED**. Healer now notifies on decline/log-fetch/zip-parse exits; added HMAC-gated Gemini `selftest` branch; daily.yml webhook step now checks HTTP status.
- PR #17 `feat/healer-retry` — **MERGED** (deployed together with #18). Shared `gemini_generate()` helper retries transient (503/429) Gemini errors only; permanent errors still fail fast.
- PR #18 `feat/healer-alert-noise` — **MERGED + DEPLOYED**. Logs-404 race now retried 3× then returns 200+🔍 (benign) instead of a false "safety net down" 500 alert; real fetch failures stay 500+⚠️.
- PR #19 `feat/streaks-per-game` — **MERGED**. Rewrote `fetch_streaks_mlb()` to per-game `/game/{pk}/boxscore` and flipped source priority to statsapi-primary. No deploy needed (runs in the Actions "Fetch live streaks" step; takes effect next scheduled build).
- Created **private repo `Wysdomos/mlb-slate-archive`** (Chapter B2 steps 1–3): `.github/workflows/archive.yml`, README, `.gitignore` committed to its `main`. NOT a PR in this repo; the public repo is untouched by that work.
- Chapter D discovery (this session, no code, no PR): analyzed the merged `services/bpp_client` snapshot to map BallparkPal API coverage of the 6 `day_data.json` BPP tabs, plus 4 follow-up gap questions.
- Earlier in session (all **MERGED**): #9 backtest-foundation, #10 site-fixes-1 (attribution + freshness gate; streaks Fix-1 was pulled OUT and later shipped properly as #19), #11 odds-api-fallback, #14 tip-attribution. (#12/#13/#15 are Codex PRs.)

## 2. RAW VERIFICATION OUTPUT
*(BallparkPal projection VALUES omitted per the report rule — field names, market names, and counts only. Non-BPP command output is verbatim.)*

Healer Gemini self-test (deployed function, valid HMAC), run twice:
```
secret loaded, length: 64
HTTP 500
❌ Healer self-test FAILED: ServerError: 503 UNAVAILABLE. {...'message': 'This model is currently experiencing high demand...'...}
```
→ 503 = TRANSIENT (model overloaded). Auth succeeded → GEMINI_API_KEY (v2) is VALID, NOT revoked; `gemini-3.5-flash` resolves. (This is why PR #17 retry exists.)

Healer diagnostics (deployed function):
```
bad signature (sha256=deadbeef)         -> HTTP 401  "Unauthorized or misconfigured webhook."
valid signature, run_id 29940016559     -> HTTP 200  "No Python file found in traceback."
```

Streaks before/after (live MLB Stats API, branch feat/streaks-per-game):
```
BEFORE (schedule-hydrate): 92 games, 0 batters, 0 active streaks
AFTER  (per-game):         92 games fetched, 0 failed, 406 batters, 212 active streaks
end-to-end main() (statsapi-primary): wrote 212 players, 212 active streaks
runtime: 51.5s (step timeout is 6 min)
ast OK
```

Firebase deploys (both):
```
✔  functions[auto_heal_webhook(us-central1)] Successful update operation.
✔  Deploy complete!
```

Archive repo:
```
gh secret list --repo Wysdomos/mlb-slate-archive  ->  (empty; no secrets set — BPP_API_KEY is human-only)
git push -u origin main  ->  new branch main created, 3 files
```

Chapter D — BPP API coverage findings (metadata/counts only):
```
projection_probabilities market catalog (markets.json): 22 markets total
  6 pitcher markets: Walks, Strikeouts, Earned Runs, To-Record-Win, Hits Allowed, Outs
  -> NO "Pitcher Home Runs Allowed" market (present only as averages.pitchers[].homeRunsAllowed point value)
  -> NO stolen-base ATTEMPT market (only "Batter Stolen Bases" = successes; averages has stolenBaseSuccesses only)
  -> all probability markets are OVER/UNDER threshold lines; NO exact-count distribution buckets
Distribution buckets (Runs0-20, HomeRuns0-5, RunsInning1-9) and batter/pitcher HANDEDNESS:
  -> MISSING from every endpoint (games, averages, probabilities, parkfactors, parkfactors_hitters, matchups)
  -> these currently come from the uploaded workbook, not the API
First-5 splits: PRESENT as point values -> projection_averages.data.teams[].runsFirstFive
  and .winFirstFiveProbability; RunsFirstInningPct = probabilities mkt_4 "Runs First Inning" side=over probability
Q3 test — sum(projection_averages.batters[]) per team vs BP_Teams (34 game-team pairs, 2026-07-22 snapshot):
  Doubles:    MATCH 2/34,  DIFF 32/34
  Strikeouts: MATCH 0/34,  DIFF 34/34
  Walks:      MATCH 0/34,  DIFF 34/34
  direction always negative (sum UNDERSHOOTS BP_Teams by ~1-2.5%); NOT an exact reproduction
```

## 3. WHERE I STOPPED AND WHY
- Chapter D is a **discovery task only** — complete, no code written. Next action is an architect decision (see §6) on how to source the workbook-only columns (handedness, distribution buckets) if the workbook is to be replaced.
- Archive repo: steps 1–3 done; **verification (manual "Run workflow" first-run) is pending a human** because `BPP_API_KEY` must be set in the archive repo by the developer (never by me).
- Healer self-test has not yet returned a green pass — blocked only by Google's transient 503 overload, not by our code/key. Re-run when Google capacity frees up.

## 4. SURPRISES AND DEVIATIONS
- **`BPP_API_KEY` UNSET locally** → I could not do a live "today" (2026-07-23) BPP pull. Used the merged client's real cached **2026-07-22 snapshot** instead; the response schema is date-invariant, so it fully answers the discovery. This is a deviation from "pull today."
- **The BPP API does NOT contain the distribution buckets or handedness** the `day_data.json` BPP tabs carry. If Chapter D assumed the merged client could replace the workbook wholesale, that assumption is wrong: buckets (exact-count Runs/HomeRuns/RunsInning), handedness, StolenBaseAttempts, pitcher StolenBasesAllowed, win/loss margins, venue name, and the venue-level stadium/weather split all have no API source.
- **Summing `batters[]` does NOT reproduce BP_Teams exactly** — it undershoots by ~1–2.5% on every one of 34 team-games (BP_Teams includes more than the 9 starters, or is modeled separately). The "obvious" derivation is an approximation, not a match.
- **Streaks: the OLD `fetch_streaks_mlb()` returned 0 batters** (MLB bulk `hydrate=boxscore` over a date range yields empty box objects). Confirmed with a before/after BEFORE flipping priority, per the handoff's gate. Per-game fetch fixed it (0 → 212).
- **Healer key was NOT revoked** (the July-13 worry): the self-test's 503 proves the key authenticates. So no key rotation was needed.
- **`gcloud` is absent on this machine** — the earlier gcloud-based healer diagnostics could not run (used `firebase functions:log` + signed curl instead). `firebase` CLI is present.
- Left one **stash** (`stash@{0}`, pre-existing dirty build artifacts). Safe to drop — regenerated build outputs, not hand-authored.
- Minor: `/tmp` subdirectories hit a sandbox group-permission error; wrote dump files to `/tmp` top-level instead.

## 5. LOCAL STATE
- Branch: `main` — HEAD `5d46adb` (before this SESSION_STATUS commit).
- `git status --short`: clean (empty) aside from this new file.
- Stash: `stash@{0}: On feat/healer-visibility: stale build artifacts parked before healer-visibility deploy 2026-07-23` — **safe to drop** (build artifacts, regenerated by builds).
- Env (names only): `BPP_API_KEY`, `ODDS_API_KEY`, `BDL_KEY`, `GEMINI_API_KEY`, `WEBHOOK_SECRET`, `TELEGRAM_BOT_TOKEN` — all **UNSET** locally. Tooling: `firebase` present, `gcloud` absent.
- Deployed Firebase function `auto_heal_webhook` (project `wysdomos-slate-healer`, us-central1) currently reflects merged PRs #16 + #17 + #18.

## 6. OPEN QUESTIONS FOR THE ARCHITECT
- Handedness (`BatterStand`, `PitcherHand`, SP `Throws`) has **no BPP source**. OK to pull it from MLB Stats API (`people` → `batSide`/`pitchHand`) in Chapter D?
- BP_Teams `Doubles`/`Strikeouts`/`Walks` reproduce only to ~1–2.5% (always low) by summing `batters[]`. Accept that approximation, or keep the workbook as the source for team-level columns?
- Exact-count distribution buckets (Runs/HomeRuns/RunsInning) have **no API source** at all. Keep the workbook for those columns, or drop them from the 63 consumed columns?
- Archive repo is ready for its first manual `workflow_dispatch` verification run once you've set `BPP_API_KEY` there — want me to walk through it after you confirm the secret is set?
