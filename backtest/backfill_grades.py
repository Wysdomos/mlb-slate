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
from shadow_chips import CHIP_FIELDS

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


def pick_source(p):
    return p.get('pick_source', 'workbook') or 'workbook'


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
            row = {
                'date': date_iso,
                'market': p.get('market'),
                'pick_source': pick_source(p),
                'name': p.get('name') or p.get('game') or p.get('pick', ''),
                'line': p.get('line', ''),
                'win_at': p.get('win_at'),
                'consensus': p.get('consensus', 0),
                'consensus_max': p.get('consensus_max', 6),
                'win': win,
                'got': got,
            }
            for field in CHIP_FIELDS:
                row[field] = p.get(field, None)
            store['graded'].append(row)
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
