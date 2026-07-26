"""Shadow-only matchup chip tier formulas.

These helpers return public-safe tier labels only. Any numeric BPP-derived
inputs must be percentile-ranked over the current slate before calling them.
"""

from __future__ import annotations

from statistics import median
from typing import Dict, Iterable, Mapping, Optional

CHIP_FIELDS = ("chip_hra", "chip_hrb", "chip_hit_a", "chip_k_a", "chip_hall_a")
CHIP_LABELS = {
    "chip_hra": "HR-A Avoidance Tax",
    "chip_hrb": "HR-B Contextual Spike",
    "chip_hit_a": "HIT-A Contact Floor",
    "chip_k_a": "K-A Volume Cap Refiner",
    "chip_hall_a": "HALLOWED-A Contact Quality Reversal",
}
TIER_ORDER = ("EDGE+", "EDGE", "NEUTRAL", "FADE")

EDGE_PLUS = "EDGE+"
NEUTRAL = "NEUTRAL"
FADE = "FADE"


def blank_chip_tiers() -> Dict[str, Optional[str]]:
    return {field: None for field in CHIP_FIELDS}


def as_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def percentile_rank(value, population: Iterable[object]) -> Optional[float]:
    needle = as_float(value)
    values = sorted(v for v in (as_float(item) for item in population) if v is not None)
    if needle is None or not values:
        return None
    below = sum(1 for item in values if item < needle)
    equal = sum(1 for item in values if item == needle)
    return 100.0 * (below + 0.5 * equal) / len(values)


def percentile_lookup(values_by_key: Mapping[str, object]) -> Dict[str, float]:
    clean = {
        str(key).strip().lower(): as_float(value)
        for key, value in values_by_key.items()
        if as_float(value) is not None
    }
    population = list(clean.values())
    return {
        key: pct
        for key, value in clean.items()
        if (pct := percentile_rank(value, population)) is not None
    }


def median_value(values: Iterable[object]) -> Optional[float]:
    clean = [v for v in (as_float(item) for item in values) if v is not None]
    return median(clean) if clean else None


def chip_hr_a(hr_prob_pct, walk_prob_pct, matchup_advantage_pct) -> Optional[str]:
    if any(v is None for v in (hr_prob_pct, walk_prob_pct, matchup_advantage_pct)):
        return None
    if hr_prob_pct >= 80 and walk_prob_pct <= 20 and matchup_advantage_pct < 60:
        return EDGE_PLUS
    if hr_prob_pct >= 80 and walk_prob_pct >= 80 and matchup_advantage_pct >= 60:
        return FADE
    return NEUTRAL


def chip_hr_b(consensus, hr_vs_typical_pct, park_hr_factor_pct) -> Optional[str]:
    c = as_float(consensus)
    if any(v is None for v in (c, hr_vs_typical_pct, park_hr_factor_pct)):
        return None
    if c <= 2 and hr_vs_typical_pct >= 80 and park_hr_factor_pct >= 80:
        return EDGE_PLUS
    if 5 <= c <= 6 and park_hr_factor_pct <= 50:
        return FADE
    return NEUTRAL


def chip_hit_a(hit_prob_pct, k_prob_pct) -> Optional[str]:
    if any(v is None for v in (hit_prob_pct, k_prob_pct)):
        return None
    if hit_prob_pct >= 75 and k_prob_pct <= 30:
        return EDGE_PLUS
    if hit_prob_pct >= 75 and k_prob_pct >= 70:
        return FADE
    return NEUTRAL


def chip_k_a(consensus, kbb_ratio_pct, innings_pct) -> Optional[str]:
    c = as_float(consensus)
    if any(v is None for v in (c, kbb_ratio_pct, innings_pct)):
        return None
    if 5 <= c <= 6 and kbb_ratio_pct >= 80 and innings_pct >= 60:
        return EDGE_PLUS
    if 4 <= c <= 6 and kbb_ratio_pct <= 25 and innings_pct <= 25:
        return FADE
    return NEUTRAL


def chip_hall_a(opponent_barrel_pct, opponent_hard_hit_pct, hits_allowed_pct) -> Optional[str]:
    if any(v is None for v in (opponent_barrel_pct, opponent_hard_hit_pct, hits_allowed_pct)):
        return None
    if opponent_barrel_pct <= 25 and opponent_hard_hit_pct <= 25:
        return EDGE_PLUS
    if opponent_barrel_pct >= 75:
        return FADE
    return NEUTRAL
