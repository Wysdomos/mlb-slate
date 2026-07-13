# HANDOFF — Backtest Foundation (feat/backtest-foundation)
**The Daily Slate · Product Era, Chapter 2 · 2026-07-13**
**Executor: Claude Code on the M5.** Independent of the odds PR — different paths, zero conflicts, can run in parallel.

## ⛔ GUARDRAILS
1. Open the PR, then **STOP**. Developer merges; nobody else.
2. `backfill_grades.py` and `calibration.py` NEED network (statsapi.mlb.com) — that's fine on the M5, that's why this runs here.
3. Grading rules mirror `grade_results.py` exactly. If they ever diverge, that's a bug in this package, not the live grader.
4. No invented data: pushes stay ungraded, absent players stay ungraded, no historical odds are fabricated.

## WHAT THIS DELIVERS
The site computes pick-level grades nightly, shows them once, and overwrites them — 10 of 11 slate days survive only as W/L totals. This package: **(1)** replays every `slate_picks_*.json` against real box scores using the live grader's own fetchers (`backfill_grades.py`), **(2)** renders `CALIBRATION.md` — hit rate by consensus bucket per market with 95% Wilson intervals (`calibration.py`), **(3)** ships the pybaseball data-access layer for the M5 (`data_access.py`, cached to CSV), **(4)** commits the Product Era roadmap. 21 offline assertions + 2 cache-layer checks already green in the build sandbox.

## FILES — exact tested bytes (also create empty `backtest/__init__.py`)

### `backtest/backfill_grades.py`
`5456 bytes · md5 15baf3c9656478af480277b2d8afc59c`

