# Remove Satellite Tag Session Status

Branch: `codex/remove-satellite-tag`

PR: draft, opened from this branch.

## Scope

Removed the visible `Satellite` role badge from parlay leg rendering only. `leg_role` remains emitted in `SLATE_PICKS` and remains in the `backtest/backfill_grades.py` copy path.

Also replaced the inert HR-anchor guard in `parlay_rules.py` with the current design rule: HR legs are allowed only in Yard Sale correlation types.

No parlay selection thresholds, nesting rules, forbidden markets, pitcher-side rules, or grading data were changed.

## Verification

### a. Role tag removed from rendered parlay cards

Screenshots:

```text
artifacts/remove_satellite_before.png
artifacts/remove_satellite_after.png
```

Capture output:

```text
before: artifacts/remove_satellite_before.png Satellite=true SAME_GAME=true
after: artifacts/remove_satellite_after.png Satellite=false SAME_GAME=true
```

Rendered grep:

```text
rg -n "Satellite" index.html built_sections.json
# no output
```

CSS cleanup: no CSS existed solely for the role badge. The removed tag used the generic `.badge.b-neutral` style, which is still used by real neutral labels elsewhere.

### b. `leg_role` data retained

Command:

```text
python3 - <<'PY'
import json
p=json.load(open('slate_picks.json'))
parlay=[x for x in p.get('picks', []) if x.get('parlay_id')]
print('slate_picks parlay legs:', len(parlay))
print('leg_role present:', sum(1 for x in parlay if 'leg_role' in x), 'unique:', sorted({x.get('leg_role') for x in parlay}))
text=open('backtest/backfill_grades.py', encoding='utf-8').read()
print('backfill copies leg_role:', "'leg_role': p.get('leg_role')" in text)
PY
```

Output:

```text
slate_picks parlay legs: 54
leg_role present: 54 unique: ['satellite']
backfill copies leg_role: True
```

Note: I did not modify `backtest/graded_picks.json`. The current checked-in graded store has no parlay rows yet, but the backfill copy path still carries `leg_role` forward when those rows are backfilled.

### c. HR rejected outside Yard Sale

Command:

```text
python3 - <<'PY'
from parlay_rules import validate_parlay
cases = [
    ('traffic_jam', [{'market':'HR','name':'A'}, {'market':'HIT','name':'B'}]),
    ('two_way_k', [{'market':'HR','name':'A'}, {'market':'K','name':'B'}]),
    ('double_barrel_same_game', [{'market':'HR','name':'A'}, {'market':'HIT','name':'B'}]),
    ('streak', [{'market':'HR','name':'A'}, {'market':'HRR','name':'B'}]),
    ('yard_sale_same_game', [{'market':'HR','name':'A'}, {'market':'HR','name':'B'}]),
]
for corr, legs in cases:
    print(corr, validate_parlay(legs, corr))
PY
```

Output:

```text
traffic_jam (False, 'HR legs are only allowed in Yard Sale')
two_way_k (False, 'HR legs are only allowed in Yard Sale')
double_barrel_same_game (False, 'HR legs are only allowed in Yard Sale')
streak (False, 'HR legs are only allowed in Yard Sale')
yard_sale_same_game (True, 'ok')
```

### d. Yard Sale still emits

Current `slate_picks.json` parlay leg summary:

```text
yard_sale_same_game 10 ['HR']
```

Rendered section count:

```text
yard-sale: cards=5 empty=False satellite_text=False
```

### e. All five sections render in both modes

Projected mode, from the actual `day_data.json` build:

```text
two-way-ks: cards=2 empty=False satellite_text=False
traffic-jam: cards=5 empty=False satellite_text=False
double-barrel: cards=5 empty=False satellite_text=False
cruise-control: cards=5 empty=False satellite_text=False
yard-sale: cards=5 empty=False satellite_text=False
```

Workbook branch smoke, using a temporary non-projected copy of the same local slate inputs because no workbook-backed `day_data` artifact is present in the repo:

```text
two-way-ks: cards=2 empty=False satellite_text=False
traffic-jam: cards=5 empty=False satellite_text=False
double-barrel: cards=5 empty=False satellite_text=False
cruise-control: cards=5 empty=False satellite_text=False
yard-sale: cards=5 empty=False satellite_text=False
```

### f. Compliance and syntax

Commands:

```text
python3 backtest/test_backtest_mock.py
python3 tools/check_bpp_compliance.py
python3 -m py_compile build_day46.py parlay_rules.py backtest/backfill_grades.py backtest/test_backtest_mock.py
python3 - <<'PY'
import ast
for path in ['build_day46.py', 'parlay_rules.py', 'backtest/backfill_grades.py', 'backtest/test_backtest_mock.py']:
    ast.parse(open(path, encoding='utf-8').read())
    print(f'ast ok {path}')
PY
```

Output:

```text
ALL TESTS PASSED
BPP compliance OK (4 changed JSON/HTML files checked against abf3ae7f8bf5)
ast ok build_day46.py
ast ok parlay_rules.py
ast ok backtest/backfill_grades.py
ast ok backtest/test_backtest_mock.py
```
