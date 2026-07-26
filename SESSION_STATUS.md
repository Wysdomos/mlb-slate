# SESSION STATUS - 2026-07-26 - Codex

## Chapter E - Matchup Chip Shadow Mode

- Branch: `codex/chapter-e-matchup-chip`
- Base: `origin/main` at `a5bf6e547ed1`
- Handoff located and used: `/tmp/codex-remote-attachments/019f9956-870f-7e62-89a9-ed1500d2bcca/B25145F8-90AD-412D-87DE-865C94FB63A7/1-HANDOFF-ChapterE-Matchup-Chip.md`
- Added five shadow tier fields to every emitted pick record:
  - `chip_hra`
  - `chip_hrb`
  - `chip_hit_a`
  - `chip_k_a`
  - `chip_hall_a`
- No rendered output intentionally reads or displays these fields.
- Existing `PICK_SOURCE` was reused. No duplicate source-of-truth was introduced.
- `tools/check_bpp_compliance.py` was read before field naming and was not modified. The selected `chip_*` field names do not contain `calibration`, `matchup`, `advantage`, or `signal`; emitted values are only string labels or `None`.
- `fetch_projected_mode.py`, `tools/projected_publish_guard.py`, `extract_xlsx.py`, and the existing `calibration_tier` emission were not changed.
- No historical `slate_picks*.json` or `backtest/graded_picks.json` files were modified.

## Formula Thresholds

All BPP/projection value thresholds are percentile-based over the current slate population before tiering.

- HR-A Avoidance Tax: `hr_prob`, `walk_prob`, and `matchup_advantage` use slate percentiles.
- HR-B Contextual Spike: `hr_vs_typical` and `park_hr_factor` use slate percentiles.
- HIT-A Contact Floor: `hit_prob` and `k_prob` use slate percentiles.
- K-A Volume Cap Refiner: K/BB ratio and projected innings use slate percentiles.
- HALLOWED-A Contact Quality Reversal: opponent barrel rate, opponent hard-hit rate, and hits allowed are slate percentiles.

Converted from raw-threshold wording in the handoff:
- HR-B park factor raw multipliers were converted to percentile thresholds: EDGE+ uses `park_hr_factor` percentile `>= 80`; FADE uses `park_hr_factor` percentile `<= 50`.
- K-A K/BB ratio multiplier thresholds were converted to percentile thresholds: EDGE+ uses K/BB percentile `>= 80`; FADE uses K/BB percentile `<= 25`.

## Verification

a. Built HTML diff vs main is empty:
```text
diff -u /tmp/chaptere-main-index.html /tmp/chaptere-branch-index.html
exit 0, empty output

diff -u /tmp/chaptere-main-sections.json /tmp/chaptere-branch-sections.json
exit 0, empty output
```

b. `slate_picks.json` gains exactly the five tier fields and nothing else:
```text
main picks: 249
branch picks: 249
missing chip fields: 0
bad chip values: 0
stripped branch equals main: True
```

c. Every value is a string tier label or `None`; no numerics:
```text
valid labels checked: EDGE+, EDGE, NEUTRAL, FADE, None
chip_hra {None: 249}
chip_hrb {None: 249}
chip_hit_a {None: 249}
chip_k_a {'NEUTRAL': 28, 'EDGE+': 2, None: 219}
chip_hall_a {None: 249}
```

d. All five fields appear in `graded_picks.json` after a backfill run:
```text
python3 backtest/backfill_grades.py
1 slate files · 0 date(s) already backfilled
-- 2026-07-25: 249 picks
games: 15 totals, 15 first-inning; keys=['ARI@WSH', 'ATL@BAL', 'CHC@PIT', 'CIN@STL', 'CLE@TB', 'COL@MIL', 'HOU@CWS', 'KC@DET', 'LAA@SF', 'LAD@NYM', 'NYY@PHI', 'OAK@MIN', 'SD@MIA', 'SEA@TEX', 'TOR@BOS']
   graded 225/249

wrote /private/tmp/chaptere-backfill-final/backtest/graded_picks.json: 249 rows, 225 gradable, 1 dates

graded rows: 249
chip_hra present in rows: 249 non-null: 0
chip_hrb present in rows: 249 non-null: 0
chip_hit_a present in rows: 249 non-null: 0
chip_k_a present in rows: 249 non-null: 30
chip_hall_a present in rows: 249 non-null: 0
```

