#!/usr/bin/env python3
"""
fetch_streaks.py  --  builds streaks.json for streak analysis.

Streak sources, in priority order:
  1. balldontlie MLB API   (/mlb/v1/games + /mlb/v1/stats)   [needs BDL_KEY]
  2. MLB Stats API         (statsapi.mlb.com, free, no key)  [fallback]

For every batter who has played in the last LOOKBACK_DAYS, computes:
  hitStreak  - consecutive games with >=1 hit
  hrStreak   - consecutive games with >=1 HR
  hrrStreak  - consecutive games with >=1 hit AND >=1 run AND >=1 RBI (same game)

Writes  {name_lower: {hitStreak, hrStreak, hrrStreak}}  to STREAKS_OUT
(default streaks_live.json).  Designed to NEVER raise — on any failure it
writes whatever it has (possibly empty) and prints a clear diagnostic so the
build keeps going.

Env:
  BDL_KEY         balldontlie GOAT key (optional; falls back to MLB Stats API)
  STREAKS_OUT     output path (default 'streaks_live.json')
  STREAK_DAYS     lookback window in days (default '10')
  BDL_MIN_GAP     min seconds between balldontlie calls (default '0.2')
"""

import os, json, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, date, timedelta

BDL_KEY     = os.environ.get('BDL_KEY', '').strip()
BDL_BASE    = 'https://api.balldontlie.io/mlb/v1'
MLB_BASE    = 'https://statsapi.mlb.com/api/v1'
OUT_FILE    = os.environ.get('STREAKS_OUT', 'streaks_live.json')
LOOKBACK    = int(os.environ.get('STREAK_DAYS', '10'))
MIN_GAP     = float(os.environ.get('BDL_MIN_GAP', '0.2'))
MLB_MIN_GAP = float(os.environ.get('MLB_MIN_GAP', '0.15'))