```python
"""Backfill pick-level grades for every slate_picks_*.json in the repo.

Runs where the network is open (M5 or GitHub Actions) -- NOT the sandbox.
Reuses grade_results.py's own fetchers and mirrors its grading rules exactly,
so backfilled grades match what the live site would have shown.

Output: backtest/graded_picks.json  {"graded": [row...], "dates": {...}}
Resumable: dates already present are skipped (delete the file to regrade).

Usage (from repo root):  python3 backtest/backfill_grades.py
Env: BDL_KEY optional (balldontlie primary, MLB Stats API fallback).
"""
import json
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grade_results as G   # fetch_bdl, fetch_box_results, fetch_games, norm, gamekey

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'graded_picks.json')
BDL_KEY = os.environ.get('BDL_KEY', '')


def grade_pick(p, box):
    """Exact mirror of grade_results.grade() per-market rules.
    Returns (win, got): win is True/False, or None when ungradeable/push."""
    mkt = p.get('market')
    nm = G.norm(p['name']) if p.get('name') else ''
    win, got = None, '—'
    if mkt == 'HR':
        b = box.get('batters', {}).get(nm)
        if b is not None:
            win = b['hr'] >= 1
            got = 'HR' if win else '0 HR'
    elif mkt == 'TOTAL':
        tot = box.get('totals', {}).get(G.gamekey(p.get('game', '')))
        if tot is not None and p.get('ref_line'):
            line = float(p.get('ref_line'))
            lean = (p.get('lean') or 'OVER').upper()
            if tot == line:
                got = f'{tot} runs · push'          # push stays ungraded
            else:
                over = tot > line
                win = over if lean == 'OVER' else (not over)
                got = f'{tot} runs'
    elif mkt == 'NRFI':
        fi = box.get('first_inning', {}).get(G.gamekey(p.get('game', '')))
        if fi is not None:
            scored = fi >= 1
            lean = (p.get('lean') or 'NRFI').upper()
            win = (not scored) if lean == 'NRFI' else scored
            got = '0 in 1st' if not scored else f'{fi} in 1st'
    else:
        b = box.get('batters', {}).get(nm, {})
        pi = box.get('pitchers', {}).get(nm, {})
        if mkt == 'HIT' and b:
            win = b['h'] >= 1; got = f"{b['h']} H"
        elif mkt == 'HRR' and b:
            s = b['h'] + b['r'] + b['rbi']
            win = s >= 1; got = f'{s} H+R+RBI'
        elif mkt == 'SB' and b:
            win = b['sb'] >= 1; got = f"{b['sb']} SB"
        elif mkt == '2B' and b:
            win = b['d'] >= 1; got = f"{b['d']} 2B"
        elif mkt == 'K' and pi:
            win = pi['k'] >= p.get('win_at', 99); got = f"{pi['k']} K"
    return win, got


def fetch_box(date_iso):
    box = {}
    if BDL_KEY:
        box = G.fetch_bdl(date_iso, BDL_KEY)
        if not box.get('batters') and not box.get('pitchers'):
            print('  balldontlie empty -- falling back to MLB Stats API')
            box = G.fetch_box_results(date_iso)
    else:
        box = G.fetch_box_results(date_iso)
    if not isinstance(box, dict):
        box = {}
    for k in ('batters', 'pitchers', 'totals', 'first_inning'):
        box.setdefault(k, {})
    games = G.fetch_games(date_iso)
    box['totals'].update(games.get('totals', {}))
    box['first_inning'].update(games.get('first_inning', {}))
    return box


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    store = {'graded': [], 'dates': {}}
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            store = json.load(f)
    done = set(store['dates'])

    files = sorted(glob.glob(os.path.join(repo, 'slate_picks_*.json')))
    print(f'{len(files)} slate files · {len(done)} date(s) already backfilled')
    for path in files:
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)
        date_iso = payload.get('slate_date')
        picks = payload.get('picks', [])
        if not date_iso or date_iso in done:
            continue
        print(f'-- {date_iso}: {len(picks)} picks')
        box = fetch_box(date_iso)
        if not box['batters'] and not box['pitchers'] and not box['totals']:
            print('   no box data returned -- skipping (rerun later)')
            continue
        n_graded = 0
        for p in picks:
            win, got = grade_pick(p, box)
            store['graded'].append({
                'date': date_iso,
                'market': p.get('market'),
                'name': p.get('name') or p.get('game') or p.get('pick', ''),
                'line': p.get('line', ''),
                'win_at': p.get('win_at'),
                'consensus': p.get('consensus', 0),
                'consensus_max': p.get('consensus_max', 6),
                'win': win,
                'got': got,
            })
            n_graded += win is not None
        store['dates'][date_iso] = {'picks': len(picks), 'graded': n_graded}
        print(f'   graded {n_graded}/{len(picks)}')
        time.sleep(1)   # be polite to statsapi between dates

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(store, f)
    total = len(store['graded'])
    gradable = sum(1 for g in store['graded'] if g['win'] is not None)
    print(f'\nwrote {OUT}: {total} rows, {gradable} gradable, {len(store["dates"])} dates')


if __name__ == '__main__':
    main()

```

### `backtest/calibration.py`
`4691 bytes · md5 755c137649f8866fc1466f6761f7bec8`

