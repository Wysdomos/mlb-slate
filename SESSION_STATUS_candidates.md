# K2a - Slate-Side Candidate Contract

Branch: `feat/slate-candidates`
Base before work: `ab4b503`

## Scope

- Added `services/kalshi_client/candidates.py`.
- Added `services/kalshi_client/tests/test_candidates.py`.
- No Kalshi matching, no UI work, and no workflow/build wiring.
- Did not modify `build_day46.py`, `sync.py`, `build.py`, or `.github/workflows/daily.yml`.

## Candidate Normalization

The normalizer emits the requested slate-side candidate contract:

- `slate_id`
- `slate_date`
- `game_key`
- `away_team`
- `home_team`
- `player`
- `player_norm`
- `market_type`
- `direction`
- `threshold`
- `display_line`
- `probability_kind`
- `consensus`
- `matchable`

Unsupported or unresolved rows also carry `reason` so failures are auditable.

## Line Parsing

Explicit test coverage includes:

- `O 5+` -> `over 4.5`
- `O 2.5` -> `over 2.5`
- `O 3.5` -> `over 3.5`
- `Ov 0.5 HR` -> `over 0.5`
- `Over 13.5 outs`
- `Under 19.5 outs`
- `Under 8.5 H allowed`
- `Ov 2.5 ER`

Unit labels are stripped before numeric parsing. The `N+` rule is only applied when the line has a plus suffix.

## TOTAL / NRFI

- `NRFI` normalizes to `market_type=run_first_inning`, `direction=no`, `threshold=None`.
- `TOTAL` rows with `line=None` resolve the numeric threshold from `slate_picks.ref_line` on the current slate. `day_data.json` / `BP_Games` is used to resolve the game and home/away order, but the current `BP_Games` rows do not carry a total-line field. The normalizer also supports fallback parsing from probability keys such as `p_over_8_5`.
- If a `TOTAL` threshold or direction cannot be resolved, the row is `matchable=false`; it does not guess.

## Home/Away Resolution

`game_key` is resolved from `day_data.json` / `BP_Games` and emitted as `AWAY@HOME`. The tests use a real current slate `BP_Games` row and verify the candidate game key matches the game-data order, not the pick's `team` / `opp` ordering.

## Live Slate Report

Command:

```bash
python3 - <<'PY'
import json
from collections import Counter
from services.kalshi_client.candidates import build_candidates, report
slate=json.load(open('slate_picks.json', encoding='utf-8'))
day=json.load(open('day_data.json', encoding='utf-8'))
c=[x.as_dict() for x in build_candidates(slate, day)]
r=report(c)
print('total', r['total'])
print('matchable', r['matchable'])
print('per_market')
for market, bucket in sorted(r['by_market'].items()):
    print(f"{market}: total={bucket['total']} matchable={bucket['matchable']}")
print('failed_count', len(r['failed']))
print('failed_by_reason')
for reason, count in sorted(Counter(f['reason'] for f in r['failed']).items()):
    print(f'{reason}: {count}')
print('parse_failures')
for f in r['failed']:
    if f['reason'] != 'no_kalshi_series':
        print(json.dumps(f, sort_keys=True))
print('sample_matchable')
for row in c:
    if row['matchable']:
        print(json.dumps(row, sort_keys=True))
        break
PY
```

Output:

```text
total 181
matchable 132
per_market
2b: total=20 matchable=0
batter_hits: total=14 matchable=14
batter_home_runs: total=10 matchable=10
batter_hrr: total=26 matchable=26
batter_total_bases: total=30 matchable=30
er_allowed: total=2 matchable=0
game_total: total=12 matchable=10
h_allowed: total=2 matchable=0
h_allowed_alt: total=1 matchable=0
outs_alt: total=2 matchable=0
pitcher_strikeouts: total=31 matchable=31
run_first_inning: total=11 matchable=11
sb: total=20 matchable=0
failed_count 49
failed_by_reason
missing_direction: 2
no_kalshi_series: 47
parse_failures
{"display_line": null, "market_type": "game_total", "reason": "missing_direction", "slate_id": "2026-08-31_DET@MIN_GAME_TOTAL_NONE_8_5"}
{"display_line": null, "market_type": "game_total", "reason": "missing_direction", "slate_id": "2026-08-31_PHI@AZ_GAME_TOTAL_NONE_8_5"}
sample_matchable
{"away_team": "SEA", "consensus": 5, "direction": "over", "display_line": "O 5+", "game_key": "SEA@BOS", "home_team": "BOS", "market_type": "pitcher_strikeouts", "matchable": true, "player": "Payton Tolle", "player_norm": "payton tolle", "probability_kind": "projection_only", "reason": null, "slate_date": "2026-08-31", "slate_id": "2026-08-31_SEA@BOS_PAYTON_TOLLE_BOS_PITCHER_STRIKEOUTS_OVER_4_5", "threshold": 4.5}
```

Expected matchable count was approximately 134. The actual count is 132 because two `TOTAL` rows are neutral rows with a resolved threshold (`8.5`) but no over/under direction. Those are intentionally marked `matchable=false` with `reason=missing_direction`; matching either side would be a guess.

Unsupported no-series rows:

- `SB`: 20
- `2B`: 20
- `OUTS_ALT`: 2
- `H_ALLOWED`: 2
- `H_ALLOWED_ALT`: 1
- `ER_ALLOWED`: 2

## Verification

```text
$ python3 -m unittest services.kalshi_client.tests.test_candidates
.........
----------------------------------------------------------------------
Ran 9 tests in 0.002s

OK

$ python3 -m unittest discover services/kalshi_client/tests
........................
----------------------------------------------------------------------
Ran 24 tests in 0.003s

OK

$ python3 - <<'PY'
import ast
for path in ['services/kalshi_client/candidates.py','services/kalshi_client/tests/test_candidates.py']:
    ast.parse(open(path, encoding='utf-8').read(), filename=path)
    print(f'{path}: ast ok')
PY
services/kalshi_client/candidates.py: ast ok
services/kalshi_client/tests/test_candidates.py: ast ok

$ python3 -m py_compile services/kalshi_client/candidates.py services/kalshi_client/tests/test_candidates.py
# passed

$ python3 tools/check_bpp_compliance.py
BPP compliance OK (0 changed JSON/HTML files checked against ab4b50302c4c)
```
