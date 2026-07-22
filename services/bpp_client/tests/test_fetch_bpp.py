import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_bpp


class FetchBppReducerTests(unittest.TestCase):
    def test_reducer_emits_only_allowlisted_derived_fields(self):
        summary = {}
        fetch_bpp.merge_projection_averages(
            summary,
            {
                "meta": {"asOf": "raw-timestamp", "requestId": "raw-request"},
                "data": {
                    "batters": [
                        {
                            "playerName": "Example Hitter",
                            "hits": 1.234,
                            "homeRuns": 0.157,
                            "strikeouts": 0.891,
                            "walks": 0.333,
                            "marketKey": "must-not-leak",
                        }
                    ],
                    "pitchers": [],
                },
            },
        )
        parks = fetch_bpp.index_hitter_park_rows(
            {
                "data": {
                    "items": [
                        {
                            "playerName": "Example Hitter",
                            "homeRuns": 1.123,
                            "singles": 0.987,
                            "doublesTriples": 1.111,
                            "asOf": "must-not-leak",
                        }
                    ]
                }
            }
        )
        matchups = fetch_bpp.index_matchup_rows(
            {
                "data": {
                    "items": [
                        {
                            "batterName": "Example Hitter",
                            "homeRunVsTypical": 18,
                            "matchupAdvantage": "must-not-leak",
                        }
                    ]
                }
            }
        )
        fetch_bpp.apply_context(summary, parks, matchups, {})
        clean = fetch_bpp.clean_summary(summary)

        self.assertEqual(
            set(clean["example hitter"]),
            {
                "proj_hits",
                "proj_hr",
                "proj_k",
                "proj_bb",
                "park_hr_factor",
                "park_hits_factor",
                "matchup_advantage",
            },
        )
        self.assertEqual(clean["example hitter"]["proj_hits"], 1.23)
        self.assertEqual(clean["example hitter"]["park_hr_factor"], 12.0)
        self.assertEqual(clean["example hitter"]["matchup_advantage"], 9)
        serialized = json.dumps(clean)
        for raw in ("marketKey", "matchupAdvantage", "requestId", "asOf"):
            self.assertNotIn(raw, serialized)

    def test_main_counts_one_projection_call_per_slate_game_plus_context_calls(self):
        class FakeClient:
            def __init__(self, use_cache=False, min_gap=0.0):
                self.use_cache = use_cache
                self.min_gap = min_gap

            def parkfactors(self, date, force_refresh=True):
                return {"data": {"items": []}}

            def hitter_parkfactors(self, date, force_refresh=True):
                return {"data": {"items": []}}

            def matchups(self, date, starters=False, force_refresh=True):
                return {"data": {"items": []}}

            def projection_averages(self, game_id, force_refresh=True):
                return {
                    "data": {
                        "batters": [{"playerName": f"Hitter {game_id}", "hits": 1}],
                        "pitchers": [],
                    }
                }

        with tempfile.TemporaryDirectory() as tmp:
            data_path = Path(tmp) / "day_data.json"
            out_path = Path(tmp) / "bpp_summary.json"
            data_path.write_text(
                json.dumps(
                    {
                        "BP_Games": [
                            {"GamePk": 101, "GameDate": "2026-07-22"},
                            {"GamePk": 202, "GameDate": "2026-07-22"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {
                    "BPP_API_KEY": "test-key",
                    "DATA_FILE": str(data_path),
                    "BPP_SUMMARY_FILE": str(out_path),
                },
            ):
                with patch.object(fetch_bpp, "BppClient", FakeClient):
                    with patch.object(fetch_bpp, "DATA_FILE", str(data_path)):
                        with patch.object(fetch_bpp, "OUT_FILE", str(out_path)):
                            fetch_bpp.main()

            written = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(set(written), {"hitter 101", "hitter 202"})
