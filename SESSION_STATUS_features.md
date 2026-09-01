# SESSION_STATUS — B1b: feature passthrough, board discriminator, segmented HR analysis

Branch: `feat/grading-features`
Base: `origin/main` at `97d4ab2` (`Preview cleanup: feat/backfill-grading` — B1 merged as #56)
Status: implemented, verified, pushed. Branch only — no PR opened, per dispatch.

## Scope

- `ab075ca` — `backtest/backfill_grades.py`: `FEATURE_FIELDS` passthrough
  (`score, sim_hr, to_hit_hr, park_hr, bpp_api_hr, calibration_tier, board,
  board_rank, team, opp, game, pitcher`) copied verbatim onto every graded
  row, null when absent. `parlay_id, leg_role, correlation_type, same_game,
  pick_source` and the five `chip_*` fields were already carried since B1.
  The nightly append runs this same script, so it inherits the change.
- `4980e51` — `build_day46.py`: a `board` field on all 12
  `SLATE_PICKS.append` sites, from each emitter's own context.
- `dd4882a` — `backtest/graded_picks.json` re-backfilled from scratch with
  the widened schema (CI run `33476680646`, `github-actions[bot]`).
- `1747735` / `09d07f8` — temporary CI runner added, then removed.
- This report.

Deliberately not touched: `sync.py`, `daily.yml`, all Kalshi files, every
threshold and board ordering (this PR labels data; the analysis below acts
on nothing). No BallparkPal raw data read — `calibration_tier` is the
derived tier the builder already commits daily.

Idempotency note: the dispatch said "keep idempotency keyed on
(date, market, name, line)". That key was measured non-unique in B1
(470 legitimate repeats; see `SESSION_STATUS_backfill.md`) and the merged
store is idempotent **per date** — that unchanged semantic is what this
branch keeps.

## Board classification (commit 2)

Every emitter classified from its own context; none guessed:

```text
build_k_board          -> 'k_board'   (both appends: K rows AND its
                                       OUTS_ALT / H_ALLOWED_ALT alt lines)
build_tb_board         -> 'tb_board'
build_hr_board         -> 'hr_board'
build_oo5_board        -> 'hits_board' (both appends: its HIT and HRR rows;
                                        there is no separate HRR board)
build_totals_board     -> 'totals'
build_nrfi_board       -> 'nrfi'
build_sb_board         -> 'sb_board'
build_doubles_board    -> 'doubles_board'
emit_conviction_picks  -> 'conviction'
emit_parlay_legs       -> its sec_id verbatim: 'two-way-ks', 'traffic-jam',
                          'double-barrel', 'cruise-control', 'yard-sale'
```

The dispatch's example spellings (`yard_sale`, `traffic_jam`, `hrr_board`)
differ from the emitters' real identifiers; the emitters' own ids won.
`build_dfs_board` and `build_park_board` emit no picks — nothing to tag.

**Found while classifying, reported not papered over:** the projected-mode
builders (`build_projected_hr_board`, `build_projected_oo5_board`) emit no
`SLATE_PICKS` at all. Since projected mode became the permanent daily path,
**HR board and Hits board picks stopped being logged after 2026-07-29** —
every HR row from 7-30 onward is a Yard Sale parlay leg (~10/day). Wiring
pick emission into the projected builders is builder-side work outside this
dispatch; until it lands, `hr_board`/`hits_board` never appear in new data
and the HR analyses below cannot grow.

Verified on a real build (scratch clone, `python3 build.py`, slate 9-01):

```text
185 picks, WITHOUT board: 0
conviction 12 {'HRR': 12} · double-barrel 10 {'HIT': 10} · doubles_board 20
k_board 39 {'K': 30, 'OUTS_ALT': 9} · nrfi 14 · sb_board 20 · tb_board 30
totals 15 · traffic-jam 15 {'HRR': 10, 'ER_ALLOWED': 3, 'H_ALLOWED': 2}
yard-sale 10 {'HR': 10}
```

(No `hr_board`/`hits_board`/`two-way-ks`/`cruise-control` rows today: the
first two are the projected outage above; the parlay builders produced no
qualifying stacks on this slate.)

## Commit 3 — re-backfill, executed in CI again

The sandbox still has no route to statsapi.mlb.com (CONNECT 403 from the
egress proxy), so the same temporary-runner pattern as B1 ran the regrade in
Actions: reset the store, full regrade of all 56 dates, idempotency re-run,
commit. Log tail from run `33476680646`:

```text
-- 2026-09-01: 200 picks
  MLB Stats API empty -- falling back to balldontlie
balldontlie unavailable: HTTP Error 404: Not Found
   no box data returned -- skipping (rerun later)
wrote .../backtest/graded_picks.json: 12077 rows, 11497 gradable, 56 dates
--- idempotency re-run ---
57 slate files · 56 date(s) already backfilled
wrote .../backtest/graded_picks.json: 12077 rows, 11497 gradable, 56 dates
```

Today's slate correctly refused to grade (games not final, both sources
empty — nothing fabricated); the nightly picks it up tomorrow. The regrade
is purely additive vs B1: 11 more gradable rows (+7W/+4L, statsapi covering
rows the BDL-era July run had left pending) and **zero existing labels
flipped** (per-market W-L deltas are all additive: HR +0/+1, HRR +3/+1,
K +0/+1, HIT +3/+1, SB +1/+0, TB/2B/TOTAL/NRFI unchanged).

