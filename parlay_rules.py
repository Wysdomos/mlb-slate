"""Validation rules for correlation-based parlay boards."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Mapping, Sequence, Tuple

FORBIDDEN_MARKETS = {"2B", "SB"}
PITCHER_SIDE_MARKETS = {"H_ALLOWED", "ER_ALLOWED"}
BATTER_NESTED_MARKETS = {"HR", "TB", "HIT", "HRR"}

# Yard Sale is an explicitly HR-only parlay product. The general HR guard stays
# active everywhere else so HR legs cannot anchor or outrank safer legs.
HR_TOP_MARKET_EXCEPTIONS = {"yard_sale_same_game", "yard_sale_cross_game"}


def norm_name(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def leg_market(leg: Mapping[str, object]) -> str:
    return str(leg.get("market") or "").upper()


def validate_parlay(
    legs: Sequence[Mapping[str, object]],
    correlation_type: str,
    *,
    max_legs: int = 3,
) -> Tuple[bool, str]:
    if not legs:
        return False, "empty parlay"
    if len(legs) > max_legs:
        return False, "too many legs"
    for leg in legs:
        market = leg_market(leg)
        if market in FORBIDDEN_MARKETS:
            return False, f"{market} legs are not parlay material"
        if (
            market == "HR"
            and leg.get("leg_role") == "anchor"
            and correlation_type not in HR_TOP_MARKET_EXCEPTIONS
        ):
            return False, "HR cannot anchor a parlay"

    ranked = sorted(
        legs,
        key=lambda leg: float(leg.get("confidence_rank", 999) or 999),
    )
    if ranked and leg_market(ranked[0]) == "HR" and correlation_type not in HR_TOP_MARKET_EXCEPTIONS:
        return False, "HR cannot be the top-conviction leg"

    pitcher_sides = defaultdict(set)
    for leg in legs:
        market = leg_market(leg)
        if market in PITCHER_SIDE_MARKETS:
            pitcher_sides[norm_name(leg.get("name"))].add(market)
    for markets in pitcher_sides.values():
        if {"H_ALLOWED", "ER_ALLOWED"} <= markets:
            return False, "duplicate pitcher-side traffic legs"

    by_player = defaultdict(list)
    for leg in legs:
        key = norm_name(leg.get("name"))
        if key:
            by_player[key].append(leg)
    for player_legs in by_player.values():
        if len(player_legs) <= 1:
            continue
        markets = {leg_market(leg) for leg in player_legs}
        allowed_pitcher_pair = (
            correlation_type == "same_pitcher_k_outs"
            and markets == {"K", "OUTS"}
            and len(player_legs) == 2
        )
        if not allowed_pitcher_pair:
            if markets & BATTER_NESTED_MARKETS:
                return False, "nested same-player batter legs"
            return False, "duplicate player leg"
    return True, "ok"


def validate_board_people(legs: Iterable[Mapping[str, object]], *, max_count: int = 2) -> Tuple[bool, str]:
    counts = Counter(norm_name(leg.get("name")) for leg in legs if norm_name(leg.get("name")))
    offenders = [name for name, count in counts.items() if count > max_count]
    if offenders:
        return False, "person appears too often across board"
    return True, "ok"
