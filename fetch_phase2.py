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

v2 hardening (root fix for the silent Phase-2 dropout):
  * CACHE-FIRST: yesterday's k_savant_data.json is loaded at start and
    seeded into the result for every slate pitcher. Fresh values merge ON
    TOP of cache, so an API outage / rate-limit storm / runner kill can
    never leave the file worse than it was. Season-aggregate metrics age
    fine for a day or two.
  * GLOBAL DEADLINE: the whole script self-terminates gracefully before
    the workflow's timeout-minutes can hard-kill it mid-write
    (PHASE2_DEADLINE_S, default 420s). Past the deadline every remaining
    pitcher just keeps cached values.
  * Pager guards: max page count + repeated-cursor detection.
  * Never clobbers: writes only when there is something to write; a run
    with zero fresh data and no cache leaves the filesystem untouched.
  * Always exits 0: a Phase-2 hiccup must never take the slate build down.

Env knobs:
  PHASE2_DEADLINE_S   soft wall-clock budget in seconds   (default 420)
  PHASE2_MAX_PAGES    per-endpoint pagination cap         (default 40)
  PHASE2_CACHE_MAX_H  max cache age in hours to reuse     (default 96)
  BDL_MIN_GAP         min seconds between BDL requests    (default 0.35)
  BDL_BASE            API base override (used by tests)
