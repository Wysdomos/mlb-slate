"""Contract tests that do not call live baseball data sources."""

from fastapi.testclient import TestClient

from backtest.data_access import UpstreamDataError
from services.pybaseball_api.app.main import create_app
from services.pybaseball_api.app.service import Dataset


class FakeService:
    backend_loaded = True
    cache_enabled = True

    def player_lookup(self, last, first, fuzzy, offset, limit):
        return Dataset(
            query={
                "last": last,
                "first": first,
                "fuzzy": fuzzy,
                "offset": offset,
                "limit": limit,
            },
            records=[{"name_last": last, "name_first": first, "key_mlbam": 592450}],
            total_rows=1,
            offset=offset,
        )

    def statcast_batter(self, player_id, start_date, end_date, offset, limit):
        return Dataset(
            query={
                "player_id": player_id,
                "start_date": start_date,
                "end_date": end_date,
                "offset": offset,
                "limit": limit,
            },
            records=[{"batter": player_id, "events": "home_run"}],
            total_rows=2,
            offset=offset,
        )

    def statcast_pitcher(self, player_id, start_date, end_date, offset, limit):
        return Dataset(
            query={
                "player_id": player_id,
                "start_date": start_date,
                "end_date": end_date,
                "offset": offset,
                "limit": limit,
            },
            records=[{"pitcher": player_id, "pitch_type": "FF"}],
            total_rows=1,
            offset=offset,
        )

    def batting_stats(self, start_season, end_season, qual, offset, limit):
        return Dataset(
            query={
                "start_season": start_season,
                "end_season": end_season,
                "qual": qual,
                "offset": offset,
                "limit": limit,
            },
            records=[{"Season": start_season, "Name": "Test Batter"}],
            total_rows=1,
            offset=offset,
        )

    def pitching_stats(self, start_season, end_season, qual, offset, limit):
        return Dataset(
            query={
                "start_season": start_season,
                "end_season": end_season,
                "qual": qual,
                "offset": offset,
                "limit": limit,
            },
            records=[{"Season": start_season, "Name": "Test Pitcher"}],
            total_rows=1,
            offset=offset,
        )


def test_health_is_local_and_read_only():
    with TestClient(create_app(FakeService())) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "daily-slate-pybaseball-api",
        "mode": "local-read-only",
        "cache_enabled": True,
        "backend_loaded": True,
    }


def test_player_search_returns_cross_site_id():
    with TestClient(create_app(FakeService())) as client:
        response = client.get(
            "/v1/players/search",
            params={"last": "judge", "first": "aaron"},
        )

    assert response.status_code == 200
    assert response.json()["records"][0]["key_mlbam"] == 592450


def test_statcast_response_reports_truncation():
    with TestClient(create_app(FakeService())) as client:
        response = client.get(
            "/v1/statcast/batter/592450",
            params={"start_date": "2026-07-01", "end_date": "2026-07-02"},
        )

    assert response.status_code == 200
    assert response.json()["row_count"] == 1
    assert response.json()["total_rows"] == 2
    assert response.json()["offset"] == 0
    assert response.json()["next_offset"] == 1
    assert response.json()["truncated"] is True


def test_reversed_date_range_is_rejected_before_upstream_call():
    with TestClient(create_app(FakeService())) as client:
        response = client.get(
            "/v1/statcast/pitcher/477132",
            params={"start_date": "2026-07-10", "end_date": "2026-07-01"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "end_date must be on or after start_date."


def test_long_statcast_range_is_rejected():
    with TestClient(create_app(FakeService())) as client:
        response = client.get(
            "/v1/statcast/pitcher/477132",
            params={"start_date": "2026-01-01", "end_date": "2026-07-01"},
        )

    assert response.status_code == 422
    assert "limited to 92 days" in response.json()["detail"]


def test_upstream_failure_is_honest_502():
    class FailingService(FakeService):
        def player_lookup(self, last, first, fuzzy, offset, limit):
            raise UpstreamDataError("The upstream source failed.")

    with TestClient(create_app(FailingService())) as client:
        response = client.get("/v1/players/search", params={"last": "judge"})

    assert response.status_code == 502
    assert response.json() == {"detail": "The upstream source failed."}
