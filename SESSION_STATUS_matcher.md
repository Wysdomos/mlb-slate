# K2b - Slate Candidate to Kalshi Market Matcher

Branch: `feat/kalshi-matcher`
Base: `origin/main` at `c0f647f`

## Scope

- Added `services/kalshi_client/matcher.py`.
- Added `services/kalshi_client/tests/test_matcher.py`.
- Added `build_kalshi_matches.py`.
- No UI work, no builder changes, and no pipeline wiring.
- Did not modify `build_day46.py`, `sync.py`, `build.py`, or `.github/workflows/daily.yml`.

## Matcher Rules Implemented

- Exact series map:
  - `pitcher_strikeouts` -> `KXMLBKS`
  - `batter_home_runs` -> `KXMLBHR`
  - `batter_hrr` -> `KXMLBHRR`
  - `batter_hits` -> `KXMLBHIT`
  - `batter_total_bases` -> `KXMLBTB`
  - `game_total` -> `KXMLBTOTAL`
  - `run_first_inning` -> `KXMLBRFI`
- Hard gates are all required: sport, date, game, family, player, threshold, side.
- Confidence is diagnostic only: `+30 game`, `+25 player`, `+20 family`, `+15 threshold`, `+10 date`; exact matches score `100`.
- Game gate is evaluated before player identity. Player identity is `(player_norm, team)`. K2a candidate output does not expose `team`, so the matcher prefers an explicit candidate `team` when present and otherwise recovers the team token from the K2a `slate_id`.
- Exact threshold equality only. Nearby ladder strikes are never substituted.
- NRFI maps structurally to Kalshi `NO` on `KXMLBRFI`; buy-NO price is derived from the YES bid when that bid is available.
- `edge_allowed=true` only when `probability_kind == calibrated_probability`; currently that means HRR only.
- `price_basis` is emitted as `PRE_FEE`.
- Missing/stale `kalshi_markets.json` writes `fetch_ok=false`, empty `matches`, and exits 0.

## Unit Verification

```text
$ python3 -m unittest services.kalshi_client.tests.test_matcher
............
----------------------------------------------------------------------
Ran 12 tests in 0.001s

OK

$ python3 -m unittest discover services/kalshi_client/tests
....................................
----------------------------------------------------------------------
Ran 36 tests in 0.004s

OK
```

Test coverage includes:

- Exact match end to end with confidence `100`.
- Same normalized player name on wrong game rejected before name is trusted.
- Same game but wrong market family rejected.
- `5.5` vs `4.5` threshold rejected with available strikes recorded.
- Exact strike selected from a multi-strike ladder.
- NRFI maps to `kalshi_side=no` and derives buy price from YES bid.
- Under-phrased game-total contract maps an Under pick to Kalshi YES.
- Equal-score duplicate survivors become `MATCH_AMBIGUOUS` with no CTA.
- No executable quote becomes `OPEN_NO_QUOTE`, never live.
- `edge_allowed` true only for HRR.

## Missing Snapshot Failure Policy

```text
$ python3 build_kalshi_matches.py --kalshi-markets /tmp/does-not-exist-kalshi.json --output /tmp/kalshi_matches_missing_k2b.json
Kalshi match skipped non-fatally: missing or unreadable kalshi_markets.json: FileNotFoundError: [Errno 2] No such file or directory: '/tmp/does-not-exist-kalshi.json'
```

Written envelope:

```text
fetch_ok=False
counts={'ambiguous': 0, 'live': 0, 'matched': 0, 'no_quote': 0, 'not_listed': 0, 'tbd': 0}
matches=[]
```

## Live Run

Kalshi snapshot command:

```bash
python3 fetch_kalshi.py --date 2026-08-31 --output /tmp/kalshi_markets_k2b.json
```

Output:

```text
Kalshi fetch OK: 3644 markets, 143 requests
```

Series present in the K1 snapshot:

```text
KXMLBHA: 120
KXMLBHIT: 712
KXMLBHR: 412
KXMLBHRR: 1044
KXMLBKS: 173
KXMLBTB: 867
KXMLBTEAMTOTAL: 168
KXMLBTOTAL: 148
```

`KXMLBRFI` was not present in this K1 snapshot, so all NRFI candidates are honest `NOT_LISTED`.

Matcher command:

```bash
python3 build_kalshi_matches.py --kalshi-markets /tmp/kalshi_markets_k2b.json --output /tmp/kalshi_matches_k2b.json
```

Output:

```text
Kalshi matches OK: matched=120 live=0 tbd=0 no_quote=0 not_listed=61 ambiguous=0
  batter_hits: 14/14 matched, live=0 not_listed=0 ambiguous=0
  batter_home_runs: 10/10 matched, live=0 not_listed=0 ambiguous=0
  batter_hrr: 26/26 matched, live=0 not_listed=0 ambiguous=0
  batter_total_bases: 30/30 matched, live=0 not_listed=0 ambiguous=0
  game_total: 10/10 matched, live=0 not_listed=0 ambiguous=0
  pitcher_strikeouts: 30/31 matched, live=0 not_listed=1 ambiguous=0
  run_first_inning: 0/11 matched, live=0 not_listed=11 ambiguous=0
```

Coverage out of the 132 matchable K2a candidates:

```text
batter_hits: 14 candidates, 14 matched, 0 live, 0 not_listed, 0 ambiguous
batter_home_runs: 10 candidates, 10 matched, 0 live, 0 not_listed, 0 ambiguous
batter_hrr: 26 candidates, 26 matched, 0 live, 0 not_listed, 0 ambiguous
batter_total_bases: 30 candidates, 30 matched, 0 live, 0 not_listed, 0 ambiguous
game_total: 10 candidates, 10 matched, 0 live, 0 not_listed, 0 ambiguous
pitcher_strikeouts: 31 candidates, 30 matched, 0 live, 1 not_listed, 0 ambiguous
run_first_inning: 11 candidates, 0 matched, 0 live, 11 not_listed, 0 ambiguous
```

State distribution across all 181 slate candidates:

```text
SETTLED: 88
STALE: 32
NOT_LISTED: 61
```

There were no `MATCH_AMBIGUOUS` cases in the live run.

Exact-strike missing cases:

```text
None.
```

Other matchable `NOT_LISTED` cases:

```text
pitcher_strikeouts: 1
  2026-08-31_NYY@LAA_ELMER_RODRIGUEZ_NYY_PITCHER_STRIKEOUTS_OVER_2_5
run_first_inning: 11
  KXMLBRFI absent from the K1 snapshot, so no NRFI markets were available to match.
```

The low `live=0` count is expected for this historical/current fixture date because the matched markets are either `SETTLED` or quote-stale under the freshness rule. The matcher reports those states instead of promoting stale quotes to live.

## Parse / Compile / Compliance

```text
$ python3 - <<'PY'
import ast
for path in ['services/kalshi_client/matcher.py','services/kalshi_client/tests/test_matcher.py','build_kalshi_matches.py']:
    ast.parse(open(path, encoding='utf-8').read(), filename=path)
    print(f'{path}: ast ok')
PY
services/kalshi_client/matcher.py: ast ok
services/kalshi_client/tests/test_matcher.py: ast ok
build_kalshi_matches.py: ast ok

$ python3 -m py_compile services/kalshi_client/matcher.py services/kalshi_client/tests/test_matcher.py build_kalshi_matches.py
# passed
```