e. `calibration.py` buckets by each of the five without error:
```text
python3 backtest/calibration.py
wrote /private/tmp/chaptere-backfill-final/backtest/CALIBRATION.md (4714 bytes)

rg -n "Shadow chip candidates|HR-A|HR-B|HIT-A|K-A|HALLOWED-A" backtest/CALIBRATION.md
88:## Shadow chip candidates
93:### HR-A Avoidance Tax (`chip_hra`) -- insufficient data -- keep accumulating
102:### HR-B Contextual Spike (`chip_hrb`) -- insufficient data -- keep accumulating
111:### HIT-A Contact Floor (`chip_hit_a`) -- insufficient data -- keep accumulating
120:### K-A Volume Cap Refiner (`chip_k_a`) -- insufficient data -- keep accumulating
129:### HALLOWED-A Contact Quality Reversal (`chip_hall_a`) -- insufficient data -- keep accumulating
```

Historical compatibility with existing records missing chip fields:
```text
python3 backtest/calibration.py
wrote /private/tmp/chaptere-historical-cal/backtest/CALIBRATION.md (4653 bytes)

historical graded rows: 2660
rows missing chip_hra: 2660
```

f. Historical files byte-identical to main:
```text
git diff --quiet origin/main -- 'slate_picks*.json' backtest/graded_picks.json
historical public pick/grade files byte-identical to origin/main
```

g. `tools/check_bpp_compliance.py` passes unmodified:
```text
git diff -- tools/check_bpp_compliance.py
exit 0, empty output

python3 tools/check_bpp_compliance.py --base origin/main
BPP compliance OK (0 changed JSON/HTML files checked against a5bf6e547ed1)
```

h. Threshold confirmation:
```text
All BPP/projection value thresholds in the five formulas are slate percentiles.
Converted raw handoff thresholds: HR-B park factor multipliers; K-A K/BB median multipliers.
No raw BPP values are emitted to committed JSON or HTML.
```

i. `ast.parse` and `py_compile` pass:
```text
python3 - <<'PY'
import ast
paths = ['fetch_bpp.py','build_day46.py','shadow_chips.py','backtest/backfill_grades.py','backtest/calibration.py','tools/test_shadow_chips.py','services/bpp_client/tests/test_fetch_bpp.py']
for path in paths:
    ast.parse(open(path, encoding='utf-8').read())
print('ast.parse OK:', ', '.join(paths))
PY
ast.parse OK: fetch_bpp.py, build_day46.py, shadow_chips.py, backtest/backfill_grades.py, backtest/calibration.py, tools/test_shadow_chips.py, services/bpp_client/tests/test_fetch_bpp.py

python3 -m py_compile fetch_bpp.py build_day46.py shadow_chips.py backtest/backfill_grades.py backtest/calibration.py tools/test_shadow_chips.py services/bpp_client/tests/test_fetch_bpp.py
exit 0
```

Additional focused tests:
```text
python3 tools/test_shadow_chips.py
shadow chip formula smoke tests OK

python3 -m unittest services.bpp_client.tests.test_fetch_bpp
Ran 3 tests in 0.001s
OK
```

Live BPP note:
```text
BPP_SUMMARY_FILE=/tmp/chaptere-bpp-summary.json python3 fetch_bpp.py
[bpp] wrote /tmp/chaptere-bpp-summary.json: 0 player entries
BPP API calls this run: 18
```
The committed workbook/day data is for 2026-07-25, and BPP reported that historical data is not available for that date. The same empty private summary was used for both main and branch parity builds.
