# SESSION_STATUS_kalshi.md

Branch: `feat/kalshi-client`
Base: `origin/main`
PR: not opened by Codex

## Summary

Added a read-only Kalshi public market-data client using new files only. No UI
or workflow files were touched. The client uses `urllib.request`, injectable
transport fixtures, a `*ApiError` exception hierarchy, no auth, no secrets, and
exactly one pinned base URL:

```text
https://external-api.kalshi.com/trade-api/v2
```

`fetch_kalshi.py` writes `kalshi_markets.json` with:

```text
schema_version, generated_at, base_url, slate_date, fetch_ok, fetch_error, request_count, markets[]
```

Failures write `fetch_ok=false` and exit 0.

## Live Harness

Command:

```bash
KALSHI_MIN_REQUEST_GAP=0.05 KALSHI_MAX_ORDERBOOK_CALLS=5 KALSHI_MAX_MARKET_PAGES=2 python3 tools/kalshi_harness.py
```

Output:

```text
Slate date: 2026-08-31
Request count: 125
Fetch OK: True
Fetch error: None
```

## Every MLB Series Found

```text
KXCOACHOUTMLBDATE — MLB Coach Out Date
KXLEADERMLBAVG — MLB Batting Average Leader
KXLEADERMLBDOUBLES — MLB Doubles Leader
KXLEADERMLBERA — MLB ERA Leader
KXLEADERMLBHITS — MLB Hits Leader
KXLEADERMLBHR — MLB Home Runs Leader
KXLEADERMLBKS — Pro Baseball Strikeouts Leader
KXLEADERMLBOPS — MLB OPS Leader
KXLEADERMLBRBI — MLB RBIs Leader
KXLEADERMLBRUNS — MLB Runs Leader
KXLEADERMLBSAVES — MLB Saves Leader
KXLEADERMLBSTEALS — MLB Steals Leader
KXLEADERMLBSTRIKEOUTS — MLB Strikeouts Leader
KXLEADERMLBTRIPLES — MLB Triples Leader
KXLEADERMLBWAR — MLB WAR Leader
KXLEADERMLBWINS — MLB Wins Leader
KXMLB — World Series
KXMLBAL — MLB American League Championship
KXMLBALCENT — American League Central Winner
KXMLBALCPOTY — Pro Baseball American League Comeback Player of the Year
KXMLBALCSMVP — Pro Baseball American League Championship Series MVP
KXMLBALCY — Pro Baseball American League Cy Young
KXMLBALEAST — American League East Winner
KXMLBALHAARON — Pro Baseball American League Hank Aaron
KXMLBALLSTAR — Pro Baseball All-Stars
KXMLBALLSTARHR — Pro Baseball All-Star Game Total Home Runs
KXMLBALMOTY — Pro Baseball American League Manager of the Year
KXMLBALMVP — Pro Baseball American League MVP
KXMLBALRELOTY — Pro Baseball American League Reliever of the Year
KXMLBALROTY — Pro Baseball American League Rookie of the Year
KXMLBALWEST — American League West Winner
KXMLBASGAME — Professional Baseball All-Star Game
KXMLBASGHIT — All Star Game Hits
KXMLBASGHR — All Star Game Home Runs
KXMLBASGKS — All Star Game Strikesouts
KXMLBASGMVP — Pro Baseball All-Star Game MVP
KXMLBAWARDCOMBO — Pro Baseball Award Combo
KXMLBAWARDFIN — Pro Baseball Award Finalists
KXMLBBESTRECORD — Pro Baseball Best Record
KXMLBCBA — CBA
KXMLBDEBUT — Pro Baseball Debut
KXMLBDRAFTPICK — Pro Baseball Draft Pick
KXMLBDRAFTTOP — Pro Baseball Top Pick
KXMLBEOTY — Pro Baseball Executive of the Year
KXMLBERA — Pro Baseball Earned Runs
KXMLBEXTRAS — MLB Extra Innings
KXMLBF3 — First 3 Innings Winner
KXMLBF5 — First 5 Innings Winner
KXMLBF5SPREAD — First 5 Innings Spread
KXMLBF5TOTAL — First 5 Innings Total
KXMLBF7 — First 7 Innings Winner
KXMLBFASTPITCH — Fastest Pitch of season
KXMLBFOD — Field of Dreams Teams
KXMLBFTGAME — Pro Baseball Futures Game
KXMLBGAME — Professional Baseball Game
KXMLBGG — Pro Baseball Gold Glove
KXMLBHA — Pro Baseball Hits Allowed
KXMLBHIT — Pro Baseball Hits
KXMLBHR — Pro Baseball Home Runs
KXMLBHRDERBY — Pro Baseball Homerun Derby
KXMLBHRDERBY500 — 500+ Foot HRs at the Home Run Derby
KXMLBHRDERBYDISTANCE — Pro Baseball Home Run Derby Longest Distance
KXMLBHRDERBYFIN — Pro Baseball Home Run Derby Finals Qualifiers
KXMLBHRDERBYFORECAST — Home Run Derby Finals Forecast
KXMLBHRDERBYLONGEST — Pro Baseball Home Run Derby Player to Hit Longest
KXMLBHRDERBYMATCHUP — Pro Baseball Home Run Derby Final Matchup
KXMLBHRDERBYOU — Pro Baseball Home Run Derby Over/Under Home Runs
KXMLBHRDERBYQUAL — Pro Baseball Home Run Derby Selections
KXMLBHRDERBYR1LEAD — Round 1 Leader
KXMLBHRDERBYSEMI — Pro Baseball Home Run Derby Semifinals Qualifiers
KXMLBHRDERBYTOT — Home Run Derby Total Home Runs
KXMLBHRDERBYVELO — Highest Exit Velocity Home run
KXMLBHRR — Pro Baseball Hits Runs RBIs
KXMLBINNINGTOTAL — Pro Baseball Inning Total
KXMLBINNINGWIN — Pro Baseball Inning Win
KXMLBKS — Pro Baseball Strikeouts
KXMLBLSTREAK — Longest Losing Streak
KXMLBMATCHUP — Pro Baseball Playoff Matchups
KXMLBNEXTHR — Pro Baseball Next Homerun
KXMLBNEXTTEAM — Pro Baseball Next Team
KXMLBNL — MLB National League Championship
KXMLBNLCENT — National League Central Winner
KXMLBNLCPOTY — National League Comeback Player of the Year
KXMLBNLCSMVP — Pro Baseball National League Championship Series MVP
KXMLBNLCY — Pro Baseball National League Cy Young
KXMLBNLEAST — National League East Winner
KXMLBNLHAARON — Pro Baseball American League Hank Aaron
KXMLBNLMOTY — Pro Baseball National League Manager of the Year
KXMLBNLMVP — Pro Baseball National League MVP
KXMLBNLRELOTY — Pro Baseball National League Reliever of the Year
KXMLBNLROTY — Pro Baseball National League Rookie of the Year
KXMLBNLWEST — National League West Winner
KXMLBOPENINGDAY — Pro Baseball Opening Day
KXMLBOUTS — Pro Baseball Outs Recorded
KXMLBPITCH — Pro Baseball Player to Pitch
KXMLBPITCHEROTM — Pro Baseball Pitcher of the Month
KXMLBPLAYEROTM — Pro Baseball Player of the Month
KXMLBPLAYEROTW — Pro Baseball Player of the Week
KXMLBPLAYOFFS — Pro Baseball Playoff Qualifiers
KXMLBRBI — Pro Baseball RBIs
KXMLBRETURN — Pro Baseball Player Return
KXMLBRFI — Pro Baseball Run in First Inning
KXMLBSB — Pro Baseball Stolen Bases
KXMLBSEASONGAMES — Pro Baseball Games Played in a Season
KXMLBSEASONHR — Pro Baseball Season Home Runs
KXMLBSERIES — Professional Baseball Series
KXMLBSERIESEXACT — Professional Baseball Series Exact Result
KXMLBSERIESGAMETOTAL — Professional Baseball Series Total Games
KXMLBSISTREAK — Pro Baseball Scoreless Innings Streak
KXMLBSPREAD — Pro Baseball Spread
KXMLBSS — Pro Baseball Silver Slugger
KXMLBSTAT — Pro Baseball Season Stat
KXMLBSTATCOUNT — Pro Baseball Season Stat
KXMLBSTGAME — Pro Baseball Spring Training game
KXMLBTB — Pro Baseball Total Bases
KXMLBTEAMSALE — Pro Baseball Team Sale
KXMLBTEAMSTAT — Pro Baseball Team Stat
KXMLBTEAMTOTAL — Pro Baseball Team Total
KXMLBTOTAL — Pro Baseball Total Points
KXMLBTRADE — Pro Baseball Trades
KXMLBTRIPLECROWN — Pro Baseball Triple Crown
KXMLBWA — Pro Baseball Walks
KXMLBWALK — Pro Baseball Walks
KXMLBWINS-ATH — Pro baseball wins A's
KXMLBWINS-ATL — Pro baseball wins Atlanta
KXMLBWINS-AZ — Pro baseball wins Arizona
KXMLBWINS-BAL — Pro baseball wins Baltimore
KXMLBWINS-BOS — Pro baseball wins Boston
KXMLBWINS-CHC — Pro baseball wins Chicago C
KXMLBWINS-CIN — Pro baseball wins Cincinnati
KXMLBWINS-CLE — Pro baseball wins Cleveland
KXMLBWINS-COL — Pro baseball wins Colorado
KXMLBWINS-CWS — Pro baseball wins Chicago W
KXMLBWINS-DET — Pro baseball wins Detroit
KXMLBWINS-HOU — Pro baseball wins Houston
KXMLBWINS-KC — Pro baseball wins Kansas City
KXMLBWINS-LAA — Pro baseball wins Los Angeles A
KXMLBWINS-LAD — Pro baseball wins Los Angeles D
KXMLBWINS-MIA — Pro baseball wins Miami
KXMLBWINS-MIL — Pro baseball wins Milwaukee
KXMLBWINS-MIN — Pro baseball wins Minnesota
KXMLBWINS-NYM — Pro baseball wins New York M
KXMLBWINS-NYY — Pro baseball wins New York Y
KXMLBWINS-PHI — Pro baseball wins Philadelphia
KXMLBWINS-PIT — Pro baseball wins Pittsburgh
KXMLBWINS-SD — Pro baseball wins San Diego
KXMLBWINS-SEA — Pro baseball wins Seattle
KXMLBWINS-SF — Pro baseball wins San Francisco
KXMLBWINS-STL — Pro baseball wins St. Louis
KXMLBWINS-TB — Pro baseball wins Tampa Bay
KXMLBWINS-TEX — Pro baseball wins Texas
KXMLBWINS-TOR — Pro baseball wins Toronto
KXMLBWINS-WSH — Pro baseball wins Washington
KXMLBWORLD — World Baseball Classic
KXMLBWORSTRECORD — Pro Baseball Best Record
KXMLBWS — MLB World Series
KXMLBWSMVP — Pro Baseball Championship MVP
KXMLBWSTREAK — Longest Winning Streak
KXNEXTTEAMMLB — MLB Player Next Team
KXTEAMSINWS — Teams in MLB Finals
KXWSAL — MLB American League champion
KXWSNL — MLB National League champion
```

