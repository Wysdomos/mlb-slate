"""Local, read-only FastAPI wrapper for selected pybaseball queries."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse

from backtest.data_access import BackendUnavailable, UpstreamDataError
from .models import DatasetResponse, ErrorResponse, HealthResponse
from .service import PyBaseballService

MAX_STATCAST_DAYS = 92
MAX_SEASONS = 10


def get_service(request: Request) -> PyBaseballService:
    return request.app.state.pybaseball_service


ServiceDependency = Annotated[PyBaseballService, Depends(get_service)]
PlayerId = Annotated[int, Path(gt=0)]
RowLimit = Annotated[int, Query(ge=1, le=5_000)]
RowOffset = Annotated[int, Query(ge=0)]


def _validate_date_range(start_date: date, end_date: date) -> tuple[str, str]:
    if end_date < start_date:
        raise HTTPException(422, "end_date must be on or after start_date.")
    inclusive_days = (end_date - start_date).days + 1
    if inclusive_days > MAX_STATCAST_DAYS:
        raise HTTPException(
            422,
            f"Statcast requests are limited to {MAX_STATCAST_DAYS} days. "
            "Split longer backtests into smaller date windows.",
        )
    return start_date.isoformat(), end_date.isoformat()


def _validate_seasons(start_season: int, end_season: int) -> None:
    if end_season < start_season:
        raise HTTPException(422, "end_season must be on or after start_season.")
    if end_season - start_season + 1 > MAX_SEASONS:
        raise HTTPException(
            422,
            f"Season requests are limited to {MAX_SEASONS} seasons.",
        )


def create_app(service: PyBaseballService | None = None) -> FastAPI:
    app = FastAPI(
        title="The Daily Slate PyBaseball API",
        version="0.1.0",
        description=(
            "A local-only, read-only adapter for selected pybaseball data. "
            "It is not part of the production Daily Slate pipeline yet."
        ),
    )
    app.state.pybaseball_service = service or PyBaseballService()

    @app.exception_handler(BackendUnavailable)
    async def backend_unavailable_handler(
        request: Request, exc: BackendUnavailable
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(UpstreamDataError)
    async def upstream_error_handler(
        request: Request, exc: UpstreamDataError
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Check the local service",
    )
    def health(pybaseball: ServiceDependency) -> HealthResponse:
        return HealthResponse(
            backend_loaded=pybaseball.backend_loaded,
            cache_enabled=pybaseball.cache_enabled,
        )

    @app.get(
        "/v1/players/search",
        response_model=DatasetResponse,
        responses={502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        summary="Find cross-site player identifiers",
    )
    def players_search(
        pybaseball: ServiceDependency,
        last: Annotated[str, Query(min_length=1, max_length=80)],
        first: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        fuzzy: bool = False,
        offset: RowOffset = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> dict:
        return pybaseball.player_lookup(
            last=last.strip(),
            first=first.strip() if first else None,
            fuzzy=fuzzy,
            offset=offset,
            limit=limit,
        ).response()

    @app.get(
        "/v1/statcast/batter/{player_id}",
        response_model=DatasetResponse,
        responses={502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        summary="Get pitch-level Statcast rows for a batter",
    )
    def batter_statcast(
        pybaseball: ServiceDependency,
        player_id: PlayerId,
        start_date: date,
        end_date: date,
        offset: RowOffset = 0,
        limit: RowLimit = 1_000,
    ) -> dict:
        start, end = _validate_date_range(start_date, end_date)
        return pybaseball.statcast_batter(
            player_id, start, end, offset, limit
        ).response()

    @app.get(
        "/v1/statcast/pitcher/{player_id}",
        response_model=DatasetResponse,
        responses={502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        summary="Get pitch-level Statcast rows for a pitcher",
    )
    def pitcher_statcast(
        pybaseball: ServiceDependency,
        player_id: PlayerId,
        start_date: date,
        end_date: date,
        offset: RowOffset = 0,
        limit: RowLimit = 1_000,
    ) -> dict:
        start, end = _validate_date_range(start_date, end_date)
        return pybaseball.statcast_pitcher(
            player_id, start, end, offset, limit
        ).response()

    @app.get(
        "/v1/stats/batting",
        response_model=DatasetResponse,
        responses={502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        summary="Get FanGraphs season batting statistics",
    )
    def season_batting(
        pybaseball: ServiceDependency,
        start_season: Annotated[int, Query(ge=1871, le=2100)],
        end_season: Annotated[int, Query(ge=1871, le=2100)],
        qual: Annotated[int | None, Query(ge=0)] = None,
        offset: RowOffset = 0,
        limit: Annotated[int, Query(ge=1, le=5_000)] = 1_000,
    ) -> dict:
        _validate_seasons(start_season, end_season)
        return pybaseball.batting_stats(
            start_season, end_season, qual, offset, limit
        ).response()

    @app.get(
        "/v1/stats/pitching",
        response_model=DatasetResponse,
        responses={502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
        summary="Get FanGraphs season pitching statistics",
    )
    def season_pitching(
        pybaseball: ServiceDependency,
        start_season: Annotated[int, Query(ge=1871, le=2100)],
        end_season: Annotated[int, Query(ge=1871, le=2100)],
        qual: Annotated[int | None, Query(ge=0)] = None,
        offset: RowOffset = 0,
        limit: Annotated[int, Query(ge=1, le=5_000)] = 1_000,
    ) -> dict:
        _validate_seasons(start_season, end_season)
        return pybaseball.pitching_stats(
            start_season, end_season, qual, offset, limit
        ).response()

    return app


app = create_app()