Feature coverage on the re-backfilled store (dispatch asked for score,
park_hr, calibration_tier):

```text
score             1150 rows (all HR)   park_hr   1150 (all HR)
calibration_tier   179 rows (all HR; only 2026-07-26..29 ever emitted it)
sim_hr / to_hit_hr / pitcher  1150     bpp_api_hr  268
board / board_rank  0  (new discriminators; populate from the next built slate)
team  10570        game  3646
```

## Analysis (commit 4) — store: 12,077 rows, 11,497 gradable, 56 dates

### 1. HR consensus buckets, segmented by consensus_max — never pooled

```text
consensus_max=6 era (6-15..7-22, 17 dates, 796 graded)
   1L  2-10    n=  12   16.7%
   2L 29-169   n= 198   14.6%
   3L 43-229   n= 272   15.8%
   4L 48-147   n= 195   24.6%   <- peak
   5L 16-81    n=  97   16.5%
   6L  3-19    n=  22   13.6%
consensus_max=7 era (7-24..7-29, 6 dates, 292 graded)
   1L  0-8     n=   8    0.0%
   2L 10-52    n=  62   16.1%
   3L  6-81    n=  87    6.9%
   4L 17-75    n=  92   18.5%   <- peak
   5L  3-33    n=  36    8.3%
   6L  1-6     n=   7   14.3%
consensus_max=1 (Yard Sale legs, 7-28..8-31, 35 dates, 304 graded)
   0L 53-251   n= 304   17.4%   (single bucket; legs carry consensus=0)
```

**The inversion survives segmentation.** It was not a pooling artifact:
each board era independently peaks at 4 lenses — cmax=6: 4L 24.6% vs
5L 16.5% (n=195/97); cmax=7: 4L 18.5% vs 5L 8.3% (n=92/36, small).
The pooled B1 numbers (4L 22.6% vs 5L 14.3%) were a blend of two real
inversions, not a mirage. HR consensus is non-monotonic in both eras;
whatever the 5th/6th lens adds, it subtracts HR hits.

### 2. HR by score bucket (live T0-T3 boundaries; n=1150)

```text
   78+  (T0)  15-69    n=  84   17.9%
   66-77 (T1) 50-271   n= 321   15.6%
   54-65 (T2) 86-474   n= 560   15.4%
   <54  (T3)  27-96    n= 123   22.0%
```

