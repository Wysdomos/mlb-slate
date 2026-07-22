# HANDOFF — Odds API K-Prop Fallback (feat/odds-api-fallback)
**The Daily Slate · Product Era, Chapter 1 · 2026-07-13**
**Builder→Reviewer chain:** module authored in-sandbox (concurrent session), independently reviewed, patched, and fully tested by Claude (architect). Executor of record: **Claude Code on the M5**.

---

## ⛔ GUARDRAILS (read before anything else)
1. **STOP gates are law.** Open the PR, then STOP. Nothing merges without the developer's explicit word. Claude reviews the PR link before the developer merges.
2. **Human-only secrets.** The `ODDS_API_KEY` is set ONLY by the developer at a hidden prompt: `gh secret set ODDS_API_KEY --repo Wysdomos/mlb-slate`. No AI ever sees or types the key value.
3. **Sign up at `the-odds-api.com` — WITH hyphens.** `theoddsapi.com` (no hyphens) is a different product and a trap. Free tier: 500 credits/month.
4. **Never merge via Brave browser** (two-tap bug). Use `gh` CLI or the GitHub app.
5. Said done ≠ done. Run the verification checklist at the bottom and paste real output.

---

## WHAT THIS DELIVERS
BDL's K-prop feed has real coverage gaps (today's feed held **one** pitcher). This adds The Odds API (`api.the-odds-api.com/v4`) as a **fallback only**:
- BDL stays primary and untagged. Fallback fires only for pitchers BDL missed.
- **Without the secret set, behavior is byte-identical to today** — the fallback is key-gated and the first Actions run after merge is a free live no-op test.
- Entries land in `k_props.json` keyed `name.lower()` with `{line, over_odds, under_odds, vendor, src:'oddsapi'}` plus a `_meta` block. `build_k_report.py` needs **zero changes** (verified: line 358 does `.get()` lookups only, so `_meta` is inert downstream).

### Architecture
`fetch_props.py` §4b (driver): after BDL, computes `missing`, builds `team_of` from SP_Projections, validates any same-day `k_props.json` via `_meta.date`, calls `fetch_odds_api.fill_missing(...)` inside a broad try/except (`"Odds API fallback failed"` → continue). Final gate unchanged: build stops only if **no source** produced props.

`fetch_odds_api.py` (module): FREE `/events` call (0 credits) with fixed UTC window (`T10:00:00Z → +1d T09:59:59Z`, covers all ET first pitches, no zoneinfo dep) → skip commenced games → query **team-mapped events first**, 1 credit each (`markets=pitcher_strikeouts&regions=us`; empty responses cost 0) → vendor priority `fanduel > draftkings > betmgm > caesars > betrivers > fanatics` (`williamhill_us`→caesars alias) → same-day entries reused at 0 credits → hard stops: per-run cap (`ODDS_MAX_PER_RUN`=20), monthly reserve floor (`ODDS_RESERVE`=60, reads `x-requests-remaining`), accurate accounting via `x-requests-last`. Never raises SystemExit.

---

## REVIEW REPORT (what independent review caught)
**Security: CLEAN.** Single host `api.the-odds-api.com`. No subprocess/eval/exec/base64. Env reads: `ODDS_MAX_PER_RUN`, `ODDS_RESERVE`, `ODDS_MIN_GAP`, `K_PROPS_FILE` only. daily.yml diff adds the secret env + timeout 2→4 min; no exfil paths.

**Two real bugs found and fixed by reviewer (both in `fetch_odds_api.py`, already applied to the embedded copy):**
1. **`covers()` case mismatch** — `nick in blob` compared a capitalized nickname (`'Red Sox'`) against a lowercased normalized blob. It could never match, so **team-priority ordering never worked**: every event was treated as sweep, maximum credit burn on every gap day. Fix: `norm(nick) in blob`.
2. **Unbounded sweep** — the secondary sweep fired for ANY still-missing pitcher, including ones whose own game was already queried (line not posted) or commenced. A K prop only exists in the pitcher's own game's event, so those sweeps are guaranteed-futile. Fix: sweep now fires **only** for pitchers who are unmapped or whose mapping matches no slate event (the genuine stale-trade/abbreviation case). Message: `"skipping sweep to save credits"`.

