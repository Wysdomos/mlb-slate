#!/usr/bin/env python3
"""Smoke tests for Chapter E shadow chip tier formulas."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shadow_chips import (
    EDGE_PLUS,
    FADE,
    NEUTRAL,
    chip_hall_a,
    chip_hit_a,
    chip_hr_a,
    chip_hr_b,
    chip_k_a,
    percentile_lookup,
)


def main() -> int:
    pcts = percentile_lookup({"a": 10, "b": 20, "c": 30, "d": 40})
    assert pcts["a"] < pcts["b"] < pcts["c"] < pcts["d"]

    assert chip_hr_a(85, 10, 50) == EDGE_PLUS
    assert chip_hr_a(85, 85, 75) == FADE
    assert chip_hr_a(70, 10, 50) == NEUTRAL
    assert chip_hr_a(None, 10, 50) is None

    assert chip_hr_b(2, 85, 85) == EDGE_PLUS
    assert chip_hr_b(5, 60, 45) == FADE
    assert chip_hr_b(4, 60, 70) == NEUTRAL
    assert chip_hr_b(2, None, 85) is None

    assert chip_hit_a(80, 20) == EDGE_PLUS
    assert chip_hit_a(80, 80) == FADE
    assert chip_hit_a(60, 20) == NEUTRAL
    assert chip_hit_a(80, None) is None

    assert chip_k_a(5, 85, 75) == EDGE_PLUS
    assert chip_k_a(4, 20, 20) == FADE
    assert chip_k_a(3, 85, 75) == NEUTRAL
    assert chip_k_a(5, None, 75) is None

    assert chip_hall_a(20, 20, 20) == EDGE_PLUS
    assert chip_hall_a(80, 20, 20) == FADE
    assert chip_hall_a(40, 40, 40) == NEUTRAL
    assert chip_hall_a(20, None, 20) is None
    print("shadow chip formula smoke tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
