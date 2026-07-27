# SESSION_STATUS — Chapter H Market Expansion

Branch: `codex/chapter-h-markets`  
Base: `origin/main` at `d6115cc`  
Status: implemented, verified, pushed as draft PR.

## Ordered commits

1. `0320d60` — Retire 2B and SB boards to shadow picks
2. `7f8855e` — Add derived total bases board
3. `28585dd` — Add pitcher line columns to K board
4. `7255943` — Fetch Chapter H main prop lines
5. `7985a34` — Emit and grade expanded markets

## Verification

### a. 2B/SB absent from rendered HTML; still emitted

Command:

```bash
python3 -c "import json, collections; html=open('/tmp/chapterh-final-index.html').read(); picks=json.load(open('/tmp/chapterh-final-picks.json'))['picks']; c=collections.Counter(p['market'] for p in picks); print('rendered id=sb-board', 'id=\"sb-board\"' in html); print('rendered id=doubles-board', 'id=\"doubles-board\"' in html); print('nav href #sb-board', 'href=\"#sb-board\"' in html); print('nav href #doubles-board', 'href=\"#doubles-board\"' in html); print('shadow SB picks', c['SB']); print('shadow 2B picks', c['2B'])"
```

Output:

```text
rendered id=sb-board False
rendered id=doubles-board False
nav href #sb-board False
nav href #doubles-board False
shadow SB picks 20
shadow 2B picks 20
```

### b. TB board renders; three E_TB hand checks

Formula used:

```text
E_hits = P(1+ Hit) + P(2+ Hits)
E_TB   = E_hits + Doubles + (3 * HR)
```

Output:

```text
TB picks 30
Yordan Alvarez: 0.6377 + 0.3279 + 0.1920 + 3*0.2880 = 2.0216; emitted 2.0216
Byron Buxton: 0.6125 + 0.2840 + 0.1910 + 3*0.2650 = 1.8825; emitted 1.8825
Royce Lewis: 0.6216 + 0.2958 + 0.2250 + 3*0.2400 = 1.8624; emitted 1.8624
```

The `2+ Hits` runtime key check found exactly one matching column in `Hit_Probabilities`.

### c. K board new mobile columns

Screenshot artifact committed:

```text
docs/chapter-h/k-board-mobile.png
```

Column assertion:

```text
column groups True True
```

### d. Projection below line recommends Under

Mocked main line for Miles Mikolas outs:

```text
Under 18.5 outs True
16.0   Under 18.5 outs   Alt Under 20.5 outs
```

### e. Below threshold shows projection and line with no recommendation

Mocked main lines close to Kohl Drake projections:

```text
Line 5.1 · no play True
13.6   Line 13.5 · no play    4.9   Line 5.1 · no play
```

### f. No price rendered near alternate lines

Command:

```bash
python3 -c "import json,re; html=json.load(open('/tmp/chapterh-final-sections.json'))['k-board']; print(bool(re.search(r'Alt [^<]*(?:[+-]\\d{3}|odds|price)', html, re.I)))"
```

Output:

```text
False
```

Alternate markets are not requested. Alternate rows render direction and line only.

### g. Odds API absent/failed still builds green

Local env:

```text
ODDS_API_KEY set False
BDL_KEY set False
BPP_API_KEY prefix bpp_live_
```

No-prop-line build:

```text
Wrote 318 pick records -> /tmp/chapterh-no-odds-picks.json (+ slate_picks_7-26.json)
Built 17 sections
build green sections 17
k groups still render True
no-line cells 60
```

### h. Odds API request count per run

No local `ODDS_API_KEY`, so actual local request count is:

```text
Odds API Chapter H request count: 0 (no ODDS_API_KEY set)
```

Mocked `fetch_odds_api.fill_market_lines()` check:

```text
request_count 1
markets_param batter_total_bases,pitcher_hits_allowed,pitcher_outs
filled markets {'pitcher_hits_allowed': ['miles mikolas'], 'pitcher_outs': ['miles mikolas'], 'batter_total_bases': ['nolan gorman']}
```

`fetch_props.py` now logs `Odds API Chapter H request count: N` and writes `oddsapi_extra_market_request_count` into `k_props.json` metadata when the key is present.

