"""
fetch_props.py -- Real prop-line fetcher (balldontlie MLB API)
==============================================================
Runs in Colab BEFORE pushing. Pulls real sportsbook strikeout lines
for the slate's starting pitchers and writes k_props.json, which
build_k_report.py reads to show: Safe Floor + Real Book Line + Cushion.

Reads:   day_data.json        (or DATA_FILE env var) -- for pitcher names + date
Key:     BDL_KEY env var      (the balldontlie GOAT API key)
Writes:  k_props.json         (or K_PROPS_FILE env var)

Output format (keyed by lowercase pitcher name):
  {
    "tarik skubal": {"line": 6.5, "over_odds": -115, "under_odds": -105, "vendor": "fanduel"},
    ...
  }

FAIL POLICY: if the key is missing or the API is unreachable, this RAISES
so the Colab "Run All" stops before pushing. If the API works but a given
pitcher simply has no posted line yet, that pitcher is skipped (logged) and
the K Report just shows the floor for them, as it does today.

FALLBACK: if ODDS_API_KEY is set, pitchers that balldontlie could not
cover are filled from The Odds API (fetch_odds_api.py) before writing.
If ODDS_API_KEY is unset, behavior is EXACTLY as before -- a no-op.
"""

import os
import sys
import json
import time
from datetime import datetime, date

import urllib.request
import urllib.parse
import urllib.error

DATA_FILE    = os.environ.get('DATA_FILE',    'day_data.json')
K_PROPS_FILE = os.environ.get('K_PROPS_FILE', 'k_props.json')
BDL_KEY      = os.environ.get('BDL_KEY', '').strip()
ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '').strip()   # optional fallback (The Odds API)
BASE         = 'https://api.balldontlie.io/mlb/v1'

# Sportsbook preference order (first available wins for a given pitcher)
# FanDuel preferred; falls back to DraftKings, then others, if FD has no line
VENDOR_PRIORITY = ['fanduel', 'draftkings', 'betmgm', 'caesars', 'betrivers', 'fanatics']

# ---- Key required -----------------------------------------------------------
if not BDL_KEY:
    raise SystemExit(
        "\n\n==================== BUILD STOPPED ====================\n"
        "No balldontlie API key found (BDL_KEY).\n"
        "Run the key cell first. Nothing has been pushed.\n"
        "=======================================================\n"
    )

# ---- HTTP helper ------------------------------------------------------------
# Pace requests so we never burst past the per-minute cap. The free tier is
# 5 req/min, so a ~13s gap is safe on any tier (paid tiers just never wait).
MIN_GAP = float(os.environ.get('BDL_MIN_GAP', '0.5'))
_last_call = [0.0]

def _pace():
    now = time.time()
    wait = MIN_GAP - (now - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()

def api_get(path, params=None, retries=6):
    url = BASE + path
    if params:
        url += '?' + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={'Authorization': BDL_KEY})
    last_err = None
    for attempt in range(retries):
        _pace()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:          # rate limited -> wait out the window
                backoff = min(15 * (attempt + 1), 60)
                print(f"    rate limited, waiting {backoff}s...")
                time.sleep(backoff)
                continue
            if e.code in (401, 403):
                raise SystemExit(
                    "\n\n==================== BUILD STOPPED ====================\n"
                    f"balldontlie rejected the API key (HTTP {e.code}).\n"
                    "Props require the GOAT tier. Confirm your plan at app.balldontlie.io.\n"
                    "Nothing has been pushed.\n"
                    "=======================================================\n"
                )
            break
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise SystemExit(
        "\n\n==================== BUILD STOPPED ====================\n"
        f"Could not reach balldontlie ({path}): {last_err}\n"
        "If this is a rate limit (429), wait 60 seconds and re-run Cell 7.\n"
        "Nothing has been pushed.\n"
        "=======================================================\n"
    )

# ---- Slate date + pitchers --------------------------------------------------
DATA = json.load(open(DATA_FILE, encoding='utf-8'))

def get_slate_date():
    for row in DATA.get('BP_Games', []):
        raw = str(row.get('GameDate', ''))[:10]
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            pass
    return date.today()

slate_date = get_slate_date()
DATE_STR = slate_date.strftime('%Y-%m-%d')

