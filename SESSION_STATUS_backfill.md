# SESSION_STATUS — B1: box-score priority, graded backfill, nightly append

Branch: `feat/backfill-grading`
Base: `origin/main` at `a73f978` (`Preview cleanup: infra/pr-previews`)
Status: implemented, verified, pushed. Branch only — no PR opened, per dispatch.

## Scope

- `892960d` — `grade_results.py`: MLB Stats API becomes the primary box-score
  source; `fetch_bdl` and `BDL_KEY` kept as fallback only (crash or zero
  players). The `source` log line now reports what was actually used
  (`MLB Stats API` / `balldontlie` / `none`), not which key exists.
- `c9da5ad` — `backtest/backfill_grades.py`: same priority flip in
  `fetch_box()`; per-date idempotency hardening; CLI date arguments.
  Plus a temporary Actions runner (see Deviations).
- `9ba3447`, `ae45bbc` — `backtest/graded_picks.json` data commits, authored
  by `github-actions[bot]` from runs of that temporary workflow
  (2026-07-26 verify run, then the full window). 2,660 → 12,077 rows.
- `7da2c46` — `grade.yml`: nightly append step wired in, non-fatal,
  idempotent; `graded_picks.json` joins the existing commit step.
- `d169c02` / `19185ac` — temp runner trigger reworked, then the whole
  temp harness removed. Net branch diff touches exactly:
  `grade_results.py`, `backtest/backfill_grades.py`,
  `backtest/graded_picks.json`, `.github/workflows/grade.yml`.

Deliberately not touched: `build_day46.py`, `sync.py`, `daily.yml`, all
Kalshi files, every threshold and formula (this PR only labels data), the
`0 9 * * *` cron and `for-the-record` concurrency group, and all BallparkPal
data paths — outcomes come from MLB Stats API box scores only, with
balldontlie demoted to fallback (kept per dispatch, not removed).

## Deviations from the dispatch, with evidence

### The backfill executed in GitHub Actions, not the sandbox

This build sandbox has no route to statsapi.mlb.com — the egress proxy
denies the CONNECT outright:

```text
FAIL: URLError <urlopen error Tunnel connection failed: 403 Forbidden>
proxy status: "gateway answered 403 to CONNECT (policy denial)" host=statsapi.mlb.com:443
```

`backtest/backfill_grades.py`'s own docstring names the venue for this case:
"Runs where the network is open (M5 or GitHub Actions) -- NOT the sandbox."
So a temporary, branch-only workflow ran the backfill in Actions and
committed only `backtest/graded_picks.json` back to this branch:

- run `33473487453` — verify pass on `2026-07-26` + idempotency re-run
- run `33473593991` — full remaining window (44 dates) + idempotency re-run

Both harness files (`backfill-oneshot.yml`, `backtest/BACKFILL_DATES`) were
removed in `19185ac` once the data landed. One wrinkle worth recording:
`workflow_dispatch` by filename returns 404 for a workflow that exists only
on a non-default branch, so the runner was converted to a push trigger gated
on the dates file (`d169c02`). All outcome data in the store came from real
CI-fetched box scores; nothing was fabricated locally.

### Idempotency key: per-date, not (date, market, name, line)

The dispatch said to key on `(date, market, name, line)`. Measured against
the committed slates, that tuple is **not unique**:

```text
470 duplicate (market,name,line) keys across all slates
('slate_picks_7-26.json', ..., [(('K', 'Jacob Misiorowski', 'O 5+'), 4), ...])
existing store dupe keys: 5
```

Doubleheaders and parlay legs legitimately share a board pick's market/name/
line, so dropping row-key "duplicates" would silently lose real rows.
Implemented instead: a date recorded in `store['dates']` is skipped, and
(re)grading a date replaces its rows wholesale — a strictly stronger
no-duplication guarantee with zero row loss. The rejected key is documented
in `c9da5ad`'s message and in the code comment.

### Window correction

The dispatch window "2026-06-23 through 2026-08-31" contains no committed
slate files for 6-23..7-8, 7-12..7-16, or 7-23. The actual ungraded set was
**45 dates, 2026-07-17 .. 2026-08-31, 9,417 picks** — all of them now graded.

## Verification

### a. Commit 0 — statsapi primary, log line proves the source used

From run `33473593991`, with `BDL_KEY: ***` present in the step env:

