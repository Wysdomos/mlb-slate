#!/usr/bin/env python3
"""Fetch read-only Kalshi public market data into kalshi_markets.json.

Kalshi is not wired into the daily build in this PR. Failures are recorded in
the output envelope and exit 0 so Kalshi can never break the slate build.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Optional

from services.kalshi_client.client import KALSHI_BASE_URL, KalshiClient
from services.kalshi_client.snapshot import build_snapshot

DEFAULT_OUTPUT = "kalshi_markets.json"


def slate_date_from_day_data(path: Path) -> Optional[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if payload.get("_slate_date"):
        return str(payload["_slate_date"])
    games = payload.get("BP_Games") or []
    if games and isinstance(games[0], dict) and games[0].get("GameDate"):
        return str(games[0]["GameDate"])[:10]
    return None


def failure_snapshot(slate_date: str, message: str, request_count: int = 0) -> dict[str, Any]:
    from datetime import datetime, timezone

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "base_url": KALSHI_BASE_URL,
        "slate_date": slate_date,
        "fetch_ok": False,
        "fetch_error": message,
        "request_count": request_count,
        "markets": [],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Kalshi public MLB market data.")
    parser.add_argument("--date", help="Slate date YYYY-MM-DD. Defaults to day_data.json or today.")
    parser.add_argument("--data-file", default=os.environ.get("DATA_FILE", "day_data.json"))
    parser.add_argument("--output", default=os.environ.get("KALSHI_MARKETS_FILE", DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    slate_date = args.date or slate_date_from_day_data(Path(args.data_file)) or date.today().isoformat()
    output = Path(args.output)
    client = KalshiClient()
    try:
        snapshot = build_snapshot(slate_date, client=client)
    except Exception as exc:
        snapshot = failure_snapshot(slate_date, f"{type(exc).__name__}: {exc}", client.request_count)
    write_json(output, snapshot)
    if snapshot.get("fetch_ok"):
        print(f"Kalshi fetch OK: {len(snapshot.get('markets') or [])} markets, {snapshot.get('request_count')} requests")
    else:
        print(f"Kalshi fetch failed non-fatally: {snapshot.get('fetch_error')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
