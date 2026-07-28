# SESSION STATUS - HRR Empirical Calibration

Branch: `codex/hrr-calibration`

## Ordered Commits

1. `c389d77` - `Measure HRR calibration gap`
2. `Apply empirical HRR calibration`

## a. Banded Table

Command:

```bash
python3 backtest/hrr_calibration.py --recover-from-slate-picks
```

Note: current `backtest/graded_picks.json` has 550 HRR rows but no `hrr_pct` field because historical backfill dropped it. Commit 1 adds `hrr_pct` to future `backfill_grades.py` rows. For the current measurement only, the script joins read-only `slate_picks_*.json` archives to recover the emitted historical `hrr_pct` values without modifying `graded_picks.json`.

Output:

```text
HRR rows with prediction + outcome: 487

| Predicted band | n | Mean predicted | Actual hit rate | Gap |
|---|---:|---:|---:|---:|
| 70-75 | 9 | 73.98% | 66.67% | 7.31 pts |
| 75-80 | 255 | 78.27% | 69.02% | 9.25 pts |
| 80-85 | 182 | 81.79% | 69.23% | 12.55 pts |
| 85-90 | 41 | 86.16% | 73.17% | 12.99 pts |
```

Bands with too few rows to fit: `70-75` has `n=9`.

## b. Gap Shape

The overstatement is roughly constant across usable bands. The populated bands show gaps of `9.25`, `12.55`, and `12.99` points. The larger apparent variation is not enough to justify a curve with only three usable buckets and no monotonic observed-rate separation.

## c. Chosen Shape

Chosen correction: flat offset.

Why: the data supports a simple level correction, not a curve. Scale and offset both improve the date-split holdout; offset is simpler to reason about and slightly better on held-out Brier in this split.

Applied constants in `build_day46.py`:

```python
HRR_CALIBRATION_FIT_DATE = '2026-07-28'
HRR_CALIBRATION_TRAIN_SAMPLE_N = 355
HRR_CALIBRATION_OFFSET_POINTS = 8.9
```

The underlying raw formula remains intact. Only its output is calibrated.

## d. Date-Split Out-of-Sample

Train: earlier slates, `n=355`  
Holdout: later slates, `n=132`

```text
| Shape | Split | Mean predicted | Actual | Gap | Brier |
|---|---|---:|---:|---:|---:|
| raw | train | 80.43% | 71.55% | 8.88 pts | 0.2127 |
| raw | holdout | 79.47% | 63.64% | 15.83 pts | 0.2543 |
| offset | train | 71.55% | 71.55% | 0.00 pts | 0.2048 |
| offset | holdout | 70.59% | 63.64% | 6.95 pts | 0.2341 |
| scale | train | 71.55% | 71.55% | 0.00 pts | 0.2046 |
| scale | holdout | 70.70% | 63.64% | 7.06 pts | 0.2344 |
```

Decision: held-out gap improved from `15.83` to `6.95` points and Brier improved from `0.2543` to `0.2341`, so the calibration is shipped.

## e. Hand Checks

```text
('2026-07-10', 'Luis Arraez', raw=82.7, calibrated=73.8, got='4 H+R+RBI', win=True)
('2026-07-10', 'Heliot Ramos', raw=81.9, calibrated=73.0, got='0 H+R+RBI', win=False)
('2026-07-10', 'Yainer Diaz', raw=84.1, calibrated=75.2, got='4 H+R+RBI', win=True)
```

## f. Colour Cut Points

Old cuts: green `>=82`, orange `>=75`.

On calibrated historical values:

```text
Old color cuts on calibrated offset values: green >=82, orange >=75
- green: n=0 share=0.0% actual=nan%
- orange: n=59 share=12.1% actual=72.9%
- base: n=428 share=87.9% actual=68.9%
```

New cuts: green `>=73`, orange `>=70`.

```text
Candidate color cuts on calibrated offset values: green >=73, orange >=70
- green: n=121 share=24.8% actual=75.2%
- orange: n=200 share=41.1% actual=69.0%
- base: n=166 share=34.1% actual=65.7%
```

The new cuts create three populated groups with visible separation on actual results.

## g. Traffic Jam Funnel

Direct builder run with offset forced to `0.0`:

```text
[traffic-jam] pool=114 -> after same-lineup pairing=12 -> after structure match=4 -> after validation=4 -> emitted=4
  traffic-jam: 2624 bytes
```

Direct builder run with applied offset `8.9`:

```text
[traffic-jam] pool=38 -> after same-lineup pairing=8 -> after structure match=4 -> after validation=4 -> emitted=4
  traffic-jam: 2624 bytes
```

The raw HRR gate candidate count drops from `114` to `38`. Emitted parlays remain `4` on the current slate. The `HRR >= 78` threshold was not changed.

## h. Missing/Small Graded Store Fallback

Command used a temp empty graded store:

```bash
GRADED_PICKS_FILE=/tmp/hrr_small_store.json python3 build_day46.py
```

Relevant output:

```text
[hrr-calibration] warning: /tmp/hrr_small_store.json has 0 graded HRR rows; need 100. Using uncalibrated HRR output.
[traffic-jam] pool=114 -> after same-lineup pairing=12 -> after structure match=4 -> after validation=4 -> emitted=4
Wrote 198 pick records -> /tmp/hrr_picks_small.json (+ slate_picks_7-28.json)
Built 19 sections
```

Missing store path also falls back cleanly:

```text
[hrr-calibration] warning: could not read /tmp/does-not-exist.json: [Errno 2] No such file or directory: '/tmp/does-not-exist.json'. Using uncalibrated HRR output.
```

## i. Checks

```bash
python3 tools/check_bpp_compliance.py
```

```text
BPP compliance OK (0 changed JSON/HTML files checked against 84eac7235765)
```

```bash
python3 -m py_compile build_day46.py backtest/hrr_calibration.py backtest/backfill_grades.py
```

```text
OK
```

```bash
python3 - <<'PY'
import ast, pathlib
for root in ['.', 'tools', 'backtest', 'functions']:
    for path in pathlib.Path(root).glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('ast.parse OK')
PY
```

```text
ast.parse OK
```

```bash
git diff --check
```

```text
OK
```
