# Chapter K — Five Parlay Sections

Branch: `codex/chapter-k-parlays`  
Base: `main` after render-defect fix merge (`f6211c91f247`)  
Status: implemented, verified locally with temporary workbook/projected builds, pushed as draft PR.

## Summary

- Retired rendered `combos-k`, `combos-hrr`, and `parlays`.
- Added five rendered parlay sections, in order: `two-way-ks`, `traffic-jam`, `double-barrel`, `cruise-control`, `yard-sale`.
- Added per-leg `same_game` emission and calibration bucketing.
- Extended `parlay_rules.py` with a documented HR-only exception for Yard Sale while keeping the general HR top-conviction guard intact.
- Added rendered artifacts:
  - `artifacts/chapter_k_parlays_workbook.png`
  - `artifacts/chapter_k_parlays_projected.png`
  - `artifacts/chapter_k_order_workbook.png`
  - `artifacts/chapter_k_order_projected.png`

## Verification

### a. All five render in workbook mode, in order

Command:

```bash
python3 build_day46 wrapper with DATA_FILE=day_data.json, HOT_STREAKS_FILE=/tmp/chapterk_hot_fixture.json
SECTIONS_FILE=/tmp/chapterk_sections.json INDEX_FILE=/tmp/chapterk_index.html python3 sync.py
```

Output:

```text
workbook ['two-way-ks', 'traffic-jam', 'double-barrel', 'cruise-control', 'yard-sale']
```

Screenshot/sample: `artifacts/chapter_k_parlays_workbook.png`, `artifacts/chapter_k_order_workbook.png`.

### b. All five render in Projected Mode

Command:

```bash
day_data.json copied to /tmp/chapterk_projected_data.json with _mode='projected'
python3 build_day46 wrapper with HOT_STREAKS_FILE=/tmp/chapterk_hot_fixture.json
SECTIONS_FILE=/tmp/chapterk_projected_sections.json INDEX_FILE=/tmp/chapterk_projected_index.html python3 sync.py
```

Output:

```text
projected ['two-way-ks', 'traffic-jam', 'double-barrel', 'cruise-control', 'yard-sale']
projected parlay legs 22 ['both_sides', 'run_environment', 'streak', 'yard_sale_same_game'] [False, True]
```

Screenshot/sample: `artifacts/chapter_k_parlays_projected.png`, `artifacts/chapter_k_order_projected.png`.

### c. Old three sections gone and retired

Command:

```bash
python3 - <<'PY'
import re
for label,path in [('workbook','/tmp/chapterk_index.html'),('projected','/tmp/chapterk_projected_index.html')]:
    ids=re.findall(r'<section id="([^"]+)"', open(path).read())
    print(label, {old:(old in ids) for old in ['combos-k','combos-hrr','parlays']})
PY
```

Output:

```text
workbook {'combos-k': False, 'combos-hrr': False, 'parlays': False}
projected {'combos-k': False, 'combos-hrr': False, 'parlays': False}
```

`sync.py`:

```text
RETIRED_SECTION_IDS = ('sb-board', 'doubles-board', 'combos-k', 'combos-hrr', 'parlays')
```

### d. SAME GAME tag appears only where legs share one game

Temporary picks output:

```text
same_game values [False, True]
sample: {'market': 'HRR', 'name': 'Jacob Wilson', 'parlay_id': '20260727-traffic-jam-1-run_environment', 'correlation_type': 'run_environment', 'leg_role': 'satellite', 'same_game': True, 'pick_source': 'workbook'}
```

Rendered samples show SAME GAME on Traffic Jam/Yard Sale entries and no tag on Cruise Control mixed-game entry.

### e. Cross-game stricter bar

Source:

```text
39:CROSS_GAME_STRICTER_DELTA = 5.0
2551:threshold = min_hit_pct + (CROSS_GAME_STRICTER_DELTA if cross_game else 0)
2775:threshold = YARD_SALE_DRIVER_MIN + (CROSS_GAME_STRICTER_DELTA if cross_game else 0)
```

Starting values:

```text
Double Barrel same-game HIT threshold: 65.0%
Double Barrel cross-game HIT threshold: 70.0%
Yard Sale same-game driver threshold: 35.0
Yard Sale cross-game driver threshold: 40.0
```

### f. Independent-family lens count

Mapping used:

```text
bpp_projection_averages_k: SP_Projections.K / BP_Pitchers.Strikeouts / bpp_summary.proj_k collapsed into one family
pitcher_k9_skill: Sweet Spot K9
projected_outs_volume: BP_Pitchers.Innings-derived outs
opponent_lineup_k_volume: BP_Teams.Strikeouts
```

Worked example:

```text
Zack Wheeler {'bpp_projection_averages_k': True, 'pitcher_k9_skill': False, 'projected_outs_volume': True, 'opponent_lineup_k_volume': True} count=3 raw_slots=4
```

### g. Cruise Control stable by slate date