```text
Grading 7-26 (API date 2026-07-26, source MLB Stats API): 318 picks from slate_picks_7-26.json, 0 homers from MLB Slate 7-29-26.xlsx
games: 15 totals, 15 first-inning; keys=['ARI@WSH', 'ATL@BAL', ...]
Graded 7-26: HR board 9-41 (+API). Wrote /tmp/results_verify.json
```

Offline stub matrix (fetchers monkeypatched, all three branches exercised):

```text
scenario 1 statsapi has players, BDL_KEY set -> source MLB Stats API, calls [statsapi, games]
scenario 2 statsapi empty, BDL_KEY set       -> source balldontlie,  calls [statsapi, bdl, games]
scenario 3 statsapi empty, no key            -> source none,          calls [statsapi, games]
```

### b. Commit 1 — one-date backfill verified on 2026-07-26

CI log (run `33473487453`):

```text
56 slate files · 11 date(s) already backfilled
-- 2026-07-26: 318 picks
   graded 315/318
wrote .../backtest/graded_picks.json: 2978 rows, 2758 gradable, 12 dates
--- idempotency re-run, same date ---
56 slate files · 12 date(s) already backfilled
wrote .../backtest/graded_picks.json: 2978 rows, 2758 gradable, 12 dates
```

Rows appended (2,660 → 2,978), not overwritten; re-running the same date
changed nothing. Chip fields survive into the store — tier spread on the
7-26 rows: `chip_k_a EDGE+ ×5 / NEUTRAL ×25`, `chip_hra NEUTRAL ×43 /
FADE ×6`, `chip_hrb NEUTRAL ×49`, `chip_hit_a EDGE+ ×27 / NEUTRAL ×21`.
The 3 ungraded picks are all Michael Harris (absent from the box score) —
`win: null`, never fabricated. Sample graded row:

```json
{"date": "2026-07-26", "market": "HR", "pick_source": "workbook",
 "name": "Munetaka Murakami", "line": "Ov 0.5", "win_at": 1,
 "consensus": 6, "consensus_max": 7, "win": true, "got": "HR",
 "chip_hra": "NEUTRAL", "chip_hrb": "NEUTRAL", "chip_hit_a": null,
 "chip_k_a": null, "chip_hall_a": null, ...}
```

Offline mechanics test additionally covered the pathological half-state
(rows present, date missing from the dates map): the run logged
`replacing 318 existing rows for 2026-07-26` and the count stayed 2,978.

### c. Commit 2 — full window backfilled, zero failed dates

Run `33473593991`, sequential with the existing `time.sleep(1)` between
dates, log tail:

```text
-- 2026-07-17: 245 picks ... graded 232/245
-- 2026-07-18: 254 picks ... graded 223/254
   (... 44 dates ...)
-- 2026-08-31: 181 picks ... graded 180/181
wrote .../backtest/graded_picks.json: 12077 rows, 11486 gradable, 56 dates
--- idempotency re-run ---
56 slate files · 56 date(s) already backfilled
wrote .../backtest/graded_picks.json: 12077 rows, 11486 gradable, 56 dates
```

Arithmetic reconciles exactly: 2,660 existing + 318 (7-26) + 9,099
(remaining 44 dates) = 12,077; the pre-run survey counted 9,417 ungraded
picks = 318 + 9,099.

### d. Commit 3 — nightly append wired, non-fatal, cron untouched

```text
steps: [checkout, setup-python, 'Install dependencies',
        'Grade results and build the record page',
        'Append graded picks to the backtest store',      <- new
        'Commit record.html + results.json',
        'Telegram alert on failure', 'Notify Firebase Auto-Healer on Failure']
append step continue-on-error: True
cron: [{'cron': '0 9 * * *'}]                              <- unchanged
concurrency: {'group': 'for-the-record', 'cancel-in-progress': False}
git add record.html results.json backtest/graded_picks.json
```

With no arguments the step grades every not-yet-graded committed slate —
normally just yesterday's, and it self-heals any date a prior run missed
(a date with no final box scores is skipped and retried the next night).

### e. Compliance and syntax gates

```text
BPP compliance OK (1 changed JSON/HTML files checked against a73f978d572d)
ast.parse OK: grade_results.py, backtest/backfill_grades.py
py_compile exit 0
changed files vs origin/main: .github/workflows/grade.yml,
  backtest/backfill_grades.py, backtest/graded_picks.json, grade_results.py
```

## Statistics (full graded set: 12,077 rows, 11,486 gradable, 56 dates)

### 1. Per-market hit rates

