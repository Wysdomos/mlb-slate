"""Behavioral verification of fetch_odds_api.fill_missing with a mocked HTTP layer.
Runs OFFLINE. Six cases. Exits nonzero on any failure."""
import sys, unicodedata
sys.path.insert(0, '.')
import fetch_odds_api as F

# --- exact copy of fetch_props.norm (shared name matching) -------------------
def norm(n):
    s = (n or '').lower()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    for ch in ['.', ',', "'", '-']:
        s = s.replace(ch, ' ' if ch == '-' else '')
    toks = [t for t in s.split() if t not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    return ' '.join(toks)

VP = ['fanduel', 'draftkings', 'betmgm', 'caesars', 'betrivers', 'fanatics']

EVENTS = [
    {'id': 'EV_TOR', 'commence_time': '2026-07-13T23:07:00Z',
     'home_team': 'New York Yankees', 'away_team': 'Toronto Blue Jays'},
    {'id': 'EV_COL', 'commence_time': '2026-07-14T02:10:00Z',
     'home_team': 'Los Angeles Dodgers', 'away_team': 'Colorado Rockies'},
    {'id': 'EV_PHI', 'commence_time': '2026-07-13T23:10:00Z',
     'home_team': 'New York Mets', 'away_team': 'Philadelphia Phillies'},
]

ODDS = {
    'EV_TOR': {'bookmakers': [
        {'key': 'draftkings', 'markets': [{'key': 'pitcher_strikeouts', 'outcomes': [
            {'name': 'Over', 'description': 'Jose Berrios', 'price': -120, 'point': 5.5},
            {'name': 'Under', 'description': 'Jose Berrios', 'price': 100, 'point': 5.5}]}]},
        {'key': 'fanduel', 'markets': [{'key': 'pitcher_strikeouts', 'outcomes': [
            {'name': 'Over', 'description': 'Jose Berrios', 'price': -118, 'point': 5.5},
            {'name': 'Under', 'description': 'Jose Berrios', 'price': -102, 'point': 5.5}]}]}]},
    'EV_COL': {'bookmakers': [
        {'key': 'williamhill_us', 'markets': [{'key': 'pitcher_strikeouts', 'outcomes': [
            {'name': 'Over', 'description': 'Kyle Freeland', 'price': -190, 'point': 4.5},
            {'name': 'Under', 'description': 'Kyle Freeland', 'price': 140, 'point': 4.5}]}]}]},
    'EV_PHI': {'bookmakers': []},
}

calls = []
def make_get(remaining_seq=None, cost=1):
    state = {'i': 0, 'remaining': 400}
    def _get(path, params, min_gap=0.35, retries=4, timeout=30):
        calls.append(path)
        if remaining_seq is not None and state['i'] < len(remaining_seq):
            state['remaining'] = remaining_seq[state['i']]
        state['i'] += 1
        if path.endswith('/events'):
            return list(EVENTS), {'x-requests-remaining': str(state['remaining']),
                                  'x-requests-last': '0'}
        eid = path.split('/events/')[1].split('/')[0]
        payload = ODDS.get(eid, {'bookmakers': []})
        last = str(cost if payload.get('bookmakers') else 0)
        state['remaining'] -= int(last)
        return payload, {'x-requests-remaining': str(state['remaining']),
                         'x-requests-last': last}
    return _get

def run(name, cond):
    print(('PASS  ' if cond else 'FAIL  ') + name)
    return cond

ok = True
TEAMS = {'José Berríos': 'TOR', 'Kyle Freeland': 'COL'}

# T1: accents + vendor priority + caesars alias + no wasted PHI call
calls.clear(); F._get = make_get()
filled, meta = F.fill_missing('K', '2026-07-13', ['José Berríos', 'Kyle Freeland'],
                              norm, VP, team_of=TEAMS)
ok &= run('T1a fills both, keys = original.lower() w/ accents',
          set(filled) == {'josé berríos', 'kyle freeland'})
ok &= run('T1b fanduel beats draftkings', filled['josé berríos']['vendor'] == 'fanduel')
ok &= run('T1c williamhill_us -> caesars', filled['kyle freeland']['vendor'] == 'caesars')
ok &= run('T1d entry shape + src', all(k in filled['kyle freeland'] for k in
          ('line', 'over_odds', 'under_odds', 'vendor', 'src')) and
          filled['kyle freeland']['src'] == 'oddsapi' and
          filled['kyle freeland']['line'] == 4.5)
ok &= run('T1e stops when done (PHI never queried)',
          not any('EV_PHI' in c for c in calls))
ok &= run('T1f credits/meta accurate', meta['credits_used_this_run'] == 2
          and meta['events_queried'] == 2 and meta['remaining'] is not None)

# T2: same-day reuse = zero network for reused pitcher
calls.clear(); F._get = make_get()
prev = {'kyle freeland': {'line': 4.5, 'over_odds': -190, 'under_odds': 140,
                          'vendor': 'caesars', 'src': 'oddsapi'}}
filled, meta = F.fill_missing('K', '2026-07-13', ['Kyle Freeland'], norm, VP,
                              team_of=TEAMS, prev_entries=prev)
ok &= run('T2 reuse: 0 calls, 0 credits, entry returned',
          len(calls) == 0 and meta['credits_used_this_run'] == 0
          and meta['reused_same_day'] == 1 and 'kyle freeland' in filled)

# T3: monthly reserve floor halts spending
calls.clear(); F._get = make_get(remaining_seq=[55])
filled, meta = F.fill_missing('K', '2026-07-13', ['Kyle Freeland'], norm, VP,
                              team_of=TEAMS, reserve=60)
ok &= run('T3 reserve stop: events listed (free) but zero paid calls',
          meta['events_queried'] == 0 and not filled)

# T4: per-run cap respected
calls.clear(); F._get = make_get()
filled, meta = F.fill_missing('K', '2026-07-13', ['José Berríos', 'Kyle Freeland'],
                              norm, VP, team_of=TEAMS, max_per_run=1)
ok &= run('T4 cap=1: one event queried, one filled, one still missing',
          meta['events_queried'] == 1 and len(filled) == 1)

# T5: commenced games skipped
calls.clear(); F._get = make_get()
EVENTS[1]['commence_time'] = '2020-01-01T00:00:00Z'   # COL game 'started'
filled, meta = F.fill_missing('K', '2026-07-13', ['Kyle Freeland'], norm, VP,
                              team_of=TEAMS)
ok &= run('T5 commenced skip: COL game excluded, nothing filled',
          not any('EV_COL' in c for c in calls) and not filled)
EVENTS[1]['commence_time'] = '2026-07-14T02:10:00Z'   # restore

# T6: one-sided line still fills (real data, no fabrication of the other side)
calls.clear(); F._get = make_get()
ODDS['EV_COL']['bookmakers'][0]['markets'][0]['outcomes'] = [
    {'name': 'Over', 'description': 'Kyle Freeland', 'price': -185, 'point': 4.5}]
filled, meta = F.fill_missing('K', '2026-07-13', ['Kyle Freeland'], norm, VP,
                              team_of=TEAMS)
ok &= run('T6 over-only entry: line kept, under_odds is None (no fake data)',
          filled['kyle freeland']['line'] == 4.5
          and filled['kyle freeland']['under_odds'] is None)

# T7: sweep gate -- Freeland's own event (EV_COL) queried and empty; the
# unrelated EV_PHI event must NOT be queried (a K prop only lives in the
# pitcher's own game). Restores pre-T6 odds first.
ODDS['EV_COL']['bookmakers'][0]['markets'][0]['outcomes'] = []
calls.clear(); F._get = make_get()
filled, meta = F.fill_missing('K', '2026-07-13', ['Kyle Freeland'], norm, VP,
                              team_of=TEAMS)
ok &= run('T7 sweep gate: known-event gap does not trigger sweep of other games',
          any('EV_COL' in c for c in calls)
          and not any('EV_PHI' in c for c in calls)
          and not any('EV_TOR' in c for c in calls) and not filled)

# T8: unmapped pitcher (no team_of entry) -- sweep is the only way to find
# him, so it MUST fire and query the remaining events.
calls.clear(); F._get = make_get()
filled, meta = F.fill_missing('K', '2026-07-13', ['Mystery Callup'], norm, VP,
                              team_of=TEAMS)
ok &= run('T8 unmapped pitcher: sweep fires across slate events',
          any('EV_TOR' in c for c in calls) and any('EV_PHI' in c for c in calls))

print('\n' + ('ALL TESTS PASSED' if ok else 'FAILURES PRESENT'))
sys.exit(0 if ok else 1)