slate_pitchers = []
for r in DATA.get('SP_Projections', []):
    nm = (r.get('Pitcher') or '').strip()
    if nm and nm.upper() != 'TBD':
        slate_pitchers.append(nm)

if not slate_pitchers:
    raise SystemExit(
        "\n\n==================== BUILD STOPPED ====================\n"
        "No starting pitchers in the slate data. Nothing pushed.\n"
        "=======================================================\n"
    )

print(f"Fetching real K lines for {len(slate_pitchers)} starters on {DATE_STR}...")

# ---- 1) Games on the slate date --------------------------------------------
games_resp = api_get('/games', {'dates[]': DATE_STR, 'per_page': 100})
games = games_resp.get('data', [])
game_ids = [g['id'] for g in games if 'id' in g]
print(f"  Found {len(game_ids)} games for {DATE_STR}")

if not game_ids:
    raise SystemExit(
        "\n\n==================== BUILD STOPPED ====================\n"
        f"balldontlie returned no games for {DATE_STR}.\n"
        "The date may be off, or lines are not posted yet. Nothing pushed.\n"
        "=======================================================\n"
    )

# ---- 2) Strikeout props for those games ------------------------------------
# Collect: player_id -> best line per vendor priority
prop_by_player = {}

# Map game_id -> "AWAY @ HOME" for clearer logging
game_label = {}
for g in games:
    if 'id' in g:
        away = (g.get('away_team') or {}).get('abbreviation') or g.get('away_team_name') or '?'
        home = (g.get('home_team') or {}).get('abbreviation') or g.get('home_team_name') or '?'
        game_label[g['id']] = f"{away} @ {home}"

def rank(v):
    return VENDOR_PRIORITY.index(v) if v in VENDOR_PRIORITY else 99

props_per_game = {}
vendors_per_player = {}   # pid -> set of books balldontlie returned (for fallback visibility)
for gid in game_ids:
    cursor = None
    seen_this_game = 0
    while True:
        params = {'game_id': gid, 'prop_type': 'pitcher_strikeouts', 'per_page': 100}
        if cursor:
            params['cursor'] = cursor
        resp = api_get('/odds/player_props', params)
        rows = resp.get('data', [])
        seen_this_game += len(rows)
        for row in rows:
            pid = row.get('player_id')
            vendor = (row.get('vendor') or '').lower()
            try:
                line = float(row.get('line_value'))
            except (TypeError, ValueError):
                continue
            mkt = row.get('market') or {}
            entry = {
                'line': line,
                'over_odds': mkt.get('over_odds'),
                'under_odds': mkt.get('under_odds'),
                'vendor': vendor,
            }
            if vendor:
                vendors_per_player.setdefault(pid, set()).add(vendor)
            cur = prop_by_player.get(pid)
            # keep the entry from the higher-priority vendor (FanDuel first, then fallbacks)
            if cur is None or rank(vendor) < rank(cur['vendor']):
                prop_by_player[pid] = entry
        cursor = (resp.get('meta') or {}).get('next_cursor')
        if not cursor:
            break
    props_per_game[gid] = seen_this_game

print(f"  Collected K lines for {len(prop_by_player)} players")
# Show games where balldontlie returned ZERO strikeout props (the real coverage gap)
empty_games = [game_label.get(g, str(g)) for g, n in props_per_game.items() if n == 0]
if empty_games:
    print(f"  ⚠ balldontlie returned NO K props for {len(empty_games)} game(s): {', '.join(empty_games)}")

if not prop_by_player:
    if not ODDS_API_KEY:
        raise SystemExit(
            "\n\n==================== BUILD STOPPED ====================\n"
            "No strikeout props posted yet for today's games.\n"
            "Pitcher K lines usually post the morning of -- try again later.\n"
            "Nothing has been pushed.\n"
            "=======================================================\n"
        )
    print("  \u26a0 balldontlie returned ZERO strikeout props -- relying on The Odds API fallback")

# ---- 3) Map player_id -> name ----------------------------------------------
player_ids = list(prop_by_player.keys())
id_to_name = {}
# batch lookup
for i in range(0, len(player_ids), 100):
    batch = player_ids[i:i+100]
    resp = api_get('/players', {'player_ids[]': batch, 'per_page': 100})
    for pl in resp.get('data', []):
        full = (pl.get('full_name')
                or f"{pl.get('first_name','')} {pl.get('last_name','')}").strip()
        id_to_name[pl['id']] = full

