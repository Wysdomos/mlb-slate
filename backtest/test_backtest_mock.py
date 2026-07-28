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
for i in range(30):   # traffic_jam: 12 parlay wins from 30 graded parlays
    leg1_win = i < 20
    leg2_win = i < 12 or 20 <= i < 26
    for market, win in (('HIT', leg1_win), ('HRR', leg2_win)):
        graded.append({'date': '2026-06-17', 'market': market, 'name': f'tj{i}-{market}',
                       'consensus': 3, 'consensus_max': 4, 'win': win,
                       'line': 'Ov 0.5', 'got': '', 'parlay_id': f'tj-{i}',
                       'correlation_type': 'traffic_jam', 'leg_role': 'satellite',
                       'same_game': True})
graded.extend([
    {'date': '2026-06-17', 'market': 'HIT', 'name': 'ung-hit',
     'consensus': 3, 'consensus_max': 4, 'win': True, 'line': 'Ov 0.5',
     'got': '', 'parlay_id': 'tj-ungraded', 'correlation_type': 'traffic_jam',
     'leg_role': 'satellite', 'same_game': True},
    {'date': '2026-06-17', 'market': 'HRR', 'name': 'ung-hrr',
     'consensus': 3, 'consensus_max': 4, 'win': None, 'line': 'Ov 0.5',
     'got': '—', 'parlay_id': 'tj-ungraded', 'correlation_type': 'traffic_jam',
     'leg_role': 'satellite', 'same_game': True},
])
for i in range(2):   # small cross-game bucket
    for market, win in (('HIT', True), ('HIT', i == 0)):
        graded.append({'date': '2026-06-17', 'market': market, 'name': f'db{i}-{market}',
                       'consensus': 3, 'consensus_max': 4, 'win': win,
                       'line': 'Ov 0.5', 'got': '', 'parlay_id': f'db-{i}',
                       'correlation_type': 'double_barrel_cross_game',
                       'leg_role': 'satellite', 'same_game': False})
store = {'graded': graded,
         'dates': {'2026-06-15': {}, '2026-06-16': {}, '2026-06-17': {}}}
report = calibration.build(store)
run('report: HR 30% bucket rendered', '**30.0%**' in report)
run('report: K by-line section present', 'O 4.5' in report)
run('report: small-n flag on K', '⚠ small n' in report)
run('report: break-even table sane (-110 -> 52.4%)', '52.4%' in report)
parlays = calibration.collect_parlays(graded)
by_id = {p['parlay_id']: p for p in parlays}
run('parlay: all legs must win', by_id['tj-0']['result'] is True and by_id['tj-12']['result'] is False)
run('parlay: ungraded leg makes parlay ungraded', by_id['tj-ungraded']['result'] is None)
run('report: parlay scoreboard present', '## Parlay scoreboard' in report)
run('report: traffic_jam parlay rate rendered', '| all | 30 | 12 | 1 | 38-22 (63.3%) | 40.0% | 40.0% | 0.0% |' in report)
run('report: same-game split rendered', 'same_game=True' in report)
run('report: cross-game split rendered', 'same_game=False' in report)
run('report: small parlay buckets do not print rates', 'insufficient data -- keep accumulating' in report)
lo, hi = calibration.wilson(12, 40)
run('wilson CI sane for 12/40', 0.17 < lo < 0.20 and 0.44 < hi < 0.48)

print('\n' + ('ALL TESTS PASSED' if ok else 'FAILURES PRESENT'))
sys.exit(0 if ok else 1)