```text
market             W     L     n   hit%  pend
HRR             1478   487  1965   75.2   154
K                966   776  1742   55.5    39
HIT              951   498  1449   65.6   139
HR               231  1160  1391   16.6    87
TB               456   637  1093   41.7    37
2B               206   876  1082   19.0    40
SB               193   853  1046   18.5    74
TOTAL            423   350   773   54.7     9
NRFI             404   314   718   56.3     7
H_ALLOWED         58    23    81   71.6     1
ER_ALLOWED        28    29    57   49.1     1
H_ALLOWED_ALT     38     8    46   82.6     1
OUTS_ALT          30     5    35   85.7     2
OUTS               3     5     8   37.5     0
```

### 2. Consensus buckets (HR, HRR, K, HIT; buckets n>=15)

```text
-- HR (graded n=1391)
   0 lenses:   53-251  n= 304   17.4%
   1 lenses:    2-18   n=  20   10.0%
   2 lenses:   39-220  n= 259   15.1%
   3 lenses:   49-310  n= 359   13.6%
   4 lenses:   65-222  n= 287   22.6%
   5 lenses:   19-114  n= 133   14.3%
   6 lenses:    4-25   n=  29   13.8%
-- HRR (graded n=1965)
   0 lenses:  767-202  n= 969   79.2%
   1 lenses:   86-44   n= 130   66.2%
   2 lenses:  246-84   n= 330   74.5%
   3 lenses:  273-133  n= 406   67.2%
   4 lenses:   99-22   n= 121   81.8%
-- K (graded n=1742)
   0 lenses:  293-454  n= 747   39.2%
   1 lenses:   91-94   n= 185   49.2%
   2 lenses:  124-53   n= 177   70.1%
   3 lenses:  135-58   n= 193   69.9%
   4 lenses:  229-96   n= 325   70.5%
   5 lenses:   73-15   n=  88   83.0%
   6 lenses:   21-6    n=  27   77.8%
-- HIT (graded n=1449)
   0 lenses:  315-138  n= 453   69.5%
   1 lenses:   78-52   n= 130   60.0%
   2 lenses:  221-109  n= 330   67.0%
   3 lenses:  239-167  n= 406   58.9%
   4 lenses:   93-28   n= 121   76.9%
```

**The HR inversion HOLDS and sharpens.** The prior sample showed 4 lenses
25.0% vs 5 lenses 16.7% at n=516; on 2.7× the data it is 4 lenses **22.6%**
(n=287) vs 5 lenses **14.3%** (n=133) and 6 lenses 13.8% (n=29). HR
consensus is non-monotonic overall (0 lenses 17.4% beats 3 lenses 13.6%).
K consensus, by contrast, is close to cleanly monotonic (39.2% → 83.0%
from 0 to 5 lenses) — the K lenses are earning their keep; the HR lens
stack above 4 is actively mislabeling its best tier.

### 3. Chip tier hit rates (Chapter E calibration; 37 chip slates, 7-26..8-31)

```text
-- chip_hra   HR-A Avoidance Tax        (tagged=179, all HR rows)
   EDGE+      never fired (0 rows in 37 slates)
   NEUTRAL    24-130  n= 154   15.6%
   FADE        1-24   n=  25    4.0%
-- chip_hrb   HR-B Contextual Spike     (tagged=179, all HR rows)
   EDGE+      never fired (0 rows)
   NEUTRAL    25-152  n= 177   14.1%
   FADE        0-2    n=   2    0.0%
-- chip_hit_a HIT-A Contact Floor       (tagged=162, all HIT rows)
   EDGE+      62-23   n=  85   72.9%
   NEUTRAL    49-28   n=  77   63.6%
-- chip_k_a   K-A Volume Cap Refiner    (tagged=1001, all K rows)
   EDGE+      12-4    n=  16   75.0%
   NEUTRAL   468-500  n= 968   48.3%
-- chip_hall_a HALLOWED-A Contact Quality Reversal
   never tagged a single row in any of the 37 chip slates
```

Findings, including the dead formulas (a dead formula is a finding):

- `chip_hit_a` is live: EDGE+ 72.9% vs NEUTRAL 63.6% (+9.3 pts, n=85/77).
- `chip_k_a` EDGE+ is directionally strong (75.0% vs 48.3%) but fires
  rarely — n=16 across 37 slates. Note its NEUTRAL (48.3%) sits below the
  all-K rate because the chip only tags a subset of K rows.
