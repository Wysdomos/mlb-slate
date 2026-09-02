#!/usr/bin/env python3
"""Build slate-to-Kalshi market matches.

This job is intentionally not wired into the daily pipeline yet. Failures write
an empty non-fatal envelope so Kalshi can never break the slate build.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from services.kalshi_client.candidates import build_candidates_from_files
from services.kalshi_client.models import TradableState
from services.kalshi_client.matcher import (
    DEFAULT_QUOTE_STALE_SECONDS,
    build_match_snapshot,
    coverage_by_market,
    load_json,
    missing_exact_strikes,
)

DEFAULT_OUTPUT = "kalshi_matches.json"

# Quote fields logged onto every slate_picks row. Kalshi is a no-vig
# exchange, so a live price IS a probability: logging it at pick time gives
# model-vs-market on every pick without waiting for outcomes.
KALSHI_PICK_FIELDS = (
    "kalshi_ticker",
    "kalshi_side",
    "kalshi_price",
    "kalshi_state",
    "kalshi_quote_ts",
    "ask_source",
    "fee_band",
)


def annotate_slate_picks(slate_picks_path: str | Path, matches: list[Any]) -> int:
    """Write Kalshi quote fields onto the pick rows the matches came from.

    Candidates are built positionally from slate["picks"] and
    build_match_snapshot preserves that order, so matches[i] belongs to
    picks[i] -- no id join, no collision risk. Every pick gets all
    KALSHI_PICK_FIELDS (null default). A matched market contributes
    ticker/side/state/quote_ts; the price and its ask_source/fee_band are
    copied ONLY from an OPEN_TRADABLE quote, so a stale, settled, or
    unopened price is never logged as if it were live. Nothing is ever
    fabricated. Returns the number of rows that received a live price.
    """
    try:
        slate = load_json(slate_picks_path)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"Kalshi annotate skipped non-fatally: {type(exc).__name__}: {exc}")
        return 0
    picks = slate.get("picks") or []
    if len(picks) != len(matches):
        print(
            "Kalshi annotate skipped non-fatally: "
            f"{len(matches)} matches vs {len(picks)} picks -- refusing a positional join"
        )
        return 0
    priced = 0
    for pick, match in zip(picks, matches):
        if not isinstance(pick, dict) or not isinstance(match, dict):
            continue
        for field in KALSHI_PICK_FIELDS:
            pick[field] = None
        if not match.get("kalshi_ticker"):
            continue
        pick["kalshi_ticker"] = match.get("kalshi_ticker")
        pick["kalshi_side"] = match.get("kalshi_side")
        pick["kalshi_state"] = match.get("tradable_state")
        pick["kalshi_quote_ts"] = match.get("quote_ts")
        if match.get("tradable_state") == TradableState.OPEN_TRADABLE.value:
            pick["kalshi_price"] = match.get("buy_price")
            pick["ask_source"] = match.get("ask_source")
            pick["fee_band"] = match.get("fee_band")
            if pick["kalshi_price"] is not None:
                priced += 1
    _write_slate_picks(Path(slate_picks_path), slate)
    return priced


def _write_slate_picks(path: Path, slate: dict[str, Any]) -> None:
    # Same serialization build_day46.py uses for these files.
    with path.open("w", encoding="utf-8") as fh:
        json.dump(slate, fh, ensure_ascii=False, indent=1)
    iso = str(slate.get("slate_date") or "")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", iso)
    if not m:
        return
    dated = path.with_name(f"slate_picks_{int(m.group(2))}-{int(m.group(3))}.json")
    if dated.exists():  # keep the dated archive the grader reads in sync
        with dated.open("w", encoding="utf-8") as fh:
            json.dump(slate, fh, ensure_ascii=False, indent=1)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Match slate picks to Kalshi markets.")
    parser.add_argument("--slate-picks", default=os.environ.get("SLATE_PICKS_FILE", "slate_picks.json"))
    parser.add_argument("--day-data", default=os.environ.get("DATA_FILE", "day_data.json"))
    parser.add_argument("--kalshi-markets", default=os.environ.get("KALSHI_MARKETS_FILE", "kalshi_markets.json"))
    parser.add_argument("--output", default=os.environ.get("KALSHI_MATCHES_FILE", DEFAULT_OUTPUT))
    parser.add_argument(
        "--quote-stale-seconds",
        type=int,
        default=int(os.environ.get("KALSHI_QUOTE_STALE_SECONDS", DEFAULT_QUOTE_STALE_SECONDS)),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    candidates = build_candidates_from_files(args.slate_picks, args.day_data)
    slate_date = _slate_date(candidates)
    try:
        kalshi_snapshot = load_json(args.kalshi_markets)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as exc:
        payload = _failure_payload(slate_date, f"missing or unreadable kalshi_markets.json: {type(exc).__name__}: {exc}")
        write_json(output, payload)
        print(f"Kalshi match skipped non-fatally: {payload['fetch_error']}")
        return 0

    payload = build_match_snapshot(
        candidates,
        kalshi_snapshot,
        slate_date=slate_date,
        quote_stale_seconds=args.quote_stale_seconds,
    )
    write_json(output, payload)
    if payload.get("fetch_ok"):
        counts = payload.get("counts") or {}
        print(
            "Kalshi matches OK: "
            f"matched={counts.get('matched', 0)} live={counts.get('live', 0)} "
            f"tbd={counts.get('tbd', 0)} no_quote={counts.get('no_quote', 0)} "
            f"not_listed={counts.get('not_listed', 0)} ambiguous={counts.get('ambiguous', 0)}"
        )
        coverage = coverage_by_market(candidates, payload.get("matches") or [])
        for market, bucket in sorted(coverage.items()):
            print(
                f"  {market}: {bucket['matched']}/{bucket['candidates']} matched, "
                f"live={bucket['live']} not_listed={bucket['not_listed']} ambiguous={bucket['ambiguous']}"
            )
        missing = missing_exact_strikes(payload.get("matches") or [])
        if missing:
            print("  exact strike missing:")
            for row in missing:
                print(f"    {row['slate_id']}: available={row['available_strikes']}")
        priced = annotate_slate_picks(args.slate_picks, payload.get("matches") or [])
        print(f"Kalshi price fields written: {priced} pick(s) carry a live OPEN_TRADABLE price")
    else:
        print(f"Kalshi match skipped non-fatally: {payload.get('fetch_error')}")
    return 0


def _slate_date(candidates: list[dict[str, Any]]) -> str:
    for candidate in candidates:
        if candidate.get("slate_date"):
            return str(candidate["slate_date"])
    return ""


def _failure_payload(slate_date: str, message: str) -> dict[str, Any]:
    from datetime import datetime, timezone

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "slate_date": slate_date,
        "fetch_ok": False,
        "fetch_error": message,
        "counts": {"matched": 0, "live": 0, "tbd": 0, "no_quote": 0, "not_listed": 0, "ambiguous": 0},
        "matches": [],
    }


if __name__ == "__main__":
    raise SystemExit(main())
