"""
fetch_phase2.py -- Phase 2 metrics from balldontlie (NOT pybaseball)
====================================================================
Pulls advanced K metrics for slate starting pitchers.
Writes k_savant_data.json for build_k_report.py.

Metrics:
  swstr_pct         SwStr% (whiffs/pitches)
  arsenal_whiff     Arsenal Whiff% (whiffs/swings)
  chase_pct         Chase% (chases/out-of-zone)
  opp_lineup_k_pct  Opponent lineup K%
  recent_form       K per start (season avg)
  ha_split          Home K/start minus Away K/start

Reads:   day_data.json     (DATA_FILE)
Key:     BDL_KEY env var
Writes:  k_savant_data.json (K_SAVANT_FILE)
"""

import os, json, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime

DATA_FILE   = os.environ.get('DATA_FILE',     'day_data.json')
SAVANT_FILE = os.environ.get('K_SAVANT_FILE', 'k_savant_data.json')
BDL_KEY     = os.environ.get('BDL_KEY', '').strip()
BASE        = 'https://api.balldontlie.io/mlb/v1'

if not BDL_KEY:
    print("Phase 2 skipped: no BDL_KEY.")
    raise SystemExit(0)

MIN_GAP = float(os.environ.get('BDL_MIN_GAP', '0.35'))
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
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                sleep_t = min(20 * (attempt + 1), 90)
                print(f"    Rate limit hit — sleeping {sleep_t}s")
                time.sleep(sleep_t); continue
            print(f"    {path}: HTTP {e.code}")
            return None
        except Exception as e:
            print(f"    {path}: {e}")
            time.sleep(3 * (attempt + 1))
    return None

def paged(path, params):
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

DATA   = json.load(open(DATA_FILE, encoding='utf-8'))
season = datetime.today().year

slate = []
for r in DATA.get('SP_Projections', []):
    nm = (r.get('Pitcher') or '').strip()
    if nm and nm.upper() != 'TBD':
        slate.append({'name': nm, 'opp': (r.get('Opp') or '').strip()})

if not slate:
    print("Phase 2 skipped: no pitchers in slate.")
    raise SystemExit(0)

print(f"Phase 2: {len(slate)} pitchers, season {season}")

def norm(n):
    return ' '.join((n or '').lower().replace('.','').replace(',','').split())

# ── OPPONENT LINEUP K% ────────────────────────────────────────────
team_k = {}
ts = list(paged('/teams/season_stats', {'season': season, 'per_page': 100}))
print(f"  /teams/season_stats returned {len(ts)} rows")
if ts:
    # Log first row to see actual field names
    sample = {k: v for k, v in list(ts[0].items())[:15]}
    print(f"  Sample team row keys: {list(ts[0].keys())[:20]}")

for row in ts:
    tm   = row.get('team') or {}
    abbr = (tm.get('abbreviation') or row.get('team_name') or '').upper()

    # Try multiple possible field names for SO, AB, BB
    so = (row.get('batting_so') or row.get('batting_strikeouts') or
          row.get('so') or row.get('strikeouts'))
    ab = (row.get('batting_ab') or row.get('batting_at_bats') or
          row.get('ab') or row.get('at_bats'))
    bb = (row.get('batting_bb') or row.get('batting_walks') or
          row.get('bb') or row.get('walks') or 0)
    try:
        pa = float(ab or 0) + float(bb)
        if pa > 0 and so is not None:
            team_k[abbr] = round(float(so) / pa * 100, 1)
    except (TypeError, ValueError):
        pass
print(f"  Opponent K% computed for {len(team_k)} teams")

# ── PLAYER ID LOOKUP ─────────────────────────────────────────────
def find_id(name):
    parts = name.split()
    q = parts[-1] if parts else name
    resp = api_get('/players', {'search': q, 'per_page': 100})
    if not resp:
        return None
    want = norm(name)
    for pl in resp.get('data', []):
        full = pl.get('full_name') or f"{pl.get('first_name','')} {pl.get('last_name','')}"
        if norm(full) == want:
            return pl['id']
    # Fuzzy fallback: last name + first initial
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
        else:
            print(f"  No ID: {p['name']}")
    except Exception as e:
        print(f"  ID lookup error {p['name']}: {e}")
print(f"  Matched {len(ids)}/{len(slate)} pitchers")

# ── RECENT FORM (K/start) ─────────────────────────────────────────
form = {}
if ids:
    ss = list(paged('/season_stats',
                    {'season': season, 'player_ids[]': list(ids.values()), 'per_page': 100}))
    for row in ss:
        pid = (row.get('player') or {}).get('id')
        k   = row.get('pitching_k')
        gs  = row.get('pitching_gs')
        try:
            if pid and gs and float(gs) > 0:
                form[pid] = round(float(k) / float(gs), 1)
        except (TypeError, ValueError):
            pass
print(f"  Recent form computed for {len(form)} pitchers")

