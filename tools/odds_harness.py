"""Gauntlet harness: runs the REAL patched fetch_props.py with urllib faked.
Usage: python3 harness.py S1|S2|S3|S4|S5   (run each in a fresh process)"""
import io, json, os, sys, runpy
import urllib.request

SCEN = sys.argv[1]
DD = json.load(open('day_data.json'))
P = [r['Pitcher'] for r in DD['SP_Projections']]          # 4 real pitchers
T = [r['Team'] for r in DD['SP_Projections']]
DATE = str(DD['BP_Games'][0]['GameDate'])[:10]

NICK = {'ARI':'Diamondbacks','AZ':'Diamondbacks','ATL':'Braves','BAL':'Orioles',
'BOS':'Red Sox','CHC':'Cubs','CWS':'White Sox','CHW':'White Sox','CIN':'Reds',
'CLE':'Guardians','COL':'Rockies','DET':'Tigers','HOU':'Astros','KC':'Royals',
'KCR':'Royals','LAA':'Angels','LAD':'Dodgers','MIA':'Marlins','MIL':'Brewers',
'MIN':'Twins','NYM':'Mets','NYY':'Yankees','OAK':'Athletics','ATH':'Athletics',
'PHI':'Phillies','PIT':'Pirates','SD':'Padres','SDP':'Padres','SEA':'Mariners',
'SF':'Giants','SFG':'Giants','STL':'Cardinals','TB':'Rays','TBR':'Rays',
'TEX':'Rangers','TOR':'Blue Jays','WSH':'Nationals','WAS':'Nationals'}
def full(abbr): return f"Testville {NICK[abbr]}"

CALLS = []

class FakeHeaders(dict):
    def items(self): return dict.items(self)

class FakeResp:
    def __init__(self, data, headers): self._d, self.headers = data, FakeHeaders(headers)
    def read(self): return json.dumps(self._d).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False

REMAIN = ['55' if SCEN == 'S4' else '480']

def fake_urlopen(req, timeout=None):
    url = req.full_url if hasattr(req, 'full_url') else req
    CALLS.append(url)
    # ---------- balldontlie ----------
    if 'balldontlie.io' in url:
        if '/games' in url:
            return FakeResp({'data': [{'id': 900,
                'away_team': {'abbreviation': T[0]}, 'home_team': {'abbreviation': T[1]}}],
                'meta': {}}, {})
        if '/odds/player_props' in url:
            if SCEN == 'S3':
                return FakeResp({'data': [{'player_id': 101, 'vendor': 'fanduel',
                    'line_value': '8.5', 'market': {'over_odds': -110, 'under_odds': -110}}],
                    'meta': {}}, {})
            return FakeResp({'data': [], 'meta': {}}, {})
        if '/players' in url:
            if SCEN == 'S3':
                return FakeResp({'data': [{'id': 101, 'full_name': P[0]}]}, {})
            return FakeResp({'data': []}, {})
        raise AssertionError('unexpected BDL url ' + url)
    # ---------- The Odds API ----------
    if 'the-odds-api.com' in url:
        assert 'apiKey=test-odds-key' in url, 'key must be passed'
        hdr = lambda last: {'x-requests-remaining': REMAIN[0],
                            'x-requests-used': str(500 - int(REMAIN[0])),
                            'x-requests-last': last}
        if '/events?' in url or url.rstrip('&').endswith('dateFormat=iso'):
            if '/events/' not in url:
                evs = []
                if SCEN != 'S5':   # S5: only pitcher0's event exists
                    evs = [
                        {'id': 'EVPAST', 'commence_time': '2026-01-01T00:00:00Z',
                         'home_team': full(T[3]), 'away_team': 'Testville Nobodys'},
                    ]
                evs.append({'id': 'EV0', 'commence_time': '2026-12-01T23:00:00Z',
                            'home_team': full(T[0]), 'away_team': 'Testville Nobodys'})
                if SCEN != 'S5':
                    evs.append({'id': 'EV1', 'commence_time': '2026-12-01T23:00:00Z',
                                'home_team': 'Testville Nobodys', 'away_team': full(T[1])})
                    evs.append({'id': 'EV2', 'commence_time': '2026-12-01T23:00:00Z',
                                'home_team': full(T[2]), 'away_team': 'Testville Nobodys'})
                return FakeResp(evs, hdr('0'))
        if '/events/EV0/odds' in url:
            REMAIN[0] = str(int(REMAIN[0]) - 1)
            return FakeResp({'id': 'EV0', 'bookmakers': [
                {'key': 'draftkings', 'markets': [{'key': 'pitcher_strikeouts', 'outcomes': [
                    {'name': 'Over', 'description': P[0], 'price': -130, 'point': 7.5},
                    {'name': 'Under', 'description': P[0], 'price': 100, 'point': 7.5}]}]},
                {'key': 'fanduel', 'markets': [{'key': 'pitcher_strikeouts', 'outcomes': [
                    {'name': 'Over', 'description': P[0], 'price': -115, 'point': 6.5},
                    {'name': 'Under', 'description': P[0], 'price': -105, 'point': 6.5}]}]},
            ]}, hdr('1'))
        if '/events/EV1/odds' in url:
            REMAIN[0] = str(int(REMAIN[0]) - 1)
            return FakeResp({'id': 'EV1', 'bookmakers': [
                {'key': 'williamhill_us', 'markets': [{'key': 'pitcher_strikeouts', 'outcomes': [
                    {'name': 'Over', 'description': P[1], 'price': -120, 'point': 5.5},
                    {'name': 'Under', 'description': P[1], 'price': 100, 'point': 5.5}]}]},
            ]}, hdr('1'))
        if '/events/EV2/odds' in url:
            REMAIN[0] = str(int(REMAIN[0]) - 1)
            return FakeResp({'id': 'EV2', 'bookmakers': [
                {'key': 'draftkings', 'markets': [{'key': 'pitcher_strikeouts', 'outcomes': [
                    {'name': 'Over', 'description': P[2], 'price': -140, 'point': 7.5},
                    {'name': 'Over', 'description': P[2], 'price': -105, 'point': 6.5},
                    {'name': 'Under', 'description': P[2], 'price': -115, 'point': 6.5}]}]},
            ]}, hdr('1'))
        raise AssertionError('unexpected Odds url ' + url)
    raise AssertionError('unexpected url ' + url)

