# SESSION_STATUS — Render Defects Fix

Branch: `codex/fix-render-defects`  
Base: `origin/main` at `47f2e57`  
PR: draft, do not merge

## Summary

- Restored missing rendered sections in `index.html`, including `oo5-board`.
- Replaced `sync.py`'s one-off `tb-board` insert fallback with an explicit fallback anchor for every section in `SECTION_ORDER`.
- Added GitHub Actions `::warning::` annotations whenever `sync.py` has to restore a missing section.
- Removed stale duplicate editorial/parlay builders from `build_editorial.py`; Chapter I/J surfaces in `build_day46.py` are the only owners now.
- Removed the duplicate visible K projection column from the K board. Thresholds and consensus counts were intentionally left unchanged pending calibration review.

## Root Cause: Missing Hits Board

`oo5-board` was not removed by `sync.py` directly. It disappeared in merge commit:

```text
2e437ab Merge remote-tracking branch 'origin/main'
Parents: f68d884 0fcabdb
```

Both parents still contained `<section id="oo5-board">`:

```text
f68d884:index.html -> <section id="oo5-board" ...> present
0fcabdb:index.html -> <section id="oo5-board" ...> present
```

The combined merge diff shows the rendered `oo5-board` section removed:

```text
git show --cc 2e437ab -- index.html | rg 'oo5-board'
471: -<section id="oo5-board" class="collapsible">
```

After that, later auto-updates could not repair it because `sync.py` only replaced existing sections and only had an insert fallback for `tb-board`.

## Verification

### a. `index.html` contains `oo5-board`; board renders with real rows

```text
oo5 section True
oo5 rows 50
order hr<oo5<tb True
```

### b. Delete any section, rebuild, self-restores with warning

Temp test deleted `totals-board` from a copy of `index.html`, then ran `sync.py`:

```text
totals present before sync False
::warning::sync.py restored missing section #totals-board after #tb-board
totals restored True
```

The real repair run also restored other missing stateful-template sections:

```text
::warning::sync.py restored missing section #matchup-spotlight after #games
::warning::sync.py restored missing section #oo5-board after #hr-board
::warning::sync.py restored missing section #conviction after #parlays
::warning::sync.py restored missing section #skip after #conviction
```

### c. K board shows no duplicated column

```text
k th SS Ks False
k th BPP Ks False
k th Proj Ks True
```

### d. K lens independence audit; thresholds unchanged

Current code still computes six lens slots and all thresholds are unchanged.

The duplicated slots:

- `SP_Projections.K` is built by `fetch_bpp_tabs.py` from `projection_averages(...).strikeouts`.
- `BP_Pitchers.Strikeouts` is set from the same `projection_averages(...).strikeouts`.

Current slate check:

```text
paired pitchers 24
identical within 0.005 24
max abs diff 0.004999999999999893
sample [('George Kirby', 5.32, 5.324), ('Kumar Rocker', 5.08, 5.075), ('Merrill Kelly', 3.78, 3.782), ('Mitch Keller', 3.5, 3.497), ('Zack Wheeler', 6.47, 6.469)]
```

Independence audit:

- Lens slot 1: `SP_Projections.K` — BPP strikeout projection.
- Lens slot 2: `BP_Pitchers.Strikeouts` — duplicate BPP strikeout projection.
- Lens slot 3: `Sweet_Spot_Slate.K9` — workbook/Sweet Spot pitcher skill context; independent of the duplicated K projection.
- Lens slot 4: `BP_Pitchers.Innings * 3` — BPP workload projection, related but not the same K value.
- Lens slot 5: `BP_Teams.Strikeouts` — opponent lineup K-proneness; independent workbook/team lens.
- Lens slot 6: `bpp_summary.proj_k` — when present, also comes from BPP `projection_averages(...).strikeouts`; same source family as slots 1 and 2.

True count: six slots currently represent four distinct signal families at most:

```text
BPP pitcher K projection
Sweet Spot K9
BPP workload / outs projection
Opponent lineup strikeouts
```

This PR does not change thresholds, Strikeout Stack eligibility, Anchor threshold, or conviction ranking.

### e. Parlay sections render Chapter I structures

Screenshot artifact:

```text
docs/render-fix/parlay-surfaces.png
```

Content checks:

```text
Strikeout Stack True
Traffic Stack True
Anchor True
```

### f. Headlines, conviction, skip render Chapter J output

```text
headlines live cards 5
Full Conviction Board True
Daily Skip List True
```

Rendered samples:

```text
conviction: #1 Zack Wheeler O 5+ (K, PHI) — 4/6 K lenses; projected 6.47 strikeouts
skip: Eddy Yean K props — projected 1.13 strikeouts, below the K board tier threshold.
```

### g. No surface has two competing builders

Command:

```bash
rg -n "def build_headlines|def build_combos_k|def build_combos_hrr|def build_parlays|def build_conviction|def build_skip|SECTIONS\\['headlines'\\]|SECTIONS\\['combos-k'\\]|SECTIONS\\['combos-hrr'\\]|SECTIONS\\['parlays'\\]|SECTIONS\\['conviction'\\]|SECTIONS\\['skip'\\]" build_day46.py build_editorial.py
```

Output:

```text
build_day46.py:420:def build_headlines():
build_day46.py:2301:def build_combos_k():
build_day46.py:2361:def build_combos_hrr():
build_day46.py:2473:def build_parlays():
build_day46.py:2682:def build_conviction():
build_day46.py:2719:def build_skip():
```

`build_editorial.py` now reports:

```text
build_editorial: Chapter I/J sections owned by build_day46.py; no overrides written
build_editorial: hot_streaks audit 69 hot batters, 3 HR streakers
sections unchanged True
```

Hot-streak audit: the old `build_editorial.py` hot-streak enrichment only fed its superseded pre-Chapter-I parlay/conviction implementations. No standalone non-duplicative enrichment path existed to preserve. `build_day46.py` continues to use workbook `Streaks` data in the HR/Hits surfaces.

### h. Compliance, ast.parse, py_compile

```text
BPP compliance OK (2 changed JSON/HTML files checked against 47f2e579f48e)
```

```text
ast ok build_day46.py
ast ok sync.py
ast ok build_editorial.py
ast ok build.py
```

```text
python3 -m py_compile build_day46.py sync.py build_editorial.py build.py
exit code 0
```

Additional:

```text
git diff --check
exit code 0
```
