import json
import unittest
from pathlib import Path

from services.kalshi_client.candidates import (
    GameResolver,
    build_candidates,
    candidate_for_pick,
    parse_display_line,
)

ROOT = Path(__file__).resolve().parents[3]


class CandidateTests(unittest.TestCase):
    def test_k_line_forms_pin_plus_vs_literal_thresholds(self):
        self.assertEqual(parse_display_line("O 5+"), {"direction": "over", "threshold": 4.5, "reason": None})
        self.assertEqual(parse_display_line("O 2.5"), {"direction": "over", "threshold": 2.5, "reason": None})
        self.assertEqual(parse_display_line("O 3.5"), {"direction": "over", "threshold": 3.5, "reason": None})

    def test_hr_line_form(self):
        self.assertEqual(parse_display_line("Ov 0.5 HR"), {"direction": "over", "threshold": 0.5, "reason": None})

    def test_unit_label_stripping(self):
        self.assertEqual(parse_display_line("Over 13.5 outs"), {"direction": "over", "threshold": 13.5, "reason": None})
        self.assertEqual(parse_display_line("Under 19.5 outs"), {"direction": "under", "threshold": 19.5, "reason": None})
        self.assertEqual(parse_display_line("Under 8.5 H allowed"), {"direction": "under", "threshold": 8.5, "reason": None})
        self.assertEqual(parse_display_line("Ov 2.5 ER"), {"direction": "over", "threshold": 2.5, "reason": None})

    def test_total_line_none_resolves_from_ref_line(self):
        day_data = {"BP_Games": [{"AwayTeam": "SF", "HomeTeam": "ATL"}]}
        pick = {
            "market": "TOTAL",
            "pick": "SF@ATL OVER 8.5",
            "game": "SF@ATL",
            "line": None,
            "lean": "OVER",
            "ref_line": 8.5,
            "consensus": 2,
        }
        candidate = candidate_for_pick(pick, slate_date="2026-08-31", games=GameResolver(day_data))
        self.assertTrue(candidate.matchable)
        self.assertEqual(candidate.threshold, 8.5)
        self.assertEqual(candidate.direction, "over")

    def test_total_line_none_without_threshold_is_unmatchable(self):
        day_data = {"BP_Games": [{"AwayTeam": "SF", "HomeTeam": "ATL"}]}
        pick = {
            "market": "TOTAL",
            "pick": "SF@ATL OVER",
            "game": "SF@ATL",
            "line": None,
            "lean": "OVER",
        }
        candidate = candidate_for_pick(pick, slate_date="2026-08-31", games=GameResolver(day_data))
        self.assertFalse(candidate.matchable)
        self.assertEqual(candidate.reason, "missing_total_threshold")

    def test_nrfi_direction_is_no(self):
        day_data = {"BP_Games": [{"AwayTeam": "SF", "HomeTeam": "ATL"}]}
        pick = {"market": "NRFI", "pick": "SF@ATL Neutral", "game": "SF@ATL", "line": None, "consensus": 0}
        candidate = candidate_for_pick(pick, slate_date="2026-08-31", games=GameResolver(day_data))
        self.assertTrue(candidate.matchable)
        self.assertEqual(candidate.market_type, "run_first_inning")
        self.assertEqual(candidate.direction, "no")
        self.assertIsNone(candidate.threshold)

    def test_game_key_is_away_at_home_against_real_game(self):
        slate = json.loads((ROOT / "slate_picks.json").read_text(encoding="utf-8"))
        day_data = json.loads((ROOT / "day_data.json").read_text(encoding="utf-8"))
        first_game = day_data["BP_Games"][0]
        pick = {
            "market": "HR",
            "pick": "Test Batter Ov 0.5 HR",
            "name": "Test Batter",
            "team": first_game["HomeTeam"],
            "opp": first_game["AwayTeam"],
            "line": "Ov 0.5 HR",
            "consensus": 1,
        }
        candidate = candidate_for_pick(pick, slate_date=slate["slate_date"], games=GameResolver(day_data))
        expected = f"{first_game['AwayTeam']}@{first_game['HomeTeam']}"
        self.assertEqual(candidate.game_key, expected)
        self.assertEqual(candidate.away_team, first_game["AwayTeam"])
        self.assertEqual(candidate.home_team, first_game["HomeTeam"])

    def test_sb_and_2b_are_unmatchable_no_series(self):
        day_data = {"BP_Games": [{"AwayTeam": "SF", "HomeTeam": "ATL"}]}
        for market in ("SB", "2B"):
            pick = {
                "market": market,
                "pick": f"Test Player Ov 0.5 {market}",
                "name": "Test Player",
                "team": "SF",
                "opp": "ATL",
                "line": "Ov 0.5",
                "consensus": 1,
            }
            with self.subTest(market=market):
                candidate = candidate_for_pick(pick, slate_date="2026-08-31", games=GameResolver(day_data))
                self.assertFalse(candidate.matchable)
                self.assertEqual(candidate.reason, "no_kalshi_series")

    def test_same_normalized_name_on_different_teams_gets_different_ids(self):
        slate = {
            "slate_date": "2026-08-31",
            "picks": [
                {"market": "HIT", "pick": "Jose Ramirez Ov 0.5 H", "name": "José Ramírez Jr.", "team": "SF", "opp": "ATL", "line": "Ov 0.5 H"},
                {"market": "HIT", "pick": "Jose Ramirez Ov 0.5 H", "name": "Jose Ramirez", "team": "NYM", "opp": "TB", "line": "Ov 0.5 H"},
            ],
        }
        day_data = {"BP_Games": [{"AwayTeam": "SF", "HomeTeam": "ATL"}, {"AwayTeam": "NYM", "HomeTeam": "TB"}]}
        candidates = build_candidates(slate, day_data)
        self.assertEqual(candidates[0].player_norm, "jose ramirez")
        self.assertEqual(candidates[1].player_norm, "jose ramirez")
        self.assertNotEqual(candidates[0].slate_id, candidates[1].slate_id)


if __name__ == "__main__":
    unittest.main()
