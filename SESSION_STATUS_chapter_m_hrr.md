# SESSION STATUS - Chapter M HRR Formula + Baseball Refresh

Branch: `codex/chapter-m-hrr`

## Decision

The requested HRR replacement formula was validated and was **not shipped**.

Reason: on the available workbook slate with actual MLB box results, the proposed formula tracked outcomes worse than the existing emitted HRR values. Per the instruction, "If the new formula does not track actual outcomes better ... do not ship it," the HRR code remains byte-identical to main.

This PR ships only the baseball refresh affordance and the clearer stale-banner wording.

## Pre-Start Origin Check

Command:

```bash
git ls-remote origin
```

Relevant output:

```text
fbfaffb76dbd0d482d1bbde26e80f5f3abbeb214	HEAD
fbfaffb76dbd0d482d1bbde26e80f5f3abbeb214	refs/heads/main
0222de25fbd0282ac7679ff3de59791116c32846	refs/heads/codex/healer-archive-parse
942e7b9094fcfdf2e3131f691a12e05972745e5c	refs/heads/codex/healer-initial-delay
448c6cb9e42f9b85a2a702d0bff5df5293212970	refs/heads/codex/parlay-scoreboard
6ee089a6c90fd84996b07bab057b86c88b8a45a8	refs/heads/codex/remove-satellite-tag
```

## HRR Validation

Historical graded store baseline, old formula only:

```text
historical_old_overlap 487 mean_pred 80.17 actual_hit_rate 69.4 min 72.8 median 79.8 max 88.6 above85 37
```

The historical store does not retain raw BP_Batters `Hits`, `Runs`, or `RBIs`, so the proposed formula cannot be recomputed across those 487 historical rows from committed data. That is expected because those raw BPP projections are intentionally not public output.

Available full workbook slate validation: `MLB Slate 7-27-26.xlsx` against MLB box results for `2026-07-27`.

```text
workbook header Hits True
workbook header Runs True
workbook header RBIs True
projected rows 288 missing H/R/RBI 0
old n 40 mean_pred 78.5 actual_hit_rate 62.5 cal_gap 16.0 min 76.4 median 78.3 max 82.1 above85 0 brier 0.2616
new n 40 mean_pred 88.02 actual_hit_rate 62.5 cal_gap 25.52 min 80.1 median 88.1 max 93.4 above85 37 brier 0.3015
```

Sample rows:

```text
Luis Arraez old 78.8 new 90.3 actual_HRR 2 win True
Jackson Chourio old 82.1 new 87.6 actual_HRR 1 win True
William Contreras old 81.1 new 88.5 actual_HRR 0 win False
Brice Turang old 78.9 new 86.0 actual_HRR 0 win False
Gabriel Moreno old 79.7 new 92.1 actual_HRR 0 win False
```

Conclusion: the proposed formula overpredicted, not underpredicted, on the available workbook reality check. It increased calibration gap from `16.0` points to `25.52` points and worsened Brier from `0.2616` to `0.3015`.

## HRR Bands

The existing `82/75` color bands were not changed. If the proposed formula were used, they would likely be too low and non-separating on the checked slate: `37/40` validated rows landed above `85%`, with median `88.1%`.

## Traffic Jam Funnel Impact

Simulated current slate supply if Traffic Jam used the proposed formula:

```text
Traffic Jam simulated current slate
pool 288
old_hrr>=78 248
old_park+sp 131
new_hrr>=78 259
new_park+sp 132
examples name old new park opp_sp
('Nathan Lukes', 86.3, 87.6, 2, 'Cade Cavalli')
('Luis Garcia', 91.5, 91.2, 2, 'Shane Bieber')
('Paul Goldschmidt', 91.1, 92.0, 3, 'Anthony Kay')
```

Conclusion: the `HRR >= 78` gate would not tighten; it would slightly increase supply on the current slate. No threshold was changed.

## Baseball Refresh

Implemented:

- The baseball glyph in the wordmark is now the refresh control: `id="brandRefresh"`.
- Tap target is `44px` by `44px`.
- The text wordmark remains `id="brandBtn"` and still scrolls back to top.
- The separate bottom-dock refresh button was removed.
- The stale banner now says `Updated slate - tap to reload` and clicking the banner reloads with the cache-busting query param.

Static check:

```text
brandRefresh present True
dockRefresh present False
stale copy updated True
old stale copy present False
44px brand CSS True
```

## Verification

```bash
python3 tools/check_bpp_compliance.py
```

```text
BPP compliance OK (1 changed JSON/HTML files checked against fbfaffb76dbd)
```

```bash
python3 -m py_compile build_day46.py build_streaks.py sync.py
```

```text
OK
```

```bash
python3 - <<'PY'
import ast, pathlib
for path in pathlib.Path('.').glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
for path in pathlib.Path('backtest').glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
for path in pathlib.Path('functions').glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('ast.parse OK')
PY
```

```text
ast.parse OK
```

## Push / PR

Pending final push output and draft PR URL.
