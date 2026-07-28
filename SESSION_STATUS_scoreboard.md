# Parlay Scoreboard Session Status

Branch: `codex/parlay-scoreboard`

PR: draft, opened from this branch.

## Scope

Added parlay-level scoring to `backtest/calibration.py`. Existing calibration buckets still report individual legs; the new scoreboard groups by `parlay_id` and grades the full ticket:

- every leg won -> parlay win
- any graded losing leg -> parlay loss
- any ungraded leg (`win is None`) -> parlay ungraded, never a loss

No selection logic, thresholds, odds, payout math, EV, `graded_picks.json`, or historical pick files were changed.

## Verification

### a. Current `graded_picks.json` run

Command:

```text
python3 backtest/calibration.py
sed -n '/## Parlay scoreboard/,$p' backtest/CALIBRATION.md | sed -n '1,8p'
```

Output:

```text
wrote /Users/wysdomos/mlb-slate/backtest/CALIBRATION.md (5441 bytes)

## Parlay scoreboard

Parlays are graded as full tickets: every leg must win. If any leg is ungraded, the parlay is ungraded rather than a loss. Expected independent rate is the average product of each graded parlay's empirical leg-market hit rates inside the same bucket.

No parlay legs have been backfilled yet.
```

Note: the current checked-in `backtest/graded_picks.json` has 2,660 rows and 0 rows with `parlay_id`. The scoreboard is ready for newly backfilled parlay legs without modifying that store.

### b. Ungraded leg makes parlay ungraded

Synthetic fixture output:

```text
UNGRADED result: None [('HIT', True), ('HRR', None)]
```

This parlay is counted under `Ungraded`, not as a loss.

### c. Hand-check one parlay

Synthetic fixture output:

```text
HAND CHECK tj-12 result: False [('HIT', True), ('HRR', False)]
```

One leg won and one leg lost, so the parlay lost. A winning parlay in the same fixture requires both legs to be `True`.

### d. Same-game vs cross-game split

Synthetic fixture scoreboard excerpt:

```text
### double_barrel_cross_game

| Split | Parlays graded | Parlays won | Ungraded | Leg W-L | Parlay hit rate | Expected independent | Correlation lift |
|---|---:|---:|---:|---:|---|---|---|
| all | 2 | 1 | 0 | 3-1 | insufficient data -- keep accumulating | – | – |
| same_game=True | 0 | 0 | 0 | 0-0 | insufficient data -- keep accumulating | – | – |
| same_game=False | 2 | 1 | 0 | 3-1 | insufficient data -- keep accumulating | – | – |
| 2 legs | 2 | 1 | 0 | 3-1 | insufficient data -- keep accumulating | – | – |
| 3 legs | 0 | 0 | 0 | 0-0 | insufficient data -- keep accumulating | – | – |

### traffic_jam

| Split | Parlays graded | Parlays won | Ungraded | Leg W-L | Parlay hit rate | Expected independent | Correlation lift |
|---|---:|---:|---:|---:|---|---|---|
| all | 30 | 12 | 1 | 38-22 (63.3%) | 40.0% | 40.0% | 0.0% |
| same_game=True | 30 | 12 | 1 | 38-22 (63.3%) | 40.0% | 40.0% | 0.0% |
| same_game=False | 0 | 0 | 0 | 0-0 | insufficient data -- keep accumulating | – | – |
| 2 legs | 30 | 12 | 1 | 38-22 (63.3%) | 40.0% | 40.0% | 0.0% |
| 3 legs | 0 | 0 | 0 | 0-0 | insufficient data -- keep accumulating | – | – |
```

### e. Small buckets

The two-parlay `double_barrel_cross_game` fixture prints:

```text
insufficient data -- keep accumulating
```

No percentage is reported below 30 graded parlays.

### f. Syntax checks

Commands:

```text
python3 backtest/test_backtest_mock.py
python3 -m py_compile backtest/calibration.py backtest/test_backtest_mock.py
python3 - <<'PY'
import ast
for path in ['backtest/calibration.py', 'backtest/test_backtest_mock.py']:
    ast.parse(open(path, encoding='utf-8').read())
    print(f'ast ok {path}')
PY
```

Output:

```text
ALL TESTS PASSED
ast ok backtest/calibration.py
ast ok backtest/test_backtest_mock.py
```