"""

import os, sys, json, time, traceback
import urllib.request, urllib.parse, urllib.error
from datetime import datetime

DATA_FILE   = os.environ.get('DATA_FILE',     'day_data.json')
SAVANT_FILE = os.environ.get('K_SAVANT_FILE', 'k_savant_data.json')
BDL_KEY     = os.environ.get('BDL_KEY', '').strip()
BASE        = os.environ.get('BDL_BASE', 'https://api.balldontlie.io/mlb/v1')

MIN_GAP     = float(os.environ.get('BDL_MIN_GAP', '0.35'))
DEADLINE_S  = float(os.environ.get('PHASE2_DEADLINE_S', '420'))
MAX_PAGES   = int(os.environ.get('PHASE2_MAX_PAGES', '40'))
CACHE_MAX_H = float(os.environ.get('PHASE2_CACHE_MAX_H', '96'))

_T0 = time.monotonic()
_deadline_announced = [False]

def time_left():
    return DEADLINE_S - (time.monotonic() - _T0)

def past_deadline():
    if time_left() > 0:
        return False
    if not _deadline_announced[0]:
        _deadline_announced[0] = True
        print(f"  [deadline] {DEADLINE_S:.0f}s budget reached — "
              f"remaining pitchers keep cached values")
    return True

_last = [0.0]

def api_get(path, params=None, retries=2):
    if past_deadline():
        return None
    url = BASE + path
    if params:
        url += '?' + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={'Authorization': BDL_KEY})
    for attempt in range(retries):
        if past_deadline():
            return None
        wait = MIN_GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(min(wait, max(0.0, time_left())))
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                sleep_t = min(20 * (attempt + 1), 90, max(0.0, time_left()))
                if sleep_t <= 0:
                    return None
                print(f"    Rate limit hit — sleeping {sleep_t:.0f}s")
                time.sleep(sleep_t); continue
            print(f"    {path}: HTTP {e.code}")
            return None
        except Exception as e:
            print(f"    {path}: {e}")
            time.sleep(min(3 * (attempt + 1), max(0.0, time_left())))
    return None

def paged(path, params):
    params = dict(params)
    seen_cursors = set()
    for _page in range(MAX_PAGES):
        if past_deadline():
            return
        resp = api_get(path, params)
        if not resp:
            return
        for row in resp.get('data', []):
            yield row
        nxt = (resp.get('meta') or {}).get('next_cursor')
        if not nxt:
            return
        if nxt in seen_cursors:
            print(f"    {path}: repeated cursor — stopping pagination")
            return
        seen_cursors.add(nxt)
        params['cursor'] = nxt
    print(f"    {path}: hit {MAX_PAGES}-page cap — stopping pagination")

def norm(n):
    return ' '.join((n or '').lower().replace('.', '').replace(',', '').split())

# ── CACHE (yesterday's file = today's safety net) ─────────────────
def load_cache():
    if not os.path.exists(SAVANT_FILE):
        return {}
    try:
        age_h = (time.time() - os.path.getmtime(SAVANT_FILE)) / 3600.0
    except OSError:
        age_h = 0.0
    if age_h > CACHE_MAX_H:
        print(f"  Cache is {age_h:.0f}h old (> {CACHE_MAX_H:.0f}h) — ignoring it")
        return {}
    try:
        d = json.load(open(SAVANT_FILE, encoding='utf-8'))
        if isinstance(d, dict):
            d = {k: v for k, v in d.items() if isinstance(v, dict)}
            print(f"  Cache loaded: {len(d)} pitchers ({age_h:.0f}h old)")
            return d
    except Exception as e:
        print(f"  Cache unreadable ({e}) — starting clean")
    return {}

# ── INCREMENTAL, ATOMIC SAVE ─────────────────────────────────────
def save(d):
    tmp = SAVANT_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SAVANT_FILE)

# ── H/A SPLIT (via MLB Stats API — balldontlie has no splits endpoint) ──
_MLB_API = 'https://statsapi.mlb.com/api/v1'
_mlb_id_cache = {}

def _mlb_get(url):
    if past_deadline():
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return None

def mlb_player_id(name):
    key = (name or '').strip().lower()
    if key in _mlb_id_cache:
        return _mlb_id_cache[key]
    q = urllib.parse.urlencode({'names': name, 'sportId': 1, 'active': 'true'})
    data = _mlb_get(f'{_MLB_API}/people/search?{q}')
    pid = None
    if data and data.get('people'):
        pid = data['people'][0]['id']
    _mlb_id_cache[key] = pid
    return pid

def ha_split(pitcher_name, season):
    """Home K/start minus Away K/start from MLB Stats API statSplits."""
    pid = mlb_player_id(pitcher_name)
    if not pid:
        return None
    url = (f'{_MLB_API}/people/{pid}/stats?stats=statSplits&group=pitching'
           f'&season={season}&sitCodes=h,a')
    data = _mlb_get(url)
    if not data:
        return None
    home_k = home_g = away_k = away_g = None
    for st in data.get('stats', []):
        for sp in st.get('splits', []):
            code = (sp.get('split') or {}).get('code', '')
            stat = sp.get('stat', {})
            k  = stat.get('strikeOuts')
            gs = stat.get('gamesStarted') or stat.get('gamesPlayed')
            if k is None or not gs:
                continue
            try:
                if code == 'h':
                    home_k, home_g = float(k), float(gs)
                elif code == 'a':
                    away_k, away_g = float(k), float(gs)
            except (TypeError, ValueError):
                continue
    if home_g and away_g and home_g > 0 and away_g > 0:
        return round(home_k / home_g - away_k / away_g, 1)
    return None

# ── MAIN ─────────────────────────────────────────────────────────
def main():
    if not BDL_KEY:
        print("Phase 2 skipped: no BDL_KEY. (existing cache left untouched)")
        return

    DATA   = json.load(open(DATA_FILE, encoding='utf-8'))
    season = datetime.today().year

    slate = []
    for r in DATA.get('SP_Projections', []):
        nm = (r.get('Pitcher') or '').strip()
        if nm and nm.upper() != 'TBD':
            slate.append({'name': nm, 'opp': (r.get('Opp') or '').strip()})

    if not slate:
        print("Phase 2 skipped: no pitchers in slate. (existing cache left untouched)")
        return

    print(f"Phase 2: {len(slate)} pitchers, season {season}, "
          f"deadline {DEADLINE_S:.0f}s")

    cache = load_cache()

    # Seed today's result with cached values for today's pitchers so every
    # incremental save is already at least as good as yesterday's file.
    savant = {}
    for p in slate:
        key = p['name'].lower()
        if key in cache:
            savant[key] = dict(cache[key])
    if savant:
        print(f"  Seeded {len(savant)}/{len(slate)} pitchers from cache")

    # ── OPPONENT LINEUP K% ────────────────────────────────────────
    team_k = {}
    ts = list(paged('/teams/season_stats', {'season': season, 'per_page': 100}))
    print(f"  /teams/season_stats returned {len(ts)} rows")
    if ts:
        print(f"  Sample team row keys: {list(ts[0].keys())[:20]}")

    for row in ts:
        tm   = row.get('team') or {}
        abbr = (tm.get('abbreviation') or row.get('team_name') or '').upper()
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

    # ── PLAYER ID LOOKUP ─────────────────────────────────────────
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
        for pl in resp.get('data', []):
            full = norm(pl.get('full_name') or f"{pl.get('first_name','')} {pl.get('last_name','')}")
            if parts and full.endswith(norm(parts[-1])) and full[:1] == want[:1]:
                return pl['id']
        return None

    ids = {}
    for p in slate:
        if past_deadline():
            break
        try:
            pid = find_id(p['name'])
            if pid:
                ids[p['name']] = pid
            else:
                print(f"  No ID: {p['name']}")
        except Exception as e:
            print(f"  ID lookup error {p['name']}: {e}")
    print(f"  Matched {len(ids)}/{len(slate)} pitchers")

    # ── RECENT FORM (K/start) ─────────────────────────────────────
    form = {}
    if ids:
        ss = list(paged('/season_stats',
                        {'season': season, 'player_ids[]': list(ids.values()),
                         'per_page': 100}))
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

    # ── PITCH METRICS (SwStr%, Chase%, Arsenal Whiff%) ───────────
    def pitch_metrics(pid):
        rows = list(paged('/pitcher_pitch_type_season_stats',
                          {'season': season, 'player_id': pid, 'per_page': 100}))
        if not rows:
            return {}
        if not getattr(pitch_metrics, '_logged', False):
            print(f"  pitch_type row keys: {list(rows[0].keys())[:15]}")
            pitch_metrics._logged = True
        rows = [r for r in rows
                if isinstance(r, dict) and str(r.get('player_id')) == str(pid)]
        if not rows:
            return {}
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

    # ── MAIN LOOP — fresh values merge ON TOP of cached ones ─────
    stats = {'fresh_vals': 0, 'cache_vals': 0,
             'all_fresh': 0, 'mixed': 0, 'cache_only': 0, 'none': 0}
    source = {}

    for p in slate:
        key = p['name'].lower()
        try:
            fresh = {}
            pid = ids.get(p['name'])

            if pid and not past_deadline():
                try:
                    fresh.update(pitch_metrics(pid))
                except Exception as e:
                    print(f"  {p['name']}: pitch metrics error ({e})")

                if pid in form:
                    fresh['recent_form'] = form[pid]

                try:
                    hs = ha_split(p['name'], season)
                    if hs is not None:
                        fresh['ha_split'] = hs
                except Exception as e:
                    print(f"  {p['name']}: H/A split error ({e})")

            opp_abbr = (p['opp'] or '').upper().strip()
            ok = team_k.get(opp_abbr)
            if ok is None:
                for variant in [opp_abbr, opp_abbr.replace('WAS', 'WSH'),
                                opp_abbr.replace('WSH', 'WAS'),
                                opp_abbr.replace('CHW', 'CWS')]:
                    ok = team_k.get(variant)
                    if ok is not None:
                        break
            if ok is not None:
                fresh['opp_lineup_k_pct'] = ok

            cached_m = savant.get(key, {})
            merged = dict(cached_m)
            merged.update(fresh)               # fresh wins; cache fills gaps

            stats['fresh_vals'] += len(fresh)
            stats['cache_vals'] += sum(1 for k in merged if k not in fresh)
            if merged:
                if fresh and not cached_m:
                    src = 'fresh'
                    stats['all_fresh'] += 1
                elif fresh:
                    src = 'fresh+cache' if any(k not in fresh for k in merged) else 'fresh'
                    stats['mixed' if src == 'fresh+cache' else 'all_fresh'] += 1
                else:
                    src = 'cache'
                    stats['cache_only'] += 1
                source[key] = src
                if merged != cached_m or key not in savant:
                    savant[key] = merged
                    save(savant)
            else:
                source[key] = 'none'
                stats['none'] += 1

        except Exception as e:
            print(f"  {p['name']}: skipped ({e})")
            if key in savant:
                source[key] = 'cache'
                stats['cache_only'] += 1

    # ── FINAL WRITE — never clobber with nothing ──────────────────
    if savant:
        save(savant)
    elif cache:
        # total outage but an old cache exists outside today's slate names
        print("  No data for today's slate — existing file left untouched")
    else:
        print("  No data fetched and no cache — not writing a file")

    # ── SUMMARY ──────────────────────────────────────────────────
    filled = sum(len(v) for v in savant.values())
    print(f"\nWrote {SAVANT_FILE}: {len(savant)} pitchers, {filled} metric values"
          if savant else f"\n{SAVANT_FILE}: unchanged")
    print(f"  Sources — fresh-only: {stats['all_fresh']} · fresh+cache: {stats['mixed']}"
          f" · cache-only: {stats['cache_only']} · none: {stats['none']}"
          f"  ({stats['fresh_vals']} fresh values, {stats['cache_vals']} carried from cache)")
    if stats['cache_only'] and not stats['all_fresh'] and not stats['mixed']:
        print("  ⚠ All values came from cache — check BDL_KEY / API status")

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
            tag = source.get(p['name'].lower(), '')
            print(f"  {p['name']} [{tag}]: " + " | ".join(bits))
        else:
            print(f"  {p['name']}: no metrics")

if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"[phase2] FATAL but non-blocking — slate build continues: {e}")
        traceback.print_exc()
        sys.exit(0)
