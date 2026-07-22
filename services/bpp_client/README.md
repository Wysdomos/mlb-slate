# Ballpark Pal API client

Small standard-library client for Ballpark Pal API v1.

Base URL:

```text
https://www.ballparkpal.com/api/v1
```

Authentication uses the `X-API-Key` header only. The client never sends
`apiKey` in the query string.

## Usage

```python
from services.bpp_client import BppClient

client = BppClient()  # reads BPP_API_KEY from the environment
games = client.games(date="2026-07-22")
game_id = games["data"][0]["gameId"]
averages = client.projection_averages(game_id)
```

Typed endpoint methods:

- `health()`
- `markets()`
- `teams()`
- `players(team_id=None, q=None)`
- `games(date=None, game_id=None)`
- `game(game_id)`
- `projection_probabilities(game_id)`
- `projection_averages(game_id)`
- `parkfactors(date)`
- `hitter_parkfactors(date=None, game_id=None)`
- `matchups(date, starters=False)`
- `predict_matchup(batter_id, pitcher_id)`

## Cache

Responses are cached on disk under:

```text
services/bpp_client/cache/
```

That directory is gitignored. Pass `force_refresh=True` to any endpoint method
when a fresh pull is required.

## Snapshot archiver

Archive the daily BPP payloads:

```bash
python3 -m services.bpp_client.snapshot --date 2026-07-22
```

The archiver writes named JSON files under
`services/bpp_client/cache/snapshots/YYYY-MM-DD/`, including date-level
payloads and per-game `projection_averages` / `projection_probabilities`.

Snapshot pacing and guardrails:

- `BPP_MIN_GAP`: seconds between live BPP calls, default `1.0`
- `BPP_MAX_CALLS`: maximum calls per snapshot run, default `150`

The archiver logs each running call count to stderr against the 15,000/month
BPP budget and writes the final count to `manifest.json`.
