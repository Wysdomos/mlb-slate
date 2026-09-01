#!/usr/bin/env python3
"""Live Kalshi public API harness.

Runs once against public endpoints with no credentials and prints a Markdown
report suitable for SESSION_STATUS_kalshi.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.kalshi_client import KalshiClient
from services.kalshi_client.normalize import canonical_team, parse_event_ticker
from services.kalshi_client.snapshot import build_snapshot, check_interest_series, discover_mlb_series


def load_day_data(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def slate_date(data: Mapping[str, Any]) -> str:
    if data.get("_slate_date"):
        return str(data["_slate_date"])
    games = data.get("BP_Games") or []
    if games and isinstance(games[0], dict) and games[0].get("GameDate"):
        return str(games[0]["GameDate"])[:10]
    from datetime import date

    return date.today().isoformat()


def game_lookup(data: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    out = set()
    for game in data.get("BP_Games") or []:
        if not isinstance(game, dict):
            continue
        date = str(game.get("GameDate") or "")[:10]
        away = canonical_team(game.get("AwayTeam"))
        home = canonical_team(game.get("HomeTeam"))
        if date and away and home:
            out.add((date, away, home))
    return out


def team_order_evidence(client: KalshiClient, data: Mapping[str, Any], date: str) -> list[dict[str, Any]]:
    games = game_lookup(data)
    evidence = []
    for event in client.paged_events(series_ticker="KXMLBHR", max_pages=1):
        event_ticker = str(event.get("event_ticker") or "")
        parsed = parse_event_ticker(event_ticker)
        if parsed.get("slate_date") != date:
            continue
        away = parsed.get("away_team")
        home = parsed.get("home_team")
        evidence.append(
            {
                "event_ticker": event_ticker,
                "title": event.get("title"),
                "sub_title": event.get("sub_title"),
                "parsed_order": f"{away}@{home}",
                "matches_bp_games": (date, away, home) in games,
            }
        )
        if len(evidence) >= 5:
            break
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live Kalshi public MLB harness.")
    parser.add_argument("--data-file", default="day_data.json")
    parser.add_argument("--date")
    args = parser.parse_args()

    data = load_day_data(Path(args.data_file))
    date = args.date or slate_date(data)
    client = KalshiClient()

    series = discover_mlb_series(client)
    interest = check_interest_series(client)
    snapshot = build_snapshot(date, client=client)
    evidence = team_order_evidence(client, data, date)
    strikeout = next(
        (row for row in series if "Strikeouts" in row["title"] and row["series_ticker"].startswith("KXMLB")),
        None,
    )
    first_record = (snapshot.get("markets") or [None])[0]

    print("# Kalshi Harness Report")
    print()
    print(f"Slate date: `{date}`")
    print(f"Request count: `{client.request_count}`")
    print(f"Fetch OK: `{snapshot.get('fetch_ok')}`")
    print(f"Fetch error: `{snapshot.get('fetch_error')}`")
    print()
    print("## MLB Series")
    for row in series:
        print(f"- `{row['series_ticker']}` — {row['title']}")
    print()
    print("## Strikeout Series")
    if strikeout:
        print(f"`{strikeout['series_ticker']}` — {strikeout['title']}")
    else:
        print("Not found")
    print()
    print("## Market Family Existence")
    for label, rows in interest.items():
        if rows:
            joined = ", ".join(f"`{row['series_ticker']}` ({row['title']})" for row in rows)
            print(f"- {label}: {joined}")
        else:
            print(f"- {label}: not found by known ticker probes")
    print()
    print("## First Normalized Record")
    print("```json")
    print(json.dumps(first_record, indent=2, sort_keys=True))
    print("```")
    print()
    print("## Home/Away Order Evidence")
    print("Resolved order: event team code suffix is `away` then `home`.")
    for row in evidence:
        print(
            f"- `{row['event_ticker']}` — {row['title']} / {row['sub_title']} "
            f"=> `{row['parsed_order']}`; BP_Games match: `{row['matches_bp_games']}`"
        )
    print()
    print("## Prompt Assumption Differences")
    print("- Live market `status` values are `active` / `initialized`, not literal `open`; the client treats `active` as open and reports the raw status.")
    print("- Live `KXMLBTOTAL` series title is `Pro Baseball Total Points`; event titles use `Total Runs` wording.")
    print("- Live HR series includes ladders beyond 1+ HR, so each strike is normalized separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