Command output:

```text
same_a ['Kyle Schwarber', 'Nick Kurtz', 'Jo Adell']
same_b ['Kyle Schwarber', 'Nick Kurtz', 'Jo Adell']
other  ['Nick Kurtz', 'Eugenio Suárez', 'Kyle Schwarber']
same equal True
different date changed True
```

### h. No HR leg in Cruise Control

Command output:

```text
Cruise HR legs: []
```

### i. Yard Sale ranks on physical drivers, not lens count

Yard Sale detail text is generated from park HR context, pitcher HR-allowed profile, BPP `HomeRuns` projection, and handedness context. No K/HR consensus lens count is read in `yard_sale_candidates()`.

Sample emitted order:

```text
Yard order: [('Wilyer Abreu', 'HR', 'yard_sale_same_game'), ('Curtis Mead', 'HR', 'yard_sale_same_game'), ('Nick Kurtz', 'HR', 'yard_sale_same_game'), ('Tyler Soderstrom', 'HR', 'yard_sale_same_game'), ('Mike Trout', 'HR', 'yard_sale_same_game'), ('Zach Neto', 'HR', 'yard_sale_same_game'), ('Miguel Vargas', 'HR', 'yard_sale_same_game'), ('Colson Montgomery', 'HR', 'yard_sale_same_game'), ('Elly De La Cruz', 'HR', 'yard_sale_same_game'), ('JJ Bleday', 'HR', 'yard_sale_same_game')]
```

### j. Rule 1 and Rule 2 enforced

Command:

```bash
python3 - <<'PY'
from parlay_rules import validate_parlay
print(validate_parlay([{'market':'HIT','name':'A','leg_role':'satellite','confidence_rank':1},{'market':'HRR','name':'A','leg_role':'satellite','confidence_rank':2}], 'double_barrel_same_game', max_legs=2))
print(validate_parlay([{'market':'H_ALLOWED','name':'P','leg_role':'satellite'},{'market':'ER_ALLOWED','name':'P','leg_role':'satellite'}], 'traffic_jam', max_legs=2))
print(validate_parlay([{'market':'HR','name':'B','leg_role':'satellite','confidence_rank':1},{'market':'HIT','name':'C','leg_role':'satellite','confidence_rank':2}], 'streak', max_legs=2))
print(validate_parlay([{'market':'HR','name':'B','leg_role':'satellite','confidence_rank':1},{'market':'HR','name':'C','leg_role':'satellite','confidence_rank':2}], 'yard_sale_same_game', max_legs=2))
PY
```

Output:

```text
(False, 'nested same-player batter legs')
(False, 'duplicate pitcher-side traffic legs')
(False, 'HR cannot be the top-conviction leg')
(True, 'ok')
```

### k. same_game and correlation_type reach grading/calibration

Slate picks:

```text
fields present in slate_picks: True 22
```

Source checks:

```text
same_game copy list: True
correlation bucket: True
same_game bucket: True
```

Calibration command:

```bash
python3 backtest/calibration.py
```

Output:

```text
wrote /Users/wysdomos/mlb-slate/backtest/CALIBRATION.md (5124 bytes)
```

`backtest/CALIBRATION.md` was restored after verification and is not committed.

### l. Compliance, ast.parse, py_compile

Compliance:

```bash
python3 tools/check_bpp_compliance.py
```

Output:

```text
BPP compliance OK (0 changed JSON/HTML files checked against f6211c91f247)
```

AST:

```text
ast ok build_day46.py
ast ok parlay_rules.py
ast ok sync.py
ast ok build.py
ast ok build_streaks.py
ast ok backtest/backfill_grades.py
ast ok backtest/calibration.py
```

py_compile:

```bash
python3 -m py_compile build_day46.py parlay_rules.py sync.py build.py build_streaks.py backtest/backfill_grades.py backtest/calibration.py
```

Output: no errors.

## Notes

- Full `python3 build.py` completed with temporary output paths after the network-heavy streak fetch finished:

```text
[streaks] ✓ Wrote /tmp/chapterk_streaks.html — 110 streaks
[streaks] ✓ Wrote /tmp/chapterk_hot_streaks.json — 4 HR streakers, 68 hot batters
Wrote 313 pick records -> /tmp/chapterk_slate_picks.json (+ slate_picks_7-27.json)
Built 19 sections
  two-way-ks: 660 bytes
  traffic-jam: 2564 bytes
  double-barrel: 640 bytes
  cruise-control: 1237 bytes
  yard-sale: 3510 bytes
Pipeline complete. Sections -> /tmp/chapterk_sections.json, K Report -> /tmp/chapterk_k_report.html, Streaks -> /tmp/chapterk_streaks.html
```

The temporary full-build output left the tracked worktree clean.
- `screencapture` was unavailable in this execution environment (`could not create image from display`), so the committed PNG artifacts are Quick Look-rendered local HTML samples.
