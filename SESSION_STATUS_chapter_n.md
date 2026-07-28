# Chapter N — Workbook Regressions + Parlay Styling

Branch: `codex/chapter-n-fixes`

## Commits

1. `c12c838 Reverse projected template text on workbook builds`
2. `e01af79 Restore hit streak consensus lens`
3. `0774bf2 Color parlay legs with existing tier semantics`

## 1. Projected Text Reversal

Fix:
- `sync.py` now reverses the projected wording on non-projected builds:
  - `Projected Mode Alignment` -> `Alignment — Sweet Spot Tier Logic`
  - `Tap to expand - reconstructed board boundaries` -> `Tap to expand - tier thresholds + <date> park notes`

Verification:

```text
workbook title ok True
workbook tag ok True
projected title absent True
projected tag absent True
projected title ok True
projected tag ok True
body projected ok True
roundtrip workbook title ok True
roundtrip workbook tag ok True
roundtrip projected title absent True
roundtrip projected tag absent True
roundtrip body class absent True
```

Rendered text check:

```text
/tmp/chapter_n_workbook_index.html:1356: <div class="game-title">📊 Alignment — Sweet Spot Tier Logic</div>
/tmp/chapter_n_workbook_index.html:1357: <span class="game-tag">Tap to expand - tier thresholds + Jul 28 park notes</span>
/tmp/chapter_n_projected_index.html:1650: <div class="game-title">📊 Projected Mode Alignment</div>
/tmp/chapter_n_projected_index.html:1651: <span class="game-tag">Tap to expand - reconstructed board boundaries</span>
```

Screenshot artifact:
- `artifacts/chapter_n/chapter_n_workbook_index.html.png`
- `artifacts/chapter_n/chapter_n_projected_index.html.png`

## Projected Mutation Audit

Found in `sync.py` projected path:
- Projected CSS block: reversible; removed by marker regex before each run.
- Projected chrome/banner block: reversible; removed by marker regex before each run.
- Projected JS block: reversible; removed by marker regex before each run.
- Standalone projected banner: reversible; removed by marker regex before each run.
- Body class `projected-mode`: reversible; workbook builds remove it.
- Alignment title text swap: was one-way, now reversible.
- Alignment tag text swap: was one-way, now reversible.
- `projected-unavailable` placeholder section drops: safe because section replacement/insert runs before theme application each sync.

## 2. Hit Streak Data

Root cause:
- Current workbook `day_data.json` has `Streaks` as an empty list.
- `STREAK_BY_NAME` previously read only that workbook tab, so the hits-board streak lens was empty.
- Live streak data existed in `streaks_live.json` and build output exists in `hot_streaks.json`, but `build_oo5_board()` did not use either for `Hit Streak`.
- This was not a key-name change, not name matching alone, and not a slate with no 5+ hit streaks.

Fix:
- Added normalized player-key matching.
- `STREAK_BY_NAME` now loads workbook `Streaks`, `streaks_live.json`, and `hot_streaks.json` details.
- Added warning if the streak lens is empty or unexpectedly small.

Consensus vote distribution before and after:

```text
before {1: 6, 2: 20, 3: 22, 4: 2}
before 5+ chips names ['Riley Greene', 'Colt Keith']
after {1: 5, 2: 18, 3: 23, 4: 4}
after 5+ chips names ['Andruw Monasterio', 'Jake Mangum', 'Riley Greene', 'Colt Keith']
```

Runtime load check:

```text
[streaks] Hits-board streak lens loaded 237 batter(s) (workbook=0, live=227, hot=121)
```

Empty warning check:

```text
::warning::build_day46.py streak lens has no data: workbook Streaks tab empty and live/hot streak files unavailable or empty
```

## 3. Parlay Leg Styling

Fix:
- `parlay_leg_html()` now wraps each leg in a styled `parlay-leg`.
- The parlay container remains neutral.
- SAME GAME tag styling is unchanged.
- `SLATE_PICKS` emission is unchanged; styling metadata stays render-only.

Existing color semantics reused:
- K legs: K board projection tier.
- HIT legs: hits-board 1+ hit bands.
- HRR legs: existing HRR green/orange cut points.
- Pitcher-side traffic legs: existing pitcher vulnerability bands.
- Cruise Control fallback: active streak length only when market-specific tier data is unavailable.
- Yard Sale: its established physical-driver score, not HR consensus.

No new color meanings were introduced; green/gold/orange/red continue to mean stronger/secondary/warn/bad within the existing board semantics.

Rendered evidence:

```text
<span class="parlay-leg b-tier0" ...><strong>Chris Sale</strong> Over 2.5 K ...
<span class="parlay-leg b-tier0" ...><strong>Romy Gonzalez</strong> Ov 0.5 H ...
<span class="parlay-leg b-tier1" ...><strong>Pete Alonso</strong> Ov 0.5 HRR ...
<span class="parlay-leg b-tier0" ...><strong>Willson Contreras</strong> Ov 0.5 HR ...
```

Screenshot artifact:
- `artifacts/chapter_n/chapter_n_parlay_sample.html.png`

Note: current slate emitted no Traffic Jam rows, so that section renders its honest empty state. The styling path is wired for its HRR, HIT, H_ALLOWED, and ER_ALLOWED legs when the funnel emits them.

## Build Verification

Workbook sync:

```text
OK #two-way-ks
OK #traffic-jam
OK #double-barrel
OK #cruise-control
OK #yard-sale
Done -- wrote 336,066 bytes to /tmp/chapter_n_workbook_index.html
```

Projected sync:

```text
OK #two-way-ks
OK #traffic-jam
OK #double-barrel
OK #cruise-control
OK #yard-sale
Projected: 2 withheld board(s) -> one disclosure
Done -- wrote 280,221 bytes to /tmp/chapter_n_projected_index.html
```

Funnel/output checks:

```text
[two-way-ks] pool=32 -> after lens>=2=13 -> after tier 0-1=13 -> after same-game pairing=4 -> after same-game alt margin=4 -> after cross-game margin>=2.5=11 -> emitted=5
[traffic-jam] pool=0 -> after same-lineup pairing=0 -> after structure match=0 -> after validation=0 -> emitted=0
[double-barrel] pool=270 -> after hit>=65=3 -> after park>=0+opp_sp=2 -> after contact vuln=2 -> after same-lineup pairing=1 -> after validation=1 -> emitted=1
[cruise-control] details_key=1 -> pool=121 -> after streak>=3=121 -> after supported non-HR market=121 -> after leg build=120 -> after validation=5 -> emitted=5
[yard-sale] pool=288 -> after park>=8+opp_sp=80 -> after driver threshold=79 -> after same-game pairing=12 -> after validation=10 -> emitted=10
```

## Final Checks

```text
BPP compliance OK (0 changed JSON/HTML files checked against c4617d3fc45d)
ast.parse OK build_day46.py
ast.parse OK sync.py
python3 -m py_compile build_day46.py sync.py
```

