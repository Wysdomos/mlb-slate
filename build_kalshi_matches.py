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


def annotate_slate_picks(
    slate_picks_path: str | Path,
    matches: "list[Any] | None",
    *,
    default_quote_ts: "str | None" = None,
) -> tuple[int, int]:
    """Write Kalshi quote fields onto the pick rows the matches came from.

    Two layers, so the day's captured prices survive the 8x-daily rebuild:

    1. Carry-forward: build_day46 regenerates slate_picks fresh every build,
       which would null every previously captured price by the final (post-
       game) rebuild -- exactly the rows the 5AM grader reads. So any prior
       row in the dated archive holding a real kalshi_price is carried onto
       the matching new pick first (keyed join; duplicate keys consume
       first-match, mirroring the row multiset). This layer runs even when
       today's fetch failed (matches=None), so a bad Kalshi hour cannot
       erase the morning's quotes.
    2. Fresh quotes: candidates are built positionally from slate["picks"]
       and build_match_snapshot preserves that order, so matches[i] belongs
       to picks[i]. A matched market refreshes ticker/side/state; the price
       with its ask_source/fee_band/quote_ts is (over)written ONLY from an
       OPEN_TRADABLE quote -- a stale, settled, or unopened price is never
       logged as live, and a settled state never erases the price captured
       while the market was live. quote_ts falls back to the market
       snapshot's generated_at (the matcher's own quote_ts source is not
       serialized by the fetcher). Nothing is ever fabricated.

    Returns (fresh_priced, carried_forward).
    """
    try:
        slate = load_json(slate_picks_path)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"Kalshi annotate skipped non-fatally: {type(exc).__name__}: {exc}")
        return 0, 0
    picks = slate.get("picks") or []
    dated = _dated_path(Path(slate_picks_path), slate)
    # In-pipeline, build.py snapshots the pre-rebuild dated archive to
    # KALSHI_PRIOR_FILE before build_day46 overwrites it; standalone runs
    # fall back to the dated archive itself.
    prior_path = Path(os.environ.get("KALSHI_PRIOR_FILE", ".kalshi_prior_picks.json"))
    if prior_path.exists():
        prior = _prior_priced_rows(prior_path)
    elif dated is not None and dated.exists():
        prior = _prior_priced_rows(dated)
    else:
        prior = {}
    carried = 0
    for pick in picks:
        if not isinstance(pick, dict):
            continue
        for field in KALSHI_PICK_FIELDS:
            pick[field] = None
        stack = prior.get(_pick_key(pick))
        if stack:
            pick.update(stack.pop(0))
            carried += 1
    priced = 0
    if matches is None:
        pass  # fetch failed today: carry-forward only
    elif len(picks) != len(matches):
        print(
            "Kalshi fresh-quote join refused non-fatally: "
            f"{len(matches)} matches vs {len(picks)} picks (carried fields kept)"
        )
    else:
        for pick, match in zip(picks, matches):
            if not isinstance(pick, dict) or not isinstance(match, dict):
                continue
            if not match.get("kalshi_ticker"):
                continue  # unmatched today; carried fields (if any) stay
            pick["kalshi_ticker"] = match.get("kalshi_ticker")
            pick["kalshi_side"] = match.get("kalshi_side")
            pick["kalshi_state"] = match.get("tradable_state")
            if (
                match.get("tradable_state") == TradableState.OPEN_TRADABLE.value
                and match.get("buy_price") is not None
            ):
                pick["kalshi_price"] = match.get("buy_price")
                pick["ask_source"] = match.get("ask_source")
                pick["fee_band"] = match.get("fee_band")
                pick["kalshi_quote_ts"] = match.get("quote_ts") or default_quote_ts
                priced += 1
    _write_slate_picks(Path(slate_picks_path), slate, dated)
    return priced, carried


def _pick_key(pick: "dict[str, Any]") -> tuple[str, ...]:
    return (
        str(pick.get("market") or ""),
        str(pick.get("name") or pick.get("game") or pick.get("pick") or ""),
        str(pick.get("line") or ""),
        str(pick.get("board") or ""),
        str(pick.get("parlay_id") or ""),
        str(pick.get("leg_role") or ""),
    )


def _prior_priced_rows(path: Path) -> "dict[tuple[str, ...], list[dict[str, Any]]]":
    try:
        prior = load_json(path)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}
    out: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in prior.get("picks") or []:
        if isinstance(row, dict) and row.get("kalshi_price") is not None:
            out.setdefault(_pick_key(row), []).append(
                {field: row.get(field) for field in KALSHI_PICK_FIELDS}
            )
    return out


def _dated_path(path: Path, slate: "dict[str, Any]") -> "Path | None":
    iso = str(slate.get("slate_date") or "")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", iso)
    if not m:
        return None
    return path.with_name(f"slate_picks_{int(m.group(2))}-{int(m.group(3))}.json")


def _write_slate_picks(path: Path, slate: "dict[str, Any]", dated: "Path | None") -> None:
    # Same serialization build_day46.py uses; atomic so a mid-dump crash can
    # never leave a truncated file for the commit step to pick up.
    _atomic_dump(path, slate)
    if dated is not None and dated.exists():  # keep the grader's archive in sync
        _atomic_dump(dated, slate)


def _atomic_dump(path: Path, payload: "dict[str, Any]") -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Match slate picks to Kalshi markets.")
    parser.add_argument(
        "--slate-picks",
        # build_day46 writes the picks under PICKS_FILE (preview.yml sets it);
        # honor it so we always annotate the picks this build just wrote.
        default=os.environ.get("SLATE_PICKS_FILE")
        or os.environ.get("PICKS_FILE")
        or "slate_picks.json",
    )
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
        _, carried = annotate_slate_picks(args.slate_picks, None)
        print(f"Kalshi match skipped non-fatally: {payload['fetch_error']} (carried {carried} prior price(s))")
        return 0

    # A same-slate_date snapshot left behind by a failed fetch would pass the
    # matcher's date gate with quote ages frozen at fetch time -- hours-old
    # asks would be logged as live. Gate on the snapshot's own age instead.
    max_age = int(os.environ.get("KALSHI_SNAPSHOT_MAX_AGE", "1800"))
    age = _snapshot_age_seconds(kalshi_snapshot)
    if age is None or age > max_age:
        shown = "unknown" if age is None else f"{age:.0f}s"
        payload = _failure_payload(slate_date, f"stale kalshi_markets.json snapshot (age {shown} > {max_age}s)")
        write_json(output, payload)
        _, carried = annotate_slate_picks(args.slate_picks, None)
        print(f"Kalshi match skipped non-fatally: {payload['fetch_error']} (carried {carried} prior price(s))")
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
        priced, carried = annotate_slate_picks(
            args.slate_picks,
            payload.get("matches") or [],
            default_quote_ts=str(kalshi_snapshot.get("generated_at") or "") or None,
        )
        print(
            f"Kalshi price fields written: {priced} fresh OPEN_TRADABLE price(s), "
            f"{carried} carried forward from earlier builds"
        )
    else:
        _, carried = annotate_slate_picks(args.slate_picks, None)
        print(f"Kalshi match skipped non-fatally: {payload.get('fetch_error')} (carried {carried} prior price(s))")
    return 0


def _snapshot_age_seconds(snapshot: "dict[str, Any]") -> "float | None":
    from datetime import datetime, timezone

    raw = str(snapshot.get("generated_at") or "")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds()


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
