import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from services.bpp_client.client import BppApiAuthError, BppApiError, BppClient


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.responses = {}

    def add(self, path, payload):
        self.responses[path] = payload

    def __call__(self, url, headers, timeout):
        parsed = urllib.parse.urlparse(url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        self.calls.append(
            {"path": parsed.path, "query": query, "headers": dict(headers), "timeout": timeout}
        )
        if parsed.path not in self.responses:
            raise AssertionError(f"unexpected path: {parsed.path}")
        return self.responses[parsed.path], {"x-test": "ok"}


class BppClientTests(unittest.TestCase):
    def test_auth_uses_header_and_never_query_param(self):
        fake = FakeTransport()
        fake.add(
            "/api/v1/games",
            {"meta": {"asOf": "2026-07-22T12:00:00Z"}, "data": [{"gameId": 1}]},
        )

        with tempfile.TemporaryDirectory() as tmp:
            client = BppClient(api_key="test-key", cache_dir=tmp, transport=fake)
            payload = client.games(date="2026-07-22")

        self.assertEqual(payload["data"][0]["gameId"], 1)
        self.assertEqual(fake.calls[0]["headers"]["X-API-Key"], "test-key")
        self.assertNotIn("apiKey", fake.calls[0]["query"])
        self.assertEqual(fake.calls[0]["query"], {"date": "2026-07-22"})

    def test_health_does_not_require_auth_header(self):
        fake = FakeTransport()
        fake.add("/api/v1/health", {"data": {"status": "ok"}})

        with tempfile.TemporaryDirectory() as tmp:
            client = BppClient(api_key="", cache_dir=tmp, transport=fake)
            payload = client.health()

        self.assertEqual(payload["data"]["status"], "ok")
        self.assertNotIn("X-API-Key", fake.calls[0]["headers"])

    def test_auth_endpoint_without_key_raises_before_network(self):
        fake = FakeTransport()

        with tempfile.TemporaryDirectory() as tmp:
            client = BppClient(api_key="", cache_dir=tmp, transport=fake)
            with self.assertRaises(BppApiAuthError):
                client.markets()

        self.assertEqual(fake.calls, [])

    def test_cache_reads_second_call_from_disk(self):
        fake = FakeTransport()
        fake.add(
            "/api/v1/teams",
            {"meta": {"asOf": "2026-07-22T12:00:00Z"}, "data": [{"abv": "NYY"}]},
        )

        with tempfile.TemporaryDirectory() as tmp:
            client = BppClient(api_key="test-key", cache_dir=tmp, transport=fake)
            first = client.teams()
            second = client.teams()
            cache_files = list(Path(tmp).glob("teams_*.json"))
            cached = json.loads(cache_files[0].read_text(encoding="utf-8"))

        self.assertEqual(first, second)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(len(cache_files), 1)
        self.assertIn("response", cached)

    def test_force_refresh_bypasses_cache(self):
        fake = FakeTransport()
        fake.add("/api/v1/markets", {"meta": {}, "data": []})

        with tempfile.TemporaryDirectory() as tmp:
            client = BppClient(api_key="test-key", cache_dir=tmp, transport=fake)
            client.markets()
            client.markets(force_refresh=True)

        self.assertEqual(len(fake.calls), 2)

    def test_each_documented_endpoint_has_a_typed_method(self):
        fake = FakeTransport()
        for path in (
            "/api/v1/markets",
            "/api/v1/teams",
            "/api/v1/players",
            "/api/v1/games",
            "/api/v1/games/776345",
            "/api/v1/projections/probabilities",
            "/api/v1/projections/averages",
            "/api/v1/parkfactors",
            "/api/v1/parkfactors/hitters",
            "/api/v1/matchups",
            "/api/v1/matchups/predict",
        ):
            fake.add(path, {"meta": {"asOf": "2026-07-22T12:00:00Z"}, "data": []})

        with tempfile.TemporaryDirectory() as tmp:
            client = BppClient(api_key="test-key", cache_dir=tmp, transport=fake)
            client.markets()
            client.teams()
            client.players(team_id=147, q="judge")
            client.games(game_id=776345)
            client.game(776345)
            client.projection_probabilities(776345)
            client.projection_averages(776345)
            client.parkfactors("2026-07-22")
            client.hitter_parkfactors(game_id=776345)
            client.matchups("2026-07-22", starters=True)
            client.predict_matchup(batter_id=592450, pitcher_id=477132)

        paths = [call["path"] for call in fake.calls]
        self.assertEqual(paths[0], "/api/v1/markets")
        self.assertEqual(paths[-1], "/api/v1/matchups/predict")
        self.assertEqual(fake.calls[9]["query"]["starters"], "true")

    def test_error_envelope_raises(self):
        fake = FakeTransport()
        fake.add(
            "/api/v1/players",
            {
                "error": {
                    "code": "invalid_argument",
                    "message": "bad team",
                    "requestId": "req-123",
                }
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            client = BppClient(api_key="test-key", cache_dir=tmp, transport=fake)
            with self.assertRaises(BppApiError) as ctx:
                client.players(team_id=999)

        self.assertEqual(ctx.exception.code, "invalid_argument")
        self.assertEqual(ctx.exception.request_id, "req-123")


if __name__ == "__main__":
    unittest.main()