```python
"""Calibration report from backfilled pick grades. Fully offline.

Reads backtest/graded_picks.json, writes backtest/CALIBRATION.md.
Answers one question per market: when the slate says "play this",
how often does it actually hit -- overall, and by consensus strength?

No odds are invented. A break-even reference table for common American
prices is included so hit rates can be eyeballed against real books.

Usage (from repo root):  python3 backtest/calibration.py
"""
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'graded_picks.json')
OUT = os.path.join(HERE, 'CALIBRATION.md')

MARKET_ORDER = ['K', 'HR', 'HIT', 'HRR', '2B', 'SB', 'NRFI', 'TOTAL']
BANDS = [(5, 6, '5-6 lenses'), (4, 4, '4 lenses'), (0, 3, '<=3 lenses')]


def wilson(w, n, z=1.96):
    """95% Wilson score interval for a hit rate -- honest at small n."""
    if n == 0:
        return (0.0, 0.0)
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def line(w, l, label):
    n = w + l
    if n == 0:
        return f'| {label} | – | – | – | – |'
    lo, hi = wilson(w, n)
    flag = ' ⚠ small n' if n < 30 else ''
    return (f'| {label} | {w}-{l} | {n} | **{w / n:.1%}** | '
            f'{lo:.0%}–{hi:.0%}{flag} |')


def build(store):
    rows = [g for g in store['graded'] if g['win'] is not None]
    dates = store.get('dates', {})
    md = []
    md.append('# The Daily Slate — Calibration Report')
    md.append(f"\n*{len(rows)} graded picks across {len(dates)} slate days "
              f"({min(dates)} → {max(dates)}). Pushes and ungradeable picks "
              f"excluded. Intervals are 95% Wilson.*\n")

    by_mkt = defaultdict(list)
    for g in rows:
        by_mkt[g['market']].append(g)

    md.append('## Overall by market\n')
    md.append('| Market | W-L | n | Hit rate | 95% CI |')
    md.append('|---|---|---|---|---|')
    for mkt in MARKET_ORDER:
        sub = by_mkt.get(mkt, [])
        w = sum(1 for g in sub if g['win'])
        md.append(line(w, len(sub) - w, mkt))

    for mkt in MARKET_ORDER:
        sub = by_mkt.get(mkt, [])
        if not sub:
            continue
        md.append(f'\n## {mkt} — by consensus\n')
        md.append('| Bucket | W-L | n | Hit rate | 95% CI |')
        md.append('|---|---|---|---|---|')
        for lo, hi, label in BANDS:
            band = [g for g in sub if lo <= g['consensus'] <= hi]
            w = sum(1 for g in band if g['win'])
            md.append(line(w, len(band) - w, label))
        if mkt == 'K':
            md.append(f'\n### {mkt} — by line (win_at)\n')
            md.append('| Line | W-L | n | Hit rate | 95% CI |')
            md.append('|---|---|---|---|---|')
            lines = sorted({g.get('win_at') for g in sub if g.get('win_at')})
            for wa in lines:
                band = [g for g in sub if g.get('win_at') == wa]
                w = sum(1 for g in band if g['win'])
                md.append(line(w, len(band) - w, f'O {wa - 0.5}'))

    md.append('\n## Break-even reference (for eyeballing edge)\n')
    md.append('*Reference math only — historical book prices were not stored, '
              'so no edge is claimed. Compare a bucket\'s hit rate to the '
              'break-even of the price you actually see.*\n')
    md.append('| Price | Break-even hit rate |')
    md.append('|---|---|')
    for am in (-200, -150, -110, 100, 150, 250, 400):
        be = (-am) / (-am + 100) if am < 0 else 100 / (am + 100)
        md.append(f'| {am:+d} | {be:.1%} |')

    md.append('\n## Reading this honestly\n')
    md.append('A bucket only means something once n clears ~30; below that '
              'the interval says more than the point estimate. If a high-'
              'consensus bucket does not clearly beat a low one, the consensus '
              'signal is not separating -- that is a finding, not a failure. '
              'This report is the gate for the XGBoost question: models only '
              'earn a seat if these buckets leave measurable room.\n')
    return '\n'.join(md) + '\n'


def main():
    if not os.path.exists(SRC):
        raise SystemExit('backtest/graded_picks.json missing -- run '
                         'backtest/backfill_grades.py first (needs network).')
    with open(SRC, encoding='utf-8') as f:
        store = json.load(f)
    report = build(store)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'wrote {OUT} ({len(report)} bytes)')


if __name__ == '__main__':
    main()

```

### `backtest/data_access.py`
`2614 bytes · md5 a7438bf34a97c0b37ac0da6150dfe1e7`

