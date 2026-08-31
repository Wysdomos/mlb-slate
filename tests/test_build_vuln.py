#!/usr/bin/env python3
"""Tests for BPP-derived Sweet_Spot_Slate reconstruction."""

from __future__ import annotations

import math
import runpy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_vuln import derive_vuln_row, vuln_by_name

SCHEMA = {
    "ERA",
    "WHIP",
    "K9",
    "BB9",
    "ParkFactor",
    "VulnScore",
    "DangerBatter1",
    "DangerBatter2",
    "DangerBatter3",
    "Opponent",
    "Pitcher",
    "Team",
    "Throws",
}

FIXTURE = runpy.run_path(str(ROOT / "tests/fixtures/vuln_2026_07_29.py"))["VULN_2026_07_29"]


def band(value: float | int | str) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "dash"
    if numeric >= 50:
        return ">=50"
    if numeric >= 32:
        return "32-49"
    return "<32"


class BuildVulnTest(unittest.TestCase):
    def test_schema_and_pitcher_arithmetic_against_fixture(self) -> None:
        for case in FIXTURE:
            row = derive_vuln_row(case["sp_row"], parks=case["parks"], batters=[])
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(set(row), SCHEMA)
            sp = case["sp_row"]
            inn = float(sp["Inn"])
            self.assertEqual(row["WHIP"], round((float(sp["H"]) + float(sp["BB"])) / inn, 2))
            self.assertEqual(row["K9"], round((float(sp["K"]) / inn) * 9, 1))
            self.assertEqual(row["BB9"], round((float(sp["BB"]) / inn) * 9, 1))

    def test_vuln_banding_report_vs_workbook(self) -> None:
        actual = []
        predicted = []
        for case in FIXTURE:
            row = derive_vuln_row(case["sp_row"], parks=case["parks"], batters=[])
            assert row is not None
            actual.append(float(case["expected"]["VulnScore"]))
            predicted.append(float(row["VulnScore"]))
        mean_actual = sum(actual) / len(actual)
        mean_pred = sum(predicted) / len(predicted)
        numerator = sum((p - mean_pred) * (a - mean_actual) for p, a in zip(predicted, actual))
        denom = math.sqrt(
            sum((p - mean_pred) ** 2 for p in predicted)
            * sum((a - mean_actual) ** 2 for a in actual)
        )
        corr = numerator / denom
        mae = sum(abs(p - a) for p, a in zip(predicted, actual)) / len(actual)
        same_band = sum(band(p) == band(a) for p, a in zip(predicted, actual))
        print(
            f"Vuln fixture report: n={len(actual)} corr={corr:.3f} "
            f"mae={mae:.2f} same_band={same_band}/{len(actual)}"
        )
        self.assertEqual(len(actual), 32)

    def test_workbook_present_wins_and_gets_source_label(self) -> None:
        expected = dict(FIXTURE[0]["expected"])
        expected["VulnScore"] = 12
        data = {
            "Sweet_Spot_Slate": [expected],
            "SP_Projections": [FIXTURE[0]["sp_row"]],
            "Park_Factors": FIXTURE[0]["parks"],
            "BP_Batters": [],
        }
        rows = vuln_by_name(data)
        row = rows[expected["Pitcher"].lower()]
        self.assertEqual(row["VulnScore"], 12)
        self.assertEqual(row["source"], "workbook")

    def test_workbook_absent_uses_bpp_and_gets_source_label(self) -> None:
        data = {
            "Sweet_Spot_Slate": [],
            "SP_Projections": [FIXTURE[0]["sp_row"]],
            "Park_Factors": FIXTURE[0]["parks"],
            "BP_Batters": [],
        }
        rows = vuln_by_name(data)
        row = rows[FIXTURE[0]["sp_row"]["Pitcher"].lower()]
        self.assertEqual(row["source"], "bpp")
        self.assertNotEqual(row["VulnScore"], "—")

    def test_zero_or_missing_innings_degrades_to_dash(self) -> None:
        cases = []
        zero_inn = dict(FIXTURE[0]["sp_row"])
        zero_inn["Inn"] = 0
        cases.append(zero_inn)
        missing_inn = dict(FIXTURE[0]["sp_row"])
        del missing_inn["Inn"]
        cases.append(missing_inn)
        for sp in cases:
            row = derive_vuln_row(sp, parks=FIXTURE[0]["parks"], batters=[])
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["WHIP"], "—")
            self.assertEqual(row["K9"], "—")
            self.assertEqual(row["BB9"], "—")
            self.assertEqual(row["VulnScore"], "—")

    def test_tbd_pitcher_returns_none(self) -> None:
        sp = dict(FIXTURE[0]["sp_row"])
        sp["Pitcher"] = "TBD"
        self.assertIsNone(derive_vuln_row(sp, parks=FIXTURE[0]["parks"], batters=[]))


if __name__ == "__main__":
    unittest.main()