_last = [0.0]
def _pace():
    now = time.time()
    wait = MIN_GAP - (now - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()

# ──────────────────────────────────────────────────────────────────────
# Streak math (shared by both sources)
# ──────────────────────────────────────────────────────────────────────
def _compute(player_games):
    """
    player_games[name_lower] = list of (date_str, hits, hrs, runs, rbi)
    Returns {name_lower: {hitStreak, hrStreak, hrrStreak}} for active streaks.
    """
    result = {}
    for key, games in player_games.items():
        games.sort(key=lambda x: x[0])      # oldest -> newest
        rev = list(reversed(games))         # newest -> oldest
        hit_s = hr_s = hrr_s = 0
        for g in rev:
            if g[1] >= 1: hit_s += 1
            else: break
        for g in rev:
            if g[2] >= 1: hr_s += 1
            else: break
        for g in rev:
            if g[1] >= 1 and g[3] >= 1 and g[4] >= 1: hrr_s += 1
            else: break
        if hit_s or hr_s or hrr_s:
            result[key] = {"hitStreak": hit_s, "hrStreak": hr_s, "hrrStreak": hrr_s}
    return result

# ──────────────────────────────────────────────────────────────────────
# Source 1 — balldontlie
# ──────────────────────────────────────────────────────────────────────
def _bdl_get(path, params=None, retries=4):
    url = BDL_BASE + path
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
            if e.code == 429:
                backoff = min(10 * (attempt + 1), 45)
                print(f"    [bdl] rate limited, waiting {backoff}s...")
                time.sleep(backoff)
                continue
            if e.code in (401, 403):
                print(f"    [bdl] key rejected (HTTP {e.code}) — falling back to MLB Stats API")
                return None
            break
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    print(f"    [bdl] request failed ({path}): {last_err}")
    return None

def fetch_streaks_bdl():
    if not BDL_KEY:
        print("[streaks] no BDL_KEY set — skipping balldontlie")
        return None
    print(f"[streaks] balldontlie: pulling last {LOOKBACK} days of games...")
    today = date.today()
    player_games = {}
    games_seen = 0
    for d in range(LOOKBACK):
        day = today - timedelta(days=d)
        ds  = day.strftime('%Y-%m-%d')
        resp = _bdl_get('/games', {'dates[]': ds, 'per_page': 100})
        if resp is None:
            return None                       # auth/network fail -> let caller fall back
        games = resp.get('data', [])
        game_ids = [g['id'] for g in games if 'id' in g
                    and str(g.get('status', '')).lower() in ('final', 'completed', 'closed', 'f')]
        if not game_ids:
            continue
        games_seen += len(game_ids)
        # Pull per-player stats for each game (paginate)
        for gid in game_ids:
            cursor = None
            while True:
                params = {'game_ids[]': gid, 'per_page': 100}
                if cursor:
                    params['cursor'] = cursor
                sresp = _bdl_get('/stats', params)
                if sresp is None:
                    return None
                for s in sresp.get('data', []):
                    player = s.get('player') or {}
                    name = ((player.get('full_name')
                             or f"{player.get('first_name','')} {player.get('last_name','')}").strip())
                    if not name:
                        continue
                    # balldontlie hitting fields
                    hits = int(s.get('hits') or s.get('h') or 0)
                    hrs  = int(s.get('home_runs') or s.get('hr') or 0)
                    runs = int(s.get('runs') or s.get('r') or 0)
                    rbi  = int(s.get('rbi') or s.get('rbis') or 0)
                    ab   = int(s.get('at_bats') or s.get('ab') or 0)
                    if ab == 0 and hits == 0 and hrs == 0 and runs == 0 and rbi == 0:
                        continue              # didn't bat
                    key = name.lower()
                    player_games.setdefault(key, []).append((ds, hits, hrs, runs, rbi))
                cursor = (sresp.get('meta') or {}).get('next_cursor')
                if not cursor:
                    break
    if games_seen == 0:
        print("[streaks] balldontlie returned 0 completed games — falling back")
        return None
    result = _compute(player_games)
    active = sum(1 for v in result.values() if any(v.values()))
    print(f"[streaks] balldontlie OK: {games_seen} games, "
          f"{len(player_games)} batters, {active} active streaks")
    return result

# ──────────────────────────────────────────────────────────────────────
# Source 2 — MLB Stats API (free fallback)
# ──────────────────────────────────────────────────────────────────────
def fetch_streaks_mlb():
    print(f"[streaks] MLB Stats API: pulling last {LOOKBACK} days of box scores (per-game)...")
    today = date.today()
    start = today - timedelta(days=LOOKBACK)
    sched_url = (f"{MLB_BASE}/schedule?sportId=1"
                 f"&startDate={start}&endDate={today}")
    try:
        req = urllib.request.Request(sched_url, headers={"User-Agent": "DailySlate/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
    except Exception as e:
        print(f"[streaks] MLB Stats API schedule unavailable: {e}")
        return {}

    # Collect (gamePk, date_str) for every completed game. Bulk boxscore
    # hydrate over a date range is unreliable (returns empty/partial box
    # objects), so we fetch each game's /game/{pk}/boxscore individually —
    # the fully-populated endpoint grade_results.fetch_box_results() trusts.
    games = []
    for date_obj in data.get("dates", []):
        ds = date_obj.get("date", "")
        for game in date_obj.get("games", []):
            status = (game.get("status") or {}).get("codedGameState", "")
            if status not in ("F", "O", "C", "TR"):
                continue
            pk = game.get("gamePk")
            if pk:
                games.append((pk, ds))

    if not games:
        print("[streaks] MLB Stats API returned 0 completed games")
        return {}

    player_games = {}
    fetched, failed = 0, 0
    for pk, ds in games:
        try:
            box_url = f"{MLB_BASE}/game/{pk}/boxscore"
            breq = urllib.request.Request(box_url, headers={"User-Agent": "DailySlate/1.0"})
            with urllib.request.urlopen(breq, timeout=25) as r:
                box = json.load(r)
        except Exception as e:
            failed += 1
            print(f"[streaks]   game {pk} boxscore failed (non-fatal): {e}")
            time.sleep(MLB_MIN_GAP)
            continue
        fetched += 1
        for side in ("home", "away"):
            team = ((box.get("teams") or {}).get(side)) or {}
            for pid, pdata in (team.get("players") or {}).items():
                name = ((pdata.get("person") or {}).get("fullName") or "").strip()
                if not name:
                    continue
                bat = (pdata.get("stats") or {}).get("batting") or {}
                ab   = int(bat.get("atBats")   or 0)
                hits = int(bat.get("hits")     or 0)
                hrs  = int(bat.get("homeRuns") or 0)
                runs = int(bat.get("runs")     or 0)
                rbi  = int(bat.get("rbi")      or 0)
                if ab == 0 and hits == 0 and hrs == 0 and runs == 0:
                    continue
                key = name.lower()
                player_games.setdefault(key, []).append((ds, hits, hrs, runs, rbi))
        time.sleep(MLB_MIN_GAP)

    result = _compute(player_games)
    active = sum(1 for v in result.values() if any(v.values()))
    print(f"[streaks] MLB Stats API OK (per-game): {fetched} games fetched, "
          f"{failed} failed, {len(player_games)} batters, {active} active streaks")
    return result

# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main():
    streaks = None
    try:
        streaks = fetch_streaks_mlb()       # statsapi first: 100% coverage
    except Exception as e:
        print(f"[streaks] MLB Stats API crashed (non-fatal): {e}")
        streaks = None

    if not streaks:                          # None or empty -> fallback
        try:
            streaks = fetch_streaks_bdl()
        except Exception as e:
            print(f"[streaks] balldontlie crashed (non-fatal): {e}")
            streaks = {}

    streaks = streaks or {}
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(streaks, f)
    active = sum(1 for v in streaks.values() if any(v.values()))
    print(f"[streaks] ✓ Wrote {OUT_FILE} — {len(streaks)} players, {active} active streaks")

if __name__ == '__main__':
    main()