**Score does not separate.** T0-T2 sit within 2.5 points of each other, and
the sub-54 bucket — the tier the site tells readers to skip — has the
highest hit rate of all. On this window, score ranks HR outcomes worse than
consensus does (consensus at least shows a real 4L peak). A negative
finding, reported plainly.

### 3. HR by calibration_tier (BPP matchup tier; n=179, 7-26..7-29 only)

```text
   plus        5-69    n=  74    6.8%
   lean-plus   5-33    n=  38   13.2%
   neutral    10-25    n=  35   28.6%
   lean-minus  2-11    n=  13   15.4%
   minus       3-16    n=  19   15.8%
```

The archive question, answered from logged data: **inverted**. The tier
that marks the best matchups ('plus') hit at 6.8% — the worst bucket by
half — while 'neutral' more than doubled the board base rate. Four days of
coverage (the builder only emitted the field 7-26..7-29), so treat as a
red flag on the tier's direction, not a calibration; it cannot grow until
the projected HR board logs picks again.

### 4. HR by park_hr bucket (n=1150; range -22..+47, median +11)

```text
   <= -5%     34-122   n= 156   21.8%
   -4..+4%    24-172   n= 196   12.2%
   +5..+14%   37-222   n= 259   14.3%
   >= +15%    83-394   n= 477   17.4%
```

Also not monotonic: pitcher parks (<= -5%) produced the best HR hit rate in
this window and neutral parks the worst. Park HR context, as a standalone
cut on already-boarded bats, does not rank outcomes.

### 5. The same cuts for HRR and K, where fields exist

Score, calibration_tier, and park_hr have **zero coverage** outside HR —
the builder never wrote them on HRR or K picks — so only the consensus_max
segmentation exists there:

```text
HRR  cmax=5 era (6-15..7-22, 750 graded): 1L 70.3% · 2L 74.8% · 3L 67.9% · 4L 81.1%
     cmax=6 era (7-24..7-29, 274 graded): 2L 72.7% · 3L 65.4% · 4L 82.1% · 5L 75.0% (n=8)
     cmax=1 legs (7-26..8-31, 945 graded): 80.0%
K    cmax=5 era (6-15..7-22, 446 graded): 0L 41.4% -> 4L 75.4% -> 5L 92.9%  monotonic
     cmax=6 era (7-24..8-31, 1204 graded): 0L 36.3% -> 4L 69.2% -> 6L 77.8%  monotonic
     cmax=4 legs (74 graded): 90.9% at 2L · cmax=1 legs (19 graded): 94.7%
```

K consensus is cleanly monotonic in both eras — the K lens stack works.
HRR peaks at 4L in both eras but its selected parlay legs (80.0% at
consensus=0) nearly match the best board bucket: leg selection is doing the
work there, not lens count. K parlay legs (~91-95%) show the same strong
selection effect.

## Verification

```text
ast.parse OK: build_day46.py, backtest/backfill_grades.py   py_compile exit 0
BPP compliance OK (1 changed JSON/HTML files checked against 97d4ab2b874f)
board on a real build: 185/185 picks tagged, 0 unclassified
stub passthrough (7-26): score=81.0 sim_hr='18.6%' to_hit_hr='14.49%'
  park_hr=13 calibration_tier='neutral' board=None board_rank=None  (50/318 rows carry score)
changed files vs origin/main: SESSION_STATUS_features.md, backtest/backfill_grades.py,
  backtest/graded_picks.json, build_day46.py
```

## Not done / for the next builder

- No PR opened; branch pushed only, per dispatch.
- `board_rank` is passed through but no emitter writes it yet — always null.
- The projected HR/oo5 builders still emit no picks; until that lands, the
  HR analyses above are frozen at 7-29 and `hr_board`/`hits_board` stay
  absent from new rows. That decision (and whether the 5th/6th HR lens,
  the score tiers, and the 'plus' matchup tier survive their inversions)
  belongs to the architect.