## Strikeout Series

```text
KXMLBKS — Pro Baseball Strikeouts
```

## Requested Market Families

```text
hits: KXMLBHIT — Pro Baseball Hits
total_bases: KXMLBTB — Pro Baseball Total Bases
hrr: KXMLBHRR — Pro Baseball Hits Runs RBIs
nrfi: not found by known ticker probes
team_totals: KXMLBTEAMTOTAL — Pro Baseball Team Total
```

Note: `KXMLBRFI` exists as `Pro Baseball Run in First Inning`; no direct
`KXMLBNRFI` series was found by known ticker probe.

## Normalized Live Record

```json
{
  "ask_source": "agree",
  "away_team": "PHI",
  "event_ticker": "KXMLBHR-26AUG312140PHIAZ",
  "fee_band": "extreme",
  "freshness": "STALE",
  "home_team": "AZ",
  "kalshi_side": "yes",
  "market_family": "KXMLBHR",
  "market_ticker": "KXMLBHR-26AUG312140PHIAZ-AZKMARTE4-2",
  "player_name": "Ketel Marte",
  "quote_age_seconds": 18687.822682857513,
  "raw_status": "active",
  "rules_primary": "If Ketel Marte records 2+ home runs in Philadelphia vs Arizona professional baseball game originally scheduled for Aug 31, 2026 at 9:40 PM EDT, then the market resolves to Yes.",
  "series_ticker": "KXMLBHR",
  "settlement_note": "Market references the originally scheduled game datetime for settlement.",
  "slate_date": "2026-08-31",
  "slate_market": "HR",
  "slate_side": "over",
  "team": "AZ",
  "threshold": 1.5,
  "title": "Ketel Marte: 2+ home runs?",
  "tradable_state": "STALE",
  "url": "https://kalshi.com/markets/kxmlbhr/pro-baseball-home-runs/KXMLBHR-26AUG312140PHIAZ",
  "yes_ask_derived": 0.02,
  "yes_ask_reported": 0.02
}
```

