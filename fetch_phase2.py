"""
fetch_phase2.py -- Phase 2 metrics from balldontlie (NOT pybaseball)
====================================================================
Runs in Colab AFTER fetch_props.py. Pulls the advanced K metrics for the
slate's starting pitchers and writes k_savant_data.json, which
build_k_report.py reads to fill the Phase 2 info cells.

Metrics (keyed by lowercase pitcher name):
  swstr_pct         whiff_count / pitch_count * 100        (pitch_type_season_stats)
  arsenal_whiff     whiff_count / swing_count * 100        (pitch_type_season_stats)
  chase_pct         chase_count / out-of-zone pitches *100 (pitch_type_season_stats)
  opp_lineup_k_pct  opponent batting_so/(ab+bb) * 100      (teams/season_stats)
  recent_form       pitching_k / pitching_gs (K per start) (season_stats)
  ha_split          home K/start - away K/start            (players/splits, best-effort)

FAIL POLICY: Phase 2 is INFO-ONLY, so this never stops the build. The real
K lines (fetch_props.py) are the core and already succeeded. If a metric or a
whole call fails, it's logged and simply left out -- the K Report shows "P2"
for anything missing, exactly as it does today.

Reads:   day_data.json     (DATA_FILE)
Key:     BDL_KEY env var
Writes:  k_savant_data.json (K_SAVANT_FILE)
"""

import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

DATA_FILE     = os.environ.get('DATA_FILE',     'day_data.json')
SAVANT_FILE   = os.environ.get('K_SAVANT_FILE', 'k_savant_data.json')
BDL_KEY       = os.environ.get('BDL_KEY', '').strip()
BASE          = 'https://api.balldontlie.io/mlb/v1'

if not BDL_KEY:
    print("Phase 2 skipped: no BDL_KEY. (K Report shows P2 for advanced cells.)")
    raise SystemExit(0)

# ---- paced HTTP (shared limiter w/ patient 429 backoff) ---------------------
MIN_GAP = float(os.environ.get('BDL_MIN_GAP', '0.3'))
_last = [0.0]

def api_get(path, params=None, retries=2):
    url = BASE + path
    if params:
        url += '?' + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={'Authorization': BDL_KEY})
    for attempt in range(retries):
        wait = MIN_GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(min(15 * (attempt + 1), 60)); continue
            # Any other HTTP error: give up on THIS call (Phase 2 is optional)
            print(f"    {path}: HTTP {e.code} (skipped)")
            return None
        except Exception as e:
            time.sleep(2 * (attempt + 1))
    print(f"    {path}: unreachable (skipped)")
    return None

def paged(path, params):
    """Yield all data rows across cursor pages."""
    params = dict(params)
    while True:
        resp = api_get(path, params)
        if not resp:
            return
        for row in resp.get('data', []):
            yield row
        nxt = (resp.get('meta') or {}).get('next_cursor')
        if not nxt:
            return
        params['cursor'] = nxt

# ---- slate context ----------------------------------------------------------
DATA = json.load(open(DATA_FILE, encoding='utf-8'))
season = datetime.today().year

slate = []
for r in DATA.get('SP_Projections', []):
    nm = (r.get('Pitcher') or '').strip()
    if nm and nm.upper() != 'TBD':
        slate.append({'name': nm, 'opp': (r.get('Opp') or '').strip()})

if not slate:
    print("Phase 2 skipped: no pitchers in slate.")
    raise SystemExit(0)

print(f"Phase 2: pulling balldontlie metrics for {len(slate)} pitchers (season {season})...")

def norm(n):
    return ' '.join((n or '').lower().replace('.', '').replace(',', '').split())

# ---- 1) opponent team K% (one bulk call) -----------------------------------
team_k = {}        # abbreviation -> K%
team_id_abbr = {}  # team id -> abbreviation
ts = list(paged('/teams/season_stats', {'season': season, 'per_page': 100}))
for row in ts:
    tm = row.get('team') or {}
    abbr = (tm.get('abbreviation') or row.get('team_name') or '').upper()
    so = row.get('batting_so'); ab = row.get('batting_ab'); bb = row.get('batting_bb') or 0
    try:
        pa = float(ab) + float(bb)
        if pa > 0 and so is not None:
            team_k[abbr] = round(float(so) / pa * 100, 1)
    except (TypeError, ValueError):
        pass
print(f"  opponent K% for {len(team_k)} teams")

# ---- 2) resolve pitcher name -> player_id ----------------------------------
def find_id(name):
    parts = name.split()
    q = parts[-1] if parts else name          # search by last name
    resp = api_get('/players', {'search': q, 'per_page': 100})
    if not resp:
        return None
    want = norm(name)
    for pl in resp.get('data', []):
        full = pl.get('full_name') or f"{pl.get('first_name','')} {pl.get('last_name','')}"
        if norm(full) == want:
            return pl['id']
    # loose fallback: last name + first initial
    for pl in resp.get('data', []):
        full = norm(pl.get('full_name') or f"{pl.get('first_name','')} {pl.get('last_name','')}")
        if parts and full.endswith(norm(parts[-1])) and full[:1] == want[:1]:
            return pl['id']
    return None