# ── PITCH METRICS (SwStr%, Chase%, Arsenal Whiff%) ───────────────
def pitch_metrics(pid):
    rows = list(paged('/pitcher_pitch_type_season_stats',
                      {'season': season, 'player_id': pid, 'per_page': 100}))
    if not rows:
        return {}
    # Log field names on first call
    if rows:
        sample_keys = list(rows[0].keys())
        # Only log once globally
        if not getattr(pitch_metrics, '_logged', False):
            print(f"  pitch_type row keys: {sample_keys[:15]}")
            pitch_metrics._logged = True

    pitches = whiffs = swings = chases = zone = 0
    for r in rows:
        pitches += int(r.get('pitch_count') or r.get('pitches') or 0)
        whiffs  += int(r.get('whiff_count') or r.get('whiffs') or 0)
        swings  += int(r.get('swing_count') or r.get('swings') or 0)
        chases  += int(r.get('chase_count') or r.get('chases') or 0)
        zone    += int(r.get('zone_count')  or r.get('in_zone') or 0)

    out = {}
    if pitches > 0:
        out['swstr_pct'] = round(whiffs / pitches * 100, 1)
    if swings > 0:
        out['arsenal_whiff'] = round(whiffs / swings * 100, 1)
    oz = pitches - zone
    if oz > 0:
        out['chase_pct'] = round(chases / oz * 100, 1)
    return out

# ── H/A SPLIT ─────────────────────────────────────────────────────
def ha_split(pid):
    """Home K/start minus Away K/start. Tries multiple balldontlie endpoints."""

    # Attempt 1: /players/splits
    resp = api_get('/players/splits', {'season': season, 'player_id': pid})
    if resp:
        rows = resp.get('data', [])
        if not rows and isinstance(resp, list):
            rows = resp
        home_k = home_g = away_k = away_g = None
        for row in rows:
            label = str(row.get('split') or row.get('split_name') or
                        row.get('name') or row.get('type') or '').lower()
            k  = row.get('pitching_k', row.get('p_k', row.get('strikeouts')))
            gs = row.get('pitching_gs', row.get('games_started', row.get('gs')))
            if k is None or gs is None:
                continue
            if 'home' in label:
                home_k, home_g = float(k), float(gs)
            elif 'away' in label or 'road' in label:
                away_k, away_g = float(k), float(gs)
        try:
            if home_g and away_g and home_g > 0 and away_g > 0:
                return round(home_k/home_g - away_k/away_g, 1)
        except (TypeError, ValueError):
            pass

    # Attempt 2: /splits with different param name
    resp2 = api_get('/splits', {'season': season, 'player_id': pid, 'per_page': 50})
    if resp2:
        rows2 = resp2.get('data', [])
        home_k = home_g = away_k = away_g = None
        for row in rows2:
            label = str(row.get('split') or row.get('name') or '').lower()
            k  = row.get('pitching_k', row.get('strikeouts'))
            gs = row.get('pitching_gs', row.get('gs', row.get('games_started')))
            if k is None or gs is None:
                continue
            if 'home' in label:
                home_k, home_g = float(k), float(gs)
            elif 'away' in label or 'road' in label:
                away_k, away_g = float(k), float(gs)
        try:
            if home_g and away_g and home_g > 0 and away_g > 0:
                return round(home_k/home_g - away_k/away_g, 1)
        except (TypeError, ValueError):
            pass

    return None

# ── INCREMENTAL SAVE ─────────────────────────────────────────────
def save(d):
    tmp = SAVANT_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SAVANT_FILE)

# ── MAIN LOOP ────────────────────────────────────────────────────
savant = {}
for p in slate:
    try:
        pid     = ids.get(p['name'])
        metrics = {}

        if pid:
            # Pitch metrics
            try:
                pm = pitch_metrics(pid)
                metrics.update(pm)
            except Exception as e:
                print(f"  {p['name']}: pitch metrics error ({e})")

            # Recent form
            if pid in form:
                metrics['recent_form'] = form[pid]

            # H/A split
            try:
                hs = ha_split(pid)
                if hs is not None:
                    metrics['ha_split'] = hs
                else:
                    print(f"  {p['name']}: H/A split returned None (endpoint may not exist)")
            except Exception as e:
                print(f"  {p['name']}: H/A split error ({e})")

        # Opp lineup K%
        opp_abbr = (p['opp'] or '').upper().strip()
        ok = team_k.get(opp_abbr)
        if ok is None:
            # Try common team abbr variants
            for variant in [opp_abbr, opp_abbr.replace('WAS','WSH'),
                            opp_abbr.replace('WSH','WAS'),
                            opp_abbr.replace('CHW','CWS')]:
                ok = team_k.get(variant)
                if ok is not None:
                    break
        if ok is not None:
            metrics['opp_lineup_k_pct'] = ok

        if metrics:
            savant[p['name'].lower()] = metrics
            save(savant)

    except Exception as e:
        print(f"  {p['name']}: skipped ({e})")

save(savant)

# ── SUMMARY ──────────────────────────────────────────────────────
filled = sum(len(v) for v in savant.values())
print(f"\nWrote {SAVANT_FILE}: {len(savant)} pitchers, {filled} metric values")
for p in slate:
    m = savant.get(p['name'].lower())
    if m:
        bits = []
        if 'swstr_pct'        in m: bits.append(f"SwStr {m['swstr_pct']}%")
        if 'chase_pct'        in m: bits.append(f"Chase {m['chase_pct']}%")
        if 'arsenal_whiff'    in m: bits.append(f"Whiff {m['arsenal_whiff']}%")
        if 'opp_lineup_k_pct' in m: bits.append(f"OppK {m['opp_lineup_k_pct']}%")
        if 'recent_form'      in m: bits.append(f"Form {m['recent_form']}")
        if 'ha_split'         in m: bits.append(f"H/A {m['ha_split']:+}")
        print(f"  {p['name']}: " + " | ".join(bits))
    else:
        print(f"  {p['name']}: no metrics")
