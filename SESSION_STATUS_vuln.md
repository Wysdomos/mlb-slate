# SESSION_STATUS_vuln.md

Branch: `feat/vuln-from-bpp`
Base: `origin/main` at `f464a4f` after rebase over PR #49
PR: not opened by Codex

## Commit SHAs

- Commit 1, `build_vuln.py`: `d7b1943`
- Commit 2, `build_day46.py` wiring: `9a0b43d`
- Commit 3, tests + report: `7446aa7`
- Commit 4, Zone column removal: appended after rebase; final SHA confirmed by `git log` / final response after push

## Summary

Implemented BPP-only reconstruction of `Sweet_Spot_Slate`-style pitcher vulnerability data while preserving workbook-first behavior.

Runtime output is keyed by lowercase pitcher name and carries the Sweet Spot fields consumed by `build_day46.py`: `Pitcher`, `Team`, `Throws`, `Opponent`, `ERA`, `WHIP`, `K9`, `BB9`, `ParkFactor`, `VulnScore`, `DangerBatter1`, `DangerBatter2`, `DangerBatter3`, plus debug `source`.

Workbook mode wins unchanged: if `Sweet_Spot_Slate` has rows, those rows populate `SS_BY_NAME` with `source='workbook'`. BPP mode only runs when the workbook tab is absent/empty and labels reconstructed rows `source='bpp'`.

## Derivations

- `ERA`: `SP_Projections.ERA`
- `WHIP`: `(H + BB) / Inn`
- `K9`: `(K / Inn) * 9`
- `BB9`: `(BB / Inn) * 9`
- `ParkFactor`: matching `Park_Factors` game `HR %`, converted to multiplier
- `DangerBatter1-3`: top three opposing-team batters by projected ISO
- Projected ISO: `(Bases - Hits) / AtBats`, because the current `BP_Batters` tab does not expose a literal `ISO` column
- `VulnScore`: fitted clipped composite of ERA, HR/9, ParkFactor and BB9, capped at `72`

The fixture was extracted from `MLB Slate 7-29-26.xlsx` for tests only. Production runtime does not read that workbook. The workbook did not include runtime-shaped `SP_Projections` or `Park_Factors`, so the fixture uses workbook `BP_Pitchers` plus Sweet Spot park factors converted into the runtime shape.

## Fit Quality

Command:

```bash
python3 tests/test_build_vuln.py
```

Output:

```text
......
----------------------------------------------------------------------
Ran 6 tests in 0.003s

OK
Vuln fixture report: n=32 corr=0.915 mae=5.62 same_band=25/32
```

Additional fit details:

```text
n 32 corr 0.915 mae 5.62 same_band 25/32
target >=50 8 target >=32 20
pred >=50 4 pred >=32 23
largest_errors
Brady Singer actual 72 pred 53 abs_error 19 bands >=50 >=50
Jacob Lopez actual 65 pred 51 abs_error 14 bands >=50 >=50
Zack Littell actual 54 pred 40 abs_error 14 bands >=50 32-49
Ryan Gusto actual 55 pred 42 abs_error 13 bands >=50 32-49
Kyle Hart actual 51 pred 39 abs_error 12 bands >=50 32-49
```

Honest read: the fit tracks rank order well and keeps the same 72 ceiling, but it is conservative in the top band. It predicts fewer `>=50` pitchers than the 7/29 workbook target (`4` vs `8`) while keeping the broader `>=32` population close (`23` vs `20`).

## Verification Gate

Before command:

```bash
DATA_FILE=day_data.json SECTIONS_FILE=/tmp/vuln_before_sections.json K_REPORT_FILE=/tmp/vuln_before_k_report.html STREAKS_FILE=/tmp/vuln_before_streaks.html HOT_STREAKS_FILE=/tmp/vuln_before_hot_streaks.json python3 build.py
```

After command:

```bash
DATA_FILE=day_data.json SECTIONS_FILE=/tmp/vuln_after_final_sections.json K_REPORT_FILE=/tmp/vuln_after_final_k_report.html STREAKS_FILE=/tmp/vuln_after_final_streaks.html HOT_STREAKS_FILE=/tmp/vuln_after_final_hot_streaks.json python3 build.py
```

After build output excerpt:

```text
Built 19 sections
  matchup-spotlight: 29906 bytes
  k-board: 17523 bytes
  sp-vuln-board: 12220 bytes
Pipeline complete. Sections -> /tmp/vuln_after_final_sections.json, K Report -> /tmp/vuln_after_final_k_report.html, Streaks -> /tmp/vuln_after_final_streaks.html
```

Current BPP-only reconstructed rows:

```text
source_counts Counter({'bpp': 24})
pitchers 24 vuln>=50 6 vuln>=32 20
top5 [('Kyle Harrison', 72), ('Clay Holmes', 68), ('Anthony Molina', 59), ('Bryce Elder', 52), ('Brady Singer', 52)]
```

Before/after K-board impact:

```text
/tmp/vuln_before_sections.json rows,total_votes,vuln>=50,vuln>=32,vuln_cells (24, 23, 0, 0, 0)
/tmp/vuln_after_final_sections.json rows,total_votes,vuln>=50,vuln>=32,vuln_cells (24, 34, 6, 20, 24)
```

Board row ordering changes:

```text
k_order_changed True
first_diff 12 Anthony Kay -> Will Dion
before_order ['Payton Tolle', 'Jacob deGrom', 'Taj Bradley', 'Gage Jump', 'Ian Seymour', 'Michael King', 'Peter Lambert', 'Aaron Nola', 'Walbert Urena', 'Kyle Harrison', 'George Kirby', 'Brandon Pfaadt', 'Anthony Kay', 'Bryce Elder', 'Brady Singer', 'Clay Holmes', 'Tanner Gordon', 'Kyle Bradish', 'Elmer Rodriguez', 'Jackson Jobe', 'Ryan Gusto', 'Robert Stock', 'Will Dion', 'Anthony Molina']
after_order ['Payton Tolle', 'Jacob deGrom', 'Taj Bradley', 'Gage Jump', 'Ian Seymour', 'Michael King', 'Peter Lambert', 'Aaron Nola', 'Walbert Urena', 'Kyle Harrison', 'George Kirby', 'Brandon Pfaadt', 'Will Dion', 'Anthony Kay', 'Bryce Elder', 'Brady Singer', 'Clay Holmes', 'Tanner Gordon', 'Kyle Bradish', 'Elmer Rodriguez', 'Jackson Jobe', 'Ryan Gusto', 'Robert Stock', 'Anthony Molina']
```

Unavailable surfaces restored in BPP mode:

```text
matchup-spotlight bytes 735 -> 29906 unavailable_before True unavailable_after False
sp-vuln-board bytes 748 -> 12220 unavailable_before True unavailable_after False
```

## Tests

AST parse:

```bash
python3 - <<'PY'
import ast
for path in ['build_vuln.py','build_day46.py','tests/test_build_vuln.py','tests/fixtures/vuln_2026_07_29.py']:
    ast.parse(open(path, encoding='utf-8').read(), filename=path)
print('ast.parse ok')
PY
```

Output:

```text
ast.parse ok
```

py_compile:

```bash
python3 -m py_compile build_vuln.py build_day46.py tests/test_build_vuln.py tests/fixtures/vuln_2026_07_29.py
```

Output: no output, exit 0.

Compliance:

```bash
python3 tools/check_bpp_compliance.py
```

Output:

```text
BPP compliance OK (0 changed JSON/HTML files checked against d8daa754bf4e)
```

## Constraints Checked

- Did not touch `parlay_rules.py`
- Did not change Vuln thresholds `50` / `32`
- Did not touch CSS tokens
- Did not delete `MLB Slate 7-29-26.xlsx`
- `get_vuln_for_pitcher()` and `vuln_cell()` unchanged

## Rebase Over PR #49

Command:

```bash
git fetch origin
git rebase origin/main
```

Output:

```text
Rebasing (1/3)
Rebasing (2/3)
Rebasing (3/3)
Successfully rebased and updated refs/heads/feat/vuln-from-bpp.
```

Diff shape after rebase:

```bash
git diff origin/main..HEAD --stat
```

Output:

```text
 SESSION_STATUS_vuln.md            |  169 ++++++
 build_day46.py                    |   18 +-
 build_vuln.py                     |  271 +++++++++
 tests/fixtures/vuln_2026_07_29.py | 1188 +++++++++++++++++++++++++++++++++++++
 tests/test_build_vuln.py          |  135 +++++
 5 files changed, 1768 insertions(+), 13 deletions(-)
```

`sync.py` PR #49 copy check:

```text
live-copy-present True
old-projected-copy-absent True
```

No `sync.py`, `SESSION_STATUS_copy.md`, or `docs/projected-copy/*.png` files appear in this branch diff.

## Commit 4: Zone Column Removal

Removed the deferred HR-board Zone display from `build_day46.py`:

- Deleted the projected HR board `Zone` column and cells
- Deleted the workbook HR board `Zone` column and cells
- Deleted the now-unused `zone_for_batter()` helper
- Removed Zone chips from danger-batter formatting
- Removed Zone wording from the SP vulnerability board copy

Post-edit checks:

```bash
git grep -n "Zone\|zone" -- build_day46.py
```

Output: no matches.

Temp build:

```bash
DATA_FILE=day_data.json SECTIONS_FILE=/tmp/vuln_zone_sections.json K_REPORT_FILE=/tmp/vuln_zone_k_report.html STREAKS_FILE=/tmp/vuln_zone_streaks.html HOT_STREAKS_FILE=/tmp/vuln_zone_hot_streaks.json python3 build.py
```

Output excerpt:

```text
Built 19 sections
  hr-board: 17156 bytes
  matchup-spotlight: 29879 bytes
  sp-vuln-board: 11235 bytes
Pipeline complete. Sections -> /tmp/vuln_zone_sections.json, K Report -> /tmp/vuln_zone_k_report.html, Streaks -> /tmp/vuln_zone_streaks.html
```
