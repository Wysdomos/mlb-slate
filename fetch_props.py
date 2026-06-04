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

for gid in game_ids:
    cursor = None
    while True:
        params = {'game_id': gid, 'prop_type': 'pitcher_strikeouts', 'per_page': 100}
        if cursor:
            params['cursor'] = cursor
        resp = api_get('/odds/player_props', params)
        for row in resp.get('data', []):
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
            cur = prop_by_player.get(pid)
            # keep the entry from the higher-priority vendor
            def rank(v):
                return VENDOR_PRIORITY.index(v) if v in VENDOR_PRIORITY else 99
            if cur is None or rank(vendor) < rank(cur['vendor']):
                prop_by_player[pid] = entry
        cursor = (resp.get('meta') or {}).get('next_cursor')
        if not cursor:
            break

print(f"  Collected K lines for {len(prop_by_player)} players")

if not prop_by_player:
    raise SystemExit(
        "\n\n==================== BUILD STOPPED ====================\n"
        "No strikeout props posted yet for today's games.\n"
        "Pitcher K lines usually post the morning of -- try again later.\n"
        "Nothing has been pushed.\n"
        "=======================================================\n"
    )

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

with open(K_PROPS_FILE, 'w', encoding='utf-8') as f:
    json.dump(k_props, f, ensure_ascii=False, indent=1)

print(f"\nWrote {K_PROPS_FILE}: {matched}/{len(slate_pitchers)} pitchers matched to a real K line")
for sp in slate_pitchers:
    if sp.lower() in k_props:
        e = k_props[sp.lower()]
        print(f"  {sp}: O/U {e['line']} ({e['vendor']})")
if unmatched:
    print(f"No line yet for: {', '.join(unmatched)}")