**One harness assertion corrected:** S3 originally asserted EV0 (a BDL-covered pitcher's game) is never queried — but the harness loads the real 31-starter `day_data.json`, and Bubba Chandler (PIT, genuinely missing) legitimately maps that event into primary. Corrected to the true invariant: *queried exactly once, never via sweep mode*.

**Accepted nitpicks (non-blocking):** a malformed event missing `id` would raise KeyError, escaping to the driver's catch-all → degrades to no-op, safe. urllib error strings don't embed URLs, so no apiKey scrubbing needed.

## TEST EVIDENCE — all green, 2026-07-13
- **Unit (offline, mocked HTTP): 13/13 PASS** — accent name matching (José Berríos), vendor priority, caesars alias, entry shape/src, early-stop, credit accounting, same-day reuse = 0 calls, reserve stop, per-run cap, commenced skip, over-only keeps `under_odds: None` (no fabricated data), **sweep gate saves credits (T7)**, **unmapped pitcher still swept (T8)**.
- **End-to-end gauntlet (real fetch_props.py via runpy, both APIs faked): 23/23 PASS across S1–S5** — S1: no key + empty BDL → original `BUILD STOPPED` preserved, no file written (the critical no-op safety property). S2: full fallback path, vendor priority, alias, both-sides preference, `_meta`, commenced skip. S3: BDL primary/untagged + gap fill + no sweep. S4: reserve guard, zero paid calls, any-source gate. S5: same-day reuse, fresh fetch for new gaps, reuse counted in `_meta`.

## QUOTA MATH (500 credits/month, free tier)
Events list: free. Each gap-game odds query: 1 credit (empty responses: 0). **Typical day: 1–4 credits** (gaps cluster in a few games). Worst day (BDL fully empty, like today): ≈ one credit per slate game ≈ 15, hard-capped at 20/run. Worst-case month ≈ 450 < 500, and the reserve floor halts at 60 remaining regardless. The covers() fix is what makes typical days cheap — pre-fix every gap day cost worst-case.

---

## FILES — exact tested bytes (verify md5 after writing)

### `fetch_odds_api.py`  (repo root -- NEW file)
`14151 bytes · md5 14cbba43bf5862449b5ed8398209151e`

```python
"""
fetch_odds_api.py -- The Odds API fallback for pitcher strikeout lines
======================================================================
Called by fetch_props.py AFTER the balldontlie pass, and ONLY for slate
pitchers that still have no K line. Fills the exact k_props.json entry
shape, so build_k_report.py needs zero changes:

    {"line": 6.5, "over_odds": -115, "under_odds": -105,
     "vendor": "fanduel", "src": "oddsapi"}

QUOTA DESIGN (free tier = 500 credits / month):
  * GET /v4/sports/baseball_mlb/events .......... 0 credits (always free)
  * GET /v4/sports/.../events/{id}/odds ......... 1 credit per event, max
      (markets=pitcher_strikeouts only, regions=us only; per the docs the
       cost is [unique markets RETURNED] x [regions], so an event with no
       props posted costs 0)
  * Events are queried ONLY if they involve a missing pitcher's team.
    Unmappable teams fall back to the remaining slate events, in order.
  * Same-day fallback entries already committed in k_props.json are
    reused instead of re-fetched (the workflow runs 3x per day).
  * Two hard budget stops, both env-tunable:
      ODDS_MAX_PER_RUN  max event-odds calls per run        (default 20)
      ODDS_RESERVE      stop once x-requests-remaining <= N (default 60)

FAIL POLICY: this module must NEVER kill the build. Every error raises
OddsApiError (or is caught upstream); fetch_props.py catches everything
and proceeds with whatever balldontlie matched. balldontlie is primary.
"""

import os
import json
import time
from datetime import datetime, timedelta, timezone

import urllib.request
import urllib.parse
import urllib.error

ODDS_BASE = 'https://api.the-odds-api.com/v4'
SPORT     = 'baseball_mlb'
MARKET    = 'pitcher_strikeouts'
REGION    = 'us'

# The Odds API bookmaker keys -> the vendor names The Daily Slate uses
BOOK_ALIAS = {'williamhill_us': 'caesars'}

# BallparkPal team abbreviations -> nickname tokens, matched as substrings
# of The Odds API's normalized full team names ("Philadelphia Phillies").
# Substring matching keeps this robust to city renames (e.g. "Athletics"
# with or without a city prefix). Alt abbreviations included on purpose.
TEAM_NICK = {
    'ARI': 'diamondbacks', 'AZ': 'diamondbacks',
    'ATL': 'braves', 'BAL': 'orioles', 'BOS': 'red sox',
    'CHC': 'cubs', 'CWS': 'white sox', 'CHW': 'white sox',
    'CIN': 'reds', 'CLE': 'guardians', 'COL': 'rockies',
    'DET': 'tigers', 'HOU': 'astros',
    'KC': 'royals', 'KCR': 'royals',
    'LAA': 'angels', 'LAD': 'dodgers', 'MIA': 'marlins',
    'MIL': 'brewers', 'MIN': 'twins', 'NYM': 'mets', 'NYY': 'yankees',
    'OAK': 'athletics', 'ATH': 'athletics',
    'PHI': 'phillies', 'PIT': 'pirates',
    'SD': 'padres', 'SDP': 'padres',
    'SEA': 'mariners',
    'SF': 'giants', 'SFG': 'giants',
    'STL': 'cardinals',
    'TB': 'rays', 'TBR': 'rays',
    'TEX': 'rangers', 'TOR': 'blue jays',
    'WSH': 'nationals', 'WAS': 'nationals',
}


class OddsApiError(Exception):
    """Any Odds API problem. Caught by fetch_props.py; never kills a build."""


# ---- HTTP (stdlib only, paced, 429-aware, never prints the api key) --------
_last_call = [0.0]

def _pace(min_gap):
    now = time.time()
    wait = min_gap - (now - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def _get(path, params, min_gap=0.35, retries=4, timeout=30):
    """GET a v4 endpoint. Returns (parsed_json, lowercase_headers_dict)."""
    url = ODDS_BASE + path + '?' + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(retries):
        _pace(min_gap)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                headers = {k.lower(): v for k, v in r.headers.items()}
                return json.loads(r.read().decode('utf-8')), headers
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                backoff = min(5 * (attempt + 1), 20)
                print(f"    Odds API rate limited (429), waiting {backoff}s...")
                time.sleep(backoff)
                continue
            if e.code in (401, 403):
                raise OddsApiError(
                    f"The Odds API rejected the key (HTTP {e.code}). "
                    "Check ODDS_API_KEY at the-odds-api.com/account."
                )
            if e.code == 422:
                raise OddsApiError(f"The Odds API rejected the request (HTTP 422) on {path}")
            break
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise OddsApiError(f"Could not reach The Odds API ({path}): {last_err}")


# ---- Slate-day event discovery (FREE endpoint) ------------------------------
def _slate_window_utc(date_str):
    """UTC window covering every first pitch on an ET slate date.
    Earliest MLB start ~11:30 AM ET (15:30Z); latest ~10:15 PM ET (02:15Z d+1)."""
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    return (f"{d.isoformat()}T10:00:00Z",
            f"{(d + timedelta(days=1)).isoformat()}T09:59:59Z")


def get_slate_events(api_key, date_str, min_gap=0.35):
    frm, to = _slate_window_utc(date_str)
    data, headers = _get(f'/sports/{SPORT}/events', {
        'apiKey': api_key,
        'commenceTimeFrom': frm,
        'commenceTimeTo': to,
        'dateFormat': 'iso',
    }, min_gap=min_gap)
    return (data or []), headers


# ---- Parse one event's pitcher_strikeouts market ----------------------------
def _parse_event_k_lines(ev_json, norm):
    """Returns {norm_pitcher_name: {vendor: entry}}, pairing Over/Under
    outcomes by (player, point) within each bookmaker."""
    out = {}
    for bm in ev_json.get('bookmakers') or []:
        raw = (bm.get('key') or '').lower()
        vendor = BOOK_ALIAS.get(raw, raw)
        for mkt in bm.get('markets') or []:
            if mkt.get('key') != MARKET:
                continue
            pair = {}   # (norm_name, point) -> {'over': price, 'under': price}
            for oc in mkt.get('outcomes') or []:
                who = norm(oc.get('description') or '')
                side = (oc.get('name') or '').lower()
                try:
                    point = float(oc.get('point'))
                except (TypeError, ValueError):
                    continue
                if not who or side not in ('over', 'under'):
                    continue
                pair.setdefault((who, point), {})[side] = oc.get('price')
            for (who, point), sides in pair.items():
                entry = {
                    'line': point,
                    'over_odds': sides.get('over'),
                    'under_odds': sides.get('under'),
                    'vendor': vendor,
                    'src': 'oddsapi',
                }
                cur = out.setdefault(who, {})
                old = cur.get(vendor)
                # keep one line per vendor; prefer the point with both sides
                if old is None or (
                    entry['over_odds'] is not None and entry['under_odds'] is not None
                    and (old.get('over_odds') is None or old.get('under_odds') is None)
                ):
                    cur[vendor] = entry
    return out


def _rank(vendor, priority):
    return priority.index(vendor) if vendor in priority else 99


# ---- Orchestrator ------------------------------------------------------------
def fill_missing(api_key, date_str, missing, norm, vendor_priority,
                 team_of=None, prev_entries=None,
                 max_per_run=None, reserve=None, min_gap=None):
    """
    missing         list of slate pitcher names (original casing), no line yet
    norm            fetch_props.norm -- shared so name matching is identical
    vendor_priority fetch_props.VENDOR_PRIORITY (FanDuel first)
    team_of         {pitcher_name: 'PIT'} from SP_Projections (optional)
    prev_entries    prior k_props.json dict, ALREADY validated by the caller
                    as belonging to this slate date (same-day reuse)
    Returns (filled, meta):
      filled  {lowercase_pitcher_name: entry} ready to merge into k_props
      meta    quota bookkeeping dict, written to k_props['_meta'] upstream
    """
    if max_per_run is None:
        max_per_run = int(os.environ.get('ODDS_MAX_PER_RUN', '20'))
    if reserve is None:
        reserve = int(os.environ.get('ODDS_RESERVE', '60'))
    if min_gap is None:
        min_gap = float(os.environ.get('ODDS_MIN_GAP', '0.35'))
    team_of = team_of or {}
    prev_entries = prev_entries or {}

    filled = {}
    still = list(missing)
    meta = {'date': date_str, 'source': 'the-odds-api.com',
            'events_queried': 0, 'credits_used_this_run': 0,
            'remaining': None, 'reused_same_day': 0}

    # 0) Same-day reuse: a line fetched on an earlier run today beats a dash.
    #    balldontlie already had its chance to refresh these upstream.
    for name in list(still):
        e = prev_entries.get(name.lower())
        if isinstance(e, dict) and e.get('src') == 'oddsapi' and e.get('line') is not None:
            filled[name.lower()] = e
            still.remove(name)
            meta['reused_same_day'] += 1
    if meta['reused_same_day']:
        print(f"  Reused {meta['reused_same_day']} same-day Odds API line(s) already in {os.environ.get('K_PROPS_FILE', 'k_props.json')}")
    if not still:
        return filled, meta

    # 1) Slate-day events (FREE -- 0 credits)
    events, headers = get_slate_events(api_key, date_str, min_gap=min_gap)
    try:
        meta['remaining'] = int(headers.get('x-requests-remaining'))
    except (TypeError, ValueError):
        pass
    print(f"  Odds API events for {date_str}: {len(events)} "
          f"(credits remaining this month: {meta['remaining']})")
    if not events:
        return filled, meta

    now_utc = datetime.now(timezone.utc)

    def commenced(ev):
        try:
            t = datetime.strptime(ev.get('commence_time', ''), '%Y-%m-%dT%H:%M:%SZ')
            return t.replace(tzinfo=timezone.utc) <= now_utc
        except (TypeError, ValueError):
            return False

    future = [ev for ev in events if not commenced(ev)]
    skipped = len(events) - len(future)
    if skipped:
        print(f"  Skipping {skipped} already-started game(s)")

    # 2) Order the queue: events covering a missing pitcher's team first,
    #    every other future event after (catches unmapped/traded oddities).
    def nick_of(pitcher):
        return TEAM_NICK.get((team_of.get(pitcher) or '').upper())

    def covers(ev, pitcher):
        nick = nick_of(pitcher)
        if not nick:
            return False
        blob = norm(f"{ev.get('home_team', '')} {ev.get('away_team', '')}")
        return norm(nick) in blob

    primary = [ev for ev in future if any(covers(ev, p) for p in still)]
    secondary = [ev for ev in future if ev not in primary]
    unmapped = [p for p in still if not nick_of(p)]
    if unmapped:
        print(f"  No team mapping for: {', '.join(unmapped)} -- will sweep remaining events if needed")

    in_secondary = False
    for ev in primary + secondary:
        if not still:
            break
        if meta['events_queried'] >= max_per_run:
            print(f"  ⚠ Odds API per-run cap hit ({max_per_run} events) -- stopping")
            break
        if meta['remaining'] is not None and meta['remaining'] <= reserve:
            print(f"  ⚠ Odds API monthly reserve reached ({meta['remaining']} <= {reserve}) -- stopping to protect the quota")
            break
        if not in_secondary and ev in secondary:
            # A pitcher's K prop can only appear in his own game's event.
            # Sweeping is only worthwhile for pitchers we could not locate:
            # no team mapping at all, or a mapping that matches no event on
            # the slate (stale abbreviation / trade). If every remaining gap
            # already had its event queried (line not posted) or its game
            # commenced, the sweep is guaranteed-futile credit burn -- skip.
            lost = [p for p in still
                    if not nick_of(p) or not any(covers(e, p) for e in events)]
            if not lost:
                print("  (remaining gaps have known events -- skipping sweep to save credits)")
                break
            in_secondary = True
            print("  (team-mapped events exhausted -- sweeping remaining slate events)")

        label = f"{ev.get('away_team', '?')} @ {ev.get('home_team', '?')}"
        try:
            ev_json, headers = _get(
                f"/sports/{SPORT}/events/{ev['id']}/odds", {
                    'apiKey': api_key,
                    'regions': REGION,
                    'markets': MARKET,
                    'oddsFormat': 'american',
                    'dateFormat': 'iso',
                }, min_gap=min_gap)
        except OddsApiError as e:
            print(f"  ⚠ {label}: {e}")
            continue
        meta['events_queried'] += 1
        try:
            meta['credits_used_this_run'] += int(headers.get('x-requests-last', 0) or 0)
        except (TypeError, ValueError):
            pass
        try:
            meta['remaining'] = int(headers.get('x-requests-remaining'))
        except (TypeError, ValueError):
            pass

        by_name = _parse_event_k_lines(ev_json, norm)
        got_here = []
        for p in list(still):
            vendors = by_name.get(norm(p))
            if not vendors:
                continue
            best = min(vendors.values(),
                       key=lambda e: (_rank(e['vendor'], vendor_priority), e['vendor']))
            filled[p.lower()] = best
            still.remove(p)
            got_here.append(f"{p} O/U {best['line']} ({best['vendor']})")
        if got_here:
            print(f"  {label}: " + '; '.join(got_here)
                  + f"  [remaining: {meta['remaining']}]")
        else:
            print(f"  {label}: no K props posted yet (cost 0 if empty)  [remaining: {meta['remaining']}]")

    if still:
        print(f"  Odds API also had no line (yet) for: {', '.join(still)}")
    return filled, meta

```

### `fetch_props.py`  (repo root -- REPLACES existing)
`15108 bytes · md5 f267f12ab3fa29a03ec1047b1e882285`

```python
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
if unmatched and not ODDS_API_KEY:
    print(f"  (no ODDS_API_KEY set -- {len(unmatched)} pitcher(s) stay line-less; "
          "add the ODDS_API_KEY secret to enable The Odds API fallback)")
elif unmatched and ODDS_API_KEY:
    try:
        import fetch_odds_api

        # Same-day reuse: only trust prior fallback entries written for THIS
        # slate date (the committed file is otherwise yesterday's slate).
        prev_entries = {}
        if os.path.exists(K_PROPS_FILE):
            try:
                _prev = json.load(open(K_PROPS_FILE, encoding='utf-8'))
                if isinstance(_prev, dict) and (_prev.get('_meta') or {}).get('date') == DATE_STR:
                    prev_entries = _prev
            except Exception:
                prev_entries = {}

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

if not k_props and not prop_by_player:
    raise SystemExit(
        "\n\n==================== BUILD STOPPED ====================\n"
        "No strikeout props found from ANY source for today's games.\n"
        "Pitcher K lines usually post the morning of -- try again later.\n"
        "Nothing has been pushed.\n"
        "=======================================================\n"
    )

if ODDS_META:
    k_props['_meta'] = ODDS_META

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

```

### `.github/workflows/daily.yml`  (REPLACES existing)
`4749 bytes · md5 c5c01399a8431256c4ead954e3fa3916`

```yaml
name: Daily MLB Slate Build

on:
  push:
    paths:
      - '**.xlsx'
  schedule:
    - cron: '30 10 * * *'   # 6:30 AM ET  - morning build
    - cron: '0 15 * * *'    # 11:00 AM ET - mid-morning line posts
    - cron: '0 20 * * *'    # 4:00 PM ET  - late lines + confirmed lineups
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install openpyxl

      - name: Find slate file
        run: |
          XLSX=$(python3 extract_xlsx.py --which)
          if [ -z "$XLSX" ]; then echo "No xlsx found" && exit 1; fi
          echo "XLSX_FILE=$XLSX" >> $GITHUB_ENV
          echo "Using newest slate by date: $XLSX"

      - name: Extract slate data
        run: python3 extract_xlsx.py "$XLSX_FILE" day_data.json

      - name: Fetch real K lines
        timeout-minutes: 4
        continue-on-error: true
        env:
          BDL_KEY: ${{ secrets.BDL_KEY }}
          ODDS_API_KEY: ${{ secrets.ODDS_API_KEY }}
          K_PROPS_FILE: k_props.json
          DATA_FILE: day_data.json
        run: python3 fetch_props.py

      - name: Fetch Phase 2 metrics
        timeout-minutes: 8
        continue-on-error: true
        env:
          BDL_KEY: ${{ secrets.BDL_KEY }}
          K_SAVANT_FILE: k_savant_data.json
          DATA_FILE: day_data.json
          BDL_MIN_GAP: '0.1'
        run: python3 fetch_phase2.py

      - name: Fetch live streaks
        timeout-minutes: 6
        continue-on-error: true
        env:
          BDL_KEY: ${{ secrets.BDL_KEY }}
          STREAKS_OUT: streaks_live.json
          STREAK_DAYS: '10'
          BDL_MIN_GAP: '0.2'
        run: python3 fetch_streaks.py

      - name: Build slate
        env:
          DATA_FILE: day_data.json
          SECTIONS_FILE: built_sections.json
          K_REPORT_FILE: k-report.html
          K_PROPS_FILE: k_props.json
          K_SAVANT_FILE: k_savant_data.json
          BDL_KEY: ${{ secrets.BDL_KEY }}
          STREAKS_OUT: streaks_live.json
          STREAK_DAYS: '10'
        run: python3 build.py

      - name: Sync to HTML
        run: python3 sync.py

      - name: Commit and push
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          git config user.email "mrwwright9@gmail.com"
          git config user.name "Wysdomos"
          git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/Wysdomos/mlb-slate.git"
          git add index.html k-report.html streaks.html day_data.json built_sections.json
          git add scout.html 2>/dev/null || true
          git add streaks_live.json 2>/dev/null || true
          git add slate_picks*.json 2>/dev/null || true
          git add k_props.json 2>/dev/null || true
          git add k_savant_data.json 2>/dev/null || true
          if ! git diff --staged --quiet; then
            git commit -m "Auto-update: $XLSX_FILE"
            # Generated files (index.html etc.) can't be line-merged with a parallel build,
            # so merge the remote keeping OUR freshly-built versions, and retry the push.
            pushed=0
            for i in 1 2 3 4 5; do
              git fetch origin main || true
              git merge -X ours --no-edit origin/main || git merge --abort || true
              if git push origin main; then pushed=1; echo "pushed on attempt $i"; break; fi
              echo "push rejected, retrying ($i)"; sleep $((RANDOM % 4 + 2))
            done
            [ "$pushed" = 1 ] || { echo "push failed after retries"; exit 1; }
          else
            echo "No changes to commit"
          fi

      - name: Telegram alert on failure
        if: failure()
        run: |
          curl -s -X POST "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
            -d chat_id="${{ secrets.TELEGRAM_CHAT_ID }}" \
            --data-urlencode text="🚨 Daily Slate FAILED: ${{ github.workflow }} — https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}"

      - name: Notify Firebase Auto-Healer on Failure
        if: failure()
        run: |
          PAYLOAD=$(printf '{"repository":"%s","run_id":"%s","sha":"%s"}' \
            "${{ github.repository }}" \
            "${{ github.run_id }}" \
            "${{ github.sha }}")
          SIG=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 \
            -hmac "${{ secrets.WEBHOOK_SECRET }}" | awk '{print $2}')
          curl -s -X POST "${{ secrets.FIREBASE_WEBHOOK_URL }}" \
            -H "Content-Type: application/json" \
            -H "X-Hub-Signature-256: sha256=$SIG" \
            -d "$PAYLOAD"

```

### `tools/test_odds_mock.py`  (NEW -- offline unit tests)
`7671 bytes · md5 924e075efb5d4b0460fb34a7633289f9`

```python
"""Behavioral verification of fetch_odds_api.fill_missing with a mocked HTTP layer.
Runs OFFLINE. Six cases. Exits nonzero on any failure."""
import sys, unicodedata
sys.path.insert(0, '/home/claude/slate/mlb-slate-main')
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

```

### `tools/odds_harness.py`  (NEW -- e2e gauntlet (run from repo root))
`8970 bytes · md5 557a2b1d0fbfa8673c276f0adde8cc69`

```python
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

```

---

## EXECUTION STEPS (Claude Code, M5)
```bash
cd ~/mlb-slate && git checkout main && git pull
git checkout -b feat/odds-api-fallback
# 1) Write the five files above at their exact paths (create tools/ if absent)
# 2) Verify bytes:
md5 fetch_odds_api.py fetch_props.py .github/workflows/daily.yml tools/test_odds_mock.py tools/odds_harness.py
# 3) Gates:
python3 -c "import ast; ast.parse(open('fetch_odds_api.py').read()); ast.parse(open('fetch_props.py').read()); print('ast OK')"
python3 tools/test_odds_mock.py                     # expect: ALL TESTS PASSED (13)
for S in S1 S2 S3 S4 S5; do rm -f k_props.S*.json; PYTHONPATH=. python3 tools/odds_harness.py $S; done
rm -f k_props.S*.json                               # expect: 23 PASS, 0 FAIL
# NOTE: tools/test_odds_mock.py line 4 hardcodes sys.path '/home/claude/slate/mlb-slate-main'
#       -- change that line to sys.path.insert(0, '.') when writing the file.
git add -A && git commit -m "feat: Odds API fallback for K props (key-gated, reviewed, 36 tests)"
git push -u origin feat/odds-api-fallback
gh pr create --title "Odds API K-prop fallback" --body "Key-gated fallback. 13 unit + 23 e2e assertions green. Inert without ODDS_API_KEY."
# >>> STOP. Post PR link. Claude reviews. Developer merges. <<<
```

**Deployment note (why imports work in CI):** Actions runs `python3 fetch_props.py` from the repo root, so `sys.path[0]` = repo root and `import fetch_odds_api` resolves. Both files MUST stay in repo root. (The sandbox gauntlet needed `PYTHONPATH=.` only because the harness lives in `tools/`.)

## AFTER MERGE — activation sequence
1. **First scheduled run, no secret:** log should show the normal BDL path and zero Odds API lines. This is the free live no-op test.
2. Developer signs up at **the-odds-api.com** (hyphens!), then: `gh secret set ODDS_API_KEY --repo Wysdomos/mlb-slate` (hidden prompt).
3. Next run: look for `Falling back to The Odds API for N pitcher(s)` and `[via The Odds API]` tags; `k_props.json` gains `_meta` with credit counts.

## VERIFICATION CHECKLIST (paste real output next to each)
- [ ] md5 of all 5 written files matches the values above
- [ ] `ast OK`
- [ ] Unit: `ALL TESTS PASSED` (13/13)
- [ ] Gauntlet: 23 PASS / 0 FAIL across S1–S5
- [ ] PR opened, link posted, **no merge**
- [ ] Post-merge run WITHOUT secret: behavior identical to today
- [ ] Secret set by human only; next run shows fallback lines + `_meta`

## ROLLBACK
Revert the PR — one commit. Or do nothing: without `ODDS_API_KEY` the entire path is inert. `k_props.json` is regenerated daily, so no data migration in either direction.
