# SESSION_STATUS — HR1: projected HR board consensus restored

Branch: `fix/hr-board-consensus`
Base: `origin/main` at `7072e04` (`For The Record: graded latest slate`)
Status: implemented, verified, pushed. Branch only — no PR opened, per dispatch.

## Diagnosis, corrected before editing

The dispatch's diagnosis was right in substance and wrong in one detail —
in the direction of a **bigger** gap: `build_projected_hr_board()` computes
no votes AND emits no `SLATE_PICKS` at all. There is no projected emitter
with `consensus_max: 1` (line ~1505 is `build_tb_board`'s emitter); the
`consensus_max=1` HR rows in the graded store are Yard Sale parlay legs
from `emit_parlay_legs`. The workbook path (vote block 1588-1595, emitter
1618, `consensus_max: 7`) last ran 2026-07-29. Not the "smaller fix" case,
so the dispatched commit plan applied.

## The seven lenses in Projected Mode (probed on the live 9-01 data)

```text
1 score >= 70        LIVE   HR_Leaderboard carries Score, 80/80 rows
2 sim_raw >= 0.15    LIVE   BP_Batters HomeRunProbability, 80/80
3 To Hit HR >= 12    EXCLUDED -- resolves (80/80) but is NOT independent:
                     fetch_projected_mode.build_hit_rows writes
                     player_probs['hr'] with a fallback to the same matchup
                     HR probability that feeds lens 2, and on the 9-01 slate
                     it is byte-identical to HomeRunProbability for all 50
                     board rows (36 double-votes, 10 more in the 12-15%
                     band). Counting it would double-vote one signal at a
                     second threshold. Excluded, never substituted; the
                     value IS still emitted as to_hit_hr for calibration.
4 VulnScore >= 50    LIVE   build_vuln BPP fallback (PR 3b), 80/80, source='bpp'
5 park_hr >= 10      LIVE   Park_Factors 'HR %', 80/80
6 streak_fires       LIVE   streaks_live.json (committed daily) merged with
                     build-time hot_streaks.json; 48/80 board names carried
                     an entry on 9-01 (the lens fires on HR>=1 or Hit>=5)
7 bpp_proj_hr >= .15 LIVE IN THE PIPELINE, dataset-gated: bpp_summary.json
                     is written by daily.yml's fetch phase and untracked,
                     so it exists in every daily CI build (July-era
                     bpp_api_hr coverage proves it) and never in fetch-less
                     environments.
```

So `consensus_max` is **dynamic**: the count of lens datasets actually
loaded — **6 in the daily pipeline, 5 in a fetch-less build** — never the
workbook's hardcoded 7, and never a fabricated vote. A lens whose dataset
loaded but which cannot see a player simply does not vote (workbook
semantics). Thresholds untouched: 70, 0.15, 50, 10, streak, 0.15.

Segmentation note for the analyst: projected `hr_board` rows carry
`pick_source='projected'` and cmax 5/6; workbook history is
`pick_source='workbook'` with cmax 6/7. Segment by `pick_source` (or
`board` + era), not by cmax alone — the lens sets differ across eras even
where the counts coincide.

## Commits

- `d3b0fa4` — vote block in `build_projected_hr_board()`, 6 declared
  lenses, dataset-gated `consensus_max`. No HTML change: no vote column is
  rendered and the board is not reordered.
- `cd4bca6` — the board emits its 50 displayed rows, in display order,
  with the workbook emitter's field set plus `board: 'hr_board'`
  (`consensus, consensus_max, score, sim_hr, to_hit_hr, park_hr,
  bpp_api_hr, calibration_tier, chip_*`). Null/dash for absent inputs.
  (B1b is not yet merged to main; this emitter carries the same `board`
  field B1b adds to the other emitters, with no textual overlap.)
- Commit 3 is this verification record.

Not done, per the dispatch's DO-NOT list: no Yard Sale changes, no 4-lens
filter or anchor rule, no reordering, no tier-boundary change. The
`to_hit_hr` lens re-enters the vote block only if/when the per-player
probabilities feed resolves values distinct from `HomeRunProbability` —
an architect decision, one line here.

## Verification (live build of the 9-01 projected slate, scratch clone)

```text
base 7072e04 build exit 0 · branch cd4bca6 build exit 0
picks: base=192  branch=242   delta: {('HR', 'hr_board'): +50} and nothing else

HR rows: 60 = 50 hr_board + 10 yard-sale legs, 0 unclassified
hr_board consensus_max: {5: 50}          (local fetch-less build; CI runs 6)
vote distribution:      {0: 2, 1: 5, 2: 9, 3: 11, 4: 16, 5: 7}
lens fire counts:       score>=70: 41 · sim>=0.15: 36 · park>=10: 33
legs: consensus_max={1: 10}, all carry parlay_id+leg_role: True
hr_board rows carrying parlay_id or leg_role: 0   <- fully distinguishable

sample row: {"name": "Yordan Alvarez", "board": "hr_board", "consensus": 2,
 "consensus_max": 5, "score": 88.0, "sim_hr": "18.4%", "to_hit_hr": "18.40%",
 "park_hr": 7, "bpp_api_hr": null, "calibration_tier": null,
 "pick_source": "projected"}

built_sections.json: differing sections vs base: NONE -- HTML byte-identical
ast.parse OK: build_day46.py · py_compile exit 0
```

`bpp_api_hr`/`calibration_tier`/chips are null in this local build because
`bpp_summary.json` is fetch-phase-only; they populate in the daily CI build
exactly as they did in the July workbook era. Nothing was fabricated to
make them non-null here.

## Addendum — adversarial review pass: one code fix, four corrections

An 11-agent review (three dimension reviewers, one adversarial refuter per
finding) confirmed seven minor findings, none refuted except a preexisting
grader-bands item. Dispositions (sections above stand; this supersedes):

1. **`chip_hr_b` is no longer computed by the projected emitter.** Its
   consensus bands (`<=2` EDGE+, `5-6` FADE) are defined on the workbook
   board's 7-lens scale; fed this board's 6-lens CI votes, every unanimous
   6/6 row was emitted as `chip_hrb='FADE'` (reproduced by the reviewers
   with a populated `bpp_summary.json`: Michael Harris II, Jackson Chourio,
   Seiya Suzuki). Out-of-domain input — the chip now stays `None` from the
   projected board; the frozen formula in `shadow_chips.py` and the
   workbook call site are untouched. `chip_hra` takes no consensus input
   and is unaffected.
2. **Selection-rule disclosure the sections above lack:** the two eras'
   archives differ in *selection*, not just lens sets. The workbook emitter
   re-ranks 80 candidates by `(-votes, -score)` and keeps 50 — a
   consensus-censored sample (low-vote score-leaders dropped, high-vote
   rank-51-80 bats admitted). The projected emitter keeps the displayed
   score-top-50, uncensored — mandated by this dispatch's no-reordering
   scope. On 9-01 the two rules select materially different populations
   (9 of 50 rows differ). Cross-era bucket comparisons therefore mix
   selection effects with lens signal, and the default pooling in
   `backtest/calibration.py` / `grade_results.py` (both untouched here,
   bands preexisting) does not segment. Segment by `pick_source` AND
   remember the censoring difference.
3. **`board` does not reach the graded store until B1b merges** — main's
   `backfill_grades.py` still drops unknown fields; `pick_source`
   ('projected' vs 'workbook') is the segmentation key that exists in the
   store today. The analyst note above is corrected accordingly. (B1b's
   `FEATURE_FIELDS` passthrough picks `board` up with no further change.)
4. **Two lens-audit numbers corrected:** the park lens resolves **76/80**
   top-80 rows, not 80/80 — the four misses are Washington batters:
   `tn()` maps `WSH`→`WAS` while `PARK_BY_TEAM` is keyed by the raw
   `WSH` from Park_Factors game strings, so their `park_hr` is 0 and the
   lens cannot fire for them. **Pre-existing** — the workbook vote block
   has the identical lookup (found, not fixed: changing the lookup would
   change measurement parity with the workbook era; flagged for the
   architect). The streak-entry count under the build's `player_key`
   normalization is **51/80**, not the naive lowercase-match 48/80.

Re-verified after the chip fix (fresh scratch-clone build of 9-01):

```text
hr_board rows: 50 · consensus_max {5: 50} (fetch-less)
vote distribution unchanged: {0: 2, 1: 5, 2: 9, 3: 11, 4: 16, 5: 7}
chip_hrb: None on all 50 rows · chip_hra: unchanged
built_sections.json vs base: NONE differing -- HTML still byte-identical
ast.parse OK · py_compile exit 0
```

## Addendum 2 — recovered onto fix/hr-consensus-v2

`fix/hr-board-consensus` was abandoned after repeated rebase failures on
the owner's side: its real content was only ever the two files above, but
main's daily-build churn (16 generated files in the two-dot view) made
every rebase fight conflicts that had nothing to do with the change.
Recovery: fresh branch from `origin/main` (`5647e63`, B1b merged as #57),
then the HR1 delta for `build_day46.py` (diff `7072e04..fix/hr-board-consensus`)
applied 3-way onto main's B1b-bearing file — B1b cannot be reverted by
construction. Verified: one hunk, +67/-0, entirely inside
`build_projected_hr_board()`; the function is byte-identical to the
reviewed v1; `'board':` field count 13 (B1b's 12 + this emitter);
`ast.parse` + `py_compile` clean.

With B1b on main, the `board='hr_board'` discriminator now DOES reach
`backtest/graded_picks.json` via `FEATURE_FIELDS` — Addendum item 3 is
resolved; segment by `board` or `pick_source`.
