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
CHAPTER_H_MARKETS = (
    'pitcher_hits_allowed',
    'pitcher_outs',
    'batter_total_bases',
)

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

def _parse_event_market_lines(ev_json, market_key, norm):
    """Returns {norm_player_name: {vendor: entry}} for one main-line market.
    Entries intentionally store the line only. Prices are not needed by this
    chapter and alternate markets are never requested.
    """
    out = {}
    for bm in ev_json.get('bookmakers') or []:
        raw = (bm.get('key') or '').lower()
        vendor = BOOK_ALIAS.get(raw, raw)
        for mkt in bm.get('markets') or []:
            if mkt.get('key') != market_key:
                continue
            pair = {}
            for oc in mkt.get('outcomes') or []:
                who = norm(oc.get('description') or '')
                side = (oc.get('name') or '').lower()
                try:
                    point = float(oc.get('point'))
                except (TypeError, ValueError):
                    continue
                if not who or side not in ('over', 'under'):
                    continue
                pair.setdefault((who, point), set()).add(side)
            for (who, point), sides in pair.items():
                entry = {
                    'line': point,
                    'vendor': vendor,
                    'src': 'oddsapi',
                    'market': market_key,
                }
                cur = out.setdefault(who, {})
                old = cur.get(vendor)
                if old is None or ('over' in sides and 'under' in sides):
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


def fill_market_lines(api_key, date_str, needs_by_market, norm, vendor_priority,
                      team_of=None, prev_entries=None,
                      max_per_run=None, reserve=None, min_gap=None):
    """
    Fetch Chapter H main-line markets:
      pitcher_hits_allowed, pitcher_outs, batter_total_bases.

    Returns (filled_by_market, meta):
      filled_by_market {market_key: {lowercase_player_name: line_entry}}
      meta includes event request count and credits used this run.
    """
    if max_per_run is None:
        max_per_run = int(os.environ.get('ODDS_MAX_PER_RUN', '20'))
    if reserve is None:
        reserve = int(os.environ.get('ODDS_RESERVE', '60'))
    if min_gap is None:
        min_gap = float(os.environ.get('ODDS_MIN_GAP', '0.35'))
    team_of = team_of or {}
    prev_entries = prev_entries or {}

    wanted = {
        market: list(dict.fromkeys(names or []))
        for market, names in (needs_by_market or {}).items()
        if market in CHAPTER_H_MARKETS
    }
    filled = {market: {} for market in wanted}
    still = {market: list(names) for market, names in wanted.items()}
    meta = {
        'date': date_str,
        'source': 'the-odds-api.com',
        'markets': sorted(wanted),
        'events_queried': 0,
        'request_count_this_run': 0,
        'credits_used_this_run': 0,
        'remaining': None,
        'reused_same_day': 0,
    }
    if not wanted:
        return filled, meta

    # Same-day reuse from k_props.json.
    for market, names in list(still.items()):
        for name in list(names):
            lname = name.lower()
            if market == 'batter_total_bases':
                e = (prev_entries.get('_batter_total_bases') or {}).get(lname)
            else:
                nested_key = 'hits_allowed' if market == 'pitcher_hits_allowed' else 'outs'
                e = (prev_entries.get(lname) or {}).get(nested_key)
            if isinstance(e, dict) and e.get('src') == 'oddsapi' and e.get('line') is not None:
                filled[market][lname] = e
                names.remove(name)
                meta['reused_same_day'] += 1
    if meta['reused_same_day']:
        print(f"  Reused {meta['reused_same_day']} same-day Chapter H Odds API line(s)")
    if not any(still.values()):
        return filled, meta

    events, headers = get_slate_events(api_key, date_str, min_gap=min_gap)
    try:
        meta['remaining'] = int(headers.get('x-requests-remaining'))
    except (TypeError, ValueError):
        pass
    print(f"  Odds API Chapter H events for {date_str}: {len(events)} "
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

    def player_team(name):
        return TEAM_NICK.get((team_of.get(name) or '').upper())

    def covers_any(ev):
        blob = norm(f"{ev.get('home_team', '')} {ev.get('away_team', '')}")
        for names in still.values():
            for player in names:
                nick = player_team(player)
                if nick and norm(nick) in blob:
                    return True
        return False

    primary = [ev for ev in future if covers_any(ev)]
    secondary = [ev for ev in future if ev not in primary]
    markets_param = ','.join(sorted(wanted))

    for ev in primary + secondary:
        if not any(still.values()):
            break
        if meta['events_queried'] >= max_per_run:
            print(f"  ⚠ Odds API per-run cap hit ({max_per_run} events) -- stopping")
            break
        if meta['remaining'] is not None and meta['remaining'] <= reserve:
            print(f"  ⚠ Odds API monthly reserve reached ({meta['remaining']} <= {reserve}) -- stopping to protect the quota")
            break

        label = f"{ev.get('away_team', '?')} @ {ev.get('home_team', '?')}"
        try:
            ev_json, headers = _get(
                f"/sports/{SPORT}/events/{ev['id']}/odds", {
                    'apiKey': api_key,
                    'regions': REGION,
                    'markets': markets_param,
                    'oddsFormat': 'american',
                    'dateFormat': 'iso',
                }, min_gap=min_gap)
        except OddsApiError as e:
            print(f"  ⚠ {label}: {e}")
            continue
        meta['events_queried'] += 1
        meta['request_count_this_run'] += 1
        try:
            meta['credits_used_this_run'] += int(headers.get('x-requests-last', 0) or 0)
        except (TypeError, ValueError):
            pass
        try:
            meta['remaining'] = int(headers.get('x-requests-remaining'))
        except (TypeError, ValueError):
            pass

        hits = []
        parsed = {market: _parse_event_market_lines(ev_json, market, norm) for market in wanted}
        for market, names in list(still.items()):
            for player in list(names):
                vendors = parsed.get(market, {}).get(norm(player))
                if not vendors:
                    continue
                best = min(vendors.values(),
                           key=lambda e: (_rank(e['vendor'], vendor_priority), e['vendor']))
                filled[market][player.lower()] = best
                names.remove(player)
                hits.append(f"{player} {market} O/U {best['line']} ({best['vendor']})")
        if hits:
            print(f"  {label}: " + '; '.join(hits)
                  + f"  [remaining: {meta['remaining']}]")
        else:
            print(f"  {label}: no Chapter H main props posted yet  [remaining: {meta['remaining']}]")

    gaps = sum(len(names) for names in still.values())
    if gaps:
        print(f"  Odds API Chapter H still had no line for {gaps} player-market pair(s)")
    return filled, meta