```python
"""pybaseball access layer for backtesting -- The Daily Slate.

This is the project's "pybaseball API": not a server (doctrine: AI writes,
Python runs, GitHub hosts), but one clean module every backtest script goes
through. Runs on the M5 where pybaseball is installed; every pull is cached
to backtest/cache/ as CSV so repeat runs cost zero network and stay
reproducible.

Usage (M5, from repo root):
    pip install pybaseball pandas
    python3 -c "from backtest.data_access import pitcher_game_logs;
                print(pitcher_game_logs(2026).shape)"
"""
import os

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')


def _cached(name, fetch, loader=None, saver=None):
    """Disk-cache a DataFrame pull. fetch() runs only on cache miss."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name + '.csv')
    if os.path.exists(path):
        if loader is None:
            import pandas as pd
            loader = pd.read_csv
        return loader(path)
    df = fetch()
    if saver is None:
        saver = lambda d, p: d.to_csv(p, index=False)
    saver(df, path)
    return df


def _pb():
    try:
        import pybaseball
        pybaseball.cache.enable()
        return pybaseball
    except ImportError:
        raise SystemExit('pybaseball not installed -- run on the M5: '
                         'pip install pybaseball pandas')


def pitcher_game_logs(season):
    """Per-start pitching logs for a season (K, IP, H, ER by date).
    Feeds K-market calibration slices (line difficulty, rest, opponent)."""
    return _cached(f'pitching_{season}',
                   lambda: _pb().pitching_stats_range(
                       f'{season}-03-01', f'{season}-11-30'))


def batter_game_logs(season):
    """Per-game batting logs for a season (HR, H, RBI, SB, 2B by date).
    Feeds HR/HIT/HRR calibration slices."""
    return _cached(f'batting_{season}',
                   lambda: _pb().batting_stats_range(
                       f'{season}-03-01', f'{season}-11-30'))


def statcast_pitcher_percentiles(season):
    """Savant expected stats (xERA, xwOBA, hard-hit) for pitcher context.
    Backs the VulnScore-vs-expected-stats comparison."""
    return _cached(f'statcast_exp_pitch_{season}',
                   lambda: _pb().statcast_pitcher_expected_stats(season))


def statcast_batter_percentiles(season):
    """Savant expected stats (barrel%, xSLG) for batter context.
    Backs the RBI+ and HR-board enrichment work."""
    return _cached(f'statcast_exp_bat_{season}',
                   lambda: _pb().statcast_batter_expected_stats(season))

```

### `backtest/test_backtest_mock.py`
`4198 bytes · md5 c5c019e3618e674758615e3199b16e81`

