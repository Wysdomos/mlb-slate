"""Archive Ballpark Pal daily API snapshots.

Usage:
    python3 -m services.bpp_client.snapshot --date 2026-07-22
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as date_type
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from services.bpp_client.client import BppClient, DEFAULT_CACHE_DIR
else:
    from .client import BppClient, DEFAULT_CACHE_DIR


def archive_date(
    date: str,
    *,
    api_key: Optional[str] = None,
    output_dir: Optional[Path] = None,
    force_refresh: bool = True,
) -> Dict[str, Any]:
    client = BppClient(api_key=api_key, use_cache=True)
    out_dir = output_dir or DEFAULT_CACHE_DIR / "snapshots" / date
    out_dir.mkdir(parents=True, exist_ok=True)

    archived: Dict[str, Any] = {"date": date, "files": [], "asOf": {}}

    games_payload = client.games(date=date, force_refresh=force_refresh)
    _write_json(out_dir / "games.json", games_payload)
    _record(archived, "games.json", games_payload)

    for filename, getter in (
        ("markets.json", lambda: client.markets(force_refresh=force_refresh)),
        ("teams.json", lambda: client.teams(force_refresh=force_refresh)),
        ("parkfactors.json", lambda: client.parkfactors(date, force_refresh=force_refresh)),
        (
            "parkfactors_hitters.json",
            lambda: client.hitter_parkfactors(date=date, force_refresh=force_refresh),
        ),
        ("matchups.json", lambda: client.matchups(date, force_refresh=force_refresh)),
        (
            "matchups_starters.json",
            lambda: client.matchups(date, starters=True, force_refresh=force_refresh),
        ),
    ):
        payload = getter()
        _write_json(out_dir / filename, payload)
        _record(archived, filename, payload)

    for game_id in _game_ids(games_payload):
        averages = client.projection_averages(game_id, force_refresh=force_refresh)
        probabilities = client.projection_probabilities(game_id, force_refresh=force_refresh)
        avg_name = f"projection_averages_{game_id}.json"
        prob_name = f"projection_probabilities_{game_id}.json"
        _write_json(out_dir / avg_name, averages)
        _write_json(out_dir / prob_name, probabilities)
        _record(archived, avg_name, averages)
        _record(archived, prob_name, probabilities)

    manifest = out_dir / "manifest.json"
    _write_json(manifest, archived)
    return archived


def _game_ids(payload: Dict[str, Any]) -> Iterable[int]:
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        rows = data["items"]
    elif isinstance(data, list):
        rows = data
    else:
        rows = [data]
    for row in rows:
        if isinstance(row, dict) and row.get("gameId") is not None:
            yield int(row["gameId"])


def _record(archived: Dict[str, Any], filename: str, payload: Dict[str, Any]) -> None:
    archived["files"].append(filename)
    meta = payload.get("meta")
    if isinstance(meta, dict) and meta.get("asOf"):
        archived["asOf"][filename] = meta["asOf"]


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive BPP API responses for a slate date.")
    parser.add_argument("--date", default=date_type.today().isoformat())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--use-cache", action="store_true", help="Allow existing cache reads.")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _parse_args(argv)
    if not os.environ.get("BPP_API_KEY"):
        print("BPP_API_KEY is not set; snapshot archive requires live API access.", file=sys.stderr)
        return 2
    archived = archive_date(
        args.date,
        output_dir=args.output_dir,
        force_refresh=not args.use_cache,
    )
    print(json.dumps({"date": archived["date"], "files": len(archived["files"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
