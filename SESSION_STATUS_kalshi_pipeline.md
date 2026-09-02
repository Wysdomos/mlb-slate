# SESSION_STATUS — K3a: Kalshi wired into the pipeline (no UI)

Branch: `feat/kalshi-pipeline`
Base: rebased onto `origin/main` immediately before the final push (see foot)
Status: implemented, verified on three CI runs, pushed. Branch only — no PR.

## Scope

- `b832d5e` — `daily.yml`: `Fetch Kalshi markets` step after all other
  fetches, before `build.py`. `continue-on-error: true` + the script's own
  always-exit-0 envelope: Kalshi can never break the slate build. Caps:
  `KALSHI_MAX_MARKET_PAGES=2, KALSHI_MAX_ORDERBOOK_CALLS=20,
  KALSHI_MIN_REQUEST_GAP=0.35, KALSHI_TIMEOUT=10`. `kalshi_markets.json` +
  `kalshi_matches.json` join the commit step.
- `930fb5d` — `build.py` step 2b: `build_kalshi_matches.py` after
  `build_day46`, every failure (incl. SystemExit plumbing) caught and logged.
- `0b4eab1` — `annotate_slate_picks()`: kalshi_ticker/side/price/state/
  quote_ts/ask_source/fee_band onto every pick (positional join —
  candidates are built from `slate["picks"]` in order and the match
  snapshot preserves it), null when unmatched; price only from an
  OPEN_TRADABLE quote; grading passthrough widened (`FEATURE_FIELDS`).
- `55e6295` — projected HR emitter carries `opp` (its own `Pitcher Team`):
  without it all 50 hr_board picks were `missing_game_teams` →
  candidate-unmatchable, and the highest-value rows could never get a
  price. Data-only; no rendering change (the only `build_day46.py` edit).
- `cd288f9` — adversarial-review fixes (16-agent pass, 12 confirmed):
  - **Carry-forward**: build_day46 regenerates slate_picks 8x/day, so the
    final post-game rebuild nulled every captured price right before the
    5AM grader read the archive. `build.py` now snapshots the dated
    archive before the rebuild (`.kalshi_prior_picks.json`), and annotate
    carries prior non-null prices onto the new picks (keyed:
    market/name/line/board/parlay_id/leg_role; duplicate keys consume
    first-match). Fresh OPEN_TRADABLE overwrites; settled states update
    `kalshi_state` but never erase the live-captured price; the carry
    layer also runs when the fetch failed.
  - **Stale gate**: a same-slate_date snapshot left by a killed fetch
    passed the matcher's date check with quote ages frozen at fetch time.
    The snapshot's own `generated_at` is now gated
    (`KALSHI_SNAPSHOT_MAX_AGE`, default 1800s).
  - `kalshi_quote_ts` was structurally null (matcher reads keys the
    fetcher never serializes); fresh prices stamp the snapshot's
    `generated_at`.
  - `PICKS_FILE` honored (preview.yml) and both slate_picks writes atomic.
- Temp report-only verify runner added and removed (`abbc3f8`/final).

No UI, no rail chip, no market column; `sync.py`, rendering, and Kalshi
formulas untouched; no auth or secrets — public endpoints only.

## Real-run numbers (CI verify runs 1-3, report-only, committed nothing)

```text
request_count       156  (run 1; runs 2-3 same caps, ~57-63s fetch wall)
markets fetched   4,496  (states at 11:22pm ET: STALE 1201, SETTLED 2740,
                          LISTED_UNOPENED 555)
match coverage (run 3, after the opp fix; 258 picks):
  matched=169  not_listed=89  ambiguous=0  no_quote=0
  HIT 15/15 · HR 56/60 · HRR 31/34 · TB 28/30 · TOTAL 13/15 · K 26/30
  NRFI 0/14 (series never fetched -- see found-not-fixed)
  2B/SB/OUTS_ALT/H_ALLOWED*/ER_ALLOWED 0 by design (no Kalshi series)
picks with a live price: 0 -- honest: every verify run happened post-game
  (11:22pm-12:20am ET; states on picks: SETTLED 141, STALE 28). Live
  pregame coverage remains UNMEASURED; the wired pipeline measures it
  automatically starting with the first daytime build after merge.
build wall-clock: with Kalshi 170.5s/126.2s vs without 156.3s/101.7s
  across runs -> delta ~+14 to +25s, dominated by the O(picks x markets)
  matcher (258 x 4,496); run-to-run streaks-fetch noise is large.
missing-file resilience: kalshi_markets.json deleted -> build.py exit 0,
  non-fatal envelope written, keys carried -- proven in CI twice and
  locally (T3).
```

### Request budget, said plainly

The dispatch target was ~60/run. **The caps cannot reach it**: the
dominant cost is one `/markets` listing per slate event per series
(uncapped count — 15 games x ~8 series), so requests scale with slate
size. Measured 156/run ≈ 1,250/day at 8 builds — gap-paced at 0.35s
(~1 minute of traffic per build). Reducing pages/orderbooks risks losing
slate coverage instead of bounding the walk. A true ceiling needs a
per-series fetch redesign in `services/kalshi_client/snapshot.py`
(flagged for K3b); tightening the existing caps further would have been
fake compliance and was not done.

## Day-lifecycle verification (local, stubbed markets — mechanics only)

```text
T1 fresh capture : live stub -> price 0.12 on the right pick, real quote_ts
T2 settled rebuild: full build.py rerun, market now SETTLED ->
                    price 0.12 KEPT, state updated to SETTLED, 243/243 keys
T3 fetch missing  : full rebuild, no kalshi_markets.json ->
                    price survives, keys present, "carried 1 prior price(s)"
T4 stale snapshot : 2h-old file refused ("age 7201s > 1800s"), price kept
T5 atomicity      : no .tmp residue
```

## Found, not fixed (K1-package surgery, flagged for K3b)

- `KXMLBRFI` is absent from `KNOWN_SERIES`, so NRFI can never match
  (0/14 every run). Adding it grows the request walk.
- 'no'-side quotes are unpricable: `NormalizedMarket` serializes no
  no-ask/yes-bid fields, so any pick mapping to kalshi_side 'no'
  (NRFI, TOTAL unders) would land OPEN_NO_QUOTE even when live.
- The 5PM-vs-9AM price question: carry-forward keeps the LAST live price
  (closest to lock). If pick-time-of-first-capture is ever wanted
  instead, flip the overwrite rule — one line, architect's call.

ast.parse + py_compile clean: build.py, build_day46.py,
build_kalshi_matches.py, backtest/backfill_grades.py.
