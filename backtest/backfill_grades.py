"""Backfill pick-level grades for every slate_picks_*.json in the repo.

Runs where the network is open (M5 or GitHub Actions) -- NOT the sandbox.
Reuses grade_results.py's own fetchers and mirrors its grading rules exactly,
so backfilled grades match what the live site would have shown.

Output: backtest/graded_picks.json  {"graded": [row...], "dates": {...}}
Resumable: dates already present are skipped (delete the file to regrade).

Usage (from repo root):  python3 backtest/backfill_grades.py [YYYY-MM-DD ...]
With date arguments, only those slate dates are processed.
Env: BDL_KEY optional (MLB Stats API primary, balldontlie fallback).
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
    def directional(actual):
        direction = (p.get('direction') or 'Over').lower()
        target = p.get('win_at')
        if target is None:
            return None
        return actual <= target if direction == 'under' else actual >= target

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
        elif mkt == 'TB' and b:
            tb = b['h'] + b['d'] + (2 * b.get('t', 0)) + (3 * b['hr'])
            win = tb >= p.get('win_at', 99); got = f'{tb} TB'
        elif mkt == 'K' and pi:
            win = pi['k'] >= p.get('win_at', 99); got = f"{pi['k']} K"
        elif mkt == 'OUTS' and pi:
            win = pi['outs'] >= p.get('win_at', 99); got = f"{pi['outs']} outs"
        elif mkt == 'H_ALLOWED' and pi:
            win = pi['h'] >= p.get('win_at', 99); got = f"{pi['h']} H allowed"
        elif mkt == 'OUTS_ALT' and pi:
            win = directional(pi['outs']); got = f"{pi['outs']} outs"
        elif mkt == 'H_ALLOWED_ALT' and pi:
            win = directional(pi['h']); got = f"{pi['h']} H allowed"
        elif mkt == 'ER_ALLOWED' and pi:
            win = pi['er'] >= p.get('win_at', 99); got = f"{pi['er']} ER"
    return win, got


def pick_source(p):
    return p.get('pick_source', 'workbook') or 'workbook'


def fetch_box(date_iso):
    # statsapi first: free, keyless, 100% coverage. balldontlie only when
    # statsapi returns no players -- BDL's partial-data failure mode
    # (HTTP 200, missing games) must never silently become the labels.
    # Both fetchers catch their own exceptions and return {} on failure,
    # so emptiness IS the failure signal; nothing here can raise.
    box = G.fetch_box_results(date_iso)
    if not isinstance(box, dict):
        box = {}
    if not box.get('batters') and not box.get('pitchers') and BDL_KEY:
        print('  MLB Stats API empty -- falling back to balldontlie')
        box = G.fetch_bdl(date_iso, BDL_KEY)
        if not isinstance(box, dict):
            box = {}
    for k in ('batters', 'pitchers', 'totals', 'first_inning'):
        box.setdefault(k, {})
    games = G.fetch_games(date_iso)
    box['totals'].update(games.get('totals', {}))
    box['first_inning'].update(games.get('first_inning', {}))
    return box


def main(only_dates=None):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    store = {'graded': [], 'dates': {}}
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            store = json.load(f)
    done = set(store['dates'])

    files = sorted(glob.glob(os.path.join(repo, 'slate_picks_*.json')))
    print(f'{len(files)} slate files · {len(done)} date(s) already backfilled')
    matched = set()
    for path in files:
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)
        date_iso = payload.get('slate_date')
        picks = payload.get('picks', [])
        if not date_iso:
            continue
        if only_dates:
            if date_iso not in only_dates:
                continue
            matched.add(date_iso)
        if date_iso in done:
            if only_dates:
                print(f'-- {date_iso}: already backfilled -- skipped (delete '
                      'the date from "dates" in graded_picks.json to regrade)')
            continue
        print(f'-- {date_iso}: {len(picks)} picks')
        box = fetch_box(date_iso)
        if not box['batters'] and not box['pitchers'] and not box['totals']:
            print('   no box data returned -- skipping (rerun later)')
            continue
        # Idempotency is per DATE: a date recorded in store['dates'] is skipped
        # above, and (re)grading a date replaces its rows wholesale, so the same
        # date can never append twice. A (date, market, name, line) row key
        # cannot be used instead -- that tuple legitimately repeats inside a
        # slate (doubleheaders; parlay legs sharing a board pick's market/name/
        # line), so dropping "duplicates" would silently lose real rows.
        kept = [r for r in store['graded'] if r.get('date') != date_iso]
        if len(kept) != len(store['graded']):
            if not box['batters'] and not box['pitchers']:
                # Degraded fetch (game-level totals only): replacing would
                # overwrite existing player-prop grades with nulls. Keep them.
                print(f'   {date_iso} has existing rows but no player data '
                      'returned -- keeping them (rerun later)')
                continue
            print(f'   replacing {len(store["graded"]) - len(kept)} existing rows for {date_iso}')
        store['graded'] = kept
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
                'parlay_id': p.get('parlay_id'),
                'correlation_type': p.get('correlation_type'),
                'leg_role': p.get('leg_role'),
                'same_game': p.get('same_game'),
                'conviction_rank': p.get('conviction_rank'),
                'projection': p.get('projection'),
                'main_line': p.get('main_line'),
                'direction': p.get('direction'),
                'alt_margin': p.get('alt_margin'),
                'hrr_pct': p.get('hrr_pct'),
            }
            for field in CHIP_FIELDS:
                row[field] = p.get(field, None)
            store['graded'].append(row)
            n_graded += win is not None
        store['dates'][date_iso] = {'picks': len(picks), 'graded': n_graded}
        print(f'   graded {n_graded}/{len(picks)}')
        time.sleep(1)   # be polite to statsapi between dates

    if only_dates:
        for miss in sorted(only_dates - matched):
            print(f'!! no committed slate file has slate_date {miss} '
                  '(dates are ISO YYYY-MM-DD) -- nothing done for it')

    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(store, f)
    os.replace(tmp, OUT)   # atomic: a crash mid-write can never truncate OUT
    total = len(store['graded'])
    gradable = sum(1 for g in store['graded'] if g['win'] is not None)
    print(f'\nwrote {OUT}: {total} rows, {gradable} gradable, {len(store["dates"])} dates')


if __name__ == '__main__':
    main(only_dates=set(sys.argv[1:]) or None)