## Home/Away Order

Resolved order: event team code suffix is `away` then `home`.

Evidence from live Kalshi event tickers/titles matched to current
`BP_Games`:

```text
KXMLBHR-26AUG312140PHIAZ — Philadelphia vs Arizona: Home Runs / PHI vs AZ (Aug 31) => PHI@AZ; BP_Games match: True
KXMLBHR-26AUG312138NYYLAA — New York Y vs Los Angeles A: Home Runs / NYY vs LAA (Aug 31) => NYY@LAA; BP_Games match: True
KXMLBHR-26AUG312040BALCOL — Baltimore vs Colorado: Home Runs / BAL vs COL (Aug 31) => BAL@COL; BP_Games match: True
KXMLBHR-26AUG312010CWSHOU — Chicago WS vs Houston: Home Runs / CWS vs HOU (Aug 31) => CHW@HOU; BP_Games match: True
KXMLBHR-26AUG312005ATHTEX — A's vs Texas: Home Runs / ATH vs TEX (Aug 31) => ATH@TEX; BP_Games match: True
```

A fixture test pins `KXMLBHR-26AUG312140PHIAZ` as away `PHI`, home `AZ`.

## Prompt Assumption Differences

- Live market `status` values are `active` / `initialized`, not literal `open`; the client treats `active` as open and preserves `raw_status`.
- Live `KXMLBTOTAL` series title is `Pro Baseball Total Points`; event titles use `Total Runs` wording.
- Live HR, K, TB and HRR series include ladders. Each strike is normalized as its own market record.

