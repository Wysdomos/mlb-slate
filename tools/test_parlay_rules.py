#!/usr/bin/env python3
"""Smoke tests for correlation parlay hard guards."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parlay_rules import validate_parlay


def assert_rejected(legs, correlation_type, expected):
    ok, reason = validate_parlay(legs, correlation_type)
    assert not ok, (legs, reason)
    assert expected in reason, reason
    print(f"rejected: {reason}")


def main() -> int:
    assert_rejected(
        [
            {"market": "HRR", "name": "Sample Batter", "leg_role": "satellite", "confidence_rank": 1},
            {"market": "HIT", "name": "Sample Batter", "leg_role": "satellite", "confidence_rank": 2},
        ],
        "lineup_stack",
        "nested same-player",
    )
    assert_rejected(
        [
            {"market": "H_ALLOWED", "name": "Sample Pitcher", "leg_role": "satellite", "confidence_rank": 2},
            {"market": "ER_ALLOWED", "name": "Sample Pitcher", "leg_role": "satellite", "confidence_rank": 3},
        ],
        "both_sides",
        "duplicate pitcher-side",
    )
    assert_rejected(
        [
            {"market": "HR", "name": "Sample Batter", "leg_role": "anchor", "confidence_rank": 1},
            {"market": "HIT", "name": "Other Batter", "leg_role": "satellite", "confidence_rank": 2},
        ],
        "anchor",
        "HR cannot anchor",
    )
    assert_rejected(
        [
            {"market": "HR", "name": "Sample Batter", "leg_role": "satellite", "confidence_rank": 1},
            {"market": "HIT", "name": "Other Batter", "leg_role": "satellite", "confidence_rank": 2},
        ],
        "lineup_stack",
        "HR cannot be the top-conviction",
    )
    assert_rejected(
        [
            {"market": "SB", "name": "Sample Runner", "leg_role": "satellite", "confidence_rank": 2},
        ],
        "lineup_stack",
        "SB legs",
    )
    ok, reason = validate_parlay(
        [
            {"market": "K", "name": "Sample Pitcher", "leg_role": "anchor", "confidence_rank": 1},
            {"market": "OUTS", "name": "Sample Pitcher", "leg_role": "satellite", "confidence_rank": 2},
        ],
        "same_pitcher_k_outs",
    )
    assert ok, reason
    print("accepted: same pitcher K plus outs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
