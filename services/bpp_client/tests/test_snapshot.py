import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.bpp_client import snapshot


class FakeSnapshotClient:
    instances = []

    def __init__(self, api_key=None, use_cache=True, min_gap=0.0):
        self.api_key = api_key
        self.use_cache = use_cache
        self.min_gap = min_gap
        self.calls = []
        FakeSnapshotClient.instances.append(self)

    def _payload(self, label, data=None):
        self.calls.append(label)
        return {"meta": {"asOf": f"asof-{label}"}, "data": data if data is not None else []}

    def games(self, date, force_refresh=True):
        return self._payload("games", {"items": [{"gameId": 101}, {"gameId": 202}]})

    def markets(self, force_refresh=True):
        return self._payload("markets")

    def teams(self, force_refresh=True):
        return self._payload("teams")

    def parkfactors(self, date, force_refresh=True):
        return self._payload("parkfactors")

    def hitter_parkfactors(self, date=None, game_id=None, force_refresh=True):
        return self._payload("hitter_parkfactors")

    def matchups(self, date, starters=False, force_refresh=True):
        return self._payload("matchups_starters" if starters else "matchups")

    def projection_averages(self, game_id, force_refresh=True):
        return self._payload(f"projection_averages_{game_id}")

    def projection_probabilities(self, game_id, force_refresh=True):
        return self._payload(f"projection_probabilities_{game_id}")


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        FakeSnapshotClient.instances = []

    def test_archive_uses_env_min_gap_and_logs_call_count(self):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BPP_MIN_GAP": "1.25", "BPP_MAX_CALLS": "20"}):
                with patch.object(snapshot, "BppClient", FakeSnapshotClient):
                    with patch("sys.stderr", stream):
                        archived = snapshot.archive_date(
                            "2026-07-22",
                            output_dir=Path(tmp),
                            force_refresh=True,
                        )

        self.assertEqual(FakeSnapshotClient.instances[0].min_gap, 1.25)
        self.assertEqual(archived["callCount"], 11)
        self.assertFalse(archived["stopped"])
        self.assertIn("BPP snapshot call 1/20", stream.getvalue())
        self.assertIn("monthly budget 15000", stream.getvalue())

    def test_archive_stops_cleanly_at_max_calls_and_writes_manifest(self):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BPP_MAX_CALLS": "3"}, clear=False):
                with patch.object(snapshot, "BppClient", FakeSnapshotClient):
                    with patch("sys.stderr", stream):
                        archived = snapshot.archive_date("2026-07-22", output_dir=Path(tmp))
            manifest = json.loads((Path(tmp) / "manifest.json").read_text(encoding="utf-8"))

        self.assertTrue(archived["stopped"])
        self.assertEqual(archived["callCount"], 3)
        self.assertEqual(manifest["callCount"], 3)
        self.assertIn("BPP_MAX_CALLS=3 reached", archived["stopReason"])
        self.assertIn("BPP snapshot stopped", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