```python
"""Offline verification of backfill grading rules + calibration report.
No network. Run from repo root:  python3 backtest/test_backtest_mock.py"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.backfill_grades import grade_pick
from backtest import calibration

ok = True


def run(label, cond):
    global ok
    print(('PASS ' if cond else 'FAIL ') + label)
    ok = ok and cond


BOX = {
    'batters': {
        'ben rice':      {'hr': 1, 'h': 2, 'r': 1, 'rbi': 2, 'sb': 0, 'd': 1},
        'heliot ramos':  {'hr': 0, 'h': 0, 'r': 0, 'rbi': 0, 'sb': 0, 'd': 0},
        'jose caballero': {'hr': 0, 'h': 0, 'r': 1, 'rbi': 0, 'sb': 2, 'd': 0},
    },
    'pitchers': {
        'sean burke':   {'k': 5, 'h': 4, 'er': 2, 'outs': 18},
        'kyle freeland': {'k': 4, 'h': 7, 'er': 4, 'outs': 15},
    },
    'totals': {'KC@WSH': 9.0, 'PHI@CIN': 8.5},
    'first_inning': {'KC@WSH': 0, 'PHI@CIN': 2},
}

# --- batter markets ---------------------------------------------------------
run('HR hit', grade_pick({'market': 'HR', 'name': 'Ben Rice'}, BOX) == (True, 'HR'))
run('HR miss', grade_pick({'market': 'HR', 'name': 'Heliot Ramos'}, BOX) == (False, '0 HR'))
run('HR absent -> ungraded',
    grade_pick({'market': 'HR', 'name': 'Not In Box'}, BOX)[0] is None)
run('HIT hit', grade_pick({'market': 'HIT', 'name': 'Ben Rice'}, BOX) == (True, '2 H'))
w, got = grade_pick({'market': 'HRR', 'name': 'Jose Caballero'}, BOX)
run('HRR: run-only still counts (h+r+rbi>=1)', w is True and got == '1 H+R+RBI')
run('HRR miss', grade_pick({'market': 'HRR', 'name': 'Heliot Ramos'}, BOX)[0] is False)
run('SB hit', grade_pick({'market': 'SB', 'name': 'Jose Caballero'}, BOX) == (True, '2 SB'))
run('2B hit', grade_pick({'market': '2B', 'name': 'Ben Rice'}, BOX) == (True, '1 2B'))

# --- K boundary -------------------------------------------------------------
run('K exact win_at wins',
    grade_pick({'market': 'K', 'name': 'Sean Burke', 'win_at': 5}, BOX) == (True, '5 K'))
run('K one short loses',
    grade_pick({'market': 'K', 'name': 'Kyle Freeland', 'win_at': 5}, BOX)[0] is False)
run('K missing win_at never false-wins',
    grade_pick({'market': 'K', 'name': 'Sean Burke'}, BOX)[0] is False)

# --- game markets -----------------------------------------------------------
run('TOTAL over wins', grade_pick(
    {'market': 'TOTAL', 'game': 'KC@WAS', 'ref_line': '8.5', 'lean': 'OVER'}, BOX)[0] is True)
run('TOTAL under on 9>8.5 loses', grade_pick(
    {'market': 'TOTAL', 'game': 'KC@WAS', 'ref_line': '8.5', 'lean': 'UNDER'}, BOX)[0] is False)
w, got = grade_pick({'market': 'TOTAL', 'game': 'PHI@CIN', 'ref_line': '8.5', 'lean': 'OVER'}, BOX)
run('TOTAL exact push stays ungraded', w is None and 'push' in got)
run('NRFI clean first wins', grade_pick(
    {'market': 'NRFI', 'game': 'KC@WAS', 'lean': 'NRFI'}, BOX) == (True, '0 in 1st'))
run('YRFI on 2-run first wins', grade_pick(
    {'market': 'NRFI', 'game': 'PHI@CIN', 'lean': 'YRFI'}, BOX) == (True, '2 in 1st'))

# --- calibration report on synthetic history --------------------------------
graded = []
for i in range(40):   # HR 5-6 bucket: 12W-28L = 30%
    graded.append({'date': '2026-06-15', 'market': 'HR', 'name': f'p{i}',
                   'consensus': 6, 'consensus_max': 6, 'win': i < 12,
                   'line': 'Ov 0.5', 'got': ''})
for i in range(10):   # K O 4.5 small sample: 7W-3L
    graded.append({'date': '2026-06-16', 'market': 'K', 'name': f'k{i}',
                   'consensus': 4, 'consensus_max': 5, 'win': i < 7,
                   'win_at': 5, 'line': 'O 5+', 'got': ''})
store = {'graded': graded,
         'dates': {'2026-06-15': {}, '2026-06-16': {}}}
report = calibration.build(store)
run('report: HR 30% bucket rendered', '**30.0%**' in report)
run('report: K by-line section present', 'O 4.5' in report)
run('report: small-n flag on K', '⚠ small n' in report)
run('report: break-even table sane (-110 -> 52.4%)', '52.4%' in report)
lo, hi = calibration.wilson(12, 40)
run('wilson CI sane for 12/40', 0.17 < lo < 0.20 and 0.44 < hi < 0.48)

print('\n' + ('ALL TESTS PASSED' if ok else 'FAILURES PRESENT'))
sys.exit(0 if ok else 1)

```

### `backtest/ROADMAP.md`
`3243 bytes · md5 dbcf394719da368fda2f566f91c6f0ec`

