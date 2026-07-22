"""Business service between the FastAPI routes and shared data access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from backtest.data_access import PyBaseballDataAccess, frame_page


@dataclass(frozen=True)
class Dataset:
    query: dict[str, Any]
    records: list[dict[str, Any]]
    total_rows: int
    offset: int = 0

    @property
    def next_offset(self) -> int | None:
        consumed = self.offset + len(self.records)
        return consumed if consumed < self.total_rows else None

    def response(self) -> dict[str, Any]:
        return {
            "source": "pybaseball",
            "query": self.query,
            "row_count": len(self.records),
            "total_rows": self.total_rows,
            "offset": self.offset,
            "next_offset": self.next_offset,
            "truncated": self.next_offset is not None,
            "records": self.records,
        }


class PyBaseballService:
    """Validate query intent and page frames supplied by the data layer."""

    def __init__(self, data_access: PyBaseballDataAccess | None = None) -> None:
        self._data_access = data_access or PyBaseballDataAccess()

    @property
    def backend_loaded(self) -> bool:
        return self._data_access.backend_loaded

    @property
    def cache_enabled(self) -> bool:
        return self._data_access.cache_enabled

    @staticmethod
    def _dataset(
        frame_loader: Callable[[], pd.DataFrame],
        query: dict[str, Any],
        offset: int,
        limit: int,
    ) -> Dataset:
        frame = frame_loader()
        page = frame_page(frame, offset=offset, limit=limit)
        return Dataset(
            query=query,
            records=page.records,
            total_rows=page.total_rows,
            offset=page.offset,
        )

    def player_lookup(
        self,
        last: str,
        first: str | None,
        fuzzy: bool,
        offset: int,
        limit: int,
    ) -> Dataset:
        query = {
            "last": last,
            "first": first,
            "fuzzy": fuzzy,
            "offset": offset,
            "limit": limit,
        }
        return self._dataset(
            lambda: self._data_access.player_lookup(last, first, fuzzy),
            query,
            offset,
            limit,
        )

    def statcast_batter(
        self,
        player_id: int,
        start_date: str,
        end_date: str,
        offset: int,
        limit: int,
    ) -> Dataset:
        query = {
            "player_id": player_id,
            "start_date": start_date,
            "end_date": end_date,
            "offset": offset,
            "limit": limit,
        }
        return self._dataset(
            lambda: self._data_access.statcast_batter(
                player_id, start_date, end_date
            ),
            query,
            offset,
            limit,
        )

    def statcast_pitcher(
        self,
        player_id: int,
        start_date: str,
        end_date: str,
        offset: int,
        limit: int,
    ) -> Dataset:
        query = {
            "player_id": player_id,
            "start_date": start_date,
            "end_date": end_date,
            "offset": offset,
            "limit": limit,
        }
        return self._dataset(
            lambda: self._data_access.statcast_pitcher(
                player_id, start_date, end_date
            ),
            query,
            offset,
            limit,
        )

    def batting_stats(
        self,
        start_season: int,
        end_season: int,
        qual: int | None,
        offset: int,
        limit: int,
    ) -> Dataset:
        query = {
            "start_season": start_season,
            "end_season": end_season,
            "qual": qual,
            "offset": offset,
            "limit": limit,
        }
        return self._dataset(
            lambda: self._data_access.batting_stats(
                start_season, end_season, qual
            ),
            query,
            offset,
            limit,
        )

    def pitching_stats(
        self,
        start_season: int,
        end_season: int,
        qual: int | None,
        offset: int,
        limit: int,
    ) -> Dataset:
        query = {
            "start_season": start_season,
            "end_season": end_season,
            "qual": qual,
            "offset": offset,
            "limit": limit,
        }
        return self._dataset(
            lambda: self._data_access.pitching_stats(
                start_season, end_season, qual
            ),
            query,
            offset,
            limit,
        )