urllib.request.urlopen = fake_urlopen

os.environ['BDL_KEY'] = 'test-bdl-key'
os.environ['BDL_MIN_GAP'] = '0'
os.environ['ODDS_MIN_GAP'] = '0'
os.environ['DATA_FILE'] = 'day_data.json'
KP = f'k_props.{SCEN}.json'
os.environ['K_PROPS_FILE'] = KP
if SCEN == 'S1':
    os.environ.pop('ODDS_API_KEY', None)
else:
    os.environ['ODDS_API_KEY'] = 'test-odds-key'

if SCEN == 'S5':   # pre-seed a same-day fallback entry for pitcher1
    json.dump({'_meta': {'date': DATE},
               P[1].lower(): {'line': 5.5, 'over_odds': -120, 'under_odds': 100,
                              'vendor': 'draftkings', 'src': 'oddsapi'}},
              open(KP, 'w'))

buf = io.StringIO()
_stdout, sys.stdout = sys.stdout, buf
code = 0
try:
    runpy.run_path('fetch_props.py', run_name='__main__')
except SystemExit as e:
    code = 1 if e.code else 0
    if isinstance(e.code, str):
        buf.write(e.code)
finally:
    sys.stdout = _stdout
out = buf.getvalue()

def ok(cond, msg):
    print(('PASS' if cond else 'FAIL') + f' [{SCEN}] ' + msg)
    if not cond:
        print(out); sys.exit(2)

if SCEN == 'S1':
    ok(code != 0 and 'BUILD STOPPED' in out and 'posted yet' in out,
       'no key + empty BDL -> original BUILD STOPPED preserved')
    ok(not os.path.exists(KP), 'no props file written')
elif SCEN == 'S2':
    kp = json.load(open(KP))
    ok(code == 0, 'exit 0')
    ok(kp[P[0].lower()]['vendor'] == 'fanduel' and kp[P[0].lower()]['line'] == 6.5,
       'FanDuel 6.5 beats DraftKings 7.5 (vendor priority)')
    ok(kp[P[1].lower()]['vendor'] == 'caesars', 'williamhill_us aliased to caesars')
    ok(kp[P[2].lower()]['line'] == 6.5 and kp[P[2].lower()]['under_odds'] == -115,
       'both-sides point preferred over Over-only point')
    ok(P[3].lower() not in kp, 'pitcher with no line anywhere stays absent')
    ok(kp['_meta']['date'] == DATE and kp['_meta']['events_queried'] == 3,
       '_meta written with date + 3 events queried')
    ok('Skipping 1 already-started game' in out, 'commenced event skipped')
    ok(all(e['src'] == 'oddsapi' for k, e in kp.items() if k != '_meta'), 'src tags present')
elif SCEN == 'S3':
    kp = json.load(open(KP))
    ok(code == 0, 'exit 0')
    ok('src' not in kp[P[0].lower()] and kp[P[0].lower()]['line'] == 8.5,
       'BDL entry stays primary and untagged')
    ok(kp[P[1].lower()]['src'] == 'oddsapi', 'gap filled by Odds API')
    ok('[via The Odds API]' in out, 'summary tags fallback lines')
    ok(sum('/events/EV0/odds' in c for c in CALLS) == 1,
       'EV0 queried exactly once (primary for still-missing PIT pitcher)')
    ok('sweeping remaining slate events' not in out,
       'no sweep mode entered (all events were team-mapped)')
elif SCEN == 'S4':
    ok('monthly reserve reached' in out, 'reserve guard fired at remaining=55')
    ok(not any('/events/EV' in c and '/odds' in c for c in CALLS),
       'zero event-odds credits spent')
    ok(code != 0 and 'ANY source' in out, 'final any-source gate stops the build')
elif SCEN == 'S5':
    kp = json.load(open(KP))
    ok(code == 0 and 'Reused 1 same-day' in out, 'same-day entry reused')
    ok(kp[P[1].lower()]['line'] == 5.5, 'reused line intact')
    ok(kp[P[0].lower()]['vendor'] == 'fanduel', 'new gap still fetched fresh')
    ok(kp['_meta']['reused_same_day'] == 1, '_meta counts the reuse')
print(f'== {SCEN} complete ==')
