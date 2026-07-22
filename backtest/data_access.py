"""Shared pybaseball access layer for backtests and the local API.

All pybaseball calls and CSV caching live here. FastAPI routes call the
service layer, and the service layer calls this module; this module never
imports the service or FastAPI application.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import pandas as pd

CACHE = Path(__file__).resolve().parent / "cache"


class BackendUnavailable(RuntimeError):
    """Raised when the optional local pybaseball dependency is unavailable."""


class UpstreamDataError(RuntimeError):
    """Raised when an upstream baseball source cannot fulfill a query."""


class IncompleteDatasetError(RuntimeError):
    """Raised instead of returning a capped or internally inconsistent load."""


@dataclass(frozen=True)
class FramePage:
    records: list[dict[str, Any]]
    total_rows: int
    offset: int
    next_offset: int | None

    @property
    def truncated(self) -> bool:
        return self.next_offset is not None


@dataclass(frozen=True)
class CompleteDataset:
    records: list[dict[str, Any]]
    total_rows: int


class PageFetcher(Protocol):
    def __call__(self, offset: int, limit: int) -> Mapping[str, Any]: ...


def frame_page(frame: pd.DataFrame, offset: int, limit: int) -> FramePage:
    """Serialize one deterministic DataFrame page as strict, valid JSON data."""

    total_rows = len(frame.index)
    selected = frame.iloc[offset : offset + limit]
    records = json.loads(
        selected.to_json(orient="records", date_format="iso", date_unit="s")
    )
    json.dumps(records, allow_nan=False)

    consumed = offset + len(records)
    next_offset = consumed if consumed < total_rows else None
    return FramePage(
        records=records,
        total_rows=total_rows,
        offset=offset,
        next_offset=next_offset,
    )


def load_complete_dataset(
    fetch_page: PageFetcher,
    *,
    page_size: int = 1_000,
    max_pages: int = 10_000,
) -> CompleteDataset:
    """Load every page or raise; never return a response marked truncated."""

    if page_size < 1:
        raise ValueError("page_size must be at least 1.")

    offset = 0
    records: list[dict[str, Any]] = []
    expected_total: int | None = None

    for _ in range(max_pages):
        payload = fetch_page(offset, page_size)
        page_records = payload.get("records")
        total_rows = payload.get("total_rows")
        row_count = payload.get("row_count")
        truncated = payload.get("truncated")
        page_offset = payload.get("offset", offset)

        if not isinstance(page_records, list):
            raise IncompleteDatasetError("Page records must be a list.")
        if not isinstance(total_rows, int) or total_rows < 0:
            raise IncompleteDatasetError("Page total_rows must be non-negative.")
        if row_count != len(page_records):
            raise IncompleteDatasetError("Page row_count does not match records.")
        if page_offset != offset:
            raise IncompleteDatasetError("Page offset does not match the request.")
        if expected_total is None:
            expected_total = total_rows
        elif total_rows != expected_total:
            raise IncompleteDatasetError("total_rows changed during pagination.")

        records.extend(page_records)

        if truncated is False:
            if len(records) != expected_total:
                raise IncompleteDatasetError(
                    "Final page ended before the complete dataset was loaded."
                )
            return CompleteDataset(records=records, total_rows=expected_total)

        if truncated is not True:
            raise IncompleteDatasetError("Page truncated must be a boolean.")

        next_offset = payload.get("next_offset")
        expected_next = offset + len(page_records)
        if (
            not isinstance(next_offset, int)
            or next_offset != expected_next
            or next_offset <= offset
        ):
            raise IncompleteDatasetError(
                "Truncated page did not provide a forward next_offset."
            )
        offset = next_offset

    raise IncompleteDatasetError("Pagination exceeded the maximum page count.")


class PyBaseballDataAccess:
    """The single owner of pybaseball calls and persistent CSV caching."""

    DEFAULT_CACHE_TTL_SECONDS = 6 * 60 * 60

    def __init__(
        self,
        *,
        backend: Any | None = None,
        cache_dir: str | Path | None = None,
        cache_ttl_seconds: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        configured_dir = os.environ.get("PYBASEBALL_API_CACHE_DIR")
        self._cache_dir = Path(
            cache_dir or configured_dir or CACHE / "pybaseball-api"
        ).expanduser()
        configured_ttl = os.environ.get("PYBASEBALL_API_CACHE_TTL_SECONDS")
        if cache_ttl_seconds is not None:
            ttl = cache_ttl_seconds
        elif configured_ttl is not None:
            ttl = int(configured_ttl)
        else:
            ttl = self.DEFAULT_CACHE_TTL_SECONDS
        if ttl < 0:
            raise ValueError("cache_ttl_seconds cannot be negative.")

        self._cache_ttl_seconds = ttl
        self._clock = clock
        self._backend = backend

    @property
    def backend_loaded(self) -> bool:
        return self._backend is not None

    @property
    def cache_enabled(self) -> bool:
        return self._cache_ttl_seconds > 0

    def _load_backend(self) -> Any:
        if self._backend is not None:
            return self._backend

        internal_cache_dir = self._cache_dir.parent / "pybaseball-internal"
        os.environ.setdefault("PYBASEBALL_CACHE", str(internal_cache_dir))
        try:
            import pybaseball
        except ImportError as exc:
            raise BackendUnavailable(
                "pybaseball is not installed; install the service requirements."
            ) from exc

        pybaseball.cache.config.cache_directory = str(internal_cache_dir)
        pybaseball.cache.enable()
        self._backend = pybaseball
        return self._backend

    @staticmethod
    def _cache_key(
        function_name: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]
    ) -> str:
        encoded = json.dumps(
            {"function": function_name, "args": args, "kwargs": kwargs},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _cache_path(
        self, function_name: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]
    ) -> Path:
        key = self._cache_key(function_name, args, kwargs)
        return self._cache_dir / f"{function_name}-{key}.csv"

    def _read_fresh_cache(self, path: Path) -> pd.DataFrame | None:
        if not self.cache_enabled or not path.is_file():
            return None
        age_seconds = self._clock() - path.stat().st_mtime
        if age_seconds > self._cache_ttl_seconds:
            return None
        try:
            return pd.read_csv(path)
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            return None

    def _write_cache(self, path: Path, frame: pd.DataFrame) -> None:
        if not self.cache_enabled or frame.empty:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        frame.to_csv(temporary, index=False)
        temporary.replace(path)

    def _fetch(
        self,
        function_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> pd.DataFrame:
        path = self._cache_path(function_name, args, kwargs)
        cached = self._read_fresh_cache(path)
        if cached is not None:
            return cached

        backend = self._load_backend()
        function: Callable[..., Any] = getattr(backend, function_name)
        try:
            frame = function(*args, **kwargs)
        except Exception as exc:
            raise UpstreamDataError(
                f"The upstream source failed while running {function_name}."
            ) from exc

        if frame is None:
            frame = pd.DataFrame()
        if not isinstance(frame, pd.DataFrame):
            raise UpstreamDataError(
                f"The upstream source returned a non-DataFrame for {function_name}."
            )

        self._write_cache(path, frame)
        return frame

    def player_lookup(
        self, last: str, first: str | None, fuzzy: bool
    ) -> pd.DataFrame:
        return self._fetch("playerid_lookup", last, first=first, fuzzy=fuzzy)

    def statcast_batter(
        self, player_id: int, start_date: str, end_date: str
    ) -> pd.DataFrame:
        return self._fetch("statcast_batter", start_date, end_date, player_id)

    def statcast_pitcher(
        self, player_id: int, start_date: str, end_date: str
    ) -> pd.DataFrame:
        return self._fetch("statcast_pitcher", start_date, end_date, player_id)

    def batting_stats(
        self, start_season: int, end_season: int, qual: int | None
    ) -> pd.DataFrame:
        kwargs = {} if qual is None else {"qual": qual}
        return self._fetch("batting_stats", start_season, end_season, **kwargs)

    def pitching_stats(
        self, start_season: int, end_season: int, qual: int | None
    ) -> pd.DataFrame:
        kwargs = {} if qual is None else {"qual": qual}
        return self._fetch("pitching_stats", start_season, end_season, **kwargs)

    def pitcher_game_logs(self, season: int) -> pd.DataFrame:
        return self._fetch(
            "pitching_stats_range", f"{season}-03-01", f"{season}-11-30"
        )

    def batter_game_logs(self, season: int) -> pd.DataFrame:
        return self._fetch(
            "batting_stats_range", f"{season}-03-01", f"{season}-11-30"
        )

    def statcast_pitcher_percentiles(self, season: int) -> pd.DataFrame:
        return self._fetch("statcast_pitcher_expected_stats", season)

    def statcast_batter_percentiles(self, season: int) -> pd.DataFrame:
        return self._fetch("statcast_batter_expected_stats", season)


def _backtest_access() -> PyBaseballDataAccess:
    return PyBaseballDataAccess(cache_dir=CACHE)


def pitcher_game_logs(season: int) -> pd.DataFrame:
    """Per-start pitching logs for a season."""

    return _backtest_access().pitcher_game_logs(season)


def batter_game_logs(season: int) -> pd.DataFrame:
    """Per-game batting logs for a season."""

    return _backtest_access().batter_game_logs(season)


def statcast_pitcher_percentiles(season: int) -> pd.DataFrame:
    """Savant expected stats for pitcher context."""

    return _backtest_access().statcast_pitcher_percentiles(season)


def statcast_batter_percentiles(season: int) -> pd.DataFrame:
    """Savant expected stats for batter context."""

    return _backtest_access().statcast_batter_percentiles(season)
