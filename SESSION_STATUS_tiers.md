# PR 3a - T0-T3 rename, SSJ removal, honest grading copy

Branch: `refactor/tiers-and-ssj-removal`
Base: `origin/main` at `13a0806d91a0`

## Scope completed

- Read `AGENTS.md`.
- Read `docs/BPP_REBUILD_SPEC.md`.
- Did not create `build_vuln.py`; Vuln rebuild is left for PR 3b.
- Did not touch `parlay_rules.py`.
- Did not touch CSS tokens or `.projected-mode`.

## Commit 1 - projected tier rename

- `fetch_projected_mode.py` `projected_grade()` now returns `T0/T1/T2/T3`.
- Thresholds remain unchanged:
  - `>= 78` -> `T0`
  - `>= 66` -> `T1`
  - `>= 54` -> `T2`
  - `< 54` -> `T3`
- `assert OLD in src` was run before replacement.
- `ast.parse` and `py_compile` passed for the edited file.

Consumer grep:

```text
fetch_projected_mode.py:498: "Grade": projected_grade(score)
fetch_projected_mode.py:646:def projected_grade(score: int) -> str:
build_day46.py:1369: renders r.get("Grade","-") directly
```

Other active-source matches are not tier consumers:

```text
build_day46.py: STREAKS_LIVE variable names
build_k_report.py: Phase 2 LIVE status text
build_k_report.py/build_streaks.py: SCORECARD labels
```

Generated/static artifact matches remain in `day_data.json`, `index.html`, and `docs/preview/projected.html`; those are existing rendered/projected artifacts, not CSS classes, badge maps, sort keys, or filters.

## Commit 2 - board legend

- Replaced the alignment matrix with the requested four-column legend: `Tier | Score | Meaning | Typical use`.
- Corrected scores to match code: `>=78`, `66-77`, `54-65`, `<54`.
- Removed unit-sizing/staking copy:
  - `ANCHOR - max unit`
  - `PLAY - standard unit`
  - `VALUE - half unit`
  - `PASS - park kills edge`
- Kept the `tldr-box` park summary below the table.
- Retitled the section to `How to read a board`.

## Commit 3 - SSJ navigation removal

Removed exactly three `scout.html`/SSJ links from `index.html`:

```text
headline/footer SSJ link + subtitle block
bottom dock SSJ button
More sheet SSJ row
```

Verification:

```text
$ rg -n "scout\.html|SSJ|The Zone" index.html
# no output

$ python3 - <<'PY'
from pathlib import Path
src = Path('index.html').read_text()
start = src.index('<nav class="dock"')
end = src.index('</nav>', start)
block = src[start:end]
print('dock buttons:', block.count('class="dock-btn"'))
assert block.count('class="dock-btn"') == 6
PY
dock buttons: 6
```

Dock layout note: `.dock` uses `display:flex` and `.dock-btn { flex: 1; max-width: 96px; min-width: 0; }`, so the remaining six controls distribute evenly.

Screenshot note: attempted to render 390px dark/light dock screenshots. Quick Look required unsandboxed GUI access and the attempt was interrupted; Playwright is installed but has no browser executable available, and Safari cannot be driven headlessly by the installed Playwright package in this environment.

## Commit 4 - retire SSJ builder

- Deleted `build_scout.py`.
- Removed the entire Step 5 `build_scout.py -> scout.html` block from `build.py`, including the Projected Mode unavailable-page fallback and try/except.
- Left `scout.html` untouched and orphaned, as requested.
- `ast.parse` and `py_compile` passed for `build.py`.

Verification:

```text
$ rg -n "build_scout|Step 5|scout\.html|SSJ|The Zone" build.py index.html
# no output
```

## Commit 5 - honest grading copy

- Replaced unsupported HR insight copy in `grade_results.py`.
- Current `results.json` `hr_buckets` state:

```json
[
  {
    "name": "0-1 lenses",
    "cls": "f",
    "w": 0,
    "l": 3
  }
]
```

New copy:

```text
not enough graded days yet to compare lens buckets; check back as the sample builds.
```

No edge direction is asserted.

## Final validation

```text
$ python3 - <<'PY'
import ast
from pathlib import Path
for path in [Path(p) for p in __import__('subprocess').check_output(['git','ls-files','*.py'], text=True).splitlines()]:
    ast.parse(path.read_text())
print('ast.parse OK: git-tracked Python files')
PY
ast.parse OK: git-tracked Python files
```

```text
$ python3 -m py_compile $(git ls-files '*.py')
# passed
```

```text
$ python3 tools/check_bpp_compliance.py
BPP compliance OK (1 changed JSON/HTML files checked against 13a0806d91a0)
```

```text
$ DATA_FILE=day_data.json SECTIONS_FILE=/tmp/tiers_sections_rebased.json K_REPORT_FILE=/tmp/tiers_k_report_rebased.html STREAKS_FILE=/tmp/tiers_streaks_rebased.html HOT_STREAKS_FILE=/tmp/tiers_hot_streaks_rebased.json python3 build.py
Pipeline complete. Sections -> /tmp/tiers_sections_rebased.json, K Report -> /tmp/tiers_k_report_rebased.html, Streaks -> /tmp/tiers_streaks_rebased.html
```

The temp build wrote fixed-name generated pick JSON as a side effect; those files were restored and not committed.

Required parlay smoke test status:

```text
$ python3 tools/test_parlay_rules.py
rejected: nested same-player batter legs
rejected: duplicate pitcher-side traffic legs
AssertionError: HR legs are only allowed in Yard Sale
```

This is inherited from current `origin/main`: `tools/test_parlay_rules.py` still expects `HR cannot anchor`, while `parlay_rules.py` now returns `HR legs are only allowed in Yard Sale`. This branch leaves both files unchanged per constraints, so the mismatch remains unresolved here.