## Fetcher Smoke Test

Command:

```bash
KALSHI_MIN_REQUEST_GAP=0.05 KALSHI_MAX_ORDERBOOK_CALLS=2 KALSHI_MAX_MARKET_PAGES=1 python3 fetch_kalshi.py --output /tmp/kalshi_markets_test.json
```

Output:

```text
Kalshi fetch OK: 2843 markets, 106 requests
```

Envelope check:

```text
keys ['base_url', 'fetch_error', 'fetch_ok', 'generated_at', 'markets', 'request_count', 'schema_version', 'slate_date']
fetch_ok True request_count 106 markets 2843
base_url https://external-api.kalshi.com/trade-api/v2
```

## Tests

Unit tests:

```bash
python3 -m unittest discover services/kalshi_client/tests
```

Output:

```text
...............
----------------------------------------------------------------------
Ran 15 tests in 0.001s

OK
```

AST parse:

```bash
python3 - <<'PY'
import ast
from pathlib import Path
for path in sorted(Path('services/kalshi_client').rglob('*.py')) + [Path('fetch_kalshi.py'), Path('tools/kalshi_harness.py')]:
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('ast ok')
PY
```

Output:

```text
ast ok
```

py_compile:

```bash
python3 -m py_compile fetch_kalshi.py tools/kalshi_harness.py services/kalshi_client/*.py services/kalshi_client/tests/*.py services/kalshi_client/tests/fixtures/*.py
```

Output: no output, exit 0.

Compliance:

```bash
python3 tools/check_bpp_compliance.py
```

Output:

```text
BPP compliance OK (0 changed JSON/HTML files checked against 82bb79bf0c8d)
```

## Constraints Checked

- New files only.
- No credentials, env keys, auth headers, or secrets added.
- No `requests` or `httpx`; stdlib `urllib.request` only.
- Did not touch `daily.yml`, `build.py`, `sync.py`, or `build_day46.py`.
- `last_price` is never used as an ask.
- URL construction is isolated in `services/kalshi_client/urls.py`.
