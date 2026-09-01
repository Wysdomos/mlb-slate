# Kalshi public market-data client

Small standard-library client for Kalshi public REST market data.

Base URL:

```text
https://external-api.kalshi.com/trade-api/v2
```

Authentication: none. These public market-data endpoints require no
credentials, and the client never sends auth headers, API keys, or secrets.

## Usage

```python
from services.kalshi_client import KalshiClient
from services.kalshi_client.snapshot import build_snapshot

client = KalshiClient()
snapshot = build_snapshot("2026-08-31", client=client)
```

Typed endpoint methods:

- `series(category=None, tags=None, limit=200)`
- `series_detail(series_ticker)`
- `events(series_ticker=None, cursor=None, limit=200)`
- `markets(series_ticker=None, event_ticker=None, cursor=None, limit=200)`
- `market(ticker)`
- `orderbook(ticker)`
- `paged_events(series_ticker, max_pages=None, limit=200)`
- `paged_markets(event_ticker, series_ticker=None, max_pages=None, limit=200)`

## Snapshot fetcher

Write the read-only snapshot envelope:

```bash
python3 fetch_kalshi.py --date 2026-08-31
```

Output file:

```text
kalshi_markets.json
```

The output contains:

- `schema_version`
- `generated_at`
- `base_url`
- `slate_date`
- `fetch_ok`
- `fetch_error`
- `request_count`
- `markets[]`

Failures write `fetch_ok=false` and exit 0. Kalshi is not wired into the
daily build in this PR.

## Environment knobs

- `KALSHI_MAX_MARKET_PAGES`: maximum cursor pages per series/event, default `3`
- `KALSHI_MAX_ORDERBOOK_CALLS`: maximum orderbook calls per snapshot, default `25`
- `KALSHI_TIMEOUT`: HTTP timeout in seconds, default `20`
- `KALSHI_MIN_REQUEST_GAP`: seconds between live calls, default `0.25`
- `KALSHI_QUOTE_STALE_SECONDS`: quote stale cutoff, default `180`

Freshness labels:

- `FRESH`: 0-60 seconds
- `AGING`: 61 seconds through `KALSHI_QUOTE_STALE_SECONDS`
- `STALE`: older than `KALSHI_QUOTE_STALE_SECONDS`

## Pricing

`GET /markets/{ticker}/orderbook` exposes bid arrays. The client derives:

```text
cost to BUY YES = 1 - best NO bid
cost to BUY NO  = 1 - best YES bid
```

`GET /markets` reported asks are primary. Derived orderbook asks are a
cross-check. If reported and derived asks disagree by more than one cent, the
market is marked `STALE`. `last_price` is never used as an entry price.

## Series observed

The live harness discovers baseball series from:

```text
GET /series?category=Sports&tags=Baseball&limit=200
```

Known MLB series currently used by the snapshot:

- `KXMLBHR`: Pro Baseball Home Runs
- `KXMLBTOTAL`: Pro Baseball Total Points
- `KXMLBKS`: Pro Baseball Strikeouts
- `KXMLBHIT`: Pro Baseball Hits
- `KXMLBTB`: Pro Baseball Total Bases
- `KXMLBHRR`: Pro Baseball Hits Runs RBIs
- `KXMLBTEAMTOTAL`: Pro Baseball Team Total
- `KXMLBHA`: Pro Baseball Hits Allowed