- `chip_hra`'s value is its FADE arm: 4.0% (1-24) vs NEUTRAL 15.6% — a
  real avoid signal. Its EDGE+ arm has never fired.
- `chip_hrb` is dead as calibrated: EDGE+ never fired, FADE fired twice.
- `chip_hall_a` is completely dead — its inputs never all resolve, so it
  never returns a tier at all.
- Structural: no formula in `shadow_chips.py` ever returns plain `EDGE`
  (`TIER_ORDER` lists it; every formula returns EDGE+/NEUTRAL/FADE), so
  the EDGE tier is unreachable by construction.

No threshold or formula was changed — these are labels for the
calibration review to act on.

### 4. Dates that could not be graded

**None.** All 56 committed slate dates are in the store. The 591 ungraded
rows (of 12,077) are individual picks, not dates: players absent from the
final box score (scratched/DNP) and picks tied to games that never went
final that day — e.g. `2026-07-21` has 37 pending rows and its log shows 13
finals against a 15-game slate (two postponements); `2026-06-18` (36) and
`2026-07-18` (31) are the same shape. Every such row carries `win: null`
per AGENTS.md rule 2 — missing result is null, never a loss.

## Not done / for the next builder

- No PR opened; branch pushed only, per dispatch.
- The nightly append retries postponed-game rows only when their whole date
  was skipped; a date already stored keeps its `null` rows even if a
  suspended game completes later. Regrading such a date is a manual
  `delete-the-date` + re-run today; acceptable for now, worth a flag later.
- `chip_hall_a` (dead) and the unreachable `EDGE` tier are calibration
  questions for the architect, not code fixes here.

## Addendum — adversarial review pass, five confirmed findings, four fixed

Before the final push, a 10-agent review (five dimension reviewers over the
branch diff, one adversarial refuter per finding) confirmed five minor
findings and refuted none. Dispositions:

1. **CLI date args were silently ignored** when bogus, wrong-format (`6-15`
   instead of ISO), or already graded — the run exited 0 looking successful.
   Fixed: an explicit already-graded date now prints
   `already backfilled -- skipped (delete the date from "dates" ... to regrade)`,
   and any CLI date matching no committed slate prints
   `!! no committed slate file has slate_date <arg> (dates are ISO YYYY-MM-DD)`.
2. **The wholesale-replace path could destroy good grades**: regrading a date
   on a day statsapi returned no players (while `fetch_games` still returned
   totals) replaced fully-graded rows with `win: null` rows and re-marked the
   date done. Fixed: the replace now requires player data in the fresh box;
   otherwise existing rows are kept, the date stays un-done, and the nightly
   retries it. Verified: the degraded-regrade scenario now keeps all 232
   non-null wins for `2026-07-17`; the healthy-regrade path still replaces
   245 rows wholesale and re-marks the date.
3. **Dead try/except in `fetch_box()`**: both underlying fetchers catch their
   own exceptions and return `{}`, so the `crashed` handlers could never fire
   and their promised log lines could never appear. Fixed: handlers removed;
   the comment now states that emptiness is the failure signal. The matching
   try/except in `grade_results.py` is deliberately kept — the dispatch
   prescribed mirroring `fetch_streaks.py main()`, and there it is harmless
   insurance around a function whose internals may drift.
4. **Non-atomic final write**: a crash mid-`json.dump` could commit a
   truncated `graded_picks.json` via the non-fatal nightly step, silently
   disabling the append until manually repaired. Fixed: write to
   `graded_picks.json.tmp` then `os.replace` (atomic on the same filesystem).
5. **This report undercounted the diff**: "net branch diff touches exactly"
   four files — it is five, including `SESSION_STATUS_backfill.md` itself
   (and this addendum's fixes make `backtest/backfill_grades.py` differ from
   what commits `c9da5ad`..`dd13102` alone contained). Corrected here rather
   than by editing the sections above, per the report standard.

Re-verified after the fixes:

```text
ast.parse OK: backtest/backfill_grades.py    py_compile exit 0
scenario A degraded regrade : rows kept, non-null wins 232 -> 232, date left un-done
scenario B explicit done date: visible skip line printed, store unchanged
scenario C bogus CLI dates   : loud !! warning per arg, store unchanged
scenario D atomic write      : no .tmp residue; healthy regrade still replaces 245
```

The store itself (`12077 rows, 11486 gradable, 56 dates`) is untouched by
this addendum's fixes; the data-integrity and dispatch-compliance reviewers
returned no findings against it.
