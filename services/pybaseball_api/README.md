# Local PyBaseball API v0.1

This service wraps selected [`pybaseball`](https://github.com/jldbc/pybaseball)
functions in a small read-only API for The Daily Slate. It is for local M5
development and backtesting only. It does not run in GitHub Actions, Firebase,
or the live website.

## Why this exists

`pybaseball` is a Python library, not a hosted API. This wrapper gives the
Daily Slate tools one stable JSON interface while keeping source-specific
scraping code behind an adapter that can be replaced later.

## Safety boundaries

- Bind to `127.0.0.1`; do not expose this first version to the public internet.
- All routes are GET/read-only.
- Statcast requests are capped at 92 days and 5,000 returned rows.
- Season-stat requests are capped at 10 seasons.
- `backtest/data_access.py` owns every pybaseball call and CSV cache.
- Complete non-empty query results use a six-hour local CSV cache by default.
- Paginated responses include `offset` and `next_offset`; loaders must call
  `load_complete_dataset` and may not proceed while `truncated` is true.
- Upstream failure returns an error; the service never fabricates data.
- No endpoint is connected to the production slate pipeline yet.

## M5 copy-and-paste setup

From the repository root:

```bash
python3 -m venv .venv-pybaseball
source .venv-pybaseball/bin/activate
python -m pip install --upgrade pip
python -m pip install -r services/pybaseball_api/requirements-dev.txt
```

Run the tests:

```bash
python -m pytest services/pybaseball_api/tests -q
```

Start the local API:

```bash
python -m uvicorn services.pybaseball_api.app.main:app \
  --host 127.0.0.1 --port 8000
```

Open the interactive local documentation:

```text
http://127.0.0.1:8000/docs
```

Stop the server with `Control-C`. Deactivate the environment with:

```bash
deactivate
```

## First test calls

Health check:

```bash
curl 'http://127.0.0.1:8000/health'
```

Find Aaron Judge's IDs:

```bash
curl 'http://127.0.0.1:8000/v1/players/search?last=judge&first=aaron'
```

Get a short batter Statcast window after obtaining the MLBAM ID:

```bash
curl 'http://127.0.0.1:8000/v1/statcast/batter/592450?start_date=2026-07-01&end_date=2026-07-07&limit=100'
```

Every dataset response includes `row_count`, `total_rows`, `offset`,
`next_offset`, and `truncated`. A consumer loading data for analysis must keep
requesting `next_offset` until `truncated` is false. The shared
`backtest.data_access.load_complete_dataset` enforces that rule and raises instead of
returning an incomplete dataset.

The CSV cache defaults to:

```text
backtest/cache/pybaseball-api
```

Override its location or six-hour TTL with `PYBASEBALL_API_CACHE_DIR` and
`PYBASEBALL_API_CACHE_TTL_SECONDS`. Set the TTL to `0` to disable CSV caching.

## v0.1 endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Local service health |
| `GET /v1/players/search` | Chadwick cross-site player ID lookup |
| `GET /v1/statcast/batter/{player_id}` | Batter pitch-level Statcast rows |
| `GET /v1/statcast/pitcher/{player_id}` | Pitcher pitch-level Statcast rows |
| `GET /v1/stats/batting` | FanGraphs season batting table |
| `GET /v1/stats/pitching` | FanGraphs season pitching table |

## Known limitation

The PyPI release of `pybaseball` is 2.2.7 from September 2023. Its upstream
sites can change independently. Keeping all upstream and CSV operations in
`backtest/data_access.py` gives us one replacement point if a scraper breaks or a
maintained alternative is needed. The dependency direction stays FastAPI →
service → data access and never reverses.