### i. TB and both alt markets grade clean against a real box score date

Used live MLB Stats API date `2025-07-25` through the existing backfill grading function, without rewriting `backtest/graded_picks.json`.

```text
batters 320 pitchers 136
sample batter jackson chourio {'h': 1, 'hr': 1, 'r': 1, 'rbi': 1, 'sb': 0, 'd': 0, 't': 0}
sample pitcher tobias myers {'k': 1, 'h': 0, 'er': 0, 'outs': 3}
TB (True, '4 TB')
H_ALLOWED_ALT (True, '0 H allowed')
OUTS_ALT (True, '3 outs')
```

New copied fields in graded rows: `projection`, `main_line`, `direction`, `alt_margin`.

### j. Empty critical tabs degrade without crash

Empty `Park_Factors`:

```text
Wrote 299 pick records -> /tmp/chapterh-empty-parks-picks2.json (+ slate_picks_7-26.json)
Built 17 sections
park-board: 638 bytes
build ok sections 17
park unavailable True
tb-board ok True
```

Additional empty-tab checks:

```text
SP_Projections ok 17 k 2119 tb 6418
BP_Batters ok 17 k 23070 tb 635
BP_Pitchers ok 17 k 20760 tb 6418
```

### k. Projected Mode still builds

Temporary `_mode='projected'` build:

```text
Wrote 170 pick records -> /tmp/chapterh-projected-picks.json (+ slate_picks_7-26.json)
Built 17 sections
projected build sections 17
k-board True 23295
tb-board True 6605
projected badge on TB True
```

### l. Compliance, ast.parse, py_compile

Compliance:

```text
BPP compliance OK (0 changed JSON/HTML files checked against d6115ccf95db)
```

AST:

```text
ast ok build_day46.py
ast ok sync.py
ast ok fetch_props.py
ast ok fetch_odds_api.py
ast ok grade_results.py
ast ok backtest/backfill_grades.py
ast ok backtest/calibration.py
```

Py compile:

```bash
python3 -m py_compile build_day46.py sync.py fetch_props.py fetch_odds_api.py grade_results.py backtest/backfill_grades.py backtest/calibration.py
```

Exit code: `0`.

## Historical-file safety

Command:

```bash
git diff --name-only -- 'slate_picks*.json' 'backtest/graded_picks.json'
```

Output was empty. No historical `slate_picks*.json` or `backtest/graded_picks.json` file was modified.

## Addendum — Total Bases HR Header Accessor

`BP_Batters` workbook header checked directly from `MLB Slate 7-26-26.xlsx`:

```text
... Doubles, Triples, HomeRuns, RBIs, Runs, ...
```

`build_day46.py` now reads batter HR projection through a normalized required accessor accepting `HomeRuns` and `HR`. These normalize to distinct keys (`homeruns`, `hr`). If neither spelling is present, it raises instead of silently treating HR as `0`.

Loud-failure check with both accepted HR spellings removed from a temporary `BP_Batters` copy:

```text
RuntimeError: BP_Batters is missing required home runs column; accepted spellings: HomeRuns, HR
```

Workbook-mode E_TB hand checks after the accessor change:

```text
mode workbook
Yordan Alvarez: 0.6377 + 0.3279 + 0.1920 + 3*0.2880 = 2.0216; emitted 2.0216
Byron Buxton: 0.6125 + 0.2840 + 0.1910 + 3*0.2650 = 1.8825; emitted 1.8825
Royce Lewis: 0.6216 + 0.2958 + 0.2250 + 3*0.2400 = 1.8624; emitted 1.8624
```

Follow-up correction: removed duplicate normalized accepted spelling `Home Runs`; accepted keys are now `HomeRuns` and `HR`.

Workbook-mode E_TB checks after the accepted-key correction:

```text
mode workbook
Yordan Alvarez: 0.6377 + 0.3279 + 0.1920 + 3*0.2880 = 2.0216; emitted 2.0216
Byron Buxton: 0.6125 + 0.2840 + 0.1910 + 3*0.2650 = 1.8825; emitted 1.8825
Royce Lewis: 0.6216 + 0.2958 + 0.2250 + 3*0.2400 = 1.8624; emitted 1.8624
```