ids = {}
for p in slate:
    try:
        pid = find_id(p['name'])
        if pid:
            ids[p['name']] = pid
    except Exception as e:
        print(f"    {p['name']}: id lookup skipped ({e})")
print(f"  matched {len(ids)}/{len(slate)} pitchers to balldontlie IDs")

# ---- 3) season K/start (one bulk call) -------------------------------------
form = {}  # player_id -> K per start
if ids:
    ss = list(paged('/season_stats',
                    {'season': season, 'player_ids[]': list(ids.values()), 'per_page': 100}))
    for row in ss:
        pid = (row.get('player') or {}).get('id')
        k = row.get('pitching_k'); gs = row.get('pitching_gs')
        try:
            if pid and gs and float(gs) > 0:
                form[pid] = round(float(k) / float(gs), 1)
        except (TypeError, ValueError):
            pass

# ---- 4) per-pitcher pitch-type aggregates + H/A split ----------------------
def pitch_metrics(pid):
    rows = list(paged('/pitcher_pitch_type_season_stats',
                      {'season': season, 'player_id': pid, 'per_page': 100}))
    if not rows:
        return {}
    pitches = whiffs = swings = chases = zone = 0
    for r in rows:
        pitches += r.get('pitch_count') or 0
        whiffs  += r.get('whiff_count') or 0
        swings  += r.get('swing_count') or 0
        chases  += r.get('chase_count') or 0
        zone    += r.get('zone_count')  or 0
    out = {}
    if pitches:
        out['swstr_pct'] = round(whiffs / pitches * 100, 1)
    if swings:
        out['arsenal_whiff'] = round(whiffs / swings * 100, 1)
    oz = pitches - zone           # out-of-zone pitches
    if oz > 0:
        out['chase_pct'] = round(chases / oz * 100, 1)
    return out

def ha_split(pid):
    """Best-effort home/away K-per-start split. Schema is undocumented, so we
    probe the endpoint and look for recognizable home/away K + games fields."""
    resp = api_get('/players/splits', {'season': season, 'player_id': pid})
    if not resp:
        return None
    rows = resp.get('data', [])
    home_k = home_g = away_k = away_g = None
    for row in rows:
        label = str(row.get('split') or row.get('split_name') or row.get('name') or '').lower()
        k  = row.get('pitching_k', row.get('p_k'))
        gs = row.get('pitching_gs', row.get('games_started'))
        if k is None or gs is None:
            continue
        if 'home' in label:
            home_k, home_g = k, gs
        elif 'away' in label or 'road' in label:
            away_k, away_g = k, gs
    try:
        if home_g and away_g and float(home_g) > 0 and float(away_g) > 0:
            return round(float(home_k)/float(home_g) - float(away_k)/float(away_g), 1)
    except (TypeError, ValueError):
        pass
    return None

def save(d):
    tmp = SAVANT_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SAVANT_FILE)   # atomic: never leaves a half-written file

savant = {}
for p in slate:
    # Each pitcher is isolated: a bad API response for one can never kill the run.
    try:
        pid = ids.get(p['name'])
        metrics = {}
        if pid:
            try:
                metrics.update(pitch_metrics(pid))
            except Exception as e:
                print(f"    {p['name']}: pitch metrics skipped ({e})")
            if pid in form:
                metrics['recent_form'] = form[pid]
            # H/A split intentionally skipped: undocumented endpoint, too slow
            # (17 extra calls). Leaves H/A as "P2" in the report.
        ok = team_k.get((p['opp'] or '').upper())
        if ok is not None:
            metrics['opp_lineup_k_pct'] = ok
        if metrics:
            savant[p['name'].lower()] = metrics
            save(savant)   # incremental: a later crash/timeout still keeps this
    except Exception as e:
        print(f"    {p['name']}: skipped ({e})")

save(savant)

filled = sum(len(v) for v in savant.values())
print(f"\nWrote {SAVANT_FILE}: {len(savant)} pitchers, {filled} metric values")
for p in slate:
    m = savant.get(p['name'].lower())
    if m:
        bits = []
        if 'swstr_pct' in m:        bits.append(f"SwStr {m['swstr_pct']}%")
        if 'chase_pct' in m:        bits.append(f"Chase {m['chase_pct']}%")
        if 'arsenal_whiff' in m:    bits.append(f"Whiff {m['arsenal_whiff']}%")
        if 'opp_lineup_k_pct' in m: bits.append(f"OppK {m['opp_lineup_k_pct']}%")
        if 'recent_form' in m:      bits.append(f"Form {m['recent_form']}")
        if 'ha_split' in m:         bits.append(f"H/A {m['ha_split']:+}")
        print(f"  {p['name']}: " + " | ".join(bits))
