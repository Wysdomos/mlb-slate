#!/usr/bin/env python3
"""
fetch_bpp.py -- reduced BallparkPal public lens for The Daily Slate.

Reads day_data.json, calls BPP for slate projection context, and writes only
derived allowlisted values to bpp_summary.json. Raw API envelopes and field
names must never be persisted to tracked JSON.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from services.bpp_client import BppApiError, BppClient

DATA_FILE = os.environ.get("DATA_FILE", "day_data.json")
OUT_FILE = os.environ.get("BPP_SUMMARY_FILE", "bpp_summary.json")
BPP_MIN_GAP = float(os.environ.get("BPP_MIN_GAP", "1.0"))
BPP_MONTHLY_BUDGET = 15000

ALLOWED_FIELDS = {
    "hr_prob",
    "hit_prob",
    "k_prob",
    "walk_prob",
    "hr_vs_typical",
    "k_vs_typical",
    "proj_hits",
    "proj_hr",
    "proj_k",
    "proj_bb",
    "park_hr_factor",
    "park_hits_factor",
    "matchup_advantage",
}
RAW_FIELD_MARKERS = {
    "marketKey",
    "matchupAdvantage",
    "requestId",
    "asOf",
    "homeRunProbability",
    "strikeoutProbability",
    "singleProbability",
    "doubleTripleProbability",
    "walkProbability",
    "homeRunVsTypical",
    "strikeoutVsTypical",
}


class CallCounter:
    def __init__(self, client: BppClient) -> None:
        self.client = client
        self.count = 0

    def call(self, label: str, func: Any) -> Dict[str, Any]:
        self.count += 1
        print(
            f"[bpp] call {self.count} "
            f"(monthly budget {BPP_MONTHLY_BUDGET}): {label}",
            file=sys.stderr,
        )
        try:
            return func()
        except Exception as exc:
            print(f"[bpp] {label} failed: {exc}", file=sys.stderr)
            return {}


def main() -> int:
    if not os.environ.get("BPP_API_KEY"):
        print("[bpp] skipped: BPP_API_KEY is not set", file=sys.stderr)
        write_summary({})
        print("BPP API calls this run: 0")
        return 0

    try:
        data = json.loads(Path(DATA_FILE).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[bpp] could not read {DATA_FILE}: {exc}", file=sys.stderr)
        write_summary({})
        print("BPP API calls this run: 0")
        return 0

    games = slate_games(data)
    if not games:
        print("[bpp] no slate games found", file=sys.stderr)
        write_summary({})
        print("BPP API calls this run: 0")
        return 0

    slate_date = str(games[0].get("date") or "")[:10]
    client = BppClient(use_cache=False, min_gap=BPP_MIN_GAP)
    counter = CallCounter(client)

    summary: Dict[str, Dict[str, float]] = {}
    park_by_game = index_park_rows(
        counter.call(
            f"parkfactors({slate_date})",
            lambda: client.parkfactors(slate_date, force_refresh=True),
        )
    )
    hitter_park_by_name = index_hitter_park_rows(
        counter.call(
            f"hitter_parkfactors({slate_date})",
            lambda: client.hitter_parkfactors(date=slate_date, force_refresh=True),
        )
    )
    matchup_by_name = index_matchup_rows(
        counter.call(
            f"matchups({slate_date}, starters=True)",
            lambda: client.matchups(slate_date, starters=True, force_refresh=True),
        )
    )

    for game in games:
        game_id = game.get("game_id")
        if game_id is None:
            continue
        payload = counter.call(
            f"projection_averages({game_id})",
            lambda game_id=game_id: client.projection_averages(game_id, force_refresh=True),
        )
        merge_projection_averages(summary, payload)

    apply_context(summary, hitter_park_by_name, matchup_by_name, park_by_game)
    clean = clean_summary(summary)
    write_summary(clean)
    print(f"[bpp] wrote {OUT_FILE}: {len(clean)} player entries", file=sys.stderr)
    print(
        f"[bpp] calls/run {counter.count}; "
        f"3 runs/day ~= {counter.count * 3}; 4 runs/day ~= {counter.count * 4}; "
        f"monthly budget {BPP_MONTHLY_BUDGET}",
        file=sys.stderr,
    )
    print(f"BPP API calls this run: {counter.count}")
    return 0


def slate_games(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    seen = set()
    games: List[Dict[str, Any]] = []
    for row in data.get("BP_Games", []):
        game_id = row.get("GamePk") or row.get("gameId")
        date = row.get("GameDate") or row.get("gameDate")
        if game_id is None or game_id in seen:
            continue
        seen.add(game_id)
        games.append({"game_id": int(game_id), "date": date})
    return games


def merge_projection_averages(summary: Dict[str, Dict[str, float]], payload: Mapping[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload, Mapping) else None
    if not isinstance(data, Mapping):
        return
    for row in data.get("batters", []) or []:
        key = norm_name(row.get("playerName"))
        if not key:
            continue
        entry = summary.setdefault(key, {})
        set_round(entry, "proj_hits", row.get("hits"))
        set_round(entry, "proj_hr", row.get("homeRuns"))
        set_round(entry, "proj_k", row.get("strikeouts"))
        set_round(entry, "proj_bb", row.get("walks"))
    for row in data.get("pitchers", []) or []:
        key = norm_name(row.get("playerName"))
        if not key:
            continue
        entry = summary.setdefault(key, {})
        set_round(entry, "proj_hits", row.get("hitsAllowed"))
        set_round(entry, "proj_hr", row.get("homeRunsAllowed"))
        set_round(entry, "proj_k", row.get("strikeouts"))
        set_round(entry, "proj_bb", row.get("walks"))


def index_park_rows(payload: Mapping[str, Any]) -> Dict[int, Dict[str, float]]:
    out: Dict[int, Dict[str, float]] = {}
    for row in iter_items(payload):
        game_id = as_int(row.get("gameId"))
        if game_id is None:
            continue
        hits_parts = [as_float(row.get("singlesPercent")), as_float(row.get("doublesTriplesPercent"))]
        hits_parts = [v for v in hits_parts if v is not None]
        hit_factor = sum(hits_parts) / len(hits_parts) if hits_parts else None
        out[game_id] = {}
        set_round(out[game_id], "park_hr_factor", row.get("homeRunsPercent"), digits=0)
        if hit_factor is not None:
            set_round(out[game_id], "park_hits_factor", hit_factor, digits=0)
    return out


def index_hitter_park_rows(payload: Mapping[str, Any]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for row in iter_items(payload):
        key = norm_name(row.get("playerName"))
        if not key:
            continue
        entry = out.setdefault(key, {})
        set_round(entry, "park_hr_factor", multiplier_to_pct(row.get("homeRuns")), digits=0)
        hit_factor = average_numbers([row.get("singles"), row.get("doublesTriples")])
        set_round(entry, "park_hits_factor", multiplier_to_pct(hit_factor), digits=0)
    return out


def index_matchup_rows(payload: Mapping[str, Any]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for row in iter_items(payload):
        key = norm_name(row.get("batterName"))
        if not key:
            continue
        entry = out.setdefault(key, {})
        set_round(entry, "hr_prob", row.get("homeRunProbability"))
        set_round(entry, "k_prob", row.get("strikeoutProbability"))
        set_round(entry, "walk_prob", row.get("walkProbability"))
        hit_prob = sum_present([row.get("singleProbability"), row.get("doubleTripleProbability")])
        if hit_prob is not None:
            set_round(entry, "hit_prob", hit_prob)
        set_round(entry, "hr_vs_typical", row.get("homeRunVsTypical"))
        set_round(entry, "k_vs_typical", row.get("strikeoutVsTypical"))
        raw = as_float(row.get("homeRunVsTypical"))
        if raw is None:
            raw = as_float(row.get("runsCreatedVsTypical"))
        if raw is not None:
            entry["matchup_advantage"] = clamp(round(raw / 2), -10, 10)
    return out


def apply_context(
    summary: Dict[str, Dict[str, float]],
    hitter_park_by_name: Mapping[str, Mapping[str, float]],
    matchup_by_name: Mapping[str, Mapping[str, float]],
    park_by_game: Mapping[int, Mapping[str, float]],
) -> None:
    for key, values in hitter_park_by_name.items():
        if key in summary:
            summary[key].update(values)
    for key, values in matchup_by_name.items():
        if key in summary:
            summary[key].update(values)
    # Team/game park context is intentionally a fallback; player-specific
    # hitter factors above are preferred when BPP publishes them.
    if not park_by_game:
        return


def clean_summary(summary: Mapping[str, Mapping[str, Any]]) -> Dict[str, Dict[str, float]]:
    clean: Dict[str, Dict[str, float]] = {}
    for name in sorted(summary):
        entry = {}
        for field in sorted(ALLOWED_FIELDS):
            if field in summary[name]:
                value = summary[name][field]
                if isinstance(value, (int, float)):
                    entry[field] = value
        if entry:
            clean[name] = entry
    serialized = json.dumps(clean, sort_keys=True)
    leaked = [marker for marker in RAW_FIELD_MARKERS if marker in serialized]
    if leaked:
        raise RuntimeError(f"BPP summary firewall leak: {', '.join(leaked)}")
    return clean


def iter_items(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    data = payload.get("data") if isinstance(payload, Mapping) else None
    if isinstance(data, Mapping) and isinstance(data.get("items"), list):
        for row in data["items"]:
            if isinstance(row, Mapping):
                yield row
    elif isinstance(data, list):
        for row in data:
            if isinstance(row, Mapping):
                yield row


def write_summary(summary: Mapping[str, Mapping[str, float]]) -> None:
    tmp = f"{OUT_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, OUT_FILE)


def set_round(entry: Dict[str, float], key: str, value: Any, digits: int = 2) -> None:
    num = as_float(value)
    if num is None:
        return
    entry[key] = round(num, digits)


def average_numbers(values: Iterable[Any]) -> Optional[float]:
    nums = [v for v in (as_float(value) for value in values) if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def sum_present(values: Iterable[Any]) -> Optional[float]:
    nums = [v for v in (as_float(value) for value in values) if v is not None]
    if not nums:
        return None
    return sum(nums)


def multiplier_to_pct(value: Any) -> Optional[float]:
    num = as_float(value)
    if num is None:
        return None
    return (num - 1.0) * 100


def as_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> Optional[int]:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clamp(value: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, value)))


def norm_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[bpp] fatal reducer error: {exc}", file=sys.stderr)
        write_summary({})
        print("BPP API calls this run: 0")
        raise SystemExit(0)