# ---- 4) Match to slate pitchers by name ------------------------------------
def norm(n):
    import unicodedata
    s = (n or '').lower()
    # strip accents (José -> jose)
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    # normalize separators to spaces, drop punctuation
    for ch in ['.', ',', "'", '-']:
        s = s.replace(ch, ' ' if ch == '-' else '')
    toks = s.split()
    # drop generational suffixes that one source may include and the other omit
    toks = [t for t in toks if t not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    return ' '.join(toks)

name_to_line = {}
for pid, entry in prop_by_player.items():
    nm = id_to_name.get(pid)
    if nm:
        name_to_line[norm(nm)] = entry

k_props = {}
matched, unmatched = 0, []
for sp in slate_pitchers:
    key = norm(sp)
    if key in name_to_line:
        k_props[sp.lower()] = name_to_line[key]
        matched += 1
    else:
        unmatched.append(sp)

# ---- 4b) Fallback: The Odds API for pitchers balldontlie missed --------------
# Fires ONLY when ODDS_API_KEY is set. Must never kill the build: any failure
# here is logged and we proceed with whatever balldontlie matched above.
ODDS_META = None
EXTRA_ODDS_META = None
prev_entries = {}
if os.path.exists(K_PROPS_FILE):
    try:
        _prev = json.load(open(K_PROPS_FILE, encoding='utf-8'))
        if isinstance(_prev, dict) and (_prev.get('_meta') or {}).get('date') == DATE_STR:
            prev_entries = _prev
    except Exception:
        prev_entries = {}
if unmatched and not ODDS_API_KEY:
    print(f"  (no ODDS_API_KEY set -- {len(unmatched)} pitcher(s) stay line-less; "
          "add the ODDS_API_KEY secret to enable The Odds API fallback)")
elif unmatched and ODDS_API_KEY:
    try:
        import fetch_odds_api

        # Same-day reuse: only trust prior fallback entries written for THIS
        # slate date (the committed file is otherwise yesterday's slate).
        team_of = {}
        for r in DATA.get('SP_Projections', []):
            _nm = (r.get('Pitcher') or '').strip()
            _tm = (r.get('Team') or '').strip().upper()
            if _nm and _tm:
                team_of[_nm] = _tm

        print(f"\nFalling back to The Odds API for {len(unmatched)} pitcher(s): {', '.join(unmatched)}")
        _filled, ODDS_META = fetch_odds_api.fill_missing(
            api_key=ODDS_API_KEY,
            date_str=DATE_STR,
            missing=unmatched,
            norm=norm,
            vendor_priority=VENDOR_PRIORITY,
            team_of=team_of,
            prev_entries=prev_entries,
        )
        for _lname, _entry in _filled.items():
            k_props[_lname] = _entry
        _still = [sp for sp in unmatched if sp.lower() not in k_props]
        matched += len(unmatched) - len(_still)
        unmatched = _still
        print(f"  Odds API filled {len(_filled)} pitcher(s) "
              f"({ODDS_META.get('credits_used_this_run', '?')} credit(s) used, "
              f"{ODDS_META.get('remaining', '?')} remaining this month)")
    except Exception as e:
        print(f"  \u26a0 Odds API fallback failed ({e}) -- continuing with balldontlie data only")

if ODDS_API_KEY:
    try:
        import fetch_odds_api

        pitcher_team_of = {}
        for r in DATA.get('SP_Projections', []):
            _nm = (r.get('Pitcher') or '').strip()
            _tm = (r.get('Team') or '').strip().upper()
            if _nm and _tm:
                pitcher_team_of[_nm] = _tm

        batter_names = []
        team_of = dict(pitcher_team_of)
        for r in DATA.get('BP_Batters', []):
            _nm = (r.get('FullName') or '').strip()
            _tm = (r.get('Team') or '').strip().upper()
            if _nm:
                batter_names.append(_nm)
                if _tm:
                    team_of[_nm] = _tm

        needs_by_market = {
            'pitcher_hits_allowed': slate_pitchers,
            'pitcher_outs': slate_pitchers,
            'batter_total_bases': batter_names,
        }
        print("\nFetching Chapter H Odds API main lines "
              "(pitcher_hits_allowed, pitcher_outs, batter_total_bases)...")
        _extra_filled, EXTRA_ODDS_META = fetch_odds_api.fill_market_lines(
            api_key=ODDS_API_KEY,
            date_str=DATE_STR,
            needs_by_market=needs_by_market,
            norm=norm,
            vendor_priority=VENDOR_PRIORITY,
            team_of=team_of,
            prev_entries=prev_entries,
        )
        for _lname, _entry in _extra_filled.get('pitcher_hits_allowed', {}).items():
            k_props.setdefault(_lname, {})['hits_allowed'] = _entry
        for _lname, _entry in _extra_filled.get('pitcher_outs', {}).items():
            k_props.setdefault(_lname, {})['outs'] = _entry
        if _extra_filled.get('batter_total_bases'):
            tb = k_props.setdefault('_batter_total_bases', {})
            for _lname, _entry in _extra_filled['batter_total_bases'].items():
                tb[_lname] = _entry
        print(f"  Odds API Chapter H request count: "
              f"{EXTRA_ODDS_META.get('request_count_this_run', 0)}")
    except Exception as e:
        print(f"  \u26a0 Chapter H Odds API main-line fetch failed ({e}) -- continuing without those lines")
else:
    print("\nOdds API Chapter H request count: 0 (no ODDS_API_KEY set)")

if not k_props and not prop_by_player:
    raise SystemExit(
        "\n\n==================== BUILD STOPPED ====================\n"
        "No strikeout props found from ANY source for today's games.\n"
        "Pitcher K lines usually post the morning of -- try again later.\n"
        "Nothing has been pushed.\n"
        "=======================================================\n"
    )

meta = {'date': DATE_STR}
if ODDS_META:
    meta.update(ODDS_META)
if EXTRA_ODDS_META:
    meta['chapter_h_markets'] = EXTRA_ODDS_META
    meta['oddsapi_extra_market_request_count'] = EXTRA_ODDS_META.get('request_count_this_run', 0)
if meta:
    k_props['_meta'] = meta

with open(K_PROPS_FILE, 'w', encoding='utf-8') as f:
    json.dump(k_props, f, ensure_ascii=False, indent=1)

print(f"\nWrote {K_PROPS_FILE}: {matched}/{len(slate_pitchers)} pitchers matched to a real K line")
# Build pid lookup so we can report which books were available per matched pitcher
name_to_pid = {}
for pid, nm in id_to_name.items():
    name_to_pid[norm(nm)] = pid
for sp in slate_pitchers:
    if sp.lower() in k_props:
        e = k_props[sp.lower()]
        used = e['vendor']
        pid = name_to_pid.get(norm(sp))
        books = vendors_per_player.get(pid, set())
        if e.get('src') == 'oddsapi':
            note = '  [via The Odds API]'
        elif used == 'fanduel':
            note = ''
        elif 'fanduel' not in books:
            note = '  [FanDuel had no line - fell back]'
        else:
            note = '  [fallback]'
        others = ','.join(sorted(books)) if books else used
        print(f"  {sp}: O/U {e['line']} ({used}){note}  | books seen: {others}")
if unmatched:
    print(f"No line yet for: {', '.join(unmatched)}")
    # ---- DIAGNOSTIC: why did each miss happen? ----
    # Shows whether balldontlie returned the player at all (name-match issue)
    # or simply had no prop for them at build time (timing/coverage issue).
    print("\n--- DIAGNOSTIC: balldontlie returned props for these names ---")
    returned = sorted(id_to_name.values())
    print(f"  ({len(returned)}) {', '.join(returned)}")
    print("--- unmatched slate pitchers, normalized + closest returned name ---")
    import difflib
    returned_norm = {norm(n): n for n in returned}
    for sp in unmatched:
        k = norm(sp)
        near = difflib.get_close_matches(k, list(returned_norm.keys()), n=1, cutoff=0.85)
        if near:
            print(f"  '{sp}' -> norm '{k}'  | CLOSE in feed: '{returned_norm[near[0]]}' (norm '{near[0]}') <-- name-match fix needed")
        else:
            print(f"  '{sp}' -> norm '{k}'  | NOT in balldontlie feed at build time <-- timing/coverage")