```markdown
# The Daily Slate — Product Era Roadmap
*Committed so every AI in the orchestra builds against the same map.
Source: external skill-stack research, absorbed 2026-07-13, filtered
through project doctrine (serverless, AI writes / Python runs, no
invented data).*

## Doctrine filter on the research
**Adopted**
- **Calibration discipline** — hit-rate-by-bucket with confidence
  intervals is the gate for every modeling decision. Deliverable:
  `backtest/CALIBRATION.md`, regenerated as history grows.
- **Edge math** — once real book lines flow (Odds API), every pick gets
  implied probability vs. our number. No stored price, no edge claim.
- **Tree models (XGBoost/LightGBM), conditionally** — only if the
  calibration report shows consensus buckets leave measurable room.
  Measurement era before model era.
- **True-talent regression** — regress streaks toward long-run skill;
  upgrade path for the Streaks page and RBI+.
- **pybaseball as the historical data layer** — via
  `backtest/data_access.py` only (cached, reproducible). Runs on M5.

**Skipped, on doctrine**
- Postgres / Airflow / Streamlit — Actions is the scheduler, Pages is
  the dashboard, flat JSON is the database. SQLite if backtest queries
  ever hurt.
- FastAPI in production/CI — skipped. *Amended 2026-07-13:* a read-only
  service bound to 127.0.0.1 on the M5 (`services/pybaseball_api`) is
  in-lane as a research tool. It must consume the shared data layer
  (`backtest/data_access.py`), never bypass it.
- Web scraping — API-first, always.
- Deep learning / pitch-sequence models — benched; sample size and
  maintenance cost don't justify marginal edge yet.

## Chapter sequence
1. **Odds API K-prop fallback** — built, reviewed, 36 assertions green.
   Awaiting PR flow (see HANDOFF_OddsAPI_Fallback.md). Key-gated; inert
   without secret.
2. **Backtest foundation** (this directory) — `backfill_grades.py`
   replays all slate days against real box scores (M5/Actions, network
   needed); `calibration.py` renders the report offline. 21 offline
   assertions green.
3. **pybaseball enrichment** (M5) — join `data_access.py` pulls onto
   graded picks: slice calibration by park, handedness, line height,
   rest. Answers *where* the signal lives, not just whether.
4. **Savant expansion** — barrel / hard-hit / xSLG / xERA into
   fetch_phase2.py (keyless).
5. **OpenMeteo weather** — park-adjusted context for TOTAL/HR boards.
6. **RBI+ formula** — ships after calibration baseline exists, so its
   lift is measurable, not vibes.
7. **Model question** — XGBoost seat decided by the calibration report.
8. **Alt-parlay revamp** — K combos tiers 0–2, HRR vs high hits-allowed,
   Anchor parlays require DANGER label, max 2× same player.

## Standing rules for this directory
- Grading rules mirror `grade_results.py` exactly — if the live grader
  changes, `backfill_grades.grade_pick` changes in the same PR.
- `graded_picks.json` is append-only by date; delete to regrade.
- No historical odds exist for old picks: reports show hit rates and a
  break-even reference table, never fabricated edges.
- Every file here ships with offline tests. Network code runs on M5 or
  in Actions, never assumed in the sandbox.

```

---

## EXECUTION STEPS (from repo root)
```bash
cd ~/mlb-slate && git checkout main && git pull
git checkout -b feat/backtest-foundation
mkdir -p backtest && touch backtest/__init__.py
# 1) Write the five files above at their exact paths
# 2) Verify bytes:
md5 backtest/*.py backtest/ROADMAP.md
# 3) Offline gates:
python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('backtest/*.py')]; print('ast OK')"
python3 backtest/test_backtest_mock.py        # expect: ALL TESTS PASSED (21)
# 4) The payoff (network -- M5 only):
python3 backtest/backfill_grades.py           # replays all 11 slate days
python3 backtest/calibration.py               # writes backtest/CALIBRATION.md
# 5) Commit EVERYTHING including the generated dataset + report:
git add backtest/
git commit -m "feat: backtest foundation -- backfilled pick grades + first calibration report"
git push -u origin feat/backtest-foundation
gh pr create --title "Backtest foundation + first calibration report" --body "Recovers 11 days of pick-level grades; renders calibration by consensus bucket. 21 offline assertions green. Rules mirror grade_results.py exactly."
# >>> STOP. Post PR link + paste the 'Overall by market' table from CALIBRATION.md. <<<
```

## VERIFICATION CHECKLIST
- [ ] md5 of all 5 files matches
- [ ] `ast OK` · `ALL TESTS PASSED` (21)
- [ ] backfill printed graded counts for all 11 dates (rerun later for any date that returned no box data)
- [ ] `backtest/CALIBRATION.md` + `backtest/graded_picks.json` committed in the PR
- [ ] PR opened, link + Overall table posted, **no merge**

## ROLLBACK
Revert the PR. Nothing outside `backtest/` is touched; the daily pipeline never imports it.
