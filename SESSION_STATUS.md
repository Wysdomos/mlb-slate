# SESSION STATUS - 2026-07-26 - Codex

## Chapter I - Parlay Rebuild

- Branch: `codex/chapter-i-parlays`
- Base: `origin/main` at `2c1ee69e15cb`
- Ordered commits landed:
  1. `2f49997 Remove stale parlay board content`
  2. `40a8cec Add correlation-based Strikeout Stack`
  3. `cdeb443 Add Traffic Stack parlay board`
  4. `9104adb Add K-anchor parlay board`
  5. Pending commit: emission, grading, calibration, tests, and this report
- Removed hardcoded static parlay/combo content from `build_combos_k()`, `build_combos_hrr()`, and `build_parlays()`.
- Removed the false Projected Mode badge text `K combos rebuilt from projected starter rows.`
- Added executable parlay guards in `parlay_rules.py`.
- Added measurable parlay leg emission with `parlay_id`, `correlation_type`, `leg_role`, and existing `pick_source`.
- Added grading/copy-through for `OUTS`, `H_ALLOWED`, and `ER_ALLOWED` legs.
- Added calibration bucketing by `correlation_type`.
- Did not touch `fetch_projected_mode.py`, `tools/check_bpp_compliance.py`, `tools/projected_publish_guard.py`, `shadow_chips.py`, or SSJ/Zone logic.
- Did not modify historical `slate_picks*.json` or `backtest/graded_picks.json`.

## Verification

a. Combo-builder grep: zero hardcoded player names remain in any combo/parlay builder:
```text
awk '/CORRELATION PARLAY BOARDS/,/CONVICTION BOARD/' build_day46.py | rg -n "Will Warren|Freddy Peralta|Yamamoto|Flaherty|Elly De La Cruz|Sal Stewart|James Wood|Jacob Wilson|Paul Skenes|Mikolas|DLC|Wheeler"
exit 1, empty output
```

b. False projected badge is gone:
```text
rg -n "rebuilt from projected starter rows" build_day46.py
exit 1, empty output
```

c. Rule 1 enforced - nested same-player pair rejected:
```text
python3 tools/test_parlay_rules.py
rejected: nested same-player batter legs
```

d. Rule 2 enforced - hits-allowed plus earned-runs on one pitcher rejected:
```text
python3 tools/test_parlay_rules.py
rejected: duplicate pitcher-side traffic legs
```

e. HR leg cannot anchor or be top-conviction:
```text
python3 tools/test_parlay_rules.py
rejected: HR cannot anchor a parlay
rejected: HR cannot be the top-conviction leg

generated parlay artifact check:
HR anchor legs []
```

f. No 2B or SB leg appears in any parlay:
```text
generated parlay artifact check:
2B/SB parlay legs []
```

g. All three boards render in both modes:
```text
Projected Mode from current day_data.json:
combos-k bytes 632 empty True
combos-hrr bytes 3585 empty False
parlays bytes 582 empty True

Workbook-backed temp build from /tmp/MLB_Slate_7-26-26.xlsx:
combos-k bytes 632 empty True
combos-hrr bytes 656 empty True
parlays bytes 582 empty True
```
Workbook note: the repo workbook is dated 2026-07-25 and is stale on 2026-07-26, so I copied it to `/tmp/MLB_Slate_7-26-26.xlsx` to exercise workbook-backed rendering without changing workbook contents or tracked files. That workbook lacks `Park_Factors`, so Traffic Stack correctly rendered empty there.

h. Empty state renders honestly when nothing qualifies:
```text
Projected Mode:
combos-k empty True
parlays empty True

Workbook-backed temp build:
combos-k empty True
combos-hrr empty True
parlays empty True
```

i. `parlay_id`, `correlation_type`, `leg_role` present in `slate_picks` and after backfill:
```text
Generated Projected Mode slate_picks:
total picks 114
parlay leg picks 15
correlations ['both_sides', 'run_environment']
roles ['satellite']
markets ['ER_ALLOWED', 'HRR', 'H_ALLOWED']
missing fields 0

Temp backfill copy with final box-score date:
python3 backtest/backfill_grades.py
1 slate files · 0 date(s) already backfilled
-- 2026-07-25: 114 picks
games: 15 totals, 15 first-inning; keys=['ARI@WSH', 'ATL@BAL', 'CHC@PIT', 'CIN@STL', 'CLE@TB', 'COL@MIL', 'HOU@CWS', 'KC@DET', 'LAA@SF', 'LAD@NYM', 'NYY@PHI', 'OAK@MIN', 'SD@MIA', 'SEA@TEX', 'TOR@BOS']
   graded 76/114

wrote /private/tmp/chapteri-backfill-final/backtest/graded_picks.json: 114 rows, 76 gradable, 1 dates
graded rows 114
graded parlay legs 15
parlay fields present 15 / 15
correlations ['both_sides', 'run_environment']
roles ['satellite']
```
Backfill note: the live slate is 2026-07-26 and games were not final, so a temp-only copy of generated picks was dated 2026-07-25 to exercise the existing final box-score path. No tracked historical JSON was changed.

j. `calibration.py` buckets by `correlation_type`:
```text
python3 backtest/calibration.py
wrote /private/tmp/chapteri-backfill-final/backtest/CALIBRATION.md (3974 bytes)

rg -n "Parlay correlation buckets|both_sides|run_environment|same_pitcher_k_outs|anchor" backtest/CALIBRATION.md
108:## Parlay correlation buckets
112:| both_sides | 3-3 | 6 | **50.0%** | 19%–81% ⚠ small n |
113:| run_environment | 2-2 | 4 | **50.0%** | 15%–85% ⚠ small n |
```

k. Compliance, AST, and compile:
```text
python3 tools/check_bpp_compliance.py --base origin/main
BPP compliance OK (0 changed JSON/HTML files checked against 2c1ee69e15cb)

git diff --quiet origin/main -- 'slate_picks*.json' backtest/graded_picks.json
historical pick/grade JSON byte-identical to origin/main

python3 - <<'PY'
import ast
paths=['build_day46.py','parlay_rules.py','backtest/backfill_grades.py','backtest/calibration.py','grade_results.py','tools/test_parlay_rules.py']
for path in paths:
    ast.parse(open(path, encoding='utf-8').read())
print('ast.parse OK:', ', '.join(paths))
PY
ast.parse OK: build_day46.py, parlay_rules.py, backtest/backfill_grades.py, backtest/calibration.py, grade_results.py, tools/test_parlay_rules.py

python3 -m py_compile build_day46.py parlay_rules.py backtest/backfill_grades.py backtest/calibration.py grade_results.py tools/test_parlay_rules.py
exit 0
```

Additional generated parlay invariant check:
```text
parlay legs 15
2B/SB parlay legs []
HR anchor legs []
same-player violations []
pitcher-side duplicate violations []
```
